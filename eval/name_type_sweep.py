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

import pymupdf
import yaml

from petey.paths import BLUEPRINTS, RUNS
from petey.validate.retype import resolve_blank

_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
YN_TEXT = re.compile(r"\b(enter|input|type)\s+[\"“']?y[\"”']?\b.*\byes\b|\binput\s+[\"“']?n[\"”']?\s+for\b|\bY\s*/\s*N\b", re.I)
SUFFIX = [(r"_ind$", {"boolean"}, "_ind (indicator)"), (r"_dt$", {"date"}, "_dt (date)"),
          (r"_amt$", {"number", "integer"}, "_amt (amount)"), (r"_(cnt|count)$", {"integer", "number"}, "_cnt (count)")]


def maxlens(blank: Path) -> dict[str, int]:
    out = {}
    with pymupdf.open(str(blank)) as doc:
        for pg in doc:
            for w in pg.widgets() or []:
                if w.field_type_string == "Text":
                    out[w.field_name] = w.text_maxlen or 0
    return out


def sweep(bpt: Path) -> list[dict]:
    bp = yaml.load(bpt.read_text(encoding="utf-8"), Loader=_LOADER) or {}
    blank = resolve_blank(bp)
    ml = maxlens(blank) if blank and blank.exists() else {}
    hits = []
    for name, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        w = s.get("widget") or {}
        typ = s.get("type")
        text = f"{s.get('description') or ''}"
        is_text = (w.get("widget_type") or "text") == "text"
        one = ml.get(w.get("path") or "", 0) == 1
        if is_text and typ != "boolean" and (YN_TEXT.search(text) or (one and re.search(r"\bY\b.*\bN\b", text))):
            hits.append({"kind": "yn_text", "field": name, "type": typ, "maxlen": ml.get(w.get("path") or ""),
                         "description": text[:100]})
            continue
        for pat, ok, label in SUFFIX:
            if re.search(pat, name) and typ not in ok:
                hits.append({"kind": "suffix_type", "suffix": label, "field": name, "type": typ,
                             "widget_type": w.get("widget_type"), "description": text[:80]})
                break
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
