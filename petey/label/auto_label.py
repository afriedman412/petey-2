"""Auto-derive a blueprint (`.bpt`) from a blank AcroForm PDF.

Given a blank fillable PDF, enumerate all AcroForm widgets, dedup
Copy A/B/C variants (keep first-copy for LLM labeling), and label the
first-copy widgets per page via one LLM call per page. Each field in
the emitted blueprint bundles the physical widget layer (rect, path,
widget type) with the semantic layer (type, semantic_type, pattern)
derived from the label slug via the local semantic_types registry.

Emits a `.bpt` YAML with this shape:

    bpt_version: "1.1"
    name: <form_id>
    form_version: <string or null>
    source_pdf: <blank filename>
    source_pdf_hash: <sha1 of blank>
    source_pages: [pages that carry labeled widgets]
    description: ""
    instructions: ""
    fields:
      <field_slug>:
        type: string | number | integer | boolean | date | category
        semantic_type: <slug from registry, if inferred>
        pattern: <regex, if applicable>
        widget:
          page: <int>
          rect: [x0, y0, x1, y1]
          widget_type: text | checkbox
          path: <AcroForm path>

For mutex-grouped checkbox clusters (`<group>.<value>` dot-notation
from the LLM), the group collapses into ONE `type: category` field
carrying a `widgets:` map from value → widget block.

Requires `ANTHROPIC_API_KEY` in env.

Usage:
    python auto_label.py --blank <blank.pdf> --output <blueprint.bpt>
    python auto_label.py --blank <blank.pdf> --output <b.bpt> \\
        --form-version 2025
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
from pathlib import Path
from typing import Optional

import pymupdf
import yaml

from petey.label import call_log
from petey.bpt_version import stamp_version
from petey.label.dedup import DedupState
from petey.label.page_signature import collapse_copy_pages
from petey.label.vocab import load_form_vocab
from petey.label.retrieve import Embedder, match_labels_to_widgets
from petey.semantic_types import enrich_field
from petey.locate import enumerate_geometry
from petey.locate.acroform import enumerate_widgets, _widget_type_string, _unescape_pdf_name  # noqa: F401

MODEL = "claude-sonnet-4-6"
# Measured, not estimated: 150 labels cost 4,190 output tokens on Form 1025
# page 3, so ~28 tokens per label — not the 15-20 assumed when LABEL_BATCH was
# chosen. At 8192 the ceiling held only ~290 labels, which a single dense page
# reaches, and a response that hits the ceiling is truncated mid-JSON and
# unparseable, losing the whole form rather than the overflow. Raising it costs
# nothing: output tokens are billed as generated, and this is a ceiling.
MAX_TOKENS = 32768
BPT_VERSION = "1.1"

# Retrieval pre-pass thresholds.
# `RETRIEVAL_ACCEPT` — top-1 score at or above this labels the widget
# locally without asking the LLM.
# `RETRIEVAL_REVIEW_FLOOR` — top-1 below this is ignored entirely; between
# floor and accept it becomes a hint used to flag LLM/retrieval divergence
# for human review.
RETRIEVAL_ACCEPT = 0.85
RETRIEVAL_REVIEW_FLOOR = 0.60

# A widgeted page with fewer native words than this has no usable text
# layer. See the note at the guard in build_blueprint for why this is an
# absolute floor rather than a ratio to widget count.
MIN_PAGE_WORDS = 15

COPY_RE = re.compile(r"Copy[A-Za-z0-9]+\[\d+\]")


def first_copy_ids(widgets: list[dict]) -> set[int]:
    """First-copy dedup for non-radio widgets; keep all radios.

    Radio widgets sharing a `field_name` (AcroForm group) get grouped by
    `_group_radios_for_labeling` downstream, not by the Copy A/B/C
    heuristic here.
    """
    groups: dict[str, list[dict]] = {}
    for w in widgets:
        if w["widget_type"] == "radiobutton":
            continue
        key = COPY_RE.sub("COPY", w["path"])
        groups.setdefault(key, []).append(w)
    keep: set[int] = set()
    for arr in groups.values():
        arr.sort(key=lambda w: (w["page"], w["id"]))
        keep.add(arr[0]["id"])
    for w in widgets:
        if w["widget_type"] == "radiobutton":
            keep.add(w["id"])
    return keep


def _group_radios_for_labeling(
    widgets: list[dict],
) -> tuple[list[dict], dict[int, list[dict]]]:
    """Collapse radios sharing a `field_name` into one group entry.

    Returns `(label_entries, members_by_group_id)`. Each group entry
    carries the union bounding box across its member widgets and the
    per-member on-state export values, so the VLM sees the group as a
    single choice-set rather than N independent widgets.
    """
    radios_by_path: dict[str, list[dict]] = {}
    others: list[dict] = []
    for w in widgets:
        if w["widget_type"] == "radiobutton":
            radios_by_path.setdefault(w["path"], []).append(w)
        else:
            others.append(w)

    group_entries: list[dict] = []
    members_by_id: dict[int, list[dict]] = {}
    for path, members in radios_by_path.items():
        members.sort(key=lambda w: (w["page"], w["id"]))
        first = members[0]
        same_page = [m for m in members if m["page"] == first["page"]]
        xs = [c for m in same_page for c in (m["rect"][0], m["rect"][2])]
        ys = [c for m in same_page for c in (m["rect"][1], m["rect"][3])]
        union_rect = [min(xs), min(ys), max(xs), max(ys)]
        group_entries.append({
            "id": first["id"],
            "page": first["page"],
            "rect": union_rect,
            "widget_type": "radiobutton",
            "path": path,
            "options": [m.get("on_state") for m in members],
        })
        members_by_id[first["id"]] = members
    return others + group_entries, members_by_id


def _words_from_page(page: "pymupdf.Page") -> list[dict]:
    words = []
    for w in page.get_text("words"):
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        text = text.strip()
        if text:
            words.append({"text": text, "rect": [x0, y0, x1, y1]})
    return words


def extract_words(pdf_path: Path, page_no: int) -> list[dict]:
    doc = pymupdf.open(str(pdf_path))
    try:
        return _words_from_page(doc[page_no - 1])
    finally:
        doc.close()


def _adapt_widget_for_matcher(w: dict) -> dict:
    """Convert auto_label widget entries to the Detection dict shape
    that `retrieve.match_labels_to_widgets` expects."""
    return {
        "cls_name": w["widget_type"],
        "conf": 1.0,
        "bbox_xyxy": tuple(w["rect"]),
        "_id": w["id"],
    }


def retrieval_prepass(
    page: "pymupdf.Page",
    widgets_on_page: list[dict],
    vocab: list[tuple[str, list[str]]],
    embedder: "Embedder",
) -> dict[int, dict]:
    """Run the retrieval matcher over text + checkbox widgets on one
    page. Radios are skipped — the LLM handles group naming.

    Returns `{widget_id: {"label": str, "confidence": float}}` for every
    widget with a top-1 match at or above `RETRIEVAL_REVIEW_FLOOR`.
    Callers split by `RETRIEVAL_ACCEPT` to decide auto-accept vs
    review-hint.
    """
    eligible = [w for w in widgets_on_page
                if w["widget_type"] in ("text", "checkbox")]
    if not eligible or not vocab:
        return {}
    detections = [_adapt_widget_for_matcher(w) for w in eligible]
    result = match_labels_to_widgets(
        page, detections, vocab, embedder=embedder,
        min_similarity=RETRIEVAL_REVIEW_FLOOR,
    )
    by_widget_id: dict[int, dict] = {}
    for cid, m in result.items():
        if m.widget is None:
            continue
        wid = m.widget.get("_id")
        if wid is None:
            continue
        entry = {"label": cid, "confidence": m.similarity}
        prev = by_widget_id.get(wid)
        if prev is None or entry["confidence"] > prev["confidence"]:
            by_widget_id[wid] = entry
    return by_widget_id


LABEL_SYSTEM = """You name form fields. Given a page's fillable widgets (with rects) \
and all its printed text (also with rects), emit one snake_case slug per \
widget naming THE FIELD THAT WIDGET CARRIES.

A widget is one fillable region on the page. A field is what it means. \
Name the field. Exactly one slug per widget id, always — if several \
widgets carry parts of one field, or one repeated field set appears \
twice, that is handled by the rules below, never by emitting fewer \
slugs than there are widgets.

Rules:
- Widgets are AcroForm fillable regions. Rank your evidence in this \
order, strongest first:
  1. `"tooltip"` — the publisher's own description of THIS widget.
  2. `"path"` — the publisher's own NAME for this widget. Often prose they \
typed: "Daytime phone", "Parient Last Name", "SURETYS FULL MAILING \
ADDRESS", "Spouse_DOB". Sometimes a generated id instead ("Text16", \
"Button1", "f1_07"), which carries nothing — use it when it reads like \
words, ignore it when it does not.
  3. Printed text near the widget — usually ABOVE it on IRS forms, \
sometimes to the LEFT. This is the weakest evidence, because nearby text \
only happens to sit close by, while 1 and 2 were written ABOUT this \
widget.
When the path or tooltip names the field and the nearby text disagrees, \
the publisher wins.
- A widget may carry `"tooltip"` — the form publisher's own description \
of that field, embedded in the document. It refers to THAT widget \
specifically, whereas nearby printed text only happens to sit close by. \
When a tooltip is present, prefer it over proximity: it is the stronger \
evidence and it is the publisher's intent, not an inference.
- A tooltip may open with a COPY PREFIX identifying which repetition of \
the form the widget belongs to: "Slip 1. Employer's name", \
"Copy B - Wages", "Column (c) Amount". FOLD that prefix into the slug as a \
leading component — do NOT make it a dot-notation group, and do NOT drop \
it. "Slip 1. Employer's name" yields `slip1_employer_business_name` and \
"Slip 2. Employer's name" yields `slip2_employer_business_name`. The \
prefix is real information about which occurrence a value belongs to, and \
the form publisher's own field names usually carry it too.
- Emit snake_case slugs following IRS MeF-style conventions where \
possible: `_amt` for money, `_dt` for date, `_ind` for checkbox \
indicator, `_cd` for code, `_yr` for year, `_ssn`/`_ein` for taxpayer \
IDs, `_zip_cd` for ZIP, `_city_nm` for city, \
`_state_abbreviation_cd` for state, `_country_cd` for country, \
`_address_line_1_txt` for street address.
- For checkbox widgets, emit `<something>_ind`.
- Person names → `_nm` or `_name`. Business names → `_business_name`.
- If a widget seems purely internal or you can't confidently label it, \
emit `""` (empty string). Do NOT guess.
- For clustered checkbox groups representing a closed set of choices \
(trust type, filing status, quarter), label each with the specific \
choice slug using dot notation: `<group>.<value>` (e.g. \
`entity_type.simple_trust`, `filing_status.single`, `quarter.1`). \
Use dot notation ONLY when the checkboxes form a spatially clustered, \
visually-grouped set of exclusive OR multi-select choices under one \
heading.
- Dot notation encodes A CHOICE, NOT A NAMESPACE. The `<value>` part must \
be one option of a closed set, where selecting that option means checking \
that box. Never use it to prefix a group of DISTINCT data fields: \
`slip_1.employer_business_name` is wrong, because an employer name is not \
an option you select. If the widgets it would cover hold different kinds \
of value (a name, a date, an amount), it is not a choice group. Text and \
number widgets are never part of one.
- Forms often repeat an identical field set: two slips on one page, \
Copy A / Copy B, a column per quarter. These are REPETITIONS, not choices \
and not one field. Where the tooltip or printed text names the \
occurrence, carry that into the slug as a leading component \
(`slip1_`, `copy_b_`, `q3_`). Where nothing names it, give each occurrence \
the same slug and let the downstream ordinal suffix separate them. Either \
way emit one slug per widget and never build a `<occurrence>.<field>` \
group.
- Radio-button entries (`"type": "radiobutton"`) represent an ENTIRE \
GROUP already structurally grouped in the AcroForm. `rect` is the \
union bounding box across the group; `options` lists the selectable \
values. Emit ONE slug naming what the group asks (e.g. \
`filing_status`, `is_amended_return_ind`, `plan_type`). Do NOT use \
dot notation for radio entries — they are already grouped.

GROUND EVERY LABEL IN THIS DOCUMENT. You may recognize this form. Do \
not label from that recollection: revisions change field sets, line \
numbering and layout, and the widgets and printed text supplied here \
are authoritative for THIS file. Where memory of the form conflicts \
with what you were given, what you were given wins. Never emit a label \
for a field you remember but cannot locate in the supplied text.

Return JSON only:
{"labels": [{"id": <int>, "label": "<snake_case_slug>"}, ...]}"""


def _parse_json_object(text: str) -> Optional[dict]:
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                blob = text[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    start = -1
    return None


def _json_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


# ACORD and several state agencies prefix every tooltip with an input
# instruction — "Enter text: The full name of the producer / agency." The
# prefix restates the widget type, which the blueprint already carries in
# `type`, so it is noise in a description.
_TOOLTIP_PREFIX = re.compile(
    r"^\s*(?:please\s+)?(?:enter|select|type|input|choose)\b[^:.]{0,24}[:.]\s*",
    re.I,
)
# Tooltips on controls describe an action, not a value. Pushbuttons are
# already dropped upstream, so this is a backstop for forms that attach
# control-style help text to an ordinary widget.
_TOOLTIP_CONTROL = re.compile(r"^\s*click\b", re.I)
# Below this a tooltip is a restated label ("Name", "Date"), and the field
# name already says that. Descriptions earn their place by adding
# something.
MIN_TOOLTIP_CHARS = 12


def _description_from_tooltip(tooltip: Optional[str]) -> Optional[str]:
    """A field `description` drawn from the publisher's own `/TU` text.

    Only 6% of v1.1 fields carry a description, and the ExtractBench
    ablation makes that gap a ship blocker — 0.953 F1 with prose against
    0.813 without, on the same 20 cases with the blueprint as the only
    variable. `/TU` is a source of that prose which is written by the form
    publisher and present in the document, so it satisfies the
    document-grounded discipline in a way model-generated prose does not.

    Returns None when the tooltip earns nothing: control help text, or so
    short it merely restates the field name.
    """
    if not tooltip:
        return None
    t = " ".join(tooltip.split())
    if _TOOLTIP_CONTROL.match(t):
        return None
    t = _TOOLTIP_PREFIX.sub("", t).strip()
    if len(t) < MIN_TOOLTIP_CHARS:
        return None
    return t


# Output-token budget per labeling call. Measured at ~28 tokens per label
# (150 labels -> 4,190 output tokens), so this bounds a response to roughly
# 4,200 tokens, comfortably inside MAX_TOKENS.
# Chosen well under MAX_TOKENS: the failure it prevents is not a slow call
# but a TRUNCATED one, and truncation loses the whole page — the response
# is invalid JSON, `_parse_json_object` returns nothing, and the form is
# abandoned with no partial result.
LABEL_BATCH = 150


def label_page_via_llm(widgets_on_page, words, model: str = MODEL):
    """Label one page's widgets, in batches if the page is dense.

    The labeler already makes one call per page. That is not enough
    granularity: density is per-PAGE, not per-document, and the corpus
    contains single pages far past any per-page budget — `nj1040` page 2
    carries 302 widgets and `ao039.pdf` carries 818 on its only page. At
    `MAX_TOKENS = 8192` the 302-widget page truncated at widget 160 and
    took the whole form down with it.

    Every batch receives the page's COMPLETE printed text, not a slice of
    it. The words are what a label is inferred from, and a widget's label
    frequently sits outside any region the widget itself occupies — column
    headers above a grid, a section heading far up the page. Splitting the
    text along with the widgets would reintroduce the localisation problem
    that the pinwheel geometry already failed at.

    Pages at or under `LABEL_BATCH` take exactly one call with the full
    widget list, so behaviour is unchanged for all but the dense minority
    (14 of 229 unlabeled forms average over 200 widgets per page).
    """
    if len(widgets_on_page) <= LABEL_BATCH:
        return _label_batch_via_llm(widgets_on_page, words, model=model)

    merged: dict[int, str] = {}
    n = len(widgets_on_page)
    for i in range(0, n, LABEL_BATCH):
        batch = widgets_on_page[i:i + LABEL_BATCH]
        print(f"    [batch] widgets {i + 1}-{i + len(batch)} of {n}")
        merged.update(_label_batch_via_llm(batch, words, model=model))
    return merged


def _label_batch_via_llm(widgets_on_page, words, model: str = MODEL):
    import anthropic

    widget_lines = []
    for w in widgets_on_page:
        x0, y0, x1, y1 = w["rect"]
        line = (
            f'  {{"id": {w["id"]}, "type": "{w["widget_type"]}", '
            f'"rect": [{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}]'
        )
        if w["widget_type"] == "radiobutton" and w.get("options"):
            opts = ", ".join(f'"{s}"' for s in w["options"] if s)
            line += f', "options": [{opts}]'
        # /TU, the AcroForm tooltip. Written by the form's publisher and
        # present in the document, so it grounds the label far better than
        # inferring from whatever text happens to sit nearby — which is
        # how 30 info-icon buttons on 01-114 got named after the form
        # items they were adjacent to.
        if w.get("tooltip"):
            t = _json_escape(w["tooltip"])
            line += f', "tooltip": "{t}"'
        line += "}"
        widget_lines.append(line)
    widget_json = "[\n" + ",\n".join(widget_lines) + "\n]"

    word_lines = []
    for word in words:
        x0, y0, x1, y1 = word["rect"]
        t = word["text"].replace("\\", "\\\\").replace('"', '\\"')
        word_lines.append(
            f'  {{"text": "{t}", '
            f'"rect": [{x0:.0f}, {y0:.0f}, {x1:.0f}, {y1:.0f}]}}'
        )
    words_json = "[\n" + ",\n".join(word_lines) + "\n]"

    user_text = (
        f"Widgets on this page:\n{widget_json}\n\n"
        f"Printed text on this page (with positions):\n{words_json}\n\n"
        f"Emit a snake_case label for every widget."
    )

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=model, max_tokens=MAX_TOKENS,
        system=LABEL_SYSTEM,
        messages=[{"role": "user", "content": user_text}],
    ) as stream:
        final = stream.get_final_message()
    text = "".join(
        b.text for b in final.content
        if getattr(b, "type", None) == "text"
    )
    # `stop_reason` is the difference between "the model answered badly"
    # and "the answer was cut off at MAX_TOKENS". Log every call, so a
    # failure never needs a re-run to diagnose. See call_log.py.
    stop = getattr(final, "stop_reason", None)
    usage = getattr(final, "usage", None)
    call_log.record(
        f"auto_label/{model}", raw=text, finish_reason=stop,
        request={"widgets": len(widgets_on_page),
                 "max_tokens": MAX_TOKENS,
                 "prompt_chars": len(user_text)},
        usage={"output_tokens": getattr(usage, "output_tokens", None),
               "input_tokens": getattr(usage, "input_tokens", None)}
        if usage else None,
    )
    parsed = _parse_json_object(text)
    if not parsed or "labels" not in parsed:
        # Report the response's SIZE and SHAPE, not just its first 500
        # chars. A run that overruns MAX_TOKENS is truncated mid-JSON, so
        # its opening looks like a perfectly valid {"labels": [...]} and
        # the old message ("did not return the shape") pointed at the
        # wrong cause. Encountered with a local model that emitted 658
        # entries for 23 widgets — one per word of the page text — and
        # ran to 22,916 chars before hitting the ceiling.
        n_entries = len(re.findall(r'"id"\s*:', text))
        raise RuntimeError(
            f"LLM response unusable for {len(widgets_on_page)} widgets "
            f"({n_entries} 'id' entries returned): "
            + call_log.describe(text, stop, expected=len(widgets_on_page))
            + f"\n--- head ---\n{text[:400]}"
            + f"\n--- tail ---\n{text[-400:]}"
        )
    out: dict[int, str] = {}
    n_ignored = 0
    ids_on_page = {w["id"] for w in widgets_on_page}
    for entry in parsed["labels"]:
        wid = entry.get("id")
        lbl = (entry.get("label") or "").strip()
        if isinstance(wid, int) and wid not in ids_on_page:
            n_ignored += 1
            continue
        if isinstance(wid, int):
            out[wid] = lbl
    if n_ignored:
        print(f"[auto_label] ignored {n_ignored} label entries whose id is "
              f"not a widget on this page (of "
              f"{len(parsed['labels'])} returned)")
    return out


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def build_blueprint(
    blank_pdf: Path, name: str,
    form_version: Optional[str] = None,
    model: str = MODEL,
    use_retrieval: bool = True,
    retrieval_threshold: float = RETRIEVAL_ACCEPT,
    geometry: str = "auto",
    use_llm: bool = True,
) -> dict:
    widgets, dropped_widgets, geometry_method = enumerate_geometry(blank_pdf, geometry)
    print(f"[auto_label] geometry: {geometry_method} ({len(widgets)} fields)")
    if dropped_widgets:
        by_reason: dict[str, int] = {}
        for d in dropped_widgets:
            by_reason[d.get("reason", "?")] = (
                by_reason.get(d.get("reason", "?"), 0) + 1)
        parts = []
        if by_reason.get("pushbutton"):
            parts.append(f"{by_reason['pushbutton']} pushbutton (controls, "
                         f"no value)")
        if by_reason.get("caption"):
            parts.append(f"{by_reason['caption']} caption (locked, hold "
                         f"their own label text)")
        print(f"[auto_label] dropped {len(dropped_widgets)} widgets: "
              + ", ".join(parts or ["other"]))
    if not widgets:
        raise SystemExit(f"No geometry in {blank_pdf}: no AcroForm widgets, and step2flat found no fields")

    if geometry_method == "acroform":
        # Step 1: cross-page copy collapse (multi-copy tax forms)
        widgets, copy_page_info = collapse_copy_pages(widgets)

        # Step 2: same-canonical-path copy dedup (Copy A/B in AcroForm path).
        # Radios are exempt — they group by shared field_name in step 3.
        keep_ids = first_copy_ids(widgets)
        kept = [w for w in widgets if w["id"] in keep_ids]

        # Step 3: collapse radio-group siblings so the VLM sees one entry
        # per group, not one per individual radio widget.
        label_entries, radio_members_by_id = _group_radios_for_labeling(kept)
    else:
        # Programmatic geometry has no paths: no copy pages to detect, no
        # AcroForm radio groups to collapse. Every field is its own entry.
        copy_page_info = {}
        kept = widgets
        label_entries, radio_members_by_id = list(widgets), {}
    pages_with_widgets = sorted({w["page"] for w in label_entries})

    if copy_page_info.get("dropped_as_copies"):
        print(f"[auto_label] collapsed copy pages: "
              f"{copy_page_info['dropped_as_copies']}")
    print(f"[auto_label] {len(widgets)} widgets on canonical pages, "
          f"{len(label_entries)} label entries "
          f"({len(radio_members_by_id)} radio groups collapsed from "
          f"{sum(len(m) for m in radio_members_by_id.values())} widgets), "
          f"pages {pages_with_widgets}")

    # Retrieval setup — one embedder + one vocab load, reused per page.
    vocab: list[tuple[str, list[str]]] = []
    embedder: Optional[Embedder] = None
    if use_retrieval:
        vocab = load_form_vocab(name)
        if vocab:
            embedder = Embedder()
            print(f"[auto_label] retrieval enabled: "
                  f"{len(vocab)} vocab labels for form_id={name!r}")
        else:
            print(f"[auto_label] no vocab for form_id={name!r}; "
                  f"retrieval prepass skipped, LLM-only")

    # Precondition: this labeler reads the TEXT LAYER. A form with widgets
    # but no extractable text gives it nothing to associate them with, and
    # it fails silently — cms1500_fillable.pdf has 270 widgets and 2 words
    # per page, and produced first a blueprint of invented capital-gains
    # vocabulary on an insurance claim form (100% unlocatable under S2),
    # then, on a re-run, a blueprint with zero fields. Two other empty
    # blueprints in the library have the same shape.
    #
    # This is a precondition, not a quality score: measured across 80
    # forms, text density does not predict defect rate (r = -0.29, driven
    # entirely by this one outlier — the next-thinnest form has 222 words
    # per page and scores clean). It is a binary gate on whether the
    # method applies at all. Flat/scanned documents belong to
    # vision_label.py.
    # Checked PER PAGE, not per document. A whole-document word count
    # hides the case that matters: cbp_form_7501.pdf carries 12,009 words
    # overall and passes any aggregate test, but its page 2 has 162
    # widgets and ZERO extractable text. Those 162 widgets can only
    # receive invented labels. Sweep every widgeted page before deciding
    # anything is labelable.
    _doc = pymupdf.open(str(blank_pdf))
    try:
        _per_page = {p: len(_words_from_page(_doc[p - 1]))
                     for p in pages_with_widgets}
    finally:
        _doc.close()
    # An ABSOLUTE floor, not a words-per-widget ratio. The ratio version
    # of this test flagged cbp_form_7501 page 2 as blind: it is a
    # continuation sheet where ~8 column headers govern 162 row widgets,
    # so 70 real words ("Line No.", "Description of Merchandise",
    # "A. Entered Value") looked sparse against the widget count. Tables
    # legitimately have few words per widget, and dropping that page
    # would have silently discarded 162 labelable fields.
    #
    # Measured across the corpus the two cases do not overlap at all:
    # 2 widgeted pages carry under 5 words (OSHA-300A 0, cms1500 2), and
    # the other 510 all carry 50 or more. Nothing lands in between, so a
    # flat floor separates "no text layer" from "sparse text" exactly.
    _blind = [p for p, n in _per_page.items() if n < MIN_PAGE_WORDS]

    if _blind and len(_blind) == len(pages_with_widgets):
        raise SystemExit(
            f"[auto_label] REFUSING: {blank_pdf.name} has no usable text "
            f"layer on any of its {len(pages_with_widgets)} widgeted "
            f"page(s) ({sum(_per_page.values())} words total, "
            f"{len(label_entries)} widgets).\n"
            f"  This labeler associates widgets with PRINTED TEXT; with no "
            f"text layer it can only invent labels.\n"
            f"  Use vision_label.py, or OCR the source first "
            f"(tile_and_ocr.py recovers 84-98% of words at ~3-4s/page)."
        )
    if _blind:
        # Partial blindness: label what can be labeled, drop the rest.
        # Silently inventing labels for these widgets is strictly worse
        # than omitting them — a missing field is visible, a wrong one
        # is not.
        dropped = [w for w in label_entries if w["page"] in _blind]
        label_entries = [w for w in label_entries
                         if w["page"] not in _blind]
        pages_with_widgets = [p for p in pages_with_widgets
                              if p not in _blind]
        print(f"[auto_label] WARNING: pages {sorted(_blind)} carry "
              f"{len(dropped)} widgets but no usable text layer; "
              f"SKIPPING them rather than inventing labels. "
              f"OCR the source to recover these fields.")

    labels_by_id: dict[int, str] = {}
    audit_by_id: dict[int, dict] = {}
    retrieval_ct = 0
    llm_ct = 0
    review_ct = 0

    doc = pymupdf.open(str(blank_pdf))
    try:
        for page_no in pages_with_widgets:
            page_widgets = [w for w in label_entries
                            if w["page"] == page_no]
            page_obj = doc[page_no - 1]

            if not use_llm:
                # Placeholder names: the geometry-only draft. Real names
                # come from a later labeling pass or the validation loop.
                for w in page_widgets:
                    labels_by_id[w["id"]] = f"p{w['page']}_{w['widget_type'][0]}{w['id']:03d}"
                    audit_by_id[w["id"]] = {"source": "placeholder"}
                continue

            retrieval_hits: dict[int, dict] = {}
            if embedder is not None and vocab:
                retrieval_hits = retrieval_prepass(
                    page_obj, page_widgets, vocab, embedder,
                )
            confident = {wid: h for wid, h in retrieval_hits.items()
                         if h["confidence"] >= retrieval_threshold}
            residual = [w for w in page_widgets
                        if w["id"] not in confident]

            for wid, h in confident.items():
                labels_by_id[wid] = h["label"]
                audit_by_id[wid] = {
                    "source": "retrieval",
                    "confidence": round(h["confidence"], 3),
                }
            retrieval_ct += len(confident)

            page_review_ct = 0
            if residual:
                words = _words_from_page(page_obj)
                llm_labels = label_page_via_llm(
                    residual, words, model=model,
                )
                llm_ct += len(residual)
                for wid, lbl in llm_labels.items():
                    if not lbl:
                        continue
                    labels_by_id[wid] = lbl
                    audit = {"source": "llm"}
                    hint = retrieval_hits.get(wid)
                    if (hint
                            and hint["confidence"] >= RETRIEVAL_REVIEW_FLOOR
                            and hint["label"] != lbl):
                        audit["needs_review"] = True
                        audit["retrieval_hint"] = hint["label"]
                        audit["retrieval_confidence"] = round(
                            hint["confidence"], 3)
                        page_review_ct += 1
                    audit_by_id[wid] = audit
            review_ct += page_review_ct

            print(f"  [page {page_no}] retrieval={len(confident)} "
                  f"llm={len(residual)} flagged={page_review_ct}")
    finally:
        doc.close()

    print(f"[auto_label] labeled via retrieval={retrieval_ct} "
          f"llm={llm_ct} needs_review={review_ct}")

    for w in label_entries:
        w["label"] = labels_by_id.get(w["id"], "")

    fields: dict[str, dict] = {}
    mutex_widgets: dict[str, dict[str, dict]] = {}
    dedup = DedupState()
    n_tooltip_descriptions = 0

    labeled = sorted(
        (w for w in label_entries if w.get("label")),
        key=lambda w: (w["page"], w["id"]),
    )
    def _attach_audit(spec: dict, wid: int) -> dict:
        """Fold retrieval/LLM audit into a field spec.

        Additive fields only; existing consumers (extract.py, score.py)
        can ignore them. Never emitted on radios or mutex-cluster
        `type: category` fields — audit is per-widget and doesn't
        cleanly aggregate across group members.
        """
        audit = audit_by_id.get(wid)
        if not audit:
            return spec
        src = audit.get("source")
        if src:
            spec["label_source"] = src
        if "confidence" in audit:
            spec["label_confidence"] = audit["confidence"]
        if audit.get("needs_review"):
            spec["needs_review"] = True
            spec["retrieval_hint"] = audit.get("retrieval_hint")
            spec["retrieval_confidence"] = audit.get(
                "retrieval_confidence")
        return spec

    for w in labeled:
        label = w["label"]
        widget_block = {
            "page": w["page"],
            "rect": w["rect"],
            "widget_type": w["widget_type"],
            "path": w.get("path"),
        }

        # Radio group — single AcroForm field, N selectable states.
        # Size-1 group → boolean; size >= 2 → category with on-state
        # exports as values. Radios always come from the LLM (retrieval
        # skips them), so no audit is attached.
        if w["widget_type"] == "radiobutton":
            members = radio_members_by_id.get(w["id"], [])
            on_states = [m.get("on_state") for m in members
                         if m.get("on_state")]
            assigned = dedup.assign(
                label, page=w["page"], rect=w["rect"],
            )
            if len(on_states) <= 1:
                fields[assigned] = {
                    "type": "boolean", "widget": widget_block,
                }
            else:
                fields[assigned] = {
                    "type": "category",
                    "values": on_states,
                    "widget": widget_block,
                }
            continue

        if "." in label:
            group, value = label.split(".", 1)
            if value in mutex_widgets.get(group, {}):
                continue
            mutex_widgets.setdefault(group, {})[value] = widget_block
            continue
        assigned = dedup.assign(
            label, page=w["page"], rect=w["rect"],
        )
        spec = enrich_field(label, w["widget_type"])
        spec["widget"] = widget_block
        if "confidence" in w:  # programmatic geometry: the rect is an estimate; say how good
            spec["x_petey_geometry"] = {"confidence": w["confidence"], "source": w.get("geometry_source")}
        desc = _description_from_tooltip(w.get("tooltip"))
        if desc:
            spec["description"] = desc
            spec["x_petey_description_source"] = "tooltip"
            n_tooltip_descriptions += 1
        fields[assigned] = _attach_audit(spec, w["id"])

    for group, val_to_widget in mutex_widgets.items():
        values = sorted(val_to_widget.keys())
        if len(values) <= 1:
            for v, w_block in val_to_widget.items():
                fields[f"{group}_{v}_ind"] = {
                    "type": "boolean",
                    "widget": w_block,
                }
            continue
        fields[group] = {
            "type": "category",
            "values": values,
            "widgets": val_to_widget,
        }

    bp = {
        "bpt_version": BPT_VERSION,  # re-stamped from content below
        "name": name,
        "form_version": form_version,
        "source_pdf": blank_pdf.name,
        "source_pdf_hash": _sha1(blank_pdf),
        "source_pages": pages_with_widgets,
        "description": "",
        "instructions": "",
        # Which labeler produced this, and with which model. vision_label.py
        # has always written this block; the AcroForm path never did, so the
        # library carried no record of what labeled it — recoverable only
        # because the default had never changed. That stops being true the
        # moment two models are in use, and a blueprint whose provenance is
        # unknown cannot be compared, re-run, or trusted differently from
        # its neighbours.
        "authoring": {
            "method": "auto_label",
            "model": model if use_llm else None,
            "geometry": geometry_method,
            "labels": "llm" if use_llm else "placeholder",
        },
        "fields": fields,
    }
    # Namespaced per spec §4 — these are Petey diagnostics, not part of
    # the format. Were emitted bare (spec §14, deviation 1).
    if dedup.collisions:
        bp["x_petey_dedup_log"] = dedup.summary()
        print(
            f"  [dedup] {len(dedup.collisions)} duplicate labels "
            f"auto-suffixed"
        )
    if copy_page_info.get("dropped_as_copies"):
        bp["x_petey_copy_pages_log"] = copy_page_info
    if dropped_widgets:
        bp["x_petey_dropped_widgets"] = {
            "count": len(dropped_widgets),
            "widgets": dropped_widgets,
        }
    if n_tooltip_descriptions:
        print(f"  [tooltip] {n_tooltip_descriptions} descriptions from /TU")
    return stamp_version(bp)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--blank", required=True, type=Path,
                    help="path to blank AcroForm PDF")
    ap.add_argument("--output", required=True, type=Path,
                    help="output blueprint .bpt path")
    ap.add_argument("--name", type=str, default=None,
                    help="form_id (default: derived from --output stem)")
    ap.add_argument("--form-version", type=str, default=None,
                    help='form revision year (e.g. "2025")')
    ap.add_argument("--model", type=str, default=MODEL,
                    help="LLM model for labeling (default sonnet-4.6)")
    ap.add_argument("--geometry", choices=["auto", "acroform", "sibling", "step2flat"], default="auto",
                    help="where field rects come from; auto = AcroForm if present, else step2flat (sibling is opt-in)")
    ap.add_argument("--no-llm", action="store_true",
                    help="emit placeholder field names; no API call (geometry-only draft)")
    ap.add_argument("--no-retrieval", action="store_true",
                    help="disable local retrieval prepass; LLM-only")
    ap.add_argument("--retrieval-threshold", type=float,
                    default=RETRIEVAL_ACCEPT,
                    help=f"top-1 cosine similarity at which retrieval "
                         f"auto-labels a widget without asking the LLM "
                         f"(default {RETRIEVAL_ACCEPT})")
    args = ap.parse_args()

    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass

    if not args.blank.exists():
        raise SystemExit(f"Blank PDF not found: {args.blank}")

    name = args.name or args.output.stem
    bp = build_blueprint(
        args.blank, name,
        form_version=args.form_version,
        model=args.model,
        use_retrieval=not args.no_retrieval,
        geometry=args.geometry,
        use_llm=not args.no_llm,
        retrieval_threshold=args.retrieval_threshold,
    )

    print(f"[auto_label] {len(bp['fields'])} fields in blueprint")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        yaml.safe_dump(bp, sort_keys=False, allow_unicode=True,
                       default_flow_style=False),
        encoding="utf-8",
    )
    print(f"[ok] wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
