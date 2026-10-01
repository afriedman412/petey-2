"""Which detectors flag which fields, over a run's intact cases.

Three detectors look at the same blueprint from different sides: the
name-based reader (a field whose name leads the reader to another box, or
nowhere), the class check (the page says the box holds a different kind of
value than the blueprint types), and the inventory cross-reference's option
groups (the page partitions the option boxes differently). This prints, per
run, how many fields each flags and how far they overlap, and lists the
fields. Used for TODO step 4b: are the page-side checks finding the same
faults as the reader, or different ones?

    PYTHONPATH=. venv/bin/python eval/flags_overlap.py runs/acord25_20260930_195543 [more runs]
    PYTHONPATH=. venv/bin/python eval/flags_overlap.py --latest fw9,acord25,i765
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.paths import RUNS  # noqa: E402
from petey.validate import method_delta  # noqa: E402


def collect(run: Path) -> dict:
    reader: dict[str, set] = collections.defaultdict(set)
    tier1: dict[str, dict] = {}
    tier2: dict[str, dict] = {}
    groups: dict[str, dict] = {}
    n = 0
    for d in sorted(run.glob("case_*_intact")):
        n += 1
        arms = method_delta.meaning_methods(d)
        arm = "petey:image" if "petey:image" in arms else (arms[0] if arms else None)
        if arm:
            for r in method_delta.compare_case(d, arm):
                if r.get("cause") in ("defect", "unlocatable"):
                    reader[r["field"]].add(r["cause"])
        cd = d / "class_disagreements.json"
        if cd.exists():
            for row in json.loads(cd.read_text()):
                (tier1 if row["tier"] == 1 else tier2 if row["tier"] == 2 else {})[row["field"]] = row
        inv = d / "inventory_check.json"
        if inv.exists():
            for row in json.loads(inv.read_text()).get("rows", []):
                if row.get("class") == "option_group_mismatch":
                    groups[row["field"]] = row
    return {"run": run.name, "cases": n, "reader": dict(reader), "class": tier1, "class_suggest": tier2,
            "groups": groups}


def report(c: dict, verbose: bool = True) -> None:
    rf, cf, gf = set(c["reader"]), set(c["class"]), set(c["groups"])
    print(f"{c['run']}: {c['cases']} cases; reader {len(rf)}, class tier-1 {len(cf)}, option groups {len(gf)}; "
          f"reader&class {len(rf & cf)}, reader&groups {len(rf & gf)}, class&groups {len(cf & gf)}; "
          f"reader hit a tier-2 field {len(rf & set(c['class_suggest']))}")
    if not verbose:
        return
    for f in sorted(rf | cf | gf):
        tags = []
        if f in rf:
            tags.append("reader:" + "+".join(sorted(c["reader"][f])))
        if f in cf:
            tags.append(f"class:{c['class'][f]['page_class']}/{c['class'][f]['blueprint_class']}")
        if f in gf:
            tags.append(f"group:{c['groups'][f].get('shape')}")
        print(f"  {f:48} {'  '.join(tags)}")


def latest_run(form: str) -> Path | None:
    dirs = sorted(d for d in RUNS.glob(f"{form}_2*") if (d / "case_001_intact" / "score_native.json").exists())
    return dirs[-1] if dirs else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("runs", nargs="*", type=Path)
    ap.add_argument("--latest", default=None, help="comma-separated form stems: their newest scored run")
    ap.add_argument("--summary", action="store_true", help="counts only")
    args = ap.parse_args()
    runs = list(args.runs)
    for stem in (args.latest or "").split(","):
        if stem.strip():
            r = latest_run(stem.strip())
            if r is None:
                print(f"{stem}: no scored run")
            else:
                runs.append(r)
    for r in runs:
        report(collect(r), verbose=not args.summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
