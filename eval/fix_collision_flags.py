"""Drop the name-collision flags the first collision rule raised on numbered series (2026-10-06).

`form_run.collisions` first flagged any two names that differ only by a trailing number, which is how split and
repeated fields are named (`ssn_part1` / `ssn_part3`, `line1` / `line2`): 11 false flags on VA 21-0966 and
B-410S1. The rule now flags only a field a round renamed so that it duplicates another field's name. This removes,
from finished run records, every code-collision verdict the current rule would not raise, and refreshes the
`flagged` count in the blueprint's page-check stamp. Idempotent; run it again after forms that started under the
old rule finish.

    PYTHONPATH=. venv/bin/python eval/fix_collision_flags.py [--dry]
"""
from __future__ import annotations

import argparse
import json
import sys

import yaml

from petey.paths import RUNS
from petey.validate import form_run, page_check


def fix(path, dry: bool) -> int:
    rec = json.loads(path.read_text())
    if "result" not in rec:                     # still running
        return 0
    dropped = 0
    before: dict = {}
    for r in rec["rounds"]:
        fields_now = dict(before)
        if r["round"] == 0:
            fields_now = dict(r["fields"])
        else:
            for n in r.get("removed") or []:
                fields_now.pop(n, None)
            fields_now.update(r.get("changed") or {})
        pc = r.get("page_check") or {}
        code = {n for n, v in pc.items() if v.get("model") == "code"}
        if code:
            keep = form_run.collisions(fields_now, code, before)
            for n in code - set(keep):
                del pc[n]
                dropped += 1
        before = fields_now
    if dropped and not dry:
        path.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))
        bpt = RUNS.parent / ((rec.get("result") or {}).get("bpt") or "")
        if bpt.is_file():
            bp = yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}
            cur = page_check.verdicts(bp)
            if bp.get("x_petey_page_check"):
                bp["x_petey_page_check"]["flagged"] = sum(1 for v in cur.values() if v.get("verdict") == "flag")
                bpt.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                               encoding="utf-8")
    return dropped


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    total = 0
    for p in sorted(form_run.RECORDS.glob("*.json")):
        if "__" in p.stem:                       # archived earlier runs
            continue
        n = fix(p, args.dry)
        if n:
            print(f"{p.stem}: {n} false collision flag(s) {'would be ' if args.dry else ''}dropped")
        total += n
    print(f"total {total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
