"""Two blueprints of the same blank, field by field, no loop: fields are matched by widget path (an option group
by the set of its option paths plus on-states), then name, type, semantic_type, pattern, description and option
captions are compared.

    PYTHONPATH=. venv/bin/python eval/bpt_diff.py blueprints/acord25.bpt runs/relabel/blueprints/acord25_relabel.bpt [--show 20]
    PYTHONPATH=. venv/bin/python eval/bpt_diff.py --pairs   # the five test forms: committed vs runs/relabel side copy
"""
from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

import yaml

from petey.paths import BLUEPRINTS, RUNS
from petey.validate.name_caption import tokens


def _key(spec: dict) -> str:
    if spec.get("widgets"):
        return "group:" + "|".join(sorted(f"{w.get('path')}#{k}" for k, w in spec["widgets"].items()))
    w = spec.get("widget") or {}
    return f"{w.get('page')}:{w.get('path')}"


def _desc(spec: dict) -> str:
    return re.sub(r"\s+", " ", (spec.get("description") or "")).strip()


def diff(a_path: Path, b_path: Path) -> dict:
    a = (yaml.safe_load(a_path.read_text(encoding="utf-8")) or {}).get("fields") or {}
    b = (yaml.safe_load(b_path.read_text(encoding="utf-8")) or {}).get("fields") or {}
    ka = {_key(s): n for n, s in a.items()}; kb = {_key(s): n for n, s in b.items()}
    both = set(ka) & set(kb)
    out = collections.Counter(fields_a=len(a), fields_b=len(b), matched=len(both),
                              only_a=len(set(ka) - set(kb)), only_b=len(set(kb) - set(ka)))
    renames, retypes, descs = [], [], collections.Counter()
    for k in both:
        na, nb = ka[k], kb[k]; sa, sb = a[na], b[nb]
        if na == nb:
            out["same_name"] += 1
        elif tokens(na) == tokens(nb):
            out["same_name_tokens"] += 1
        else:
            out["renamed"] += 1; renames.append((na, nb, (sa.get("widget") or {}).get("path", "")))
        if (sa.get("type"), sa.get("semantic_type")) != (sb.get("type"), sb.get("semantic_type")):
            out["retyped"] += 1; retypes.append((na, f"{sa.get('type')}/{sa.get('semantic_type')}", f"{sb.get('type')}/{sb.get('semantic_type')}"))
        if (sa.get("pattern") or None) != (sb.get("pattern") or None):
            out["pattern_changed"] += 1
        da, db = _desc(sa), _desc(sb)
        descs["same" if da == db else ("added" if not da and db else ("removed" if da and not db else "changed"))] += 1
        if sa.get("widgets") and sb.get("widgets"):
            ca = {k2: (w.get("caption") or "") for k2, w in sa["widgets"].items()}
            cb = {k2: (w.get("caption") or "") for k2, w in sb["widgets"].items()}
            out["option_captions_changed"] += sum(1 for k2 in ca if ca[k2] != cb.get(k2, ca[k2]))
    return {"counts": dict(out), "descriptions": dict(descs), "renames": sorted(renames), "retypes": sorted(retypes),
            "only_a": sorted(ka[k] for k in set(ka) - set(kb)), "only_b": sorted(kb[k] for k in set(kb) - set(ka))}


def report(a_path: Path, b_path: Path, show: int) -> None:
    d = diff(a_path, b_path); c = d["counts"]
    print(f"\n== {a_path.name}  vs  {b_path.name}")
    print(f"   fields {c['fields_a']} vs {c['fields_b']}; matched by path {c['matched']}; only in A {c['only_a']}, only in B {c['only_b']}")
    print(f"   names: identical {c.get('same_name', 0)}, same words {c.get('same_name_tokens', 0)}, renamed {c.get('renamed', 0)}"
          f" | types: {c.get('retyped', 0)} changed, patterns {c.get('pattern_changed', 0)} | descriptions {d['descriptions']}"
          f" | option captions changed {c.get('option_captions_changed', 0)}")
    for na, nb, path in d["renames"][:show]:
        print(f"      {na:40} -> {nb:40} {path.split('.')[-1][:24]}")
    if len(d["renames"]) > show:
        print(f"      ... {len(d['renames']) - show} more renames")
    for n, ta, tb in d["retypes"][:min(show, 8)]:
        print(f"      type {n:36} {ta} -> {tb}")
    if d["only_a"][:5] or d["only_b"][:5]:
        print(f"      only in A: {d['only_a'][:5]}{' ...' if len(d['only_a']) > 5 else ''} | only in B: {d['only_b'][:5]}{' ...' if len(d['only_b']) > 5 else ''}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("a", nargs="?", type=Path); ap.add_argument("b", nargs="?", type=Path)
    ap.add_argument("--pairs", action="store_true", help="the five test forms: committed vs runs/relabel/blueprints/<form>_relabel.bpt")
    ap.add_argument("--loop", action="store_true",
                    help="every runs/judge_eval side copy: pre-loop _v0 vs the current (post-loop) file; what the loop changed")
    ap.add_argument("--show", type=int, default=12)
    args = ap.parse_args()
    if args.pairs:
        from petey.validate.test_forms import forms
        for tf in forms("full"):
            a = BLUEPRINTS / f"{tf.stem}.bpt"; b = RUNS / "relabel" / "blueprints" / f"{tf.stem}_relabel.bpt"
            if a.exists() and b.exists():
                report(a, b, args.show)
            else:
                print(f"\n== {tf.stem}: missing {'committed' if not a.exists() else 'relabel'} side")
        return 0
    if args.loop:
        bdir = RUNS / "judge_eval" / "blueprints"
        tot = collections.Counter(); trans = collections.Counter(); forms = 0
        print(f"{'form':30} {'fields':>6} {'renamed':>7} {'retyped':>7} {'pattern':>7} {'desc +/~/-':>12}")
        for v0 in sorted(bdir.glob("*_v0.bpt")):
            cur = bdir / v0.name.replace("_v0", "")
            if not cur.exists():
                continue
            d = diff(v0, cur); c = d["counts"]; ds = d["descriptions"]; forms += 1
            for k in ("matched", "renamed", "retyped", "pattern_changed"):
                tot[k] += c.get(k, 0)
            for k in ("added", "changed", "removed"):
                tot[f"desc_{k}"] += ds.get(k, 0)
            for _, ta, tb in d["retypes"]:
                trans[f"{ta} -> {tb}"] += 1
            print(f"{v0.name[:-7][:30]:30} {c['matched']:6} {c.get('renamed', 0):7} {c.get('retyped', 0):7} {c.get('pattern_changed', 0):7} "
                  f"{ds.get('added', 0):>4}/{ds.get('changed', 0):<3}/{ds.get('removed', 0):<3}")
        print(f"\n{forms} forms, {tot['matched']} fields: renamed {tot['renamed']}, type or semantic_type changed {tot['retyped']}, "
              f"pattern changed {tot['pattern_changed']}, descriptions added {tot['desc_added']} / changed {tot['desc_changed']} / removed {tot['desc_removed']}")
        print("commonest type transitions (type/semantic_type):")
        for k, v in trans.most_common(args.show):
            print(f"   {v:4}  {k}")
        return 0
    report(args.a, args.b, args.show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
