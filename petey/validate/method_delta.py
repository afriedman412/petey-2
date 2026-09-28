"""The fields where the blind method agrees and the meaning-based one does not.

`native` reads each value back through the same AcroForm path the generator
wrote it by, so a mislabeled field cancels on both sides and scores `agree`.
`petey:<parser>` never sees the widget layer and has to find each value by
name. Their disagreement set is therefore the candidate-defect list, and it
costs nothing beyond a validate run that already happened.

## Reading a row

Three values per field, and the relationship between them is the diagnosis:

    gt      what the generator intended to put at path P
    native  what is actually readable at path P
    petey   what petey found on the page when it went looking for this NAME

  gt == native != petey
      The value is where it was put. Something about the NAME sent petey
      elsewhere — the blueprint's label, or a neighbouring field that
      matches the name better. This is the blueprint-defect shape.

  gt != native
      The generator and the document already disagree before naming enters
      it. Fill-side or extract-side; not evidence about the label.

  petey == some OTHER field's gt
      A swap. Reported explicitly as `swap_with`, since a reciprocal pair
      is one defect and itemising it twice invites two uncoordinated fixes.

Flat-only disagreements are marked: a defect that appears only after
flattening is more likely extraction difficulty than a wrong name, because
the name did not change when the widgets were baked.

Local, free, no API. Pure post-processing over `runs/<form>_<stamp>/`.

Usage:
    python method_delta.py
    python method_delta.py --form cbp_form_3299_0 --verbose
    python method_delta.py --out runs/method_delta.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

from petey.paths import RUNS
HERE = Path(__file__).resolve().parent

BLIND = "native"


def _load(case_dir: Path, method: str) -> dict[str, dict]:
    p = case_dir / f"score_{method}.json"
    if not p.exists():
        return {}
    try:
        rep = json.loads(p.read_text())
    except json.JSONDecodeError:
        return {}
    return {f["field"]: f for f in rep.get("per_field", [])}


def _norm(v) -> str:
    return "".join(str(v).lower().split()) if v is not None else ""


_ALNUM = re.compile(r"[^a-z0-9]")
_DIGITS = re.compile(r"[^0-9]")
_MONTHS = {"jan": "01", "feb": "02", "mar": "03", "apr": "04", "may": "05",
           "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10",
           "nov": "11", "dec": "12"}


def _alnum(v) -> str:
    return _ALNUM.sub("", str(v).lower())


def _datenorm(v) -> str:
    s = str(v).lower()
    for m, n in _MONTHS.items():
        s = s.replace(m, n)
    return _DIGITS.sub("", s)


def classify(gt, petey) -> str:
    """Why do these two disagree?

    Raw disagreement counts are not a defect list. Measured over batch 1
    and 2, only 29% of intact differs are candidate blueprint defects —
    the rest have known causes, and reporting them undifferentiated buries
    the real findings under roughly 2.4x their number in noise.

    The categories, in the order they are tested:

      phantom      ground truth is empty and the reader returned
                   something. The field should probably not exist — a
                   pushbutton or other non-data widget. Noise, and the
                   pushbutton drop now prevents most of it at labeling
                   time.
      unlocatable  ground truth HAS a value and the reader found nothing.
                   Not noise: either the name is unfindable on the page,
                   or extraction failed. Kept separate because it is the
                   same signal S2 reports as `unlocatable`, and because
                   collapsing it into "null on one side" would discard
                   the larger half of the findings.
      punctuation  same characters, different separators — 'Hendricks,
                   Patricia A., KO' against 'Hendricks Patricia A KO'.
      date_format  same date, different rendering: '20241105', '2024-11-05'
                   and '2024NOV05' are one value three ways. This is the
                   normalize-both-sides trap on its third appearance.
      numeric      same digits, different formatting.
      boolean      a checkbox. The text parsers cannot see checkbox state
                   (C8), so these say nothing about the blueprint.
      substring    one value contains the other — truncation, or a field
                   bound to a fragment of a larger printed string.
      defect       none of the above. THIS is the list worth triaging.
    """
    gt_empty = gt is None or str(gt).strip() in ("", "None")
    pe_empty = petey is None or str(petey).strip() in ("", "None")
    if gt_empty and not pe_empty:
        return "phantom"
    if pe_empty and not gt_empty:
        return "unlocatable"
    if gt_empty and pe_empty:
        return "punctuation"
    a, b = _alnum(gt), _alnum(petey)
    if a == b:
        return "punctuation"
    da, db = _datenorm(gt), _datenorm(petey)
    if da == db and len(da) >= 6:
        return "date_format"
    na, nb = _DIGITS.sub("", str(gt)), _DIGITS.sub("", str(petey))
    if na and na == nb and (a != b):
        return "numeric"
    if str(gt).lower() in ("true", "false") or \
            str(petey).lower() in ("true", "false"):
        return "boolean"
    if a and b and (a in b or b in a):
        return "substring"
    return "defect"


# A swap is only evidence when the matched value could not have collided by
# chance. Booleans are the trap: a form with 30 `_ind` checkboxes has ~15
# fields whose ground truth is literally `True`, so ANY field petey read as
# True "swaps" with all of them. The first pass reported 22 swaps on this
# basis; almost all were boolean collisions.
SWAP_MIN_CHARS = 6
SWAP_EXCLUDED_TYPES = {"boolean", "category", "multi_category"}


def _swappable(seeing: dict, blind: dict) -> bool:
    """Is the value distinctive enough for a match to mean anything?"""
    ftype = (seeing or {}).get("type") or (blind or {}).get("type") or "string"
    if ftype in SWAP_EXCLUDED_TYPES:
        return False
    val = (seeing or {}).get("extracted_value")
    gt = (blind or {}).get("gt_value")
    return (len(_norm(val)) >= SWAP_MIN_CHARS
            or len(_norm(gt)) >= SWAP_MIN_CHARS)


def meaning_methods(case_dir: Path) -> list[str]:
    """Whichever meaning-based arm this case has, EXCLUDING datalab.

    Taking one method name at a time hid most of the corpus: this pass
    reported 23 forms while far more were comparable, because it only ever
    asked for `petey:pymupdf`.

    `datalab` is deliberately not included. It is a metered third-party OCR
    service and it buys nothing on this corpus -- these are AcroForm PDFs
    with a real text layer, and the flattened variants still carry drawn
    text, so `pymupdf` reads both. Its historical extracts are also unusable:
    on the forms where it is the only arm it emits 100% `unlocatable` on
    every one over 400 fields, which is output truncation rather than
    evidence, and counting it inflated the disagreement total twelve-fold.
    A form whose only arm is datalab has NO arm.
    """
    return [p.name[len("score_"):-len(".json")]
            for p in sorted(case_dir.glob("score_petey*.json"))]


def compare_case(case_dir: Path, method: str) -> list[dict]:
    if method == "auto":
        got = meaning_methods(case_dir)
        return compare_case(case_dir, got[0]) if got else []
    blind = _load(case_dir, BLIND)
    seeing = _load(case_dir, method)
    if not blind or not seeing:
        return []

    # gt by field, for swap detection across the whole case.
    gt_by_field = {f: r.get("gt_value") for f, r in blind.items()}

    rows = []
    for field, s in seeing.items():
        b = blind.get(field)
        if b is None:
            continue
        if s["verdict"] not in ("differ", "extract_miss"):
            continue
        if b["verdict"] != "agree":
            # The blind method also disagrees, so this is not a
            # naming-specific finding.
            continue

        swap_with = None
        if s["verdict"] == "differ" and _swappable(s, b):
            for other, gt in gt_by_field.items():
                if other == field or gt is None:
                    continue
                if not _swappable(seeing.get(other, {}), blind.get(other, {})):
                    continue
                if _norm(gt) == _norm(s["extracted_value"]):
                    swap_with = other
                    break

        rows.append({
            "field": field,
            "verdict": s["verdict"],
            "gt": b.get("gt_value"),
            "native": b.get("extracted_value"),
            "petey": s.get("extracted_value"),
            "swap_with": swap_with,
            "cause": classify(b.get("gt_value"), s.get("extracted_value")),
        })
    return rows


def arm_agrees(run_dir: Path, method: str) -> int:
    """How many fields the meaning-based arm got RIGHT in this run.

    Zero means it produced no output at all, which is different from
    producing output that misses. The distinction matters: hud1's extract is
    literally `{}` while f1040sb returned 72 keys with 34 values, and only
    the first contributes no evidence.
    """
    n = 0
    for case_dir in sorted(run_dir.glob("case_*")):
        m = method
        if m == "auto":
            got = meaning_methods(case_dir)
            if not got:
                continue
            m = got[0]
        for row in _load(case_dir, m).values():
            if row.get("verdict") == "agree":
                n += 1
    return n


def compare_run(run_dir: Path, method: str) -> dict:
    per_variant: dict[str, list[dict]] = {}
    for case_dir in sorted(run_dir.glob("case_*")):
        variant = "flat" if case_dir.name.endswith("flat") else "intact"
        per_variant.setdefault(variant, []).extend(
            compare_case(case_dir, method))

    intact_fields = {r["field"] for r in per_variant.get("intact", [])}
    rows = []
    seen = set()
    for variant, rs in per_variant.items():
        for r in rs:
            key = (r["field"], r["verdict"])
            if key in seen:
                continue
            seen.add(key)
            rows.append({**r, "variant": variant,
                         "flat_only": variant == "flat"
                         and r["field"] not in intact_fields})
    return {"run": run_dir.name, "findings": rows}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", type=Path, default=RUNS)
    ap.add_argument("--method", default="auto",
                    help="'auto' uses whichever score_petey* arm each case "
                         "has. datalab is excluded -- see meaning_methods. "
                         "Name a method explicitly to override.")
    ap.add_argument("--form", help="substring match on run dir name")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    dirs = [d for d in sorted(args.runs.iterdir())
            if d.is_dir() and any(d.glob("case_*"))]
    if args.form:
        dirs = [d for d in dirs if args.form in d.name]

    # One run per form: the most recent, since re-runs supersede.
    latest: dict[str, Path] = {}
    for d in dirs:
        form = d.name.rsplit("_", 2)[0]
        latest[form] = d

    results, counts = [], collections.Counter()
    for form, d in sorted(latest.items()):
        res = compare_run(d, args.method)
        if not res["findings"]:
            continue
        res["form"] = form
        results.append(res)
        counts[form] = len(res["findings"])

    # No form is muted, and two attempts to mute some were both wrong.
    #
    # The `unlocatable` share swings with form size -- 48% under 100 fields,
    # 98% in the 300-400 band -- because a large form exceeds the reader's
    # output budget and it returns nothing for most fields. That looked like
    # a reason to exclude those forms. It is not: `unlocatable` is already a
    # SEPARATE cause from `defect`, so the mass never contaminated the
    # candidate count, only the percentages next to it. Excluding the forms
    # threw away real evidence instead -- 8 candidate defects, and 90
    # agreements on hud1 alone.
    #
    # The two wrong criteria, recorded so neither is retried:
    #   >90% of disagreements unlocatable   muted 6 forms that had extracted
    #                                       fine and simply missed fields
    #                                       (f1040sb returned 34 values)
    #   the extract file is empty           read `fs[0]` from a glob across
    #                                       ALL runs of a form, so it scored
    #                                       an older run than the one being
    #                                       compared. hud1 is not empty.
    #
    # Read `defect` as an absolute count. Coverage is reported below instead,
    # so a form the reader barely managed is visible rather than averaged in.
    all_findings = [f for r in results for f in r["findings"]]
    intact = [f for f in all_findings if not f["flat_only"]]
    by_cause = collections.Counter(f["cause"] for f in intact)
    real = [f for f in intact if f["cause"] == "defect"]
    swaps = sum(1 for f in real if f["swap_with"])

    print(f"{len(all_findings)} raw disagreements across {len(results)} "
          f"forms — {len(intact)} intact, "
          f"{len(all_findings) - len(intact)} flat-only\n")
    thin = []
    for r in results:
        ag = arm_agrees(args.runs / r["run"], args.method)
        n_dis = len(r["findings"])
        if n_dis and ag / (ag + n_dis) < 0.25:
            thin.append((r["run"].split("_20")[0], ag, n_dis))
    if thin:
        print(f"[thin coverage] {len(thin)} forms where the meaning-based arm "
              f"located under a quarter of what it was asked for.")
        print("  Their misses land in `unlocatable`, not `defect`, so the "
              "candidate count is unaffected —")
        print("  but do not read the percentages as a property of the "
              "corpus.")
        for form, ag, n in sorted(thin, key=lambda t: -t[2])[:8]:
            print(f"    {form:24s} {ag:5d} located / {n:5d} disagreements")
        print()

    print("intact disagreements by cause:")
    for cause, n in by_cause.most_common():
        mark = "  <-- triage these" if cause == "defect" else ""
        print(f"  {cause:<16}{n:>5}{n / max(len(intact), 1) * 100:>6.0f}%"
              f"{mark}")
    print(f"\n{len(real)} candidate defects ({swaps} swaps), by form:")
    per_form = collections.Counter()
    for r in results:
        per_form[r["form"]] += sum(
            1 for f in r["findings"]
            if f["cause"] == "defect" and not f["flat_only"])
    for form, n in per_form.most_common():
        if n:
            print(f"  {form:<34}{n}")

    if args.verbose:
        for r in results:
            print(f"\n=== {r['form']} ===")
            for f in r["findings"]:
                tag = ("SWAP->" + f["swap_with"]) if f["swap_with"] else (
                    "flat-only" if f["flat_only"] else f["verdict"])
                print(f"  {f['field']:<40} {tag}")
                print(f"      gt     {str(f['gt'])[:64]!r}")
                print(f"      native {str(f['native'])[:64]!r}")
                print(f"      petey  {str(f['petey'])[:64]!r}")

    if args.out:
        args.out.write_text(json.dumps(results, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
