"""Is the judge informative? Sort its disagreements by cause, and see whether it touches the fields that look misnamed.

For each form run through the loop as a side copy (`runs/judge_eval/<form>_loop.json`, blueprint before the loop at
`runs/judge_eval/blueprints/<form>_v0.bpt`), take the first loop round's run (the judge on the v0 blueprint) and:

1. every field where the judge disagrees with ground truth while native agrees (`method_delta.compare_case`), over
   the case set, sorted into a cause by rule (below); `unexplained` is what is left for a person to read;
2. an independent misname screen: the field's name against the caption the page classifier read for its box (token
   overlap after light normalisation); a field whose name shares nothing with a readable caption is a candidate;
3. what the loop did: flags sent to the reviewer by source, edits kept, and which source each kept edit came from.

Causes, in the order tested:
    format          method_delta cause numeric / substring / date_format / punctuation / boolean
    layout_shift    a swap, a value returned where the case left the box empty (phantom), or a wrong value traced to
                    another field's ground truth: the empty-cell / column family
    code_cell       the page classed the box `code`
    mark_cell       the page classed the box `option` and the field holds a typed X
    unmarked_group  an option field the case left unmarked, answered by the judge
    implausible     the judge found nothing and the page classed the box `other` / `free_text` (a bank value
                    the box would not hold)
    unexplained     none of the above

    PYTHONPATH=. venv/bin/python eval/judge_informativeness.py [--forms a,b] [--out runs/judge_eval/informativeness.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.synth.boxes import match_rect, parse_rect_key  # noqa: E402
from petey.validate import method_delta, review  # noqa: E402
from petey.validate.name_caption import tokens  # noqa: E402

EVAL = Path("runs/judge_eval")
FORMAT = {"numeric", "substring", "date_format", "punctuation", "boolean"}
def class_boxes(case: Path) -> dict:
    cm = json.loads((case / "class_map.json").read_text())["boxes"]
    by_page = collections.defaultdict(list)
    for k, b in cm.items():
        page, rect = parse_rect_key(k)
        by_page[page].append({"rect": rect, "label": b.get("label"), "class": b.get("class")})
    return by_page


def page_box(spec: dict, by_page) -> dict:
    w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
    if not w.get("rect"):
        return {}
    return match_rect(w["rect"], by_page.get(w.get("page"), [])) or {}


def _k(v) -> str:
    return re.sub(r"\s+", " ", str(v).strip().lower()) if v not in (None, "", False, []) else ""


def cause_of(r: dict, spec: dict, box: dict, judge_vals: dict, gt_vals: dict) -> str:
    """judge_vals / gt_vals: field -> comparable value, for every field of this case."""
    c = r.get("cause") or r.get("verdict")
    gt, got = r.get("gt"), r.get("judge", r.get("petey"))
    empty = lambda v: v in (None, "", False, [])  # noqa: E731
    if c in FORMAT:
        return "format"
    if r.get("swap_with") or c == "phantom" or (empty(gt) and not empty(got)):
        return "layout_shift"
    # this field's value was given to another field, or the judge gave this field another field's value
    f = r["field"]
    if _k(gt) and any(v == _k(gt) for g, v in judge_vals.items() if g != f):
        return "layout_shift"
    if _k(got) and any(v == _k(got) for g, v in gt_vals.items() if g != f):
        return "layout_shift"
    if box.get("class") == "code":
        return "code_cell"
    if box.get("class") == "option" and str(gt).strip().upper() == "X":
        return "mark_cell"
    if (spec.get("widgets") or spec.get("type") in ("category", "boolean")) and empty(gt):
        return "unmarked_group"
    if empty(got) and box.get("class") in ("other", "free_text"):
        return "implausible"
    return "unexplained"


def analyse(form: str) -> dict:
    loop = json.loads((EVAL / f"{form}_loop.json").read_text())
    run = Path("runs") / loop["iterations"][0]["run"]
    bp0 = yaml.safe_load((EVAL / "blueprints" / f"{form}_v0.bpt").read_text())
    bp1 = yaml.safe_load((EVAL / "blueprints" / f"{form}.bpt").read_text())
    fields0 = bp0.get("fields") or {}
    cases = sorted(run.glob("case_*_intact"))
    boxes = class_boxes(cases[0])

    # 1. judge disagreements by cause (a field's cause = its most frequent over the cases)
    per_field: dict[str, list[str]] = collections.defaultdict(list)
    rows_by_field: dict[str, dict] = {}
    for c in cases:
        arm = method_delta.preferred_judge(c)
        if not arm:
            continue
        sc = json.loads((c / f"score_{arm}.json").read_text())["per_field"]
        judge_vals = {p["field"]: _k(p.get("extracted_value")) for p in sc}
        gt_vals = {p["field"]: _k(p.get("gt_value")) for p in sc}
        for r in method_delta.compare_case(c, arm):
            spec = fields0.get(r["field"], {})
            per_field[r["field"]].append(cause_of(r, spec, page_box(spec, boxes), judge_vals, gt_vals))
            rows_by_field.setdefault(r["field"], r)
    causes = {f: collections.Counter(cs).most_common(1)[0][0] for f, cs in per_field.items()}

    # 2. misname screen: name vs the caption read for the box
    screen = []
    for name, spec in fields0.items():
        box = page_box(spec, boxes)
        cap = box.get("label")
        if not cap or box.get("class") in ("none", "option") or spec.get("widgets"):
            continue
        if (spec.get("widget") or {}).get("widget_type") in ("checkbox", "radiobutton"):
            continue      # a box inside a larger caption cell matches the cell, not its own caption
        nt, ct = tokens(name), tokens(cap)
        if ct and nt and not (nt & ct):
            screen.append({"field": name, "caption": cap, "judge_disagrees": name in causes,
                           "judge_cause": causes.get(name)})

    # 3. what the loop did
    flags = review.flags_from_run(run)
    def kinds(rs):
        return sorted({r.get("kind") or r.get("reason") or r.get("detector") or "?" for r in rs})
    flag_src = collections.Counter(k for rs in flags.values() for k in kinds(rs))
    kept = []
    for name, spec in (bp1.get("fields") or {}).items():
        rv = spec.get("x_petey_review")
        if not rv:
            continue
        old = rv.get("old_name") or name
        kept.append({"field": old, "now": name, "sources": kinds(flags.get(old, flags.get(name, []))),
                     "verdict": rv.get("verdict"), "changed": (rv.get("changed") or rv.get("applied"))})
    unexplained = [{"field": f, "caption": page_box(fields0.get(f, {}), boxes).get("label"),
                    "gt": rows_by_field[f].get("gt"), "judge": rows_by_field[f].get("judge"),
                    "cause_raw": rows_by_field[f].get("cause"), "description": (fields0.get(f) or {}).get("description")}
                   for f, c in causes.items() if c == "unexplained"]
    return {"form": form, "run": run.name, "fields": len(fields0), "status": loop["status"],
            "disagreements": len(causes), "by_cause": dict(collections.Counter(causes.values())),
            "unexplained": unexplained, "misname_screen": screen,
            "screen_judged": sum(1 for s in screen if s["judge_disagrees"]),
            "flags": len(flags), "flags_by_source": dict(flag_src), "kept_edits": kept,
            "review_cost": sum((it.get("review_run") or {}).get("cost_usd") or 0 for it in loop["iterations"])}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", default=None, help="default: every form with a loop result under runs/judge_eval")
    ap.add_argument("--out", type=Path, default=EVAL / "informativeness.json")
    args = ap.parse_args()
    forms = (args.forms.split(",") if args.forms else
             sorted(p.name[:-len("_loop.json")] for p in EVAL.glob("*_loop.json")))
    res = []
    for f in forms:
        try:
            res.append(analyse(f))
        except Exception as e:
            print(f"{f}: skipped ({e!r})")
    tot = collections.Counter()
    print(f"{'form':<26}{'fields':>7}{'disagr':>7}{'unexpl':>7}{'screen':>7}{'scr&jdg':>8}{'flags':>6}"
          f"{'judge-flag edits':>17}{'other edits':>12}")
    for r in res:
        je = sum(1 for k in r["kept_edits"] if "name_reader" in k["sources"])
        oe = len(r["kept_edits"]) - je
        print(f"{r['form']:<26}{r['fields']:>7}{r['disagreements']:>7}{r['by_cause'].get('unexplained', 0):>7}"
              f"{len(r['misname_screen']):>7}{r['screen_judged']:>8}{r['flags']:>6}{je:>17}{oe:>12}")
        tot.update(r["by_cause"])
        tot["_fields"] += r["fields"]; tot["_disagreements"] += r["disagreements"]
        tot["_screen"] += len(r["misname_screen"]); tot["_screen_judged"] += r["screen_judged"]
        tot["_judge_edits"] += je; tot["_other_edits"] += oe
    print("\ntotals:", {k: v for k, v in tot.items() if k.startswith("_")})
    print("disagreements by cause:", {k: v for k, v in tot.most_common() if not k.startswith("_")})
    args.out.write_text(json.dumps(res, indent=1, default=str))
    print(f"[ok] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
