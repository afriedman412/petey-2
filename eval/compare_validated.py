"""A fresh run against the form's validated blueprint (Andrew, 2026-10-20: "run a couple forms that I've validated
and score on comparison"). Boxes are matched by page and widget rect (both come from the same form layer):

  extraction   values filled into the blank and read back wrong, first and last loop round (the measure that counts)
  coverage     validated fields and options the run has, misses, and adds (matched by position)
  groups       validated option groups the run groups the same (same boxes), and how many it left split or merged
  names        exact name match, and subject agreement with the suffix left out (simple_names_bench.subject_class)
  types        type agreement on matched boxes; semantic types dropped or conflicting (not counted: the run being
               more specific than the validated blueprint)

    PYTHONPATH=. venv/bin/python eval/compare_validated.py <run> <validated id> [<run> <validated id> ...]
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from simple_names_bench import subject_class  # noqa: E402

from petey.paths import RUNS  # noqa: E402
from petey.validate import hand_review as h  # noqa: E402


def _key(w: dict):
    r = w.get("rect")
    return (w.get("page"), tuple(round(x) for x in r)) if r and w.get("page") else None


def boxes(fields: dict) -> dict:
    """{box: (field name, spec, option key or None)} for every widget of every field."""
    out = {}
    for n, s in fields.items():
        if not isinstance(s, dict):
            continue
        if s.get("widgets"):
            for opt, w in s["widgets"].items():
                if _key(w):
                    out[_key(w)] = (n, s, opt)
        elif _key(s.get("widget") or {}):
            out[_key(s["widget"])] = (n, s, None)
    return out


def groups(fields: dict) -> dict[str, frozenset]:
    return {n: frozenset(_key(w) for w in s["widgets"].values() if _key(w))
            for n, s in fields.items() if isinstance(s, dict) and len(s.get("widgets") or {}) > 1}


# what Andrew has ruled the same (2026-10-20): any name is `name`; dates identical to iso_date are iso_date; a
# boolean's `indicator` says nothing its type does not; `text` says nothing; `address` is street_address's old spelling
SAME = {"first_name": "name", "last_name": "name", "business_name": "name", "entity_name": "name",
        "person_name": "name", "birth_date": "iso_date", "service_date": "iso_date", "address": "street_address"}


def sem(s):
    st = s.get("semantic_type")
    if st in (None, "", "text") or (st == "indicator" and s.get("type") == "boolean"):
        return None
    return SAME.get(st, st)


def compare(run: str, vid: str, paths: dict) -> dict:
    val = h._load(h.working_path(vid, paths)).get("fields") or {}
    gen = yaml.safe_load((RUNS / "judge_eval" / "blueprints" / f"{run}.bpt").read_text()).get("fields") or {}
    rec = json.loads((RUNS / "judge_eval" / "form_runs" / f"{run}.json").read_text())
    vb, gb = boxes(val), boxes(gen)
    both = vb.keys() & gb.keys()
    scalar = [k for k in both if vb[k][2] is None and gb[k][2] is None]
    vg, gg = groups(val), groups(gen)
    gsets = set(gg.values())
    same_groups = sum(1 for s in vg.values() if s in gsets)
    split = sum(1 for s in vg.values() if s not in gsets and sum(1 for k in s if k in gb and gb[k][2] is not None) < len(s))
    subj = collections.Counter(subject_class(gb[k][0], vb[k][0]) for k in scalar)
    loops = [x["loop"]["verdicts"] for x in rec["rounds"] if x.get("stage") == "loop" and (x.get("loop") or {}).get("verdicts")]
    bad = lambda v: v.get("differ", 0) + v.get("extract_miss", 0)       # noqa: E731
    return {
        "run": run, "validated": vid, "boxes": len(vb),
        "found": len(both), "missed": len(vb.keys() - gb.keys()), "extra": len(gb.keys() - vb.keys()),
        "groups": len(vg), "groups_same": same_groups, "groups_split": split,
        "scalar": len(scalar), "name_exact": sum(1 for k in scalar if gb[k][0] == vb[k][0]),
        "subject_ok": subj.get("same", 0) + subj.get("nested", 0), "subject_different": subj.get("different", 0),
        "type_ok": sum(1 for k in scalar if gb[k][1].get("type") == vb[k][1].get("type")),
        "sem_bad": sum(1 for k in scalar if sem(vb[k][1]) and sem(gb[k][1]) != sem(vb[k][1])),
        "wrong_first": bad(loops[0]) if loops else None, "wrong_last": bad(loops[-1]) if loops else None,
        "read": (loops[0].get("agree", 0) + bad(loops[0])) if loops else None,
        "flags0": sum(1 for v in rec["rounds"][0]["page_check"].values() if v.get("verdict") == "flag"),
    }


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "-"


def main() -> int:
    args = sys.argv[1:]
    paths = h.blueprint_paths()
    print("| run | wrong read back (first, last round) | fields and options found / missed / extra | groups same | names exact "
          "| subject ok / different | type ok | semantic dropped or off | round-0 flags |")
    print("|---|---|---|---|---|---|---|---|---|")
    for run, vid in zip(args[::2], args[1::2]):
        c = compare(run, vid, paths)
        wr = f"{c['wrong_first']}, {c['wrong_last']} of {c['read']}" if c["read"] else "-"
        print(f"| {run} | {wr} | {c['found']} / {c['missed']} / {c['extra']} of {c['boxes']} "
              f"| {c['groups_same']} of {c['groups']} | {pct(c['name_exact'], c['scalar'])} "
              f"| {pct(c['subject_ok'], c['scalar'])} / {c['subject_different']} | {pct(c['type_ok'], c['scalar'])} "
              f"| {c['sem_bad']} | {c['flags0']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
