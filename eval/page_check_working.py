"""The page check on review-page working copies (2026-10-15: the passes after generation run on the working copy, so
the page check has to as well): stamped, and the review records follow the new sha (`draft.follow`), as for any change
made through the page or Claude's pass.

`--changed`: only the fields whose definition changed since the stamped check (a later pass renamed or re-captioned
them; their verdicts no longer hold, `page_check.verdicts`), checked and merged into the record with the verdicts that
still hold; nothing is called for a form with no changed field.

    PYTHONPATH=. venv/bin/python eval/page_check_working.py je__boat_application ... [--changed] [--workers 5]
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import traceback

import yaml

from petey.paths import RUNS
from petey.validate import draft, hand_review as h, page_check as pc


def one(bid: str, changed_only: bool) -> str:
    p = h.working_path(bid)
    before = h._sha(p)
    if not changed_only:
        res = pc.check(p)
    else:
        bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        st = bp.get("x_petey_page_check") or {}
        rp = RUNS.parent / st["record"] if st.get("record") else None
        if rp is None or not rp.exists():
            res = pc.check(p)
        else:
            held = pc.verdicts(bp)
            todo = {n for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict) and n not in held}
            if not todo:
                return f"{bid}: nothing changed since the check"
            new = pc.check(p, only_names=todo)
            old = json.loads(rp.read_text(encoding="utf-8"))
            res = dict(new, fields={**{n: v for n, v in (old.get("fields") or {}).items() if n in held}, **new["fields"]},
                       cost_usd=round((old.get("cost_usd") or 0) + (new.get("cost_usd") or 0), 4),
                       pages=sorted(set(old.get("pages") or []) | set(new.get("pages") or [])))
    pc.save(res, p, stamp=True)
    draft.follow(bid, before, h._sha(p))
    fl = sum(1 for v in (res.get("fields") or {}).values() if v.get("verdict") == "flag")
    return f"{bid}: {len(res.get('fields') or {})} fields, {fl} flagged, ${res.get('cost_usd', 0):.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--changed", action="store_true", help="only fields changed since the stamped check")
    ap.add_argument("--workers", type=int, default=5)
    args = ap.parse_args()

    def run(bid):
        try:
            return one(bid, args.changed)
        except Exception:
            return f"{bid}: FAILED\n{traceback.format_exc()[-600:]}"
    with cf.ThreadPoolExecutor(args.workers) as ex:
        for line in ex.map(run, args.ids):
            print(line, flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
