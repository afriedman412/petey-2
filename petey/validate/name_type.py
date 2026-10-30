"""Rule checks on a field's name and type against each other and against the publisher's instructions.

Andrew, 2026-10-07, ACORD 126 page 2: `contractor_draw_plans_designs_specs_ind` is a one-letter text box the filer
types Y or N into ("Enter Y for a 'Yes' response. Input N for 'No' response"), typed `string` although its name
says indicator; every check passed it. Two rules, no model:

    yn_text      a text widget answered with Y / N (the tooltip or description says to enter Y / N, or the box takes
                 one character and the text names Y and N) that is not `boolean`. The spec's boolean reader turns Y / N
                 into true / false, and N stays distinct from blank. Graded an error; suggested type boolean.
    suffix_type  the name's suffix says one type and the field has another: `_ind` not boolean, `_dt` not date,
                 `_amt` not a number, `_cnt` / `_count` not an integer. A suggestion, not an error: some are
                 legitimate (`vehicle_1_lease_dt` is MM/YYYY, which a date cannot hold), others are misnamed.

Used by the review page (`witness.witnesses` -> `explain`) and by `eval/name_type_sweep.py`.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

YN_TEXT = re.compile(r"\b(enter|input|type)\s+[\"“']?y[\"”']?\b.*\byes\b|\binput\s+[\"“']?n[\"”']?\s+for\b|\bY\s*/\s*N\b",
                     re.I)
SUFFIX = [(r"_ind$", ("boolean",), "an indicator (yes/no)"), (r"_dt$", ("date",), "a date"),
          (r"_amt$", ("number", "integer"), "an amount"), (r"_(cnt|count)$", ("integer", "number"), "a count")]


from petey.validate.witness import _by_file  # noqa: E402  (memo per blank)


@_by_file
def text_maxlens(blank: Optional[Path]) -> dict[str, int]:
    """{path: MaxLen} for the blank's text widgets (0 when unset)."""
    if not blank or not Path(blank).exists():
        return {}
    import pymupdf
    out = {}
    with pymupdf.open(str(blank)) as doc:
        for pg in doc:
            for w in pg.widgets() or []:
                if w.field_type_string == "Text":
                    out[w.field_name] = w.text_maxlen or 0
    return out


# words that say where a field is, not what it holds: a name made of these and numbers is only an item number
_PLACE_WORDS = {"item", "items", "line", "lines", "question", "q", "part", "pt", "box", "field", "text", "txt", "check",
                "checkbox", "cb", "number", "num", "nbr", "no", "page", "pg", "p", "row", "col", "column", "section",
                "sec", "ind", "amt", "cd", "dt", "nm", "yes", "y", "n", "form", "entry", "blank", "group", "option"}
_ITEM_ID = re.compile(r"^(\d+[a-z]{0,2}|[a-z]\d+[a-z]?|[ivx]+)$")


def bare_number(name: str) -> bool:
    """The name says only where the field is, not what it holds: `item_43f`, `line_12_amt`, `q5`, `field_3`
    (Andrew, 2026-10-14: I-485 `item_43f`)."""
    # a field that holds a page / part / item number (continuation boxes, DD 1155's Item No.) says what it holds
    if re.search(r"(^|_)(page|part|item|line|row|question|section|box)_(number|nbr|no|num)(_|$)", name.lower()):
        return False
    toks = [t for t in name.lower().split("_") if t]
    rest = [t for t in toks if t not in _PLACE_WORDS]
    return bool(toks) and all(_ITEM_ID.match(t) for t in rest) and any(re.search(r"\d", t) for t in toks)


def check(name: str, spec: dict, maxlen: Optional[int] = None) -> list[dict]:
    """[{rule, grade, text, fix}] for one field. Option groups get only the item-number rule (their type is the
    group's)."""
    if not isinstance(spec, dict):
        return []
    bare = [{"rule": "bare_number", "grade": "error",
             "text": f"The name `{name}` is only an item number: it should say what the field holds "
                     f"(\"improve name\" asks for one)."}] if bare_number(name) else []
    if spec.get("widgets"):
        return bare
    out = _desc_conflict(name, spec)
    return bare + out + [r for r in _check(name, spec, maxlen) if not out or r["rule"] != "suffix_type"]


def _desc_conflict(name: str, spec: dict) -> list[dict]:
    """The description says the box holds a count / amount / percentage and the field disagrees (2026-10-07,
    Andrew: the description can be as wrong as the name, so a person decides)."""
    from petey.validate.retype import desc_kind, desc_type_conflict
    why = desc_type_conflict(name, spec)
    if not why:
        return []
    kind = desc_kind(spec)[0]
    d = (spec.get("description") or "")[:70]
    return [{"rule": "desc_type", "grade": "error", "text": f"The description says this holds {'a ' + kind if kind != 'amount' else 'an amount'} "
             f"(\"{d}…\") but {why}: the description, the name or the type is wrong."}]


def _check(name: str, spec: dict, maxlen: Optional[int] = None) -> list[dict]:
    typ = spec.get("type")
    w = spec.get("widget") or {}
    text = spec.get("description") or ""
    is_text = (w.get("widget_type") or "text") == "text"
    # a Y/N text box is a string with ^[YN]$ (Andrew, 2026-10-07: his ACORD 126 notes, then every ACORD Y/N box)
    if (is_text and not (typ == "string" and spec.get("pattern") == r"^[YN]$")
            and (YN_TEXT.search(text) or (maxlen == 1 and re.search(r"\bY\b.*\bN\b", text)))):
        return [{"rule": "yn_text", "grade": "error", "fix": {"type": "string", "pattern": r"^[YN]$"},
                 "text": f"Type: the filer types Y or N here (\"{text[:60]}…\"), so a string with pattern ^[YN]$; "
                         f"it is {typ}{' with pattern ' + spec['pattern'] if spec.get('pattern') else ''}."}]
    for pat, ok, what in SUFFIX:
        if pat == r"_ind$" and typ == "string" and spec.get("pattern") == r"^[YN]$":
            continue                                    # a Y/N box: an indicator answered Y or N
        if re.search(pat, name) and typ not in ok:
            return [{"rule": "suffix_type", "grade": "suggestion", "fix": {"type": ok[0]},
                     "text": f"The name ends `{re.search(pat, name).group(0)}` ({what}) but the field is typed {typ}: "
                             f"either the type or the name is off."}]
    return []
