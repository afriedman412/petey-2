"""LLM field reviewer: the loop's repair step for what the rules cannot fix.

The deterministic detectors say WHERE a blueprint is suspect (a generated
value its declaration rejects; a name the by-meaning reader resolved to a
different box). The mechanical classes already have rules (`retype.py`).
Everything else used to become a new taxonomy class and, eventually, a new
rule. This hands the flagged fields to a model instead, one evidence bundle
per field, and asks for a verdict: the spec is right, or here is the fix.

The model does not judge its own work. `iterate.py` re-validates after the
fixes land and reverts them if detections did not go down; the generator
stays blind and the name-based reader never sees geometry. A proposed rename
the case chain does not settle (caption unverified, or tooltip and caption
at odds) goes to `adjudicate.py` first, which reads the blank page around
the widget and upholds or drops it (2026-10-01).

Evidence per field (no ground truth beyond what the loop already produced):
  - the current spec: name, type, semantic_type, pattern, values, description
  - the box: widget type, width in points, max length, comb, the tail of the
    AcroForm path (often the publisher's own field name)
  - the publisher's tooltip and, on XFA hybrids, the template's declaration
  - printed words around the box on the blank page
  - flags: which detector fired, the label-grounded generated value, and what
    the by-meaning reader returned for this name
  - witness flags (`witness.against_flags`, 2026-10-05): a text about the
    widget that belongs to another field; a rename on such a field always
    goes to the adjudicator

    python -m petey.validate.review --form vba21526ez [--run-dir runs/...] [--scope flagged|all]
        [--model claude-opus-5] [--effort medium] [--apply]

Costs are logged per run (tokens and dollars at list price) so cheaper
models can be compared on the same fields.
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml

from petey.label import xfa as xfa_mod
from petey.paths import BLUEPRINTS, RUNS
from petey.synth.local import widget_limits
from petey.validate.retype import resolve_blank

DEFAULT_MODEL = "claude-opus-5"
PRICES = {  # $ per million tokens, input / output (list price, 2026-06)
    "claude-opus-5": (5.0, 25.0), "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0), "claude-fable-5-1": (10.0, 50.0),
}
FIELDS_PER_CALL = 25
TYPES = ("string", "number", "integer", "date", "boolean", "category", "multi_category")

SYSTEM = """You review field definitions in a blueprint: a schema that says, for \
each fillable box on a blank form, what the box holds. Each field has a name \
(snake_case, IRS MeF style: _amt money, _dt date, _ind checkbox, _cd code, _nm \
name, _txt free text, _yr year, _ssn / _ein IDs), a type (string, number, \
integer, date, boolean, category), and optionally a semantic_type, a regex \
pattern (strings only), a list of values (category only) and a description.

You receive fields the validation loop flagged, each with its evidence: the box \
(size, max length, the publisher's own field name from the PDF), the publisher's \
tooltip, the XFA declaration when the PDF has one, the printed words around the \
box, and what the loop observed:
- shape: a value generated from the printed label contradicts the declared \
type/pattern. Either the declaration is wrong (e.g. a 2-digit month box typed as \
a date) or the generated value is (e.g. the label says "approximate date" but \
the tooltip asks for MM/DD/YYYY).
- name_reader: a reader that looks for each field BY NAME found a different \
value than the one in this box. Either the name describes another box, or it is \
too vague to pick this one (a section repeated for veteran and claimant, table \
rows) and needs the copy or row in it.
- witness: a text about this box (the publisher's tooltip, the printed caption, \
or the page classifier's caption, quoted in `text`) describes another field \
better than this name, and better than that field's own text. Either the two \
names are swapped or one row off (rename), or the text is the publisher's \
mistake and the caption printed for this box confirms the current name (ok).
- page_check: a vision model that saw the whole page with every box outlined says \
the name or type does not fit what a filer writes in this box (its reading in \
`text`, its reason in `detail`, its suggestion in `page_check_proposes`). It \
read the page, not the metadata; weigh it like the printed caption, and check \
the neighbours it names before following its suggestion.

For each field decide: "ok" if the definition is right and the flag is the \
generator's or reader's fault, or "fix" with only the attributes that should \
change (null means unchanged; list an attribute in `remove` to drop it, e.g. a \
wrong semantic_type).

WHAT THE BOX HOLDS: the caption printed for THIS box (inside it, or directly \
above or beside it as the form lays out its captions) says what a filer writes \
there, and a filer types by position. When the publisher's tooltip or field name \
says something else, the publisher placed the widget in the wrong box and the \
caption wins: name the field for the caption. Publisher evidence (tooltip, XFA \
declaration, readable field name) outranks printed text that is merely NEARBY (a \
neighbouring box's caption, a section heading), and all of it outranks the \
current name. A box that holds part of a value (month, day, year, one segment of \
an SSN or phone) is a string with a digit pattern and a name that says which part.

Rename when the current name describes something other than what this box holds, \
when it cannot tell this box apart from another field on the form, or when it says \
nothing about the value at all (control, text16, field_3, check_box_1: a \
generator default or a one-word tooltip copied into the name); an uninformative \
name is a defect even when no other field claims the box. When two flagged \
fields each hold what the other's name says, the names are swapped: fix both \
names. Never write a description that contradicts the field's name; if the \
description you would write describes a different value than the name does, the \
name is what must change. Never rename \
to adjust a suffix, normalize style, or add words that do not change what the name \
points at: the name is how a reader finds the box, and a working name is worth \
keeping. When a section repeats (veteran and claimant, several employers, table \
rows), qualify with what distinguishes the copy — the section heading or role \
given in `section_heading`, and see `sibling_copies` for the other copies' names — \
not with a page number. Keep names unique on the form. Change nothing the evidence \
does not support."""

DECISION_SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["ok", "fix"]},
                    "name": {"type": ["string", "null"]},
                    "type": {"anyOf": [{"type": "string", "enum": list(TYPES)}, {"type": "null"}]},
                    "semantic_type": {"type": ["string", "null"]},
                    "pattern": {"type": ["string", "null"]},
                    "values": {"type": ["array", "null"], "items": {"type": "string"}},
                    "description": {"type": ["string", "null"]},
                    "remove": {"type": "array", "items": {"type": "string", "enum": [
                        "semantic_type", "pattern", "values", "description"]}},
                    "reason": {"type": "string"},
                },
                "required": ["field", "verdict", "name", "type", "semantic_type", "pattern",
                             "values", "description", "remove", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["decisions"],
    "additionalProperties": False,
}


# ----------------------------------------------------------------- evidence

def latest_scored_run(form: str) -> Optional[Path]:
    """Most recent run for this form with an intact score; prefer one that
    also carries a meaning-arm score."""
    dirs = sorted(d for d in RUNS.glob(f"{form}_2*") if (d / "case_001_intact" / "score_native.json").exists())
    with_judge = [d for d in dirs if method_delta.judge_scores(d / "case_001_intact")]
    return (with_judge or dirs or [None])[-1]


def flags_from_run(run_dir: Path) -> dict[str, list[dict]]:
    intact = run_dir / "case_001_intact"
    flags: dict[str, list[dict]] = collections.defaultdict(list)
    native = json.loads((intact / "score_native.json").read_text())
    gt_by_field = {p["field"]: p.get("gt_value") for p in native.get("per_field", [])}
    # The case was built box -> class -> value (petey/validate/field_chain.py). A field whose box failed or whose
    # caption the classifier took from a neighbouring box sends no class, regex or judge flag: those signals all
    # rest on the misreading, and a reviewer acting on them renames a right field (MA LIC100, Utah WC-122).
    from petey.validate.field_chain import chain_for_run
    chain = chain_for_run(run_dir, intact.name)
    held = {f for f, r in chain.items() if r.get("stage") in ("box", "class")}
    # The judge's reading is of the filled page, not of the classifier's caption, so a class-stage field (box
    # lined up, caption unverified) still reaches the reviewer on a judge flag, with the caption withheld; any
    # rename on it is contested and goes to the adjudicator (`adjudicate.py`), which reads the page itself.
    held_box = {f for f, r in chain.items() if r.get("stage") == "box"}
    class_tier1 = set()
    cd0 = intact / "class_disagreements.json"
    if cd0.exists():
        class_tier1 = {row["field"] for row in json.loads(cd0.read_text()) if row.get("tier") == 1}
    for f, why in (native.get("gt_shape_mismatches") or {}).items():
        if f in held or f in class_tier1:      # on a bank case the regex miss restates the class disagreement
            continue
        flags[f].append({"detector": "shape", "detail": why, "generated_value": gt_by_field.get(f)})
    for rv in native.get("rule_violations") or []:
        for f in rv.get("held", []):
            flags[f].append({"detector": "rule", "detail": "mutex violated", "generated_value": gt_by_field.get(f)})
    # The name-based reader: one arm (image when present — the text layer
    # misses filled values on a few forms), and only the causes that are
    # about the NAME. Substring / punctuation / boolean disagreements are
    # reading or format noise, not evidence against the field definition.
    from petey.validate import method_delta
    from petey.validate.name_caption import box_for, caption_boxes, name_matches_caption
    arm = method_delta.preferred_judge(intact)
    if arm:
        # A field whose name agrees with the caption printed for its box is about that box: when the reader
        # misses it, the cause is the page's presentation (empty cells, columns, code cells) or the case value,
        # and a reviewer handed it as a name defect renames a correct field (2026-09-30: of 308 judge
        # disagreements on 24 new forms, about 25 were naming defects, and every one of those had a name that
        # shares nothing with its box's caption). Uncaptioned boxes stay flagged.
        boxes = caption_boxes(intact)
        bp_fields = (yaml.safe_load((run_dir / "blueprint.bpt").read_text(encoding="utf-8")) or {}).get("fields") or {} \
            if (run_dir / "blueprint.bpt").exists() else {}
        for r in method_delta.compare_case(intact, arm):
            if r.get("cause") not in ("defect", "unlocatable") or r["field"] in held_box:
                continue
            rec = chain.get(r["field"]) or {}
            box = box_for(bp_fields.get(r["field"]) or {}, boxes)
            # a caption the chain found wrong gates nothing (SS-4 `ein` on the legal-name box: the caption
            # mentions the EIN, the name matched it, and the right rename never reached the reviewer)
            if rec.get("verified") is not False and name_matches_caption(r["field"], box.get("label")):
                continue
            if not rec.get("verified"):
                box = {}                       # an unverified caption is not shown to the reviewer as fact
            flags[r["field"]].append({
                "detector": "name_reader",
                "detail": ("reader could not find this name on the page" if r["cause"] == "unlocatable"
                           else "reader found a different box's value for this name"),
                "generated_value": r.get("gt"), "reader_value": r.get("judge", r.get("petey")),
                **({"caption_printed_for_this_box": box["label"]} if box.get("label") else {}),
                **({"reader_value_belongs_to": r["swap_with"]} if r.get("swap_with") else {})})
    # Page-grounded classification (synth.classify) against the blueprint's
    # typing: the second opinion on what kind of value the box holds. Only
    # captioned boxes count; an uncaptioned line under a block heading is
    # a guess on both sides.
    cd = intact / "class_disagreements.json"
    if cd.exists():
        for row in json.loads(cd.read_text()):
            if row.get("tier") != 1 or row["field"] in held:
                continue
            flags[row["field"]].append({
                "detector": "page_class",
                "detail": (f"the page says this box holds a {row['page_class']} "
                           f"(caption {row.get('label')!r}); the blueprint types it "
                           f"{row.get('semantic_type') or row.get('type') or 'untyped'}"),
                "generated_value": gt_by_field.get(row["field"])})
    # Inventory cross-reference: the page's option groups (the classifier's
    # `group`) against the blueprint's `widgets` maps. A field that spans two
    # printed questions, or a question the blueprint splits in two, is the
    # labeler's to look at; the widget layer only says which side the
    # publisher's radio paths take.
    inv = intact / "inventory_check.json"
    if inv.exists():
        for row in json.loads(inv.read_text()).get("rows", []):
            if row.get("class") != "option_group_mismatch":
                continue
            pg = row.get("page_group")
            pg = " / ".join(pg) if isinstance(pg, list) else pg
            flags[row["field"]].append({
                "detector": "option_group",
                "detail": {
                    "blueprint_field_spans_page_groups": f"the page reads this field's options as {row.get('page_groups')} "
                                                         f"separate questions ({pg}); the blueprint pools them as one field",
                    "page_group_wider": f"the page's question ({pg}) has {row.get('page_members')} option boxes; this field "
                                        f"declares {row.get('blueprint_members')}",
                    "blueprint_options_unreached": f"{row.get('unreached_options')} of this field's options have no box on the "
                                                   f"page the classifier called an option",
                    "page_sees_no_group": "the page does not read these boxes as one question",
                }.get(row.get("shape"), row.get("shape")),
                "attribution": row.get("attribution"),
                "radio_paths": row.get("radio_paths")})
    # Witnesses (`witness.py`, 2026-10-05): a text about this widget (the publisher's tooltip, the caption printed
    # at it, the classifier's caption) that belongs to another field more than that field's own text does. The
    # signature of a swap or a widget placed one row off (5500-SF day/month, ACORD 25 phone names on the state and
    # ZIP boxes), which the judge only sees when the case happens to trip it. Read from the blank, not the case.
    from petey.validate.witness import against_flags
    for f, fl in against_flags(run_dir).items():
        flags[f].extend(fl)
    return flags


def _near_words(words: list[tuple], rect: list[float], dx: float = 170, dy: float = 38) -> str:
    x0, y0, x1, y1 = rect
    box = (x0 - dx, y0 - dy, x1 + 40, y1 + 12)
    hits = [w for w in words if w[2] >= box[0] and w[0] <= box[2] and w[3] >= box[1] and w[1] <= box[3]]
    hits.sort(key=lambda w: (round(w[1] / 4), w[0]))
    return " ".join(w[4] for w in hits[:40])


_HEADING_RE = re.compile(r"^(?:SECTION|PART|Section|Part|Schedule|SCHEDULE)\b|^[IVX]+\.\s|^[A-Z]\.\s")


def _page_lines(page) -> list[tuple]:
    """(x0, y0, x1, y1, text, bold) per text line on the page."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            spans = [sp for sp in ln["spans"] if sp["text"].strip()]
            if not spans:
                continue
            text = " ".join(sp["text"].strip() for sp in spans)
            bold = all(sp["flags"] & 16 for sp in spans)
            out.append((*ln["bbox"], text, bold))
    return out


def _is_heading(text: str) -> bool:
    """A section marker, not a field label: forms like the VA's print every
    label in capitals, so case alone says nothing."""
    t = text.strip()
    return 6 <= len(t) <= 140 and bool(_HEADING_RE.search(t))


def _section_heading(lines: list[tuple], rect: list[float]) -> Optional[str]:
    """The section a box sits in: the nearest section marker above it on the
    page; for a box above every marker (a page-header copy of a repeated
    field), the first marker on the page."""
    y0 = rect[1]
    above = [(ly1, text) for _, _, _, ly1, text, _ in lines if ly1 <= y0 + 1 and _is_heading(text)]
    if above:
        return max(above)[1][:140]
    below = [(ly0, text) for _, ly0, _, _, text, _ in lines if _is_heading(text)]
    return (min(below)[1][:140] + " (section this page belongs to)") if below else None


_STEM_RE = re.compile(r"(?:_page\d+|_p\d+|_copy\d*|_\d+)+$")


def _siblings(fields: dict, name: str) -> list[str]:
    stem = _STEM_RE.sub("", name)
    out = []
    for other, spec in fields.items():
        if other == name or _STEM_RE.sub("", other) != stem:
            continue
        w = spec.get("widget") or {}
        out.append(f"{other} (page {w.get('page')})")
    return out[:8]


def build_evidence(bp: dict, blank: Path, flags: dict[str, list[dict]], scope: str) -> list[dict]:
    limits = widget_limits(blank)
    try:
        tpl = xfa_mod.parse(blank)
    except Exception:
        tpl = None
    doc = pymupdf.open(str(blank))
    words_by_page: dict[int, list[tuple]] = {}
    lines_by_page: dict[int, list[tuple]] = {}
    all_fields = bp.get("fields") or {}
    out = []
    try:
        for name, spec in (bp.get("fields") or {}).items():
            if scope == "flagged" and name not in flags:
                continue
            w = spec.get("widget") or {}
            if not w and spec.get("widgets"):
                w = next(iter(spec["widgets"].values()))
            path, page = w.get("path"), w.get("page")
            lim = limits.get(path or "", {})
            rec = {
                "field": name,
                "spec": {k: spec.get(k) for k in ("type", "semantic_type", "pattern", "values", "description")
                         if spec.get(k) not in (None, "", [])},
                "box": {"widget_type": w.get("widget_type") or ("radio group" if spec.get("widgets") else None),
                        "page": page,
                        "width_pt": round(lim.get("width") or ((w.get("rect") or [0, 0, 0, 0])[2]
                                                                - (w.get("rect") or [0, 0, 0, 0])[0]), 1),
                        "maxlen": lim.get("maxlen") or None, "comb": lim.get("comb") or None,
                        "publisher_field_name": re.sub(r"\[\d+\]", "", (path or "").split(".")[-1]) or None},
                "tooltip": (lim.get("tooltip") or None),
            }
            if "description" in rec["spec"] and len(rec["spec"]["description"]) > 240:
                rec["spec"]["description"] = rec["spec"]["description"][:240] + "..."
            if tpl is not None and path:
                x = tpl.lookup(path)
                if x is not None:
                    decl = {"kind": x.kind}
                    if x.pictures:
                        decl["pictures"] = {k: v[:1] for k, v in x.pictures.items()}
                    if x.members:
                        decl["choices"] = [m["caption"] or m["name"] for m in x.members]
                    if x.messages:
                        decl["message"] = next(iter(x.messages.values()))
                    rec["xfa"] = decl
            if page and w.get("rect"):
                if page not in words_by_page:
                    words_by_page[page] = doc[page - 1].get_text("words")
                    lines_by_page[page] = _page_lines(doc[page - 1])
                rec["printed_near_box"] = _near_words(words_by_page[page], w["rect"])
                heading = _section_heading(lines_by_page[page], w["rect"])
                if heading:
                    rec["section_heading"] = heading
            sib = _siblings(all_fields, name)
            if sib:
                rec["sibling_copies"] = sib
            rec["observed"] = flags.get(name, [])
            out.append({k: v for k, v in rec.items() if v not in (None, {}, [])})
    finally:
        doc.close()
    return out


# ------------------------------------------------------------------- model

def _client():
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass
    import anthropic
    return anthropic.Anthropic()


def ask(client, model: str, effort: str, form_title: str, fields: list[dict]) -> tuple[list[dict], dict]:
    user = (f"Form: {form_title}\n\nFlagged fields ({len(fields)}), one JSON object each:\n"
            + "\n".join(json.dumps(f, ensure_ascii=False) for f in fields)
            + "\n\nReturn one decision per field.")
    output_config: dict[str, Any] = {"format": {"type": "json_schema", "schema": DECISION_SCHEMA}}
    if not re.search(r"-(4-[0-5]|3-\d)", model):
        output_config["effort"] = effort   # Haiku 4.5 and older reject `effort`
    kwargs: dict[str, Any] = dict(
        model=model, max_tokens=64000 if not re.search(r"-(4-[0-5]|3-\d)", model) else 16000,
        system=SYSTEM, messages=[{"role": "user", "content": user}],
        output_config=output_config,
    )
    if model.startswith("claude-opus-5") or model.startswith("claude-fable"):
        # Refusal fallback: a declined request re-runs server-side on the
        # recommended model instead of coming back empty.
        kwargs["betas"] = ["server-side-fallback-2026-07-01"]
        kwargs["extra_body"] = {"fallbacks": "default"}
        with client.beta.messages.stream(**kwargs) as stream:
            resp = stream.get_final_message()
    else:
        with client.messages.stream(**kwargs) as stream:
            resp = stream.get_final_message()
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
             "stop_reason": resp.stop_reason, "model_served": resp.model}
    if resp.stop_reason == "refusal":
        return [], usage
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    try:
        return json.loads(text).get("decisions", []), usage
    except json.JSONDecodeError:
        # Truncated at max_tokens (thinking plus a long JSON): the caller
        # splits the chunk and retries. Never silently drop 40 fields.
        usage["parse_error"] = f"{resp.stop_reason}: {text[:120]}"
        return [], usage


def ask_split(client, model: str, effort: str, form_title: str, fields: list[dict],
              usage_total: collections.Counter, depth: int = 0) -> list[dict]:
    """`ask`, halving the chunk on truncation (down to single fields)."""
    got, usage = ask(client, model, effort, form_title, fields)
    for k in ("input_tokens", "output_tokens"):
        usage_total[k] += usage[k]
    usage_total["calls"] += 1
    if usage.get("stop_reason") == "refusal":
        usage_total["refusals"] += 1
        return got
    if not got and usage.get("parse_error") and len(fields) > 1 and depth < 3:
        usage_total["truncated_retries"] += 1
        mid = len(fields) // 2
        return (ask_split(client, model, effort, form_title, fields[:mid], usage_total, depth + 1)
                + ask_split(client, model, effort, form_title, fields[mid:], usage_total, depth + 1))
    if not got and usage.get("parse_error"):
        usage_total["lost_fields"] += len(fields)
    return got


# ------------------------------------------------------------------- apply

def _valid(d: dict, spec: dict) -> Optional[str]:
    new_type = d.get("type") or spec.get("type", "string")
    if d.get("pattern"):
        if new_type != "string":
            return "pattern on non-string type"
        try:
            re.compile(d["pattern"])
        except re.error:
            return "pattern does not compile"
    if d.get("values") and new_type not in ("category", "multi_category"):
        return "values on non-category type"
    if d.get("name") and not re.fullmatch(r"[a-z][a-z0-9_]*", d["name"]):
        return "name is not snake_case"
    return None


def apply_decisions(bp: dict, decisions: list[dict], model: str) -> collections.Counter:
    fields = bp["fields"]
    changes: collections.Counter = collections.Counter()
    renames: dict[str, str] = {}
    for d in decisions:
        name = d.get("field")
        if name not in fields or d.get("verdict") != "fix":
            if name in fields:
                changes["ok"] += 1
            continue
        spec = fields[name]
        bad = _valid(d, spec)
        if bad:
            changes[f"rejected:{bad}"] += 1
            continue
        adj = d.get("adjudication")
        if adj:
            # the adjudicator's verdict on the proposed rename (adjudicate.py); `unclear` is a flag for a person
            spec["x_petey_adjudication"] = {k: adj.get(k) for k in ("verdict", "proposed", "reason", "model", "contested")}
            if adj.get("verdict") == "unclear":
                spec["x_petey_adjudication"]["needs_person"] = True
            changes[f"adjudicated:{adj.get('verdict')}"] += 1
        before = {k: copy.deepcopy(spec.get(k)) for k in ("type", "semantic_type", "pattern", "values", "description")}
        touched = []
        for k in ("type", "semantic_type", "pattern", "values", "description"):
            v = d.get(k)
            if v not in (None, "", []) and v != spec.get(k):
                spec[k] = v
                touched.append(k)
        for k in d.get("remove") or []:
            if k == "values" and spec.get("type") in ("category", "multi_category"):
                continue  # a category needs its values
            if k in spec and k not in touched:
                spec.pop(k)
                touched.append(f"-{k}")
        if spec.get("type") != "string":
            spec.pop("pattern", None)
        if spec.get("type") not in ("category", "multi_category") and "values" in spec and not spec.get("widgets"):
            spec.pop("values", None)
        new_name = d.get("name")
        if new_name and new_name != name:
            if new_name in fields or new_name in renames.values():
                changes["rename_collision"] += 1
            else:
                renames[name] = new_name
                touched.append("name")
        if touched:
            spec["x_petey_review"] = {"model": model, "changed": touched, "reason": d.get("reason", "")[:300],
                                      "before": {k: v for k, v in before.items() if v is not None},
                                      **({"old_name": name} if "name" in touched else {}),
                                      **({"adjudicated": "proposed"} if "name" in touched and adj else {})}
            for k in touched:
                changes[k] += 1
    if renames:
        bp["fields"] = {renames.get(k, k): v for k, v in fields.items()}
        for rule in bp.get("x_petey_rules") or []:
            if "mutex" in rule:
                rule["mutex"] = [renames.get(m, m) for m in rule["mutex"]]
    return changes


# ------------------------------------------------------------------- driver

def review(form: str, *, run_dir: Optional[Path] = None, scope: str = "flagged",
           model: str = DEFAULT_MODEL, effort: str = "medium", apply: bool = False,
           bpt_path: Optional[Path] = None, adjudicate: bool = True,
           adjudicator_model: Optional[str] = None) -> dict:
    """Flags from the run -> evidence -> the model's decisions -> (contested renames to the adjudicator) ->
    apply. `adjudicate` sends every proposed rename the case chain does not settle to `adjudicate.py`, which
    reads the blank page around the widget; a rename it does not uphold is dropped from the decision."""
    bpt_path = bpt_path or (BLUEPRINTS / f"{form}.bpt")
    bp = yaml.safe_load(bpt_path.read_text(encoding="utf-8"))
    blank = resolve_blank(bp)
    if blank is None:
        raise SystemExit(f"{form}: blank PDF not found")
    run_dir = run_dir or latest_scored_run(form)
    flags = flags_from_run(run_dir) if run_dir else {}
    evidence = build_evidence(bp, blank, flags, scope)
    title = bp.get("name") or form
    client = _client() if evidence else None
    decisions: list[dict] = []
    usage_total = collections.Counter()
    t0 = time.time()
    for i in range(0, len(evidence), FIELDS_PER_CALL):
        chunk = evidence[i:i + FIELDS_PER_CALL]
        decisions.extend(ask_split(client, model, effort, title, chunk, usage_total))
    pin, pout = PRICES.get(model, (0.0, 0.0))
    cost = usage_total["input_tokens"] / 1e6 * pin + usage_total["output_tokens"] / 1e6 * pout
    adjudicated = None
    if adjudicate and decisions and run_dir is not None:
        from petey.validate import adjudicate as adjudicate_mod
        from petey.validate.field_chain import chain_for_run
        from petey.validate.witness import contested_fields
        adjudicated = adjudicate_mod.adjudicate_decisions(
            bp, blank, decisions, chain_for_run(run_dir), limits=widget_limits(blank),
            model=adjudicator_model or adjudicate_mod.MODEL, tag=f"adjudicate/{form}",
            contested=contested_fields(flags))
        cost += adjudicated["cost_usd"]
    changes = collections.Counter()
    if apply and decisions:
        changes = apply_decisions(bp, decisions, model)
        bpt_path.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True,
                                           default_flow_style=False), encoding="utf-8")
    verdicts = collections.Counter(d.get("verdict") for d in decisions)
    return {"form": form, "run": run_dir.name if run_dir else None, "scope": scope, "model": model,
            "effort": effort, "fields_reviewed": len(evidence), "flagged": len(flags),
            "verdicts": dict(verdicts), "applied": dict(changes), "usage": dict(usage_total),
            "cost_usd": round(cost, 4), "seconds": round(time.time() - t0, 1),
            "adjudicated": adjudicated,
            "decisions": decisions, "evidence": evidence}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True)
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--scope", choices=["flagged", "all"], default="flagged")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--no-adjudicate", action="store_true", help="land contested renames without the adjudicator")
    ap.add_argument("--adjudicator-model", default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--show", type=int, default=12, help="print this many decisions")
    args = ap.parse_args()
    res = review(args.form, run_dir=args.run_dir, scope=args.scope, model=args.model,
                 effort=args.effort, apply=args.apply, adjudicate=not args.no_adjudicate,
                 adjudicator_model=args.adjudicator_model)
    out = args.out or (RUNS / f"review_{args.form}_{args.model}.json")
    out.write_text(json.dumps(res, indent=1, default=str))
    print(json.dumps({k: v for k, v in res.items() if k not in ("decisions", "evidence")}, indent=1))
    for d in res["decisions"][:args.show]:
        if d.get("verdict") == "fix":
            ch = {k: d[k] for k in ("name", "type", "semantic_type", "pattern") if d.get(k)}
            print(f"  FIX {d['field'][:34]:<34} {ch}  -- {d.get('reason', '')[:110]}")
        else:
            print(f"  ok  {d['field'][:34]:<34} -- {d.get('reason', '')[:110]}")
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
