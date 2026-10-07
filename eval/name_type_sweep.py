"""Report-only sweep: fields whose name suffix contradicts their type, and Y/N answers typed into text boxes.

Andrew, 2026-10-07, ACORD 126 page 2: `contractor_draw_plans_designs_specs_ind` is a one-letter text box the filer
types Y or N into ("Enter Y for a 'Yes' response. Input N for 'No' response"), typed `string` although its name
says indicator; every check passed it. This lists, without changing anything:

    yn_text         a text widget answered with Y / N: tooltip or description says to enter Y / N, or the box is
                    one character with a Y/N caption, and the field is not `boolean`
    suffix_type     the name's suffix and the type disagree: `_ind` not boolean, `_dt` not date, `_amt` not a
                    number, `_cnt` / `_count` not an integer (option groups skipped: their type is the group's)

    PYTHONPATH=. venv/bin/python eval/name_type_sweep.py [--show 5]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import yaml

from petey.paths import BLUEPRINTS, RUNS
from petey.validate import name_type
from petey.validate.retype import resolve_blank

_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def sweep(bpt: Path) -> list[dict]:
    """The same rules the review page shows (`petey.validate.name_type`), over one blueprint."""
    bp = yaml.load(bpt.read_text(encoding="utf-8"), Loader=_LOADER) or {}
    ml = name_type.text_maxlens(resolve_blank(bp))
    hits = []
    for name, s in (bp.get("fields") or {}).items():
        for r in name_type.check(name, s, ml.get(((s or {}).get("widget") or {}).get("path") or "")):
            m = re.search(r"ends `([^`]+)`", r["text"])
            hits.append({"kind": r["rule"], "field": name, "type": s.get("type"),
                         "suffix": m.group(1) if m else None, "fix": r["fix"],
                         "description": (s.get("description") or "")[:100]})
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--show", type=int, default=4)
    args = ap.parse_args()
    groups = {"fresh (T1/T2 and re-runs)": sorted((RUNS / "judge_eval" / "blueprints").glob("*.bpt")),
              "library": sorted(BLUEPRINTS.glob("*.bpt"))}
    report = {}
    for label, paths in groups.items():
        paths = [p for p in paths if not p.stem.endswith(("_v0", "_run1", "_prev"))]
        kinds, suffix, forms, examples = collections.Counter(), collections.Counter(), collections.Counter(), {}
        rows = []
        for p in paths:
            try:
                hits = sweep(p)
            except Exception as e:                       # a blueprint without a resolvable blank, say
                rows.append({"form": p.stem, "error": f"{type(e).__name__}: {e}"[:100]})
                continue
            for h in hits:
                kinds[h["kind"]] += 1
                forms[(h["kind"], p.stem)] += 1
                if h["kind"] == "suffix_type":
                    suffix[(h["suffix"], h["type"], h.get("widget_type"))] += 1
                key = h["kind"] if h["kind"] == "yn_text" else h["suffix"]
                examples.setdefault(key, [])
                if len(examples[key]) < args.show:
                    examples[key].append((p.stem, h["field"], h["type"], h["description"][:70]))
                rows.append({"form": p.stem, **h})
        report[label] = rows
        print(f"== {label}: {len(paths)} blueprints")
        print(f"   {dict(kinds)}")
        print(f"   Y/N text boxes in {len({f for k, f in forms if k == 'yn_text'})} forms; "
              f"most: {sorted(((c, f) for (k, f), c in forms.items() if k == 'yn_text'), reverse=True)[:5]}")
        for (lab, typ, wt), c in suffix.most_common(10):
            print(f"   {c:5}  {lab} typed {typ} (widget {wt})")
        for key, exs in examples.items():
            print(f"   e.g. {key}:")
            for e in exs:
                print(f"        {e}")
    out = RUNS / "judge_eval" / "name_type_sweep.json"
    out.write_text(json.dumps(report, indent=1, ensure_ascii=False))
    print(f"-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
