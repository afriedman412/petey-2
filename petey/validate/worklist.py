"""The ranked relabel worklist — S1 and S2 combined, false positives removed.

Post-processes `runs/s2_all.json`, `runs/s1_report.json` and
`runs/clusters.json` into one ordered list of blueprint defects. Pure
post-processing: no API calls, no re-extraction, so it is cheap to re-run
after any scorer change.

## Why refinement is needed first

A raw S2 `suspect` means "deterministic agreed, semantic disagreed". Two
things produce that without any blueprint being wrong:

**split widgets.** f943 prints a dollars box and a cents box side by side.
`jan_tax_liability_amt` holds `4210`, `jan_tax_liability_17a_amt` holds
`18`, and the page reads `4210.18`. The semantic reader returns the whole
number for both, so both look suspect. The labeler is right — there really
are two widgets — and this alone accounted for 25 of f943's suspects.

**transcription noise.** The reader returned `Okonwo` for `Okonkwo`. The
name is bound correctly; the instrument misread one character.

Both are removed by exact, local tests before anything is ranked. What
survives is the set where the semantic reader found a genuinely DIFFERENT
value, which is the signal worth acting on.

## Ranking

Confidence comes from independent agreement, not from any single score:

  confirmed  S2 suspect AND the field also disagrees on shape in S1.
             Two instruments, different modalities, same verdict.
  vocabulary blueprint has a high unlocatable rate — the names are not
             findable on the page at all. Regenerate rather than repair.
  suspect    S2 only. Real, but could be the under-specified case (only
             6 percent of fields carry a description) rather than a wrong
             name.
  shape      S1 only. The value contradicts the declared semantic_type
             but the name/widget binding may be fine.

Usage:
    python worklist.py
    python worklist.py --form f1040 --verbose
    python worklist.py --out runs/worklist.json
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
from pathlib import Path

from petey.paths import RUNS
HERE = Path(__file__).resolve().parent

FUZZY_MIN = 0.86          # below this, two strings are genuinely different
VOCAB_MISMATCH_RATE = 0.35


def _norm(v) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v).lower())


def is_transcription_noise(truth, semantic) -> bool:
    """The reader found the right field and misread a character or two."""
    a, b = _norm(truth), _norm(semantic)
    if not a or not b or a == b:
        return False
    if abs(len(a) - len(b)) > 3:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= FUZZY_MIN


def find_split_partner(row, rows_by_field) -> str | None:
    """Is this widget one half of a value the page prints as a whole?

    Returns the partner field name when `truth` plus some sibling's
    `truth` concatenates to what the reader saw. Dollars/cents boxes are
    the common case, but the test is general: it only fires when the
    combination reproduces the semantic value exactly.
    """
    sem = _norm(row.get("semantic"))
    part = _norm(row.get("truth"))
    if not sem or not part or part == sem:
        return None
    if part not in sem:
        return None
    remainder = sem.replace(part, "", 1)
    if not remainder:
        return None
    for name, other in rows_by_field.items():
        if name == row["field"]:
            continue
        if _norm(other.get("truth")) == remainder:
            return name
    return None


def refine(form_row: dict) -> dict:
    """Split a form's raw suspects into real / split-widget / noise."""
    rows_by_field = {r["field"]: r for r in form_row["rows"]}
    real, split, noise = [], [], []
    for r in form_row["rows"]:
        if not r.get("suspect"):
            continue
        if is_transcription_noise(r.get("truth"), r.get("semantic")):
            noise.append(r)
            continue
        partner = find_split_partner(r, rows_by_field)
        if partner:
            r = {**r, "split_partner": partner}
            split.append(r)
            continue
        real.append(r)
    return {"real": real, "split": split, "noise": noise}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", type=str)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    runs = RUNS
    s2 = {r["form"]: r for r in json.loads((runs / "s2_all.json").read_text())}
    s1_issues = json.loads((runs / "s1_report.json").read_text())["issues"]
    s1_by = collections.defaultdict(set)
    for i in s1_issues:
        if i.get("field"):
            s1_by[i["form"]].add(i["field"])

    entries, stats = [], collections.Counter()
    for form, r in sorted(s2.items()):
        if args.form and form != args.form:
            continue
        ref = refine(r)
        stats["split_widget"] += len(ref["split"])
        stats["transcription_noise"] += len(ref["noise"])

        if r["unlocatable_rate"] >= VOCAB_MISMATCH_RATE:
            entries.append({
                "form": form, "kind": "vocabulary",
                "n": r["n_unlocatable"], "of": r["n_tested"],
                "detail": f"{r['unlocatable_rate']:.0%} of names not findable "
                          f"on the page — regenerate, do not repair",
                "fields": [],
            })
            stats["vocabulary"] += 1
            continue

        for x in ref["real"]:
            confirmed = x["field"] in s1_by.get(form, ())
            entries.append({
                "form": form,
                "kind": "confirmed" if confirmed else "suspect",
                "field": x["field"], "n": 1, "of": r["n_tested"],
                "detail": f"widget={x['truth']!r} meaning={x['semantic']!r}",
                "fields": [x["field"]],
            })
            stats["confirmed" if confirmed else "suspect"] += 1

    # S1-only fields, for completeness — cluster, do not filter.
    for form, fields in s1_by.items():
        if args.form and form != args.form:
            continue
        s2f = {x["field"] for x in s2.get(form, {}).get("rows", [])}
        for f in fields - s2f:
            stats["shape_only"] += 1

    order = {"vocabulary": 0, "confirmed": 1, "suspect": 2}
    entries.sort(key=lambda e: (order.get(e["kind"], 3), -e["n"], e["form"]))

    print("=" * 78)
    print("RELABEL WORKLIST")
    print("=" * 78)
    print(f"  {'confirmed (S1+S2 agree)':<34} {stats['confirmed']:>5}")
    print(f"  {'suspect (S2 only)':<34} {stats['suspect']:>5}")
    print(f"  {'vocabulary mismatch (whole form)':<34} {stats['vocabulary']:>5}")
    print(f"  {'shape only (S1, not tested by S2)':<34} "
          f"{stats['shape_only']:>5}")
    print()
    print(f"  removed as FALSE POSITIVES:")
    print(f"    {'split widget (dollars/cents)':<32} "
          f"{stats['split_widget']:>5}")
    print(f"    {'transcription noise':<32} "
          f"{stats['transcription_noise']:>5}")

    print()
    print("-" * 78)
    print(f"TOP {args.top}")
    print("-" * 78)
    per_form = collections.Counter(e["form"] for e in entries
                                   if e["kind"] in ("confirmed", "suspect"))
    for e in entries[:args.top]:
        tag = e["kind"].upper()
        if e["kind"] == "vocabulary":
            print(f"\n  [{tag}] {e['form']} — {e['detail']}")
        else:
            print(f"  [{tag}] {e['form']}:{e.get('field','')}")
            print(f"          {e['detail']}")

    print()
    print("-" * 78)
    print("FORMS BY REPAIRABLE DEFECT COUNT")
    print("-" * 78)
    for form, n in per_form.most_common(15):
        print(f"  {form:<14} {n:>3}")

    if args.out:
        args.out.write_text(json.dumps(
            {"stats": dict(stats), "entries": entries}, indent=2, default=str))
        print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
