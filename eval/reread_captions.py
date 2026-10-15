"""'re-read captions' on every group of some forms (Andrew, 2026-10-15: "can you run re-read captions for every group in
the queue?"): what the button in Groups does, per group, without the page. `group_review.suggest_captions` (one call to
the review agent with the page image; captions from the XFA template or set by hand stay locked), the better captions
kept on the unit, then the grouping applied to the review page's working copy through the Groups code, as leaving
Groups does (`draft.follow`, `draft.log` by claude).

    PYTHONPATH=. venv/bin/python eval/reread_captions.py --focus [--skip ID ...] [--workers 5] [--dry]
    PYTHONPATH=. venv/bin/python eval/reread_captions.py je__boat_application ...
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import traceback

from petey.paths import RUNS
from petey.validate import draft, group_review as g, hand_review as h
from petey.validate.retype import resolve_blank


def run(bid: str, dry: bool) -> dict:
    real = h.blueprint_paths()[bid]
    p = h.working_path(bid) if dry else draft.ensure(bid, real)
    bp = h._load(p)
    blank = resolve_blank(bp)
    items, units, _ = g.current_units(bid, bp, h._sha(p))
    groups = [u for u in units if len(u["items"]) > 1 and not u.get("locked")]
    changed, locked = 0, 0
    for u in groups:
        caps = g.suggest_captions(bp, blank, u["name"], u["items"])
        locked += sum(1 for c in caps.values() if c.get("locked"))
        new = {iid: c["caption"] for iid, c in caps.items()
               if c.get("caption") and not c.get("locked") and c["caption"] != c.get("current")}
        if new:
            u["captions"] = {**(u.get("captions") or {}), **new}
            changed += len(new)
    out = {"bid": bid, "groups": len(groups), "captions_changed": changed, "locked": locked, "changes": []}
    if dry or not changed:
        return out
    pl = g.plan(bp, units, blank)
    if pl["errors"]:                     # a grouping the Groups code will not apply as it stands (SSA-827: a boolean
        out["not_applied"] = pl["errors"]  # field holding 3 options); left for the person, nothing written
        return out
    before = h._sha(p)
    g.State().put_units(bid, {"units": units})
    res = g.apply(bid)
    draft.follow(bid, before, h._sha(h.working_path(bid)))
    draft.log(bid, "claude", [f"re-read captions: {c}" for c in res["changes"]])
    out["changes"] = res["changes"]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--focus", action="store_true", help="every form in the picker's top section")
    ap.add_argument("--skip", nargs="*", default=[])
    ap.add_argument("--workers", type=int, default=5)
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--save")
    args = ap.parse_args()
    ids = list(args.ids) + (list(json.loads((RUNS / "hand_review" / "focus.json").read_text())["forms"]) if args.focus else [])
    ids = [b for b in dict.fromkeys(ids) if b not in set(args.skip)]

    def one(bid):
        try:
            return run(bid, args.dry)
        except BaseException:            # group_review.apply raises SystemExit on a refused plan
            return {"bid": bid, "error": traceback.format_exc()[-800:]}
    rows = []
    with cf.ThreadPoolExecutor(args.workers) as ex:
        for r in ex.map(one, ids):
            rows.append(r)
            print(f"{r['bid']}: " + (f"FAILED {r['error'][-300:]}" if "error" in r else
                                     f"{r['groups']} groups, {r['captions_changed']} captions changed, {r['locked']} locked"
                                     + (f"; NOT APPLIED: {'; '.join(r['not_applied'])}" if r.get("not_applied") else "")),
                  flush=True)
    print(f"total: {sum(r.get('groups', 0) for r in rows)} groups, {sum(r.get('captions_changed', 0) for r in rows)} captions "
          f"changed, {sum('error' in r for r in rows)} failed")
    if args.save:
        open(args.save, "w").write(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
