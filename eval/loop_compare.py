"""Loop 1 vs loop 2 on the judge-eval side copies, and a first read of new forms: per form, what the loop detected
before and after, what the reviewer applied, what the adjudicator said, what the loop kept or restored.

    PYTHONPATH=. venv/bin/python eval/loop_compare.py [--forms a,b] [--new runs/judge_eval/batch20c.txt]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

EVAL = Path("runs/judge_eval")


def summarize(loop: dict) -> dict:
    its = loop.get("iterations", [])
    out = {"status": loop.get("status"), "iters": len(its),
           "detected_first": next((i.get("detected") for i in its if "detected" in i), None),
           "detected_last": next((i.get("detected") for i in reversed(its) if "detected" in i), None)}
    applied: collections.Counter = collections.Counter(); adj: collections.Counter = collections.Counter()
    judged: collections.Counter = collections.Counter(); cost = 0.0
    for i in its:
        rr = i.get("review_run") or {}
        for k, v in (rr.get("applied") or {}).items():
            if k not in ("ok",) and not k.startswith("rejected") and not k.startswith("adjudicated"):
                applied[k] += v
        cost += rr.get("cost_usd", 0) or 0
        for k, v in ((rr.get("adjudicated") or {}).get("tally") or {}).items():
            adj[k] += v
        for k, v in (i.get("review") or {}).items():
            if k in ("better", "same_kept", "same_rename", "worse", "restored"):
                judged[k] += v
    out.update(renames=applied.get("name", 0), applied=dict(applied), adjudicated=dict(adj), judged=dict(judged),
               cost=round(cost, 3))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", default=None)
    ap.add_argument("--new", default=str(EVAL / "batch20c.txt"))
    args = ap.parse_args()
    new = {l.split("|")[0] for l in Path(args.new).read_text().splitlines() if "|" in l} if Path(args.new).exists() else set()
    rows = []
    for p in sorted(EVAL.glob("*_loop.json")):
        form = p.name[:-len("_loop.json")]
        if args.forms and form not in args.forms.split(","):
            continue
        l1 = summarize(json.loads(p.read_text()))
        p2 = EVAL / f"{form}_loop2.json"
        l2 = summarize(json.loads(p2.read_text())) if p2.exists() else None
        rows.append((form, "new" if form in new else "rerun", l1, l2))
    print(f"{'form':30} {'kind':5} {'loop1 det':>10} {'renames':>7} {'kept/rest':>9} | {'loop2 det':>10} {'renames':>7} {'adjudicated':>22} {'kept/rest':>9}")
    tot = collections.Counter()
    for form, kind, l1, l2 in rows:
        def fmt(l):
            if not l: return f"{'-':>10} {'-':>7} {'-':>22} {'-':>9}"
            kr = f"{l['judged'].get('better',0)+l['judged'].get('same_kept',0)}/{l['judged'].get('restored',0)}"
            a = l["adjudicated"]; at = ",".join(f"{k}={v}" for k, v in sorted(a.items())) or "-"
            return f"{str(l['detected_first'])+'->'+str(l['detected_last']):>10} {l['renames']:>7} {at:>22} {kr:>9}"
        print(f"{form[:30]:30} {kind:5} {fmt(l1)[:29]} | {fmt(l2) if l2 else fmt(None)}")
        for tag, l in (("l1", l1), ("l2", l2)):
            if l:
                tot[f"{tag}_forms"] += 1; tot[f"{tag}_renames"] += l["renames"]; tot[f"{tag}_restored"] += l["judged"].get("restored", 0)
                for k, v in l["adjudicated"].items(): tot[f"{tag}_adj_{k}"] += v
                tot[f"{tag}_cost"] += l["cost"]
    print("\ntotals:", {k: (round(v, 2) if isinstance(v, float) else v) for k, v in sorted(tot.items())})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
