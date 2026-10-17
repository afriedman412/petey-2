"""S1 — shape agreement between a blueprint's semantic layer and generated
ground truth.

The eval loop (label → generate → fill → extract → score) cannot tell you
whether a *blueprint* is correct: the generator places values by AcroForm
path and the deterministic extractor reads them back by AcroForm path, so a
wrong field name cancels on both sides and scores as `agree`.

S1 breaks that symmetry without any extraction at all. The labeler assigned
each widget a `semantic_type`; the generator, reading the same blank form
through a different modality and blind to the `.bpt`, chose a value for that
same widget. Join the two through `widget.path` and ask: **is the value the
generator chose the kind of thing the labeler said lives there?**

Disagreement means the two independent reads of the document disagree about
what the field is. That is the signal. It does not by itself say which side
is wrong — see "Interpreting a mismatch" below.

Runs entirely offline over ground truth already on disk. No fill, no
extraction, no scoring, no API calls.

## Class comparison, not pattern matching

A field's `pattern` describes Petey's *canonical extracted output*
(`^\\d{4}-\\d{2}-\\d{2}$` for `iso_date`). The generator deliberately emits
*document-realistic input* — `01/01/2025` as a filer would write it, money
with thousands separators. Testing ground-truth values against `pattern`
would flag every correctly-labeled date on the form.

So S1 compares **semantic class**: `01/01/2025` and `2025-01-01` are both
class `DATE`, and a field labeled `iso_date` holding either agrees. Literal
`pattern` conformance is reported separately as a secondary, advisory
number — informative about generator realism, not about blueprint
correctness.

## What it catches, and what it cannot

Catches cross-class confusion — a `money_whole_dollar` field holding a date,
an `iso_date` field holding a bare `2025` (OBSERVATIONS Class 3), an
IRS-family semantic applied to a non-IRS widget (Class 8b), a `city` field
over-filled with a full street address (Class 5).

Blind to within-class confusion: `wages_amt` vs `tips_amt` are both MONEY
and both agree here. Distinguishing those needs meaning, not shape — that is
S2's job.

Free-text semantics (`person_name`, `city`, `street_address`, `description`,
`text`, ...) are mutually indistinguishable by shape and collapse into one
TEXT class. Mismatches *within* TEXT are therefore not reported, except for
the targeted over-fill checks noted above.

Usage:
    python shape_agree.py                        # whole corpus
    python shape_agree.py --form fw9 --verbose
    python shape_agree.py --out runs/s1_report.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from petey.paths import RUNS, BLUEPRINTS
HERE = Path(__file__).resolve().parent


# --------------------------------------------------------------------------
# Value → observed class
# --------------------------------------------------------------------------

# Ordered: the first matching rule wins, so more specific shapes come first.
# These describe how a value *looks*, independent of what any blueprint
# claims about it.
_MONEY_RE = re.compile(r"^-?\$?\s?\d{1,3}(,\d{3})*(\.\d{1,2})?$|^-?\$?\s?\d+(\.\d{1,2})?$")
_DATE_SEPS = re.compile(
    r"^\d{4}-\d{1,2}-\d{1,2}$"          # 2025-01-31
    r"|^\d{1,2}[/-]\d{1,2}[/-]\d{4}$"   # 01/31/2025
    r"|^\d{1,2}[/-]\d{1,2}[/-]\d{2}$"   # 01/31/25
    r"|^\d{8}$"                          # 20250131 (handled below)
)
_MONTH_NAME = re.compile(
    r"^\d{0,2}\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
    r"\s*\d{0,2},?\s*\d{2,4}$",
    re.I,
)


_LINE_MARKER = re.compile(r"^[A-Z]\.\s+(?=[\d$])")
_UNIT_SUFFIX = re.compile(r"^([\d,.]+)\s+[A-Z]{2,4}$")


def normalize_value(v: Any) -> Any:
    """Strip document-realistic noise the generator legitimately emits.

    The generator writes what a filer would actually put on the page:
    `A. 18750` against a lettered line, `390 NO` for a quantity with its
    HTSUS unit, `2425|00` where the form prints a ruled cents column. None
    of those is a blueprint defect — they are the messy *input* side, and
    the blueprint's `pattern` describes canonical *output*. Treating them
    as disagreements blames the labeler for the generator being realistic.

    Conservative on purpose: the unit-suffix rule only fires when what
    remains is numeric, so `Seattle WA` is untouched and a genuine
    overfill still surfaces.
    """
    if not isinstance(v, str):
        return v
    s = v.strip()
    s = _LINE_MARKER.sub("", s)
    m = _UNIT_SUFFIX.match(s)
    if m:
        s = m.group(1)
    if re.fullmatch(r"[\d,]+\|\d{2}", s):     # ruled cents column
        s = s.replace("|", ".")
    return s


def observed_classes(v: Any) -> set[str]:
    """Every class a ground-truth value could plausibly belong to.

    Returns a SET, not one class, because raw form values are frequently
    ambiguous on shape alone: `14250` is an equally good ZIP code, dollar
    amount, and unit count, and nothing about the string decides between
    them. Committing to a single guess manufactures disagreements — an
    early build of this check reported 1,212 "money field holds a ZIP"
    mismatches that were all just five-digit dollar amounts.

    A field is only counted as mismatched when the declared semantic
    admits *none* of the plausible classes, so ambiguity resolves in the
    blueprint's favour and what survives is a real conflict.
    """
    if isinstance(v, bool):
        return {"BOOLEAN"}
    if v is None:
        return {"EMPTY"}
    if isinstance(v, (int, float)):
        out = {"NUMBER", "MONEY", "COUNT"}
        if float(v).is_integer() and 1900 <= v <= 2100:
            out.add("YEAR")
        return out

    s = str(normalize_value(v)).strip()
    if not s:
        return {"EMPTY"}
    if s.lower() in {"true", "false", "yes", "no", "on", "off", "x", "y", "n"}:
        return {"BOOLEAN", "TEXT"}

    if "@" in s and re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", s):
        return {"EMAIL"}

    # Formatted shapes — a separator is positive evidence, so these are
    # unambiguous enough to return on their own.
    if (_MONTH_NAME.fullmatch(s)
            or re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", s)
            or re.fullmatch(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", s)):
        return {"DATE"}
    if re.fullmatch(r"\d{3}-\d{2}-\d{4}", s):
        return {"SSN", "TIN", "DIGITS"}
    if re.fullmatch(r"\d{2}-\d{7}", s):
        return {"EIN", "TIN", "DIGITS"}
    if re.fullmatch(r"\d{5}-\d{4}", s):
        return {"ZIP", "DIGITS"}
    if re.fullmatch(r"\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}", s):
        return {"PHONE", "DIGITS"}
    if s.endswith("%") or re.fullmatch(r"\d{1,3}\.\d+%", s):
        return {"PERCENT", "NUMBER"}

    # Bare digit runs: ambiguous by construction. Admit every reading the
    # length permits.
    if re.fullmatch(r"\d+", s):
        out = {"NUMBER", "DIGITS", "MONEY", "COUNT"}
        n = len(s)
        if n == 4 and 1900 <= int(s) <= 2100:
            out.add("YEAR")
        if n == 5:
            out.add("ZIP")
        if n == 9:
            out |= {"SSN", "EIN", "TIN", "ZIP"}
        if n == 10:
            out |= {"PHONE", "NPI"}
        if n == 6:
            out.add("NAICS")
        return out

    # Quantity with separators / currency marks.
    if _MONEY_RE.fullmatch(s):
        return {"MONEY", "NUMBER", "COUNT"}

    if re.fullmatch(r"[A-Z]{2}", s):
        return {"STATE2", "TEXT"}
    if re.fullmatch(r"[\d\s().+-]{7,}", s):
        return {"DIGITS", "NUMBER", "PHONE"}
    return {"TEXT"}


def primary_class(classes: set[str]) -> str:
    """The most specific plausible class, for human-readable reporting."""
    for c in ("EMPTY", "BOOLEAN", "EMAIL", "DATE", "SSN", "EIN", "PHONE",
              "ZIP", "PERCENT", "YEAR", "STATE2", "MONEY", "NAICS", "NPI",
              "DIGITS", "NUMBER", "COUNT", "TEXT"):
        if c in classes:
            return c
    return "TEXT"


# --------------------------------------------------------------------------
# semantic_type → the classes that agree with it
# --------------------------------------------------------------------------

_NUMERIC_OK = {"MONEY", "NUMBER", "DIGITS", "COUNT", "PERCENT", "YEAR"}

# Each entry lists the classes that AGREE with the declared semantic. A
# mismatch requires the value's plausible-class set to intersect none of
# them.
EXPECTED: dict[str, set[str]] = {
    "ssn": {"SSN", "TIN", "DIGITS", "NUMBER"},
    "ein": {"EIN", "TIN", "DIGITS", "NUMBER"},
    "itin": {"SSN", "TIN", "DIGITS", "NUMBER"},
    "tin": {"SSN", "EIN", "TIN", "DIGITS", "NUMBER"},
    "npi": {"NPI", "DIGITS", "NUMBER"},
    "routing_number": {"DIGITS", "NUMBER"},
    "account_number": {"DIGITS", "NUMBER", "TEXT"},
    "naics": {"NAICS", "DIGITS", "NUMBER"},
    "money_whole_dollar": _NUMERIC_OK,
    "money": _NUMERIC_OK,
    "percent": {"PERCENT", "NUMBER", "MONEY", "COUNT"},
    "count": {"NUMBER", "DIGITS", "COUNT", "YEAR"},
    # YEAR is deliberately NOT accepted for a full date: a bare `2025` in a
    # date-typed field is OBSERVATIONS Class 3 (partial identifiers such as
    # `_year` / `_begin_dt` mistyped as `date`), which is exactly what this
    # check exists to surface.
    "iso_date": {"DATE"},
    "birth_date": {"DATE"},
    "service_date": {"DATE"},
    "year": {"YEAR", "NUMBER", "DATE", "COUNT", "DIGITS"},
    "phone": {"PHONE", "DIGITS", "NUMBER"},
    "email": {"EMAIL"},
    "zip": {"ZIP", "DIGITS", "NUMBER"},
    "state_abbr": {"STATE2"},
    "country_code": {"STATE2", "TEXT"},
    "indicator": {"BOOLEAN"},
}

# Classes a free-text semantic will accept. Wide by design: a name, a city
# and a street address are not separable by shape, and numbers legitimately
# appear inside all of them.
TEXT_EXPECTED_CLASSES = {"TEXT", "STATE2", "NUMBER", "DIGITS", "ZIP",
                         "COUNT", "MONEY", "YEAR"}

# Free-text semantics: mutually indistinguishable by shape.
TEXT_SEMANTICS = {
    "country", "city", "street_address", "name_and_address", "person_name", "first_name",
    "last_name", "entity_name", "business_name", "description", "text",
}

# A `type` with no `semantic_type` still constrains shape a little.
TYPE_EXPECTED: dict[str, set[str]] = {
    "boolean": {"BOOLEAN"},
    "number": _NUMERIC_OK,
    "integer": _NUMERIC_OK,
    "date": {"DATE", "YEAR"},
}


# --------------------------------------------------------------------------
# Targeted within-TEXT checks (OBSERVATIONS Class 5 and kin)
# --------------------------------------------------------------------------

_ZIP_IN = re.compile(r"\b\d{5}(-\d{4})?\b")
_STREET = re.compile(
    r"\b\d+\s+\w+|\b(street|st|avenue|ave|road|rd|blvd|boulevard|lane|ln|"
    r"drive|dr|suite|ste|apt|p\.?o\.?\s*box)\b",
    re.I,
)


def overfill_flag(semantic: str, s: str) -> Optional[str]:
    """Detect a free-text field holding more than it should.

    The generator has been observed writing a whole address into a `city`
    widget (OBSERVATIONS Class 5). That corrupts ground truth, so it needs
    surfacing even though both sides are class TEXT.
    """
    if semantic == "city":
        if _ZIP_IN.search(s) or "," in s or _STREET.search(s):
            return "city_holds_full_address"
        if len(s.split()) > 4:
            return "city_too_many_tokens"
    if semantic == "state_abbr" and len(s) > 2:
        return "state_abbr_not_abbreviated"
    if semantic in {"first_name", "last_name"} and len(s.split()) > 2:
        return "name_part_holds_full_name"
    return None


# --------------------------------------------------------------------------
# Blueprint indexing
# --------------------------------------------------------------------------

def index_by_path(bp: dict) -> dict[str, tuple[str, dict]]:
    """Map AcroForm path → (field_name, field_spec).

    Covers both `widget` (one widget) and `widgets` (a category's
    value → widget map). Fields whose widget has a null path — the
    vision-labeled flat-PDF blueprints — cannot be joined and are skipped.
    """
    out: dict[str, tuple[str, dict]] = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        w = spec.get("widget")
        if isinstance(w, dict) and w.get("path"):
            out.setdefault(str(w["path"]), (name, spec))
        for wb in (spec.get("widgets") or {}).values():
            if isinstance(wb, dict) and wb.get("path"):
                out.setdefault(str(wb["path"]), (name, spec))
    return out


def declared_semantic(spec: dict) -> Optional[str]:
    st = spec.get("semantic_type")
    return str(st) if st else None


# --------------------------------------------------------------------------
# Core check
# --------------------------------------------------------------------------

def check_case(
    bp_index: dict[str, tuple[str, dict]], gt: dict,
) -> list[dict]:
    """Compare one generated case against the blueprint's semantic layer."""
    rows: list[dict] = []
    for path, value in gt.items():
        hit = bp_index.get(str(path))
        if hit is None:
            rows.append({
                "verdict": "unjoined", "path": path,
                "field": None, "semantic_type": None,
                "observed": primary_class(observed_classes(value)),
                "value": value,
            })
            continue
        field, spec = hit
        classes = observed_classes(value)
        obs = primary_class(classes)
        sem = declared_semantic(spec)
        row = {
            "path": path, "field": field, "semantic_type": sem,
            "type": spec.get("type"), "observed": obs, "value": value,
        }

        if "EMPTY" in classes:
            row["verdict"] = "empty"
            rows.append(row)
            continue

        # An `indicator`/boolean widget the generator filled with prose is a
        # real disagreement, so booleans are checked like anything else.
        if sem in TEXT_SEMANTICS:
            flag = overfill_flag(sem, str(value))
            if flag:
                row["verdict"] = "overfill"
                row["reason"] = flag
            elif classes & TEXT_EXPECTED_CLASSES:
                row["verdict"] = "ok"
            else:
                row["verdict"] = "mismatch"
                row["reason"] = f"{sem} holds {obs}"
            rows.append(row)
            continue

        allowed = EXPECTED.get(sem) if sem else None
        if allowed is None:
            allowed = TYPE_EXPECTED.get(str(spec.get("type")))
        if allowed is None:
            row["verdict"] = "unconstrained"
        elif classes & allowed:
            row["verdict"] = "ok"
        else:
            row["verdict"] = "mismatch"
            row["reason"] = f"{sem or spec.get('type')} holds {obs}"
        rows.append(row)
    return rows


def pattern_conformance(rows: list[dict], bp_index) -> tuple[int, int]:
    """Secondary: how often a value literally satisfies the field `pattern`.

    Advisory only — a low number means the generator writes realistic
    document input rather than canonical output, which is by design.
    """
    ok = tot = 0
    for r in rows:
        if r["verdict"] in {"unjoined", "empty"}:
            continue
        hit = bp_index.get(str(r["path"]))
        if not hit:
            continue
        pat = hit[1].get("pattern")
        if not pat:
            continue
        tot += 1
        try:
            if re.fullmatch(pat, str(r["value"])):
                ok += 1
        except re.error:
            tot -= 1
    return ok, tot


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------

def form_id_from_run(run_dir: Path) -> str:
    """`runs/fw9_20260908_152003` → `fw9`."""
    return re.sub(r"_\d{8}_\d{6}$", "", run_dir.name)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--blueprints", type=Path, default=BLUEPRINTS)
    ap.add_argument("--form", type=str, default=None,
                    help="restrict to one form id")
    ap.add_argument("--out", type=Path, default=None,
                    help="write the full JSON report here")
    ap.add_argument("--verbose", action="store_true",
                    help="print every mismatch, not just the summary")
    ap.add_argument("--top", type=int, default=25,
                    help="how many mismatch clusters to print")
    args = ap.parse_args()

    gt_files = sorted(args.runs.glob("*/case_*/ground_truth.json"))
    if not gt_files:
        print(f"no ground truth under {args.runs}")
        return 1

    bp_cache: dict[str, Optional[dict]] = {}

    def blueprint_for(form: str) -> Optional[dict]:
        if form not in bp_cache:
            p = args.blueprints / f"{form}.bpt"
            bp_cache[form] = (
                yaml.safe_load(p.read_text(encoding="utf-8"))
                if p.exists() else None
            )
        return bp_cache[form]

    verdicts = collections.Counter()
    clusters = collections.Counter()
    per_form: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    # Dedup: the same (form, field) recurs across every case of that form.
    seen_field_issue: set[tuple] = set()
    examples: dict[str, list] = collections.defaultdict(list)
    detail: list[dict] = []
    pat_ok = pat_tot = 0
    missing_bp: set[str] = set()
    forms_seen: set[str] = set()

    for gt_path in gt_files:
        form = form_id_from_run(gt_path.parent.parent)
        if args.form and form != args.form:
            continue
        bp = blueprint_for(form)
        if bp is None:
            missing_bp.add(form)
            continue
        forms_seen.add(form)
        try:
            gt = json.loads(gt_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(gt, dict):
            continue

        idx = index_by_path(bp)
        rows = check_case(idx, gt)
        o, t = pattern_conformance(rows, idx)
        pat_ok += o
        pat_tot += t

        for r in rows:
            verdicts[r["verdict"]] += 1
            per_form[form][r["verdict"]] += 1
            if r["verdict"] in {"mismatch", "overfill"}:
                key = (form, r["field"], r.get("reason"))
                if key in seen_field_issue:
                    continue
                seen_field_issue.add(key)
                reason = r.get("reason", "?")
                clusters[reason] += 1
                if len(examples[reason]) < 6:
                    examples[reason].append(
                        f"{form}:{r['field']} = {r['value']!r}"
                    )
                detail.append({"form": form, **r})

    total = sum(verdicts.values())
    if not total:
        print("no joinable cases found")
        return 1

    joined = total - verdicts["unjoined"]
    print("=" * 72)
    print("S1 — SHAPE AGREEMENT (blueprint semantic layer vs generated "
          "ground truth)")
    print("=" * 72)
    print(f"forms: {len(forms_seen)}   cases: {len(gt_files)}   "
          f"field-observations: {total}")
    if missing_bp:
        print(f"skipped (no blueprint): {len(missing_bp)} forms — "
              f"{', '.join(sorted(missing_bp)[:8])}")
    print()
    print(f"  {'verdict':<16} {'count':>8}   {'% of joined':>11}")
    for v in ("ok", "mismatch", "overfill", "unconstrained", "empty",
              "unjoined"):
        c = verdicts[v]
        pct = f"{c / joined:6.1%}" if joined and v != "unjoined" else "     —"
        print(f"  {v:<16} {c:>8}   {pct:>11}")

    print()
    print(f"  distinct (form, field, reason) issues: "
          f"{len(seen_field_issue)}")
    if pat_tot:
        print(f"  literal `pattern` conformance (advisory): "
              f"{pat_ok}/{pat_tot} = {pat_ok / pat_tot:.1%}")

    if clusters:
        print()
        print("-" * 72)
        print(f"MISMATCH CLUSTERS (deduped per form+field), top {args.top}")
        print("-" * 72)
        for reason, c in clusters.most_common(args.top):
            print(f"\n  [{c:>4}]  {reason}")
            for e in examples[reason]:
                print(f"          {e}")

    worst = sorted(
        per_form.items(),
        key=lambda kv: -(kv[1]["mismatch"] + kv[1]["overfill"]),
    )[:15]
    print()
    print("-" * 72)
    print("WORST FORMS by mismatch+overfill observations")
    print("-" * 72)
    print(f"  {'form':<16} {'mismatch':>9} {'overfill':>9} {'ok':>8} "
          f"{'unjoined':>9}")
    for form, c in worst:
        if not (c["mismatch"] or c["overfill"]):
            continue
        print(f"  {form:<16} {c['mismatch']:>9} {c['overfill']:>9} "
              f"{c['ok']:>8} {c['unjoined']:>9}")

    if args.verbose:
        print()
        print("-" * 72)
        print("EVERY DISTINCT ISSUE")
        print("-" * 72)
        for d in sorted(detail, key=lambda d: (d["form"], str(d["field"]))):
            print(f"  {d['form']:<14} {str(d['field']):<34} "
                  f"{str(d.get('reason')):<34} {d['value']!r}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({
            "forms": sorted(forms_seen),
            "n_cases": len(gt_files),
            "verdicts": dict(verdicts),
            "clusters": dict(clusters),
            "pattern_conformance": {"ok": pat_ok, "total": pat_tot},
            "per_form": {k: dict(v) for k, v in per_form.items()},
            "issues": detail,
        }, indent=2, default=str))
        print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
