"""What the page check misses on grouping (Andrew, 2026-10-15: he reviews every group and groupable checkbox in full,
so his grouping corrections are a complete answer key; 'what is opus missing now?').

For each validated form: the blueprint as first generated (`belongs_to_fixture` before copy) against the validated
one, box by box (a box = page + rounded rect). A grouping correction is a validated field holding checkboxes whose box
set no generated field held (loose boxes merged, a group split or re-cut), or the same box set with another type
(category <-> multi_category). Caught when the page check flagged one of the generated fields holding those boxes:
`should_group` / `options` (a grouping flag), or any flag. False alarms: grouping flags on fields whose boxes and
type were kept.

    PYTHONPATH=. venv/bin/python eval/group_score.py [--forms ID ...] [--list]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from belongs_to_fixture import BEFORE  # noqa: E402
from triage_score import page_verdicts  # noqa: E402

GROUP_FLAGS = ("should_group", "options")
CHECKS = ("checkbox", "radiobutton")


def boxes(spec: dict) -> list[tuple]:
    ws = list((spec.get("widgets") or {}).values()) or [spec.get("widget") or {}]
    return [(w.get("page"), *(round(v) for v in w["rect"])) for w in ws if w.get("rect")]


def is_check(spec: dict) -> bool:
    if spec.get("widgets"):
        return True
    return (spec.get("widget") or {}).get("widget_type") in CHECKS or spec.get("type") == "boolean"


def fields(p: Path) -> dict[str, dict]:
    return {n: s for n, s in (yaml.safe_load(p.read_text()).get("fields") or {}).items() if isinstance(s, dict)}


def corrections(before: dict, after: dict) -> tuple[list[dict], set]:
    """([{after field, before fields, kind}], {before fields kept as they were})."""
    owner = {b: n for n, s in before.items() for b in boxes(s)}
    sets_b = {frozenset(boxes(s)): n for n, s in before.items()}
    out, kept = [], set()
    for n, s in after.items():
        if not is_check(s):
            continue
        bs = frozenset(boxes(s))
        src = sorted({owner[b] for b in bs if b in owner})
        if bs in sets_b:
            m = sets_b[bs]
            if (before[m].get("type") or "") != (s.get("type") or "") and (s.get("widgets") or before[m].get("widgets")):
                out.append({"field": n, "before": [m], "kind": f"type {before[m].get('type')} -> {s.get('type')}"})
            else:
                kept.add(m)
            continue
        whole = [m for m in src if set(boxes(before[m])) <= bs]
        if len(src) > 1 and len(whole) == len(src):
            kind = f"merged {len(src)} fields"
        elif len(src) == 1 and len(bs) < len(boxes(before[src[0]])):
            kind = "split out of a group"
        else:
            kind = "re-cut"
        out.append({"field": n, "before": src, "kind": kind})
    return out, kept


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", nargs="*")
    ap.add_argument("--list", action="store_true", help="every correction, caught or not")
    args = ap.parse_args()
    forms = args.forms or list(json.loads(Path("runs/belongs_to/validated_forms_2026-10-14.json").read_text())["forms"])
    tot = collections.Counter()
    by_kind = collections.defaultdict(collections.Counter)
    missed, false = [], []
    for bid in forms:
        bp = next((BEFORE / bid).glob("*.bpt"), None)
        rec = Path("runs/hand_review") / f"{bid}.json"
        if not bp or not rec.exists():
            print(f"  {bid}: no before copy or review record", file=sys.stderr)
            continue
        after_p = Path(json.loads(rec.read_text())["blueprint"])
        before, after = fields(bp), fields(after_p)
        pv = page_verdicts(bid)
        if not pv:
            print(f"  {bid}: no page check", file=sys.stderr)
        fixes, kept = corrections(before, after)
        groupish = [n for n, s in before.items() if is_check(s)]
        tot["checkbox fields generated"] += len(groupish)
        for c in fixes:
            fl = [pv.get(m) or {} for m in c["before"]]
            g = any(x.get("verdict") == "flag" and x.get("problem") in GROUP_FLAGS for x in fl)
            a = any(x.get("verdict") == "flag" for x in fl)
            k = c["kind"].split(" ")[0]
            tot["corrections"] += 1
            tot["caught (grouping flag)"] += g
            tot["caught (any flag)"] += a
            by_kind[k]["n"] += 1
            by_kind[k]["grouping flag"] += g
            by_kind[k]["any flag"] += a
            c.update(bid=bid, grouping_flag=g, any_flag=a,
                     flags=[f"{m}: {x.get('problem')}" for m, x in zip(c["before"], fl) if x.get("verdict") == "flag"])
            if not a or args.list:
                missed.append(c)
        for m in kept:
            x = pv.get(m) or {}
            if x.get("verdict") == "flag" and x.get("problem") in GROUP_FLAGS:
                false.append((bid, m, x.get("problem"), (x.get("reason") or "")[:90]))
    print(f"\n{len(forms)} forms; {tot['checkbox fields generated']} checkbox / option fields as generated; "
          f"{tot['corrections']} grouping corrections")
    print(f"  caught by a grouping flag: {tot['caught (grouping flag)']}   by any flag: {tot['caught (any flag)']}")
    print(f"  grouping flags on fields kept as they were (false alarms): {len(false)}")
    print("\n  by kind:")
    for k, c in sorted(by_kind.items(), key=lambda x: -x[1]["n"]):
        print(f"    {k:8} {c['n']:>4}   grouping flag {c['grouping flag']:>4}   any flag {c['any flag']:>4}")
    print(f"\n{'every correction' if args.list else 'missed (no flag on any of its fields)'}:")
    for c in missed:
        mark = "" if not args.list else ("  [grouping flag]" if c["grouping_flag"] else "  [other flag]" if c["any_flag"] else "  [MISSED]")
        print(f"  {c['bid']}  {c['field']}  <- {', '.join(c['before'])[:110]}  ({c['kind']}){mark}")
    if false:
        print("\nfalse alarms:")
        for f in false:
            print(f"  {f[0]}  {f[1]}  {f[2]}: {f[3]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
