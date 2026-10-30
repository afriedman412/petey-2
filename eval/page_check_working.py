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
import time
import traceback

import yaml

from petey.validate import draft, hand_review as h, page_check as pc


def earlier_verdicts(p, bp: dict) -> dict[str, dict]:
    """{field: verdict} still valid for the fields as they are (same name and definition), from every page-check
    record of this file, the newest first: the stamped one, the pipeline's per-round ones, earlier versions
    (2026-10-15: a merge that read only the stamped record's `fields` dropped f8825's page 1)."""
    stem = pc.record_path(p, bp).name.rsplit("__", 1)[0]
    recs = sorted(pc.OUT.glob(f"{stem}__*.json"), key=lambda q: q.stat().st_mtime)
    table: dict = {}
    for q in recs:                                   # oldest first, so a newer record's verdict wins
        try:
            table.update(pc.verdict_table(json.loads(q.read_text(encoding="utf-8"))))
        except (OSError, ValueError):
            continue
    out = {}
    for n, sp in (bp.get("fields") or {}).items():
        v = table.get((n, pc.spec_hash(sp))) if isinstance(sp, dict) else None
        if v:
            out[n] = v
    return out


def one(bid: str, changed_only: bool) -> str:
    p = h.working_path(bid)
    before = h._sha(p)
    if not changed_only:
        res = pc.check(p)
    else:
        bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        held = earlier_verdicts(p, bp)
        todo = {n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict) and n not in held}
        if not todo and (bp.get("x_petey_page_check") or {}).get("fields") == len(held):
            return f"{bid}: nothing changed since the check"
        new = pc.check(p, only_names=todo) if todo else {"fields": {}, "cost_usd": 0.0, "pages": [], "model": pc.MODEL,
                                                          "prompt": pc.PROMPT_VERSION, "blueprint": str(p),
                                                          "when": time.strftime("%Y-%m-%d %H:%M:%S"), "usage": {}}
        res = dict(new, fields={**held, **new["fields"]},
                   pages=sorted({b["page"] for r in pc.numbered(bp) for b in r["boxes"]}))
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
