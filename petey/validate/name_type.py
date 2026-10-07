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


def check(name: str, spec: dict, maxlen: Optional[int] = None) -> list[dict]:
    """[{rule, grade, text, fix}] for one field; option groups are skipped (their type is the group's)."""
    if not isinstance(spec, dict) or spec.get("widgets"):
        return []
    typ = spec.get("type")
    w = spec.get("widget") or {}
    text = spec.get("description") or ""
    is_text = (w.get("widget_type") or "text") == "text"
    if is_text and typ != "boolean" and (YN_TEXT.search(text) or (maxlen == 1 and re.search(r"\bY\b.*\bN\b", text))):
        return [{"rule": "yn_text", "grade": "error", "fix": {"type": "boolean"},
                 "text": f"Type: the filer types Y or N here (\"{text[:60]}…\"), a yes/no answer, but it is typed {typ}."}]
    for pat, ok, what in SUFFIX:
        if re.search(pat, name) and typ not in ok:
            return [{"rule": "suffix_type", "grade": "suggestion", "fix": {"type": ok[0]},
                     "text": f"The name ends `{re.search(pat, name).group(0)}` ({what}) but the field is typed {typ}: "
                             f"either the type or the name is off."}]
    return []
