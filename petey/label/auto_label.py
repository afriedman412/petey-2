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
          widget_type: text | checkbox | combobox | listbox
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
import time
from pathlib import Path
from typing import Optional

import pymupdf
import yaml

from petey.label import call_log
from petey.models import model_for
from petey.bpt_version import stamp_version
from petey.validate import field_ids
from petey.label.dedup import DedupState
from petey.label.page_signature import collapse_copy_pages
from petey.label.vocab import load_form_vocab
from petey.label import xfa as xfa_mod
from petey.label.retrieve import Embedder, match_labels_to_widgets
from petey.semantic_types import ALL_TYPES, enrich_field
from petey.locate import enumerate_geometry
from petey.locate.acroform import enumerate_widgets, _widget_type_string, _unescape_pdf_name  # noqa: F401

MODEL = model_for("labeler")   # gemini-3.8-flash since 2026-10-06, Andrew: switch the labeler to Gemini (RESULTS 2026-09-30: within noise of Sonnet 4.6 on W-9 / ACORD 25 / I-765 at about a third of the price)
# Call-log tag prefix; main() appends the form name so one form's labeler
# usage can be summed even when several forms label concurrently.
CALL_TAG = "auto_label"
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


_WORD_STATE = re.compile(r"^[A-Za-z][A-Za-z0-9 _/&'().-]*$")
_ORDINAL_STATE = re.compile(r"^\d+$")


def option_widgets(members: list[dict], group: dict) -> dict[str, dict]:
    """`{on_state: widget block}` for one option group, first appearance per state."""
    out: dict[str, dict] = {}
    for m in members:
        st = m.get("on_state")
        if not st or st in out:
            continue
        out[st] = {
            "page": m["page"],
            "rect": m["rect"],
            "widget_type": m.get("widget_type") or group.get("true_widget_type") or "radiobutton",
            "path": group.get("path"),
            "on_state": st,
        }
    return out


def caption_options(spec: dict) -> None:
    """Put the printed caption on each option: the XFA member caption when the
    template declares one, else the on-state itself when it is a word
    (`Medicare`, `Yes`); ordinal states (`0`, `1`) with no declaration stay
    uncaptioned — the description still carries `One of: ...` when the XFA
    gave it. Nothing is guessed."""
    widgets = spec.get("widgets") or {}
    if not widgets:
        return
    declared = ((spec.get("x_petey_xfa") or {}).get("choices")) or {}
    for st, block in widgets.items():
        cap = declared.get(st)
        if not cap and not _ORDINAL_STATE.match(st) and st.lower() not in ("on", "off", "true", "false"):
            # "0-5 years", "1 . Single.", "MINOR: BY CLINIC HOSPITAL",
            # "Medicare": the publisher wrote the state; it is the caption
            cap = st.capitalize() if st.lower() in ("yes", "no") else st
        if cap:
            block["caption"] = cap
        else:
            block.pop("caption", None)


def option_group_paths(widgets: list[dict]) -> set[str]:
    """Paths of button FIELDS that have more than one widget.

    One AcroForm field, several kids, each kid an option with its own
    on-state: that is a radio group whatever the field's flag says. The
    corpus survey (eval/radio_survey.py, 2026-09-29) found 692 such fields
    flagged radio and 480 flagged checkbox; the checkbox-flagged ones used
    to dedup to their first kid, so CMS-1500's seven-way insurance type
    became one boolean.
    """
    counts: dict[str, int] = {}
    for w in widgets:
        if w["widget_type"] in ("radiobutton", "checkbox"):
            counts[w["path"]] = counts.get(w["path"], 0) + 1
    return {path for path, n in counts.items() if n > 1}


def first_copy_ids(widgets: list[dict]) -> set[int]:
    """First-copy dedup for ordinary widgets; keep every member of an
    option group (see `option_group_paths`), which `_group_radios_for_labeling`
    collapses downstream instead of the Copy A/B/C heuristic here."""
    grouped = option_group_paths(widgets)
    groups: dict[str, list[dict]] = {}
    for w in widgets:
        if w["path"] in grouped:
            continue
        key = COPY_RE.sub("COPY", w["path"])
        groups.setdefault(key, []).append(w)
    keep: set[int] = set()
    for arr in groups.values():
        arr.sort(key=lambda w: (w["page"], w["id"]))
        keep.add(arr[0]["id"])
    for w in widgets:
        if w["path"] in grouped:
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
    grouped = option_group_paths(widgets)
    radios_by_path: dict[str, list[dict]] = {}
    others: list[dict] = []
    for w in widgets:
        if w["path"] in grouped or w["widget_type"] == "radiobutton":
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
        # distinct on-states in page order; kids that repeat a state are
        # extra appearances of the same option (Form400 mirrors a box on
        # pages 1 and 3), not extra options
        seen: list[str] = []
        for m in members:
            st = m.get("on_state")
            if st and st not in seen:
                seen.append(st)
        group_entries.append({
            "id": first["id"],
            "page": first["page"],
            "rect": union_rect,
            "widget_type": "radiobutton",  # the label prompt's group entry kind
            "true_widget_type": first["widget_type"],
            "path": path,
            "options": seen,
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
When the path or tooltip names the field and merely NEARBY text disagrees \
(a neighbouring box's caption, a section heading), the publisher wins.
- ONE EXCEPTION, the box's own caption: when printed words lie INSIDE the \
widget's rect, or the widget sits in a ruled cell whose caption is printed \
at the top of that same cell, that caption is what a filer reads for this \
box, and a filer types by position. If the tooltip or path says something \
else, the publisher placed the widget in the wrong box: name the field for \
the caption. (Kansas DO-10: a widget whose tooltip says EIN/SSN/PTIN sits \
inside the cell captioned "Area Code & Phone Number"; it holds a phone \
number.)
- A tooltip or path that says nothing about the value carries nothing: a \
control word or generator default ("Control", "Text16", "Check Box1", \
"Field", "Button", "Dropdown2"). Name such a widget from its caption, \
never from that word.
- A widget may carry `"tooltip"` — the form publisher's own description \
of that field, embedded in the document. It refers to THAT widget \
specifically, whereas nearby printed text only happens to sit close by. \
When a tooltip is present, prefer it over proximity: it is the stronger \
evidence and it is the publisher's intent, not an inference — except \
against the box's own caption (above).
- A tooltip may open with a COPY PREFIX identifying which repetition of \
the form the widget belongs to: "Slip 1. Employer's name", \
"Copy B - Wages", "Column (c) Amount". FOLD that prefix into the slug as a \
leading component — do NOT make it a dot-notation group, and do NOT drop \
it. "Slip 1. Employer's name" yields `slip1_employer_business_name` and \
"Slip 2. Employer's name" yields `slip2_employer_business_name`. The \
prefix is real information about which occurrence a value belongs to, and \
the form publisher's own field names usually carry it too.
- Emit snake_case slugs following IRS MeF-style conventions where \
possible: `_amt` for a sum of money only (an amount of anything else is \
named for what it measures: `_bbl`, `_mcf`, `_miles`, `_hours`, `_qty`, `_cnt`; \
a percentage `_pct`), `_dt` for date, `_ind` for checkbox \
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


# the simple naming scheme (docs/PLAN_SIMPLE_NAMES.md, 2026-10-19): the name is the subject in the form's own words,
# the kind of value is a separate answer that sets type and semantic type; no suffix in the name
NAMES = "simple"          # the default since 2026-10-20 (Andrew: "simple defaults from here")
_KINDS: dict[int, str] = {}          # widget id -> the kind the labeler gave (simple scheme)


def _simple_system() -> str:
    from petey.semantic_types import prompt_vocabulary
    a = LABEL_SYSTEM.index("- Emit snake_case slugs following IRS MeF-style")
    b = LABEL_SYSTEM.index("Business names → `_business_name`.\n") + len("Business names → `_business_name`.\n")
    rules = ("- The label names WHAT THE BOX HOLDS, in the form's own words, snake_case: `first_name`, "
             "`vehicle_make`, `gross_rents`, `years_at_current_address`, `date_of_birth`. Where the box belongs "
             "to one of several people or things the form repeats (a spouse, the 7th sibling, vehicle 2), the name "
             "says whose, with the number last as its own word: `spouse_first_name`, `sibling_marital_status_7`, "
             "`vehicle_make_2`; a caption printed once per block does not make the box stand alone. (A table or "
             "block you answer by its parts, under the page's structure rules, takes no number: printing adds it.) "
             "Do NOT add a "
             "type or kind suffix (no _txt, _nm, _nbr, _cd, _dt, _amt, _ind, _qty, _ssn): the kind of value is a separate "
             "answer, below, not part of the name.\n"
             "- With every label give `\"kind\"`: the kind of value the box holds, one of "
             + prompt_vocabulary() + " or \"identifier\" or \"checkbox\" (a tick box) or \"signature\". Use "
             "\"name\" for any name, a person's or an organization's, whole or part (a full name, a first name, "
             "a company); \"description\" for a longer explanation; \"text\" for free text and anything the list "
             "does not name; "
             "\"identifier\" for a number or "
             "code that names or refers to something rather than measuring it (a policy, location, vehicle, driver, "
             "license or reference number, a class or rating code; a caption with \"#\" or \"number\" in it, "
             "LOC #, VEH #, DRIVER NUMBER, is an identifier); \"money\" for a sum of money, \"count\" only for a "
             "box that asks how many of something (a number of units, years, days), \"indicator\" for a box answered yes or no "
             "(Y / N), \"percent\" for a percentage, \"iso_date\" for a full date, \"datetime\" for a date and a time of day in one box, \"year\" for a "
             "year alone, \"phone\", \"email\", \"ssn\", \"ein\", \"zip\", \"state_abbr\" as their names say. "
             "Outside the US: \"ca_postal_code\" for a Canadian postal code (A1A 1A1), \"uk_postcode\" for a UK "
             "postcode (SW1A 1AA), another country's postal code is \"text\"; \"phone\" is a US or Canadian "
             "number, \"uk_phone\" a UK one, \"intl_phone\" another country's.\n")
    out = (LABEL_SYSTEM[:a] + rules + LABEL_SYSTEM[b:]).replace("`is_amended_return_ind`", "`is_amended_return`")
    return out.replace('{"labels": [{"id": <int>, "label": "<snake_case_slug>"}, ...]}',
                       '{"labels": [{"id": <int>, "label": "<snake_case_slug>", "kind": "<kind>"}, ...]}')


def _system() -> str:
    return _simple_system() if NAMES == "simple" else LABEL_SYSTEM


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


def label_page_via_llm(widgets_on_page, words, model: str = MODEL, think: bool = True, structure: dict | None = None,
                       bulk: bool = False, parts_out: dict | None = None):
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
    if structure:
        # tables and repeated blocks found first (petey/label/structure.py, 2026-10-19): a structure is never split
        # across batches, and each batch's prompt says which of its widgets form one. In bulk mode the labeler names
        # a table's columns (a block's fields) once and the cells are printed from the parts, which the field keeps
        # as x_petey_identifiers; a structure the labeler calls unlike, or a column it leaves out, is labeled one by one
        from concurrent.futures import ThreadPoolExecutor
        from petey.label import structure as S
        bs = S.batches(widgets_on_page, structure, LABEL_BATCH)
        n = len(widgets_on_page)
        for i, batch in enumerate(bs):
            print(f"    [batch] {len(batch)} widgets ({i + 1} of {len(bs)}, {n} on the page; structure-{'bulk' if bulk else 'guided'})")
        if not bulk:
            with ThreadPoolExecutor(max_workers=len(bs)) as ex:
                results = list(ex.map(lambda b: _label_batch_via_llm(b, words, model=model, think=think,
                                                                     guidance=S.guidance(structure, {w["id"] for w in b})), bs))
            merged = {}
            for r in results:
                merged.update(r)
            return merged
        inside = S.in_structure(structure)
        with ThreadPoolExecutor(max_workers=len(bs)) as ex:
            results = list(ex.map(lambda b: _label_batch_via_llm(b, words, model=model, think=think,
                                                                 guidance=S.guidance_bulk(structure, {w["id"] for w in b}),
                                                                 want_parsed=True), bs))
        merged, left_ids = {}, []
        for b, (labels, parsed) in zip(bs, results):
            ids = {w["id"] for w in b}
            merged.update({i: l for i, l in labels.items() if i not in inside})
            names, parts, left = S.print_cells(structure, parsed, ids)
            merged.update(names)
            if parts_out is not None:
                parts_out.update(parts)
            left_ids += [i for i in left if i not in merged]
            for i in ids - inside:
                if i not in merged and i in labels:
                    merged[i] = labels[i]
        if left_ids:                          # cells the bulk answer did not cover: labeled one by one, guided
            by_id = {w["id"]: w for w in widgets_on_page}
            rest = [by_id[i] for i in left_ids if i in by_id]
            print(f"    [batch] {len(rest)} cells left by the bulk answer, labeled one by one")
            for i in range(0, len(rest), LABEL_BATCH):
                merged.update(_label_batch_via_llm(rest[i:i + LABEL_BATCH], words, model=model, think=think,
                                                   guidance=S.guidance(structure, {w["id"] for w in rest[i:i + LABEL_BATCH]})))
        printed = sum(1 for i in merged if i in inside and i not in left_ids)
        print(f"    [structure] {printed} cells printed from column / field labels, {len(left_ids)} labeled one by one")
        return merged
    if len(widgets_on_page) <= LABEL_BATCH:
        return _label_batch_via_llm(widgets_on_page, words, model=model, think=think)

    # the batches go out together (Andrew, 2026-10-19: ACORD 90 NY's page 1 took its three batches one after
    # another, 80 s each; a call's time is its output tokens, so the page costs one batch's time, not the sum).
    # Each batch has everything it needs before the call; the merge keeps batch order
    from concurrent.futures import ThreadPoolExecutor
    n = len(widgets_on_page)
    batches = [widgets_on_page[i:i + LABEL_BATCH] for i in range(0, n, LABEL_BATCH)]
    for i, batch in enumerate(batches):
        print(f"    [batch] widgets {i * LABEL_BATCH + 1}-{i * LABEL_BATCH + len(batch)} of {n}")
    with ThreadPoolExecutor(max_workers=len(batches)) as ex:
        results = list(ex.map(lambda b: _label_batch_via_llm(b, words, model=model, think=think), batches))
    merged: dict[int, str] = {}
    for r in results:
        merged.update(r)
    return merged


def dropdown_spec(spec: dict, w: dict) -> dict:
    """A dropdown's field takes its choice list as `values` (Andrew, 2026-10-07: hard-code dropdowns and their
    options). A closed list is `category` (`multi_category` for a list box that takes several); a combobox that also
    takes typed text stays `string` with the choices as `values`, since a filer may write something else. On a closed
    list the name's semantic type stays only when every choice fits its shape (a state list keeps `state_abbr`;
    `quarter_ended_dt` offering 1st..4th loses `iso_date`), and the pattern goes."""
    spec["values"] = list(w["choices"])
    if w.get("multiselect"):
        spec["type"] = "multi_category"
    elif not w.get("editable"):
        spec["type"] = "category"
    if spec["type"] != "string":
        spec.pop("pattern", None)
        st = next((t for t in ALL_TYPES if t.name == spec.get("semantic_type")), None)
        if st is not None and not (st.pattern and all(re.match(st.pattern, v) for v in spec["values"])):
            spec.pop("semantic_type")
    if w.get("choice_labels"):
        spec["x_petey_choice_labels"] = dict(w["choice_labels"])
    return spec


def _label_batch_via_llm(widgets_on_page, words, model: str = MODEL, think: bool = True, guidance: str = "",
                         want_parsed: bool = False):
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
        if w.get("choices"):                    # a dropdown: what it offers says what it is
            shown = w.get("choice_labels") or {}
            opts = ", ".join(json.dumps(shown.get(c, c)) for c in w["choices"][:12])
            line += f', "choices": [{opts}{", ..." if len(w["choices"]) > 12 else ""}]'
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
        + (guidance + "\n\n" if guidance else "")
        + f"Emit a snake_case label for every widget."
    )

    from petey.synth.generate import make_client, provider_for
    t0 = time.time()
    client = make_client(model)
    if provider_for(model) is not None:
        # other vendors, chat-completions dialect (same prompt, text only)
        kwargs = dict(model=model, messages=[{"role": "system", "content": _system()},
                                             {"role": "user", "content": user_text}])
        if model.startswith(("gpt-5", "o1", "o3", "o4")):
            kwargs["max_completion_tokens"] = MAX_TOKENS
        else:
            # Gemini counts its hidden thinking against max_tokens: at 32,768 a 48-126 widget page spent most of it
            # thinking and the labels were cut at ~3,300 chars (GCP runner, 2026-10-06); 65,536 is its output cap
            kwargs["max_tokens"] = 65536 if model.startswith("gemini-") else MAX_TOKENS
            if not think and model.startswith("gemini-"):
                # the review page's Groups button names one group from its captions (2026-10-13: 8 s -> 2 s with
                # thinking off; on single boxes it got 9 of 12 right against 12, so only Groups asks for this)
                kwargs["reasoning_effort"] = "none"
            kwargs["temperature"] = 0
            if model.startswith("local-"):
                # labels run to ~4k tokens at most; the context is shared with a prompt of up to ~32k. No hidden
                # thinking: it would cost minutes per page on a laptop (llama-server started with --jinja)
                kwargs["max_tokens"] = 8192
                kwargs["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        resp = client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        text = choice.message.content or ""
        stop = getattr(choice, "finish_reason", None)
        u = getattr(resp, "usage", None)
        in_tok, out_tok = (getattr(u, "prompt_tokens", None), getattr(u, "completion_tokens", None)) if u else (None, None)
    else:
        from petey.synth.generate import final_message
        final = final_message(lambda: client.messages.stream(
            model=model, max_tokens=MAX_TOKENS,
            system=_system(),
            messages=[{"role": "user", "content": user_text}],
        ), "labeler")
        text = "".join(
            b.text for b in final.content
            if getattr(b, "type", None) == "text"
        )
        # `stop_reason` is the difference between "the model answered badly"
        # and "the answer was cut off at MAX_TOKENS". Log every call, so a
        # failure never needs a re-run to diagnose. See call_log.py.
        stop = getattr(final, "stop_reason", None)
        usage = getattr(final, "usage", None)
        in_tok, out_tok = (getattr(usage, "input_tokens", None), getattr(usage, "output_tokens", None)) if usage else (None, None)
    call_log.record(
        f"{CALL_TAG}/{model.replace('/', '_')}", raw=text, finish_reason=stop,
        request={"widgets": len(widgets_on_page),
                 "max_tokens": MAX_TOKENS,
                 "prompt_chars": len(user_text)},
        usage={"output_tokens": out_tok, "input_tokens": in_tok}
        if in_tok is not None or out_tok is not None else None,
        elapsed=time.time() - t0,
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
            if entry.get("kind"):
                _KINDS[wid] = str(entry["kind"])
    if n_ignored:
        print(f"[auto_label] ignored {n_ignored} label entries whose id is "
              f"not a widget on this page (of "
              f"{len(parsed['labels'])} returned)")
    return (out, parsed) if want_parsed else out


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
    structure: Optional[str] = None,       # None, "guide" (tables and blocks in the prompt) or "bulk" (columns named once)
    names: str = "simple",                 # subject-only names, the kind of value answered apart; "standard": suffixes
) -> dict:
    global NAMES
    NAMES = names
    _KINDS.clear()
    from petey.label import structure as _S0
    _S0.SIMPLE = names == "simple"
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

    # The publisher's own field-level validation, when the form is an XFA
    # hybrid (STRATEGY_v1 §3.5): joined to widgets by AcroForm path, so
    # only meaningful with AcroForm geometry.
    xfa_tpl = None
    if geometry_method == "acroform":
        try:
            xfa_tpl = xfa_mod.parse(blank_pdf)
        except Exception as e:  # a broken packet must not sink the draft
            print(f"[auto_label] XFA template unreadable: {e}")
        if xfa_tpl is not None:
            print(f"[auto_label] XFA template: {xfa_tpl.census()}")

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

    page_structure: dict[int, dict] = {}
    parts_by_id: dict[int, dict] = {}       # bulk: the parts a cell's name was printed from
    if use_llm and structure:
        from petey.label import structure as _S
        page_structure = _S.find(blank_pdf, label_entries)
        print(f"[auto_label] structure: " + ", ".join(
            f"p{p} {len(st['tables'])} table(s) {len(st['blocks'])} block group(s)" for p, st in sorted(page_structure.items())) or "none")
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
                    residual, words, model=model, structure=page_structure.get(page_no),
                    bulk=(structure == "bulk"), parts_out=parts_by_id,
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
    page_captions: list[dict] = []
    dedup = DedupState()
    n_tooltip_descriptions = 0
    xfa_changes: collections.Counter = collections.Counter()

    def _overlay_xfa(spec: dict, path: Optional[str]) -> dict:
        """Declared beats inferred: XFA picture/nullTest/items over
        whatever `enrich_field` guessed from the name."""
        if xfa_tpl is None:
            return spec
        rec = xfa_tpl.lookup(path)
        if rec is None:
            xfa_changes["unjoined"] += 1
            return spec
        xfa_changes["joined"] += 1
        for k in xfa_mod.apply_declared(spec, rec):
            xfa_changes[k] += 1
        return spec

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
            on_states = list(w.get("options") or [])
            assigned = dedup.assign(
                label, page=w["page"], rect=w["rect"],
            )
            if len(on_states) <= 1:
                # one state (or none): a checkbox, possibly drawn in several
                # places; the first appearance is the widget
                first = members[0] if members else w
                fields[assigned] = {
                    "type": "boolean",
                    "widget": {"page": first["page"], "rect": first["rect"],
                               "widget_type": first.get("widget_type") or w.get("true_widget_type") or "checkbox",
                               "path": w.get("path")},
                }
                if len(members) > 1:
                    fields[assigned]["x_petey_appearances"] = len(members)
            else:
                # one field, one option per on-state, each with the box it
                # is drawn in: what a person sees on the page. `values`
                # stays the on-states (what the field stores) so the
                # generator, filler and scorer are unchanged.
                fields[assigned] = {
                    "type": "category",
                    "values": on_states,
                    "widgets": option_widgets(members, w),
                }
            _overlay_xfa(fields[assigned], w.get("path"))
            caption_options(fields[assigned])
            if fields[assigned].get("widgets"):
                page_captions.append(fields[assigned]["widgets"])
            continue

        if "." in label:
            group, value = label.split(".", 1)
            if value in mutex_widgets.get(group, {}):
                continue
            if w.get("on_state"):
                widget_block = dict(widget_block, on_state=w["on_state"])
            mutex_widgets.setdefault(group, {})[value] = widget_block
            continue
        assigned = dedup.assign(
            label, page=w["page"], rect=w["rect"],
        )
        kind = (parts_by_id.get(w["id"]) or {}).get("kind") or _KINDS.get(w["id"])
        if NAMES == "simple":
            from petey.semantic_types import enrich_from_kind
            spec = enrich_from_kind(kind, w["widget_type"])
        else:
            spec = enrich_field(label, w["widget_type"])
        if w.get("choices"):
            dropdown_spec(spec, w)
        spec["widget"] = widget_block
        if "confidence" in w:  # programmatic geometry: the rect is an estimate; say how good
            spec["x_petey_geometry"] = {"confidence": w["confidence"], "source": w.get("geometry_source")}
        desc = _description_from_tooltip(w.get("tooltip"))
        if desc:
            spec["description"] = desc
            spec["x_petey_description_source"] = "tooltip"
            n_tooltip_descriptions += 1
        _overlay_xfa(spec, w.get("path"))
        if w["id"] in parts_by_id:
            spec["x_petey_identifiers"] = {k: v for k, v in parts_by_id[w["id"]].items() if k != "kind"}
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
        # captions for the cluster's options: the on-state when the
        # publisher wrote it as a word (I-765: Widowed / Divorced / Single /
        # Married), else the page text beside the box
        for v, wb in val_to_widget.items():
            st = wb.get("on_state")
            if st and not _ORDINAL_STATE.match(st) and st.lower() not in ("on", "off", "yes", "no", "true", "false"):
                wb["caption"] = st
        page_captions.append(val_to_widget)

    # captions still missing after the XFA and on-state rules come from the
    # page text beside (or above) each option box; nothing else is guessed
    if page_captions:
        from petey.label.captions import caption_options_from_page
        _doc = pymupdf.open(str(blank_pdf))
        try:
            _rects: dict[int, list] = {}
            for _ws in page_captions:
                for _b in _ws.values():
                    _rects.setdefault(_b["page"], []).append(_b["rect"])
            _texts: dict[int, list] = {}           # write-in boxes: an option followed by one gets no fallback caption
            for _w in widgets:
                if _w.get("widget_type") == "text":
                    _texts.setdefault(_w["page"], []).append(_w["rect"])
            n_page_captions = sum(caption_options_from_page(_doc, _ws, _rects, _texts) for _ws in page_captions)
        finally:
            _doc.close()
        if n_page_captions:
            print(f"  [captions] {n_page_captions} option captions from page text")

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
            # when it was labeled (2026-10-05): side copies live under runs/, outside git, and a file's mtime
            # moves with every loop edit
            "when": time.strftime("%Y-%m-%d %H:%M:%S"),
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
    if xfa_changes:
        print(f"  [xfa] declared over inferred: {dict(xfa_changes)}")
        if set(xfa_changes) - {"joined", "unjoined"}:
            bp["x_petey_xfa_log"] = dict(xfa_changes)
    if geometry_method == "acroform":
        # The loop's deterministic repairs, run at emit instead of after:
        # they need only the blueprint, the box geometry and the XFA
        # template, all in hand here. Parts from box length, separator-free
        # comb patterns, short shapes off wide boxes, dates on boxes too
        # small for one, tooltips and radio captions into descriptions.
        # Imported here: retype imports this module.
        from petey.synth.local import widget_limits
        from petey.validate.retype import describe_blueprint, money_kind, retype_blueprint, type_from_description
        limits = widget_limits(blank_pdf)
        emit_fixes = retype_blueprint(bp, limits)
        emit_fixes.update(describe_blueprint(bp, limits, xfa_tpl))
        emit_fixes.update(type_from_description(bp))      # needs the descriptions; conflicts are left for review
        emit_fixes.update(money_kind(bp, blank_pdf, limits))   # after the descriptions: units, whole dollars
        if emit_fixes:
            bp["x_petey_emit_fixes"] = dict(emit_fixes)
            print(f"  [emit] loop rules applied at emit: {dict(emit_fixes)}")
    if xfa_tpl is not None:
        # Cross-field rules (STRATEGY_v1 §3.5, spec Appendix B proposal):
        # reciprocal clear-others script groups become `mutex` rules over
        # the emitted field names. Under x_petey_ until the spec adopts it.
        tmpl_path_to_name: dict[str, str] = {}
        for fname, fspec in fields.items():
            paths = []
            if fspec.get("widget", {}).get("path"):
                paths.append(fspec["widget"]["path"])
            paths += [wb.get("path") for wb in (fspec.get("widgets") or {}).values()]
            for p in paths:
                rec = xfa_tpl.lookup(p)
                if rec is not None:
                    tmpl_path_to_name[rec.path] = fname
        rules = []
        for group in xfa_mod.mutex_groups(xfa_tpl):
            names = sorted({tmpl_path_to_name[p] for p in group if p in tmpl_path_to_name})
            if len(names) >= 2:
                rules.append({"mutex": names, "source": "xfa_script"})
        if rules:
            bp["x_petey_rules"] = rules
            print(f"  [xfa] {len(rules)} mutex rules from scripts")
    field_ids.assign(bp)                    # a fixed id per field, for referring to it (x_petey_id)
    return stamp_version(bp)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--blank", required=True, type=Path,
                    help="path to blank AcroForm PDF")
    ap.add_argument("--output", type=Path, default=None,
                    help="output blueprint .bpt path (default: blueprints/<form_id>.bpt)")
    ap.add_argument("--name", type=str, default=None,
                    help="form_id (default: from the registry via petey.ingest, "
                         "else the --output stem)")
    ap.add_argument("--no-register", action="store_true",
                    help="do not identify the form or write to the registry")
    ap.add_argument("--form-version", type=str, default=None,
                    help='form revision year (e.g. "2025")')
    ap.add_argument("--model", type=str, default=MODEL,
                    help="LLM model for labeling (default sonnet-4.6)")
    ap.add_argument("--geometry", choices=["auto", "acroform", "sibling", "step2flat"], default="auto",
                    help="where field rects come from; auto = AcroForm if present, else step2flat (sibling is opt-in)")
    ap.add_argument("--no-llm", action="store_true",
                    help="emit placeholder field names; no API call (geometry-only draft)")
    ap.add_argument("--structure", nargs="?", const="guide", choices=["guide", "bulk"], default=None,
                    help="find tables and repeated blocks first: 'guide' puts them in the labeler's prompt, 'bulk' names "
                         "a column once and prints its cells (2026-10-19)")
    ap.add_argument("--names", choices=["standard", "simple"], default="simple",
                    help="simple (the default since 2026-10-20): subject-only names, the kind of value answered apart "
                         "(docs/PLAN_SIMPLE_NAMES.md); standard: MeF-style suffixes")
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

    identity = None
    if not args.no_register:
        # Identify the document and resolve or register its form, so the
        # blueprint is born with the registry's id, edition and provenance.
        from petey.ingest import ingest
        identity = ingest(args.blank, name=args.name)
        print(f"[ingest] form_id={identity['form_id']} via={identity['via']} "
              f"canonical={identity['canonical']} edition={identity['edition']} "
              f"created={identity['created']}")
    # The blueprint's own name: the caller's --name, else the --output stem,
    # else the registry form id. The registry link always uses the form id.
    name = args.name or (args.output.stem if args.output else None) or (identity or {}).get("form_id")
    if not name:
        raise SystemExit("--name or --output is required with --no-register")
    global CALL_TAG
    CALL_TAG = f"auto_label/{name}"
    if args.output is None:
        from petey.paths import BLUEPRINTS
        args.output = BLUEPRINTS / f"{name}.bpt"
    if args.form_version is None and identity and identity.get("edition"):
        args.form_version = identity["edition"]
    bp = build_blueprint(
        args.blank, name,
        form_version=args.form_version,
        model=args.model,
        use_retrieval=not args.no_retrieval,
        geometry=args.geometry,
        use_llm=not args.no_llm,
        structure=args.structure,
        names=args.names,
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
    if identity is not None:
        from petey.ingest import record_blueprint
        if record_blueprint(identity["form_id"], args.output, args.blank, placeholder_names=args.no_llm,
                            spec_version=str(bp.get("bpt_version"))):
            print(f"[ingest] registered {args.output.name} as an artifact of {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
