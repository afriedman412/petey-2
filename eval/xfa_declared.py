"""Check for STRATEGY_v1 §5 step 3: declared (XFA) vs inferred (semantic_types).

Re-emit a hybrid with `auto_label --no-llm`, then run this against the
committed blueprint. Fields join by AcroForm widget path (the committed
names are LLM slugs; the re-emit's are placeholders). Reports how many
fields now carry publisher-sourced pattern / required / values / type,
and where the inferred pattern disagrees with the declared one.

    venv/bin/python eval/xfa_declared.py --emitted runs/x.bpt --committed blueprints/vba21526ez.bpt
"""
from __future__ import annotations

import argparse
import collections
import re
from pathlib import Path

import yaml


def _by_path(bp: dict) -> dict[str, tuple[str, dict]]:
    out = {}
    for name, spec in bp.get("fields", {}).items():
        w = spec.get("widget")
        if w and w.get("path"):
            out[w["path"]] = (name, spec)
        for v, wb in (spec.get("widgets") or {}).items():
            if wb.get("path"):
                out[wb["path"]] = (f"{name}.{v}", spec)
    return out


def summarize_emitted(bp: dict) -> dict:
    c: collections.Counter = collections.Counter()
    for spec in bp.get("fields", {}).values():
        c["fields"] += 1
        x = spec.get("x_petey_xfa")
        if not x:
            continue
        c["joined"] += 1
        c[f"kind:{x.get('kind')}"] += 1
        if spec.get("x_petey_validation_source") == "xfa":
            c["validation_from_xfa"] += 1
        if "pattern" in spec and x.get("picture"):
            c["pattern_from_xfa"] += 1
        if spec.get("required"):
            c["required"] += 1
        if x.get("kind") in ("choice", "excl") and spec.get("values"):
            c["values_declared"] += 1
        if x.get("kind") in ("date", "num"):
            c["typed_from_xfa"] += 1
        if spec.get("x_petey_description_source") == "xfa_message":
            c["description_from_message"] += 1
        if x.get("message"):
            c["with_message"] += 1
    return dict(c)


def compare(emitted: dict, committed: dict) -> dict:
    e = _by_path(emitted)
    k = _by_path(committed)
    c: collections.Counter = collections.Counter()
    samples: dict[str, list] = collections.defaultdict(list)
    for path, (ename, espec) in e.items():
        if path not in k:
            c["emitted_only"] += 1
            continue
        cname, cspec = k[path]
        c["joined"] += 1
        ip, dp = cspec.get("pattern"), espec.get("pattern") if espec.get("x_petey_xfa", {}).get("picture") else None
        if ip and dp:
            key = "pattern:same" if ip == dp else "pattern:differ"
            c[key] += 1
            if key == "pattern:differ":
                samples[key].append((cname, ip, dp, espec["x_petey_xfa"]["picture"]))
        elif ip:
            c["pattern:inferred_only"] += 1
            kind = espec.get("x_petey_xfa", {}).get("kind")
            c[f"pattern:inferred_only:{kind}"] += 1
            if kind in ("date", "num"):
                samples["inferred_pattern_on_declared_" + kind].append((cname, ip, cspec.get("type"), espec.get("type")))
        elif dp:
            c["pattern:declared_only"] += 1
            samples["pattern:declared_only"].append((cname, dp, espec["x_petey_xfa"]["picture"]))
        else:
            c["pattern:neither"] += 1
        ct, et = cspec.get("type"), espec.get("type")
        if ct != et and espec.get("x_petey_xfa", {}).get("kind") in ("date", "num", "choice"):
            c[f"type:{ct}->{et}"] += 1
        if espec.get("required") and not cspec.get("required"):
            c["required:new"] += 1
        if cspec.get("values") and espec.get("values") and set(cspec["values"]) != set(espec["values"]):
            c["values:differ"] += 1
            samples["values:differ"].append((cname, cspec["values"], espec["values"]))
    c["committed_only"] = len(set(k) - set(e))
    return {"counts": dict(c), "samples": {k2: v[:12] for k2, v in samples.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--emitted", required=True, type=Path)
    ap.add_argument("--committed", type=Path)
    args = ap.parse_args()
    emitted = yaml.safe_load(args.emitted.read_text())
    print(f"== {args.emitted.name}: {summarize_emitted(emitted)}")
    if args.committed:
        committed = yaml.safe_load(args.committed.read_text())
        cc = collections.Counter()
        for s in committed["fields"].values():
            cc["fields"] += 1
            cc["pattern"] += "pattern" in s
            cc["required"] += bool(s.get("required"))
            cc["values"] += "values" in s
            cc[f"type:{s.get('type')}"] += 1
        print(f"== committed {args.committed.name}: {dict(cc)}")
        rep = compare(emitted, committed)
        print("== joined by widget path:", rep["counts"])
        for key, rows in rep["samples"].items():
            print(f"-- {key}")
            for r in rows:
                print("   ", r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
