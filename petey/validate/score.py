"""Score extraction output against LLM-generated ground truth.

Reads:
  - `.bpt` (canonical schema — per-field `widget` or `widgets` blocks).
  - Ground truth `{acroform_path: value}` from `generate_from_pdf()`.
  - Extraction output `{bpt_field: value}` from `extract.py` (including
    `_meta.dispatch_per_field`).

For each bpt field, normalize the ground-truth path-keyed values through
the .bpt's declared shape, then compare to the extracted value. Emit a
per-field verdict:

  * agree         — normalized ground truth equals extracted value.
  * differ        — both sides present but disagree.
  * extract_miss  — ground truth had a value; extract returned null.
  * gt_defect     — LLM's raw output violates the .bpt's declared shape
                    (e.g. two mutex checkboxes True, radio value not in
                    declared values enum). Not counted against extraction.

Each per-field record also carries `reached` from extract's per-widget
dispatch. It is TRI-STATE, and the distinction is load-bearing:

  * true   — extract's pipeline touched the widget.
  * false  — dispatch ran and every path ended in `missing`. Combined
             with an `agree` verdict, that's an `agree_by_absence`: the
             values match only because both are null.
  * null   — no dispatch instrumentation exists for this run at all.
             Says nothing about the field.

`null` is NOT `false`. Only `extract.py` emits a dispatch; the judge
(`judge:<parser>`, the meaning-based arm, which once shelled out to the
Petey CLI as `petey:<parser>`) does not. Collapsing the two made every
judge `agree` count as
`agree_by_absence` — a run where all 48 fields matched on real values
reported 45 matches "only because both are null." A perfect run and an
empty one were indistinguishable.

When a run is uninstrumented, `agree_confirmed_count` and
`agree_by_absence_count` are `null` rather than `0`, so a reader cannot
mistake absent instrumentation for a measured negative.

Plus one report-level count:

  * labeler_miss  — ground-truth paths not owned by any bpt field
                    (widget exists on the form, no bpt field represents
                    it). Signals labeler under-coverage.

Usage:
    python score.py --bpt <blueprint.bpt> --ground-truth <values.json> \\
        --extracted <extracted.json> --report <report.json>
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from petey.synth.boxes import widget_key

REACHED_PATHS = {"acroform", "text_clip", "ocr", "acroform_empty", "ink", "empty"}   # empty: the rect was reached, nothing in it (2026-10-19)


_FALSY_ANSWER = {"n", "no", "false", "0", "off", "/off"}     # as extract.FALSY_ANSWER


def _coerce_bool(v: Any, widget_type: Optional[str] = None) -> Optional[bool]:
    """Return True/False for standard truthy/falsy encodings, else None.

    Mirrors `extract._coerce_checkbox` exactly: bool passes through; None
    or empty/"Off" string → False; any other string → True. Includes
    export-value strings like "Yes"/"No"/"Married": on the extract side,
    reading such an on-state means the widget is checked, and the scorer
    must agree. This means when the LLM emits the raw export string on
    a boolean-typed field (e.g. the string "No" for a No checkbox with
    `export_value='No'`), the scorer treats it the same way `render_pdf`
    does — as "check the box" → True.
    """
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    if isinstance(v, str):
        s = v.strip().lower()
        if not s or s == "off":
            return False
        if widget_type not in (None, "checkbox", "radiobutton") and s in _FALSY_ANSWER:
            return False                    # a Y / N text box: "N" is an answer, not a ticked export value
        return True
    return None


# Sets aligned with what semantic_types.REGISTRY actually emits — plus
# legacy names still accepted for backwards compatibility with older bpts.
_DIGITS_ONLY = {
    "phone", "phone_number",
    "ssn", "ein", "tin", "itin", "npi", "naics",
    "routing_number", "account_number",
    "zip", "zip_cd", "postal_cd", "zipcode",
}
_MONEY = {
    "money", "money_whole_dollar", "money_amount",
    "amount", "dollar_amount", "currency",
}
_PERCENT = {"percent", "percentage", "rate"}
_STATE = {
    "state_abbr", "state_cd", "state_abbreviation_cd",
    "us_state", "country_code",
}
_LOWERCASE = {"email", "email_address", "url"}
_DATE = {"date", "iso_date", "birth_date", "service_date"}
_YEAR = {"year", "tax_year", "yyyy"}

# US state name → 2-letter code. Populated lazily to keep import cheap.
_STATE_NAME_TO_CODE = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT",
    "delaware": "DE", "district of columbia": "DC", "florida": "FL",
    "georgia": "GA", "hawaii": "HI", "idaho": "ID", "illinois": "IL",
    "indiana": "IN", "iowa": "IA", "kansas": "KS", "kentucky": "KY",
    "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT",
    "nebraska": "NE", "nevada": "NV", "new hampshire": "NH",
    "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH",
    "oklahoma": "OK", "oregon": "OR", "pennsylvania": "PA",
    "rhode island": "RI", "south carolina": "SC", "south dakota": "SD",
    "tennessee": "TN", "texas": "TX", "utah": "UT", "vermont": "VT",
    "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
    "puerto rico": "PR", "virgin islands": "VI", "guam": "GU",
    "american samoa": "AS", "northern mariana islands": "MP",
}


def _canonicalize(v: Any, semantic_type: Optional[str]) -> str:
    """Reduce a value to a canonical string per its declared semantic type.

    The scorer accepts messy inputs on both sides — LLM ground truth can
    write "Nevada" while extract reads "NV"; a text_clip can return
    "5\\n2\\n4" for what the LLM wrote as "524". Canonicalization is
    where format-only differences collapse.

    Default (no semantic_type or unknown): strip ALL whitespace
    (including internal newlines), lowercase. Kills the text_clip
    vertical-splitting class without needing an extract-side fix.
    """
    if v is None:
        return ""
    s = str(v).strip()
    if not s:
        return ""
    st = semantic_type
    if st in _DIGITS_ONLY:
        return re.sub(r"\D", "", s)
    if st in _MONEY:
        stripped = re.sub(r"[$,\s]", "", s)
        try:
            return f"{float(stripped):.2f}"
        except (ValueError, TypeError):
            return re.sub(r"\s+", "", s).lower()
    if st in _PERCENT:
        # "4%" and "0.04" collapse to the same canonical decimal.
        stripped = re.sub(r"[%,\s]", "", s)
        try:
            v = float(stripped)
            if v > 1.0:  # heuristic: probably percentage form (4 not 0.04)
                v = v / 100.0
            return f"{v:.6f}"
        except (ValueError, TypeError):
            return re.sub(r"\s+", "", s).lower()
    if st in _STATE:
        # Full state name → code; anything else → strip non-alnum,
        # uppercase, first 2 chars.
        low = s.strip().lower()
        if low in _STATE_NAME_TO_CODE:
            return _STATE_NAME_TO_CODE[low]
        return re.sub(r"\W", "", s).upper()[:2]
    if st in _LOWERCASE:
        return re.sub(r"\s+", "", s).lower()
    if st in _DATE:
        try:
            from dateutil import parser as _dp
            return _dp.parse(s, fuzzy=False).date().isoformat()
        except Exception:
            return re.sub(r"\s+", "", s).lower()
    if st in _YEAR:
        # 2-digit ↔ 4-digit collapse. `"25"` and `"2025"` compare equal.
        digits = re.sub(r"\D", "", s)
        if len(digits) == 2:
            return "20" + digits  # good for anything 2000-2099
        if len(digits) == 4:
            return digits
        return digits
    # Default: strip whitespace + template-ink chars, then lowercase.
    # Whitespace strip lets text_clip output like "5\n2\n4" compare
    # equal to "524" and "I\nL" to "IL". Template-ink strip (`,()[]{}_|`)
    # kills form-mask garnish that flatten bakes into the widget rect
    # alongside the value — e.g. text_clip on a PTAN widget reads
    # "( )\n( )\n1P47823690" where "( )" is the mask visible on the
    # blank form; stripping parens collapses to "1p47823690" which
    # matches gt "1P47823690". Chars stripped are ones that essentially
    # never appear inside a real field value.
    return re.sub(r"[\s,()\[\]{}_|]+", "", s).lower()


def _values_equal(
    a: Any, b: Any, field_type: str,
    semantic_type: Optional[str] = None,
) -> bool:
    """Compare with type-appropriate coercion + semantic canonicalization.

    For scalar fields with a `semantic_type`, both sides pass through
    `_canonicalize` first so formatting-only differences (phone with
    or without parens, money with or without $, etc.) don't produce
    false `differ` verdicts.
    """
    if field_type == "boolean":
        return _coerce_bool(a) == _coerce_bool(b)
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    if field_type == "multi_category":
        try:
            return sorted(a) == sorted(b)
        except TypeError:
            return a == b
    if field_type == "date":
        # Route through date canonicalization even when semantic_type
        # isn't set — labeler-typed `date` fields want ISO collapse too
        # (e.g. gt "03/15/1981" vs ex "1981-03-15").
        return _canonicalize(a, "date") == _canonicalize(b, "date")
    if field_type in ("integer", "number"):
        # Try direct float equality first; fall back to leading-number
        # parse to handle unit-suffixed inputs like '175 KGS' or '4.00%'
        # (class-8 labeler-mistyping cases where the widget holds a
        # unit-decorated numeric value).
        try:
            return float(a) == float(b)
        except (TypeError, ValueError):
            pass
        na = _parse_numeric(a)
        nb = _parse_numeric(b)
        if na is not None and nb is not None:
            return na == nb
        return _canonicalize(a, semantic_type) == _canonicalize(
            b, semantic_type
        )
    return _canonicalize(a, semantic_type) == _canonicalize(b, semantic_type)



def _option_selected(raw, w_block: dict) -> bool:
    """Is this option of a category field selected, given the ground-truth
    value stored at its path? Options that declare an `on_state` (one field,
    several kids: radio groups and checkbox fields with kids) are selected
    when the field holds that state; older per-field checkbox clusters keep
    the "path is checked" rule."""
    st = w_block.get("on_state")
    if st and not isinstance(raw, bool):
        # one field, several kids: the field holds the selected on-state
        if isinstance(raw, (list, tuple, set)):
            return st in {str(x) for x in raw}
        return raw not in (None, "", "Off") and str(raw) == str(st)
    # its own checkbox field (a labeler cluster): the generator writes a bool
    return _coerce_bool(raw) is True


def _normalize_ground_truth(
    field: dict, gt: dict[str, Any],
) -> tuple[Any, Optional[str]]:
    """Reduce path-keyed ground truth to the .bpt field's declared shape."""
    ftype = field.get("type", "string")

    if ftype == "category":
        allowed = field.get("values") or []
        widgets = field.get("widgets")
        if widgets:
            selected = [
                v for v, w_block in widgets.items()
                if _option_selected(gt.get(widget_key(w_block)), w_block)
            ]
            if len(selected) == 0:
                return None, None
            if len(selected) == 1:
                return selected[0], None
            return None, f"mutex_violation_{len(selected)}_true"
        widget = field.get("widget")
        if widget:
            raw = gt.get(widget_key(widget))
            if raw in (None, "", "Off"):
                return None, None
            if allowed and raw not in allowed:
                return None, f"value_not_in_enum_{raw!r}"
            return raw, None
        return None, "no_widget_block_on_category"

    if ftype == "multi_category":
        widgets = field.get("widgets") or {}
        selected = [
            v for v, w_block in widgets.items()
            if _option_selected(gt.get(widget_key(w_block)), w_block)
        ]
        return selected, None

    widget = field.get("widget")
    if not widget:
        return None, "no_widget_block"
    raw = gt.get(widget_key(widget))
    if ftype == "boolean":
        return _coerce_bool(raw, (widget.get("widget_type") or "text")), None
    return raw, None


def _bpt_owned_paths(bp: dict) -> set[str]:
    """Every ground-truth key (AcroForm path, or rect key on a flat blueprint) claimed by some field in the bpt."""
    paths: set[str] = set()
    for f in bp.get("fields", {}).values():
        w = f.get("widget")
        k = widget_key(w) if w else None
        if k:
            paths.add(k)
        for wb in (f.get("widgets") or {}).values():
            k = widget_key(wb)
            if k:
                paths.add(k)
    return paths


def _field_reached(dispatch_entry: Any) -> bool:
    """True if extract's pipeline touched a widget for this field."""
    if isinstance(dispatch_entry, str):
        return dispatch_entry in REACHED_PATHS
    if isinstance(dispatch_entry, dict):
        return any(p in REACHED_PATHS for p in dispatch_entry.values())
    return False


_LEADING_NUM_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*")


def _parse_numeric(v: Any) -> Optional[float]:
    """Parse a numeric value from raw input, handling unit suffix and %.

    Mirrors `extract._parse_leading_number` + percentage handling so both
    sides of a comparison collapse consistently. `'175 KGS'` → 175.0,
    `'4%'` → 0.04, `'1,200'` → 1200.0.
    """
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).replace(",", "").strip()
    if not s:
        return None
    if s.endswith("%"):
        try:
            return float(s[:-1].strip()) / 100.0
        except (ValueError, TypeError):
            return None
    try:
        return float(s)
    except (ValueError, TypeError):
        m = _LEADING_NUM_RE.match(s)
        if m:
            try:
                return float(m.group(1))
            except (ValueError, TypeError):
                return None
    return None


def _dispatch_is_ocr(dispatch_entry: Any) -> bool:
    """True if the field's extract path went through OCR."""
    if isinstance(dispatch_entry, str):
        return dispatch_entry == "ocr"
    if isinstance(dispatch_entry, dict):
        return "ocr" in dispatch_entry.values()
    return False


def _looks_like_ocr_noise(v: Any) -> bool:
    """True if `v` looks like OCR bleed on a legitimately-empty field.

    Heuristics: short (< 5 chars after stripping whitespace and common
    template-ink chars), OR mostly non-alphanumeric. Tesseract reads
    empty widget rects as garbage like 'BY', 'eee', 'P|} Jt dt di.'
    when the underlying value was truly blank. This lets the scorer
    collapse `gt='' ex=<noise>` to agree without touching extract.
    """
    if v is None:
        return True
    s = str(v)
    stripped = re.sub(r"[\s,()\[\]{}_|.\-]+", "", s)
    if len(stripped) < 5:
        return True
    alnum = sum(1 for c in s if c.isalnum())
    if len(s) > 0 and alnum / len(s) < 0.5:
        return True
    return False


def _is_set(v: Any, ftype: str) -> bool:
    """Does this field hold a value, for the purpose of a cross-field rule?"""
    if v is None or v == "" or v == [] or v == "Off":
        return False
    if ftype == "boolean":
        return bool(_coerce_bool(v))
    return True


def check_rules(bpt: dict, values: dict[str, Any]) -> list[dict]:
    """Evaluate the blueprint's cross-field rules against name-keyed values.

    Rules live under `rules:` (spec Appendix B, proposed) or `x_petey_rules`
    until then. Only `mutex` is implemented: at most one member may hold a
    value. Returns one record per violated rule. Needs no ground truth —
    the form's own logic is the referee (STRATEGY_v1 §3.6).
    """
    fields = bpt.get("fields", {})
    out: list[dict] = []
    for rule in bpt.get("rules") or bpt.get("x_petey_rules") or []:
        members = rule.get("mutex")
        if not members:
            continue
        held = [f for f in members
                if _is_set(values.get(f), fields.get(f, {}).get("type", "string"))]
        if len(held) > 1:
            out.append({
                "rule": rule,
                "held": held,
                "values": {f: values.get(f) for f in held},
            })
    return out


_DATE_SHAPES = re.compile(
    r"\d{8}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|\d{1,2}-\d{1,2}-\d{2,4}"
    r"|[A-Za-z]{3,9}\.? \d{1,2},? \d{4}|\d{1,2} [A-Za-z]{3,9}\.? \d{4}")
_NUMBER_SHAPE = re.compile(r"[-+(]?\s*\$?\s*[\d,]+(?:\.\d+)?\s*%?\)?")


def shape_mismatch(field: dict, value: Any) -> Optional[str]:
    """Why a label-grounded value contradicts what the field declares.

    The generator fills a box from the label printed next to it; the
    blueprint declares what it believes the box holds. Where the two
    disagree on SHAPE the blueprint is the usual suspect: a month box typed
    `date`, an SSN part typed as a whole SSN, an email box named as a
    street. Returns None when the value fits or there is nothing to test.
    """
    if value is None or value == "" or isinstance(value, bool):
        return None
    ftype = field.get("type", "string")
    s = str(value).strip()
    if not s:
        return None
    if ftype == "date":
        return None if _DATE_SHAPES.fullmatch(s) else "date_type_vs_value"
    if ftype in ("number", "integer"):
        return None if _NUMBER_SHAPE.fullmatch(s) else "number_type_vs_value"
    if ftype == "category":
        allowed = field.get("values") or []
        if allowed and s not in allowed:
            return "value_not_in_values"
        return None
    if ftype == "string":
        pat = field.get("pattern")
        if pat:
            try:
                if not re.fullmatch(pat, s):
                    return "pattern_vs_value"
            except re.error:
                return None
        st = field.get("semantic_type")
        if st in ("street_address", "name_and_address", "city", "person_name", "first_name",
                  "last_name", "entity_name", "business_name") and "@" in s:
            return "name_vs_value"
    return None


def score(
    bpt: dict,
    ground_truth: dict[str, Any],
    extracted: dict[str, Any],
    dispatch_per_field: Optional[dict[str, Any]] = None,
    unreached: Optional[set[str]] = None,
) -> dict:
    """Emit a per-field verdict report.

    `unreached` names the fields no synthetic box reached (the page finder
    found nothing at their rect, so the case never filled them). They get
    their own verdict, `not_generated`, and stay out of agreement: an empty
    ground truth against an empty extraction says nothing about the field.
    """
    fields = bpt.get("fields", {})
    unreached = unreached or set()
    gt_by_name: dict[str, Any] = {}
    shape_mismatches: dict[str, str] = {}
    dispatch = dispatch_per_field or {}
    # An empty/absent dispatch means this method emits none at all, not
    # that every field was missed. See the tri-state note in the module
    # docstring.
    instrumented = bool(dispatch)
    per_field: list[dict] = []
    verdicts = {"agree": 0, "differ": 0, "extract_miss": 0, "gt_defect": 0, "not_generated": 0}
    agree_confirmed = 0
    agree_by_absence = 0

    for name, field in fields.items():
        ftype = field.get("type", "string")
        gt_value, defect = _normalize_ground_truth(field, ground_truth)
        gt_by_name[name] = gt_value
        mismatch = shape_mismatch(field, gt_value)
        if mismatch:
            shape_mismatches[name] = mismatch
        ex_value = extracted.get(name)
        dispatch_entry = dispatch.get(name)
        reached = _field_reached(dispatch_entry) if instrumented else None

        gt_absent = gt_value in (None, "") or (
            ftype == "boolean" and _coerce_bool(gt_value) is False
        ) or (ftype == "multi_category" and not gt_value)
        ex_absent = ex_value in (None, "") or (
            ftype == "boolean" and _coerce_bool(ex_value) is False
        ) or (ftype == "multi_category" and not ex_value)

        if name in unreached and gt_absent:
            verdict = "not_generated"
        elif defect is not None:
            verdict = "gt_defect"
        elif gt_absent and ex_absent:
            verdict = "agree"
        elif _values_equal(
            gt_value, ex_value, ftype,
            semantic_type=field.get("semantic_type"),
        ):
            verdict = "agree"
        elif (
            gt_absent
            and ftype == "string"
            and _dispatch_is_ocr(dispatch_entry)
            and _looks_like_ocr_noise(ex_value)
        ):
            # Class 6: LLM correctly emitted blank for an optional field
            # (foreign address on a domestic filing, etc.); OCR read
            # noise from the empty rect. Collapse to agree so noisy
            # OCR bleed doesn't count against extract.
            verdict = "agree"
        elif ex_absent:
            verdict = "extract_miss"
        else:
            verdict = "differ"

        verdicts[verdict] += 1
        if verdict == "agree" and reached is not None:
            if reached:
                agree_confirmed += 1
            else:
                agree_by_absence += 1
        per_field.append({
            "field": name,
            "type": ftype,
            "verdict": verdict,
            "shape_mismatch": mismatch,
            "reached": reached,
            "gt_value": gt_value,
            "extracted_value": ex_value,
            "dispatch": dispatch_entry,
            "defect": defect,
        })

    owned = _bpt_owned_paths(bpt)
    labeler_miss_paths = [
        p for p, v in ground_truth.items()
        if p not in owned
        and v is not None
        and v not in ("", "Off", False)
    ]

    # Cross-field rules: a violated rule on the extracted side is its own
    # verdict; on the ground-truth side it means the generator broke the
    # form's logic (a defective case, not an extraction fault).
    ex_violations = check_rules(bpt, extracted)
    gt_violations = check_rules(bpt, gt_by_name)
    verdicts["rule_violation"] = len(ex_violations)
    # Ground truth vs declaration: a label-grounded value the blueprint's
    # own type/pattern rejects is a blueprint defect surfaced at generation
    # time, independent of extraction. Counted beside the verdicts, not
    # among them — the same field also gets agree/differ/miss.
    verdicts["gt_shape_mismatch"] = len(shape_mismatches)

    return {
        "verdicts": verdicts,
        "rule_violations": ex_violations,
        "gt_rule_violations": gt_violations,
        "gt_shape_mismatches": shape_mismatches,
        "agree_confirmed_count": agree_confirmed if instrumented else None,
        "agree_by_absence_count": agree_by_absence if instrumented else None,
        "labeler_miss_count": len(labeler_miss_paths),
        "labeler_miss_paths": labeler_miss_paths,
        "per_field": per_field,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--bpt", required=True, type=Path)
    ap.add_argument("--ground-truth", required=True, type=Path)
    ap.add_argument("--extracted", required=True, type=Path)
    ap.add_argument("--report", type=Path, default=None)
    args = ap.parse_args()

    bp = yaml.safe_load(args.bpt.read_text(encoding="utf-8"))
    gt = json.loads(args.ground_truth.read_text(encoding="utf-8"))
    ex = json.loads(args.extracted.read_text(encoding="utf-8"))
    meta = ex.pop("_meta", {}) or {}
    dispatch = meta.get("dispatch_per_field") or {}

    report = score(bp, gt, ex, dispatch_per_field=dispatch)
    v = report["verdicts"]
    total = sum(v.values())
    conf = report["agree_confirmed_count"]
    absent = report["agree_by_absence_count"]
    breakdown = ("uninstrumented" if conf is None
                 else f"confirmed={conf}, by_absence={absent}")
    print(
        f"[score] agree={v['agree']}/{total} ({breakdown}) "
        f"differ={v['differ']} extract_miss={v['extract_miss']} "
        f"gt_defect={v['gt_defect']} "
        f"labeler_miss_paths={report['labeler_miss_count']}"
    )

    out = args.report or args.extracted.with_name(
        args.extracted.stem + "_score.json"
    )
    out.write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    print(f"[ok] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
