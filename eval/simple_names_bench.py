"""The simple-naming benchmark (docs/PLAN_SIMPLE_NAMES.md): the standard arm (today's bulk runs) against the simple
arm (<form>_simple), per form, from the run records and the validated blueprints.

    PYTHONPATH=. venv/bin/python eval/simple_names_bench.py

Measures, per arm: round-0 flags by problem; type and semantic-type agreement with the validated blueprint (matched
by widget rect); subject agreement with the validated names (the suffix left out of both sides); tables on pattern
from the labeler and cells printed from parts; labeler output tokens and time; loop rounds, fields reviewed, end
state; dedup collisions.
"""
from __future__ import annotations

import collections
import glob
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field_identifiers as FI  # noqa: E402
from standardize_names import SUFFIXES  # noqa: E402

from petey.validate import grid_check as gc, hand_review as h  # noqa: E402

FORMS = {"acord_90_ny": ("je__acord_90_ny", "acord_90_ny_bulk5", "acord_90_ny_simple"),
         "f8825": ("je__f8825", "f8825_bulk3", "f8825_simple"),
         "ao040b": ("je__ao040b", "ao040b_bulk5", "ao040b_simple"),
         "imm5645": ("je__ircc_imm_5645", "imm5645_bulk3", "imm5645_simple")}


def subject_of(name: str, spec: dict, series) -> str:
    """The name's subject as the identifiers fill reads it, the suffix and iteration left out."""
    ident, _ = FI.read(name, spec, {}, None, series)
    sub = ident.get("subject") or ""
    toks = [t for t in sub.split("_") if t not in SUFFIXES]
    return "_".join(toks)


def rect_key(spec: dict):
    w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), None) or {}
    r = w.get("rect")
    return (w.get("page"), tuple(round(x) for x in r)) if r and w.get("page") else None


def by_rect(fields: dict) -> dict:
    out = {}
    for n, s in fields.items():
        if isinstance(s, dict):
            k = rect_key(s)
            if k:
                out[k] = (n, s)
    return out


def arm(tag: str, validated: dict) -> dict | None:
    rec = Path(f"runs/judge_eval/form_runs/{tag}.json")
    if not rec.exists():
        return None
    r = json.loads(rec.read_text())
    r0 = r["rounds"][0]
    bp0 = {**(r0.get("top") or {}), "fields": r0["fields"]}
    fields = {n: s for n, s in bp0["fields"].items() if isinstance(s, dict)}
    pc = r0["page_check"]
    flags = collections.Counter(v.get("problem") for v in pc.values() if v.get("verdict") == "flag")
    tabs = gc.tables(bp0)
    calls = []
    for f in sorted(glob.glob(f"runs/_calls/auto_label/{tag}/*/*.json")):
        j = json.load(open(f))
        if (j.get("when") or "") >= (r.get("started") or ""):
            calls.append((j.get("elapsed_s") or 0, (j.get("usage") or {}).get("output_tokens") or 0))
    # against the validated blueprint, by rect
    vr, rr = by_rect(validated), by_rect(fields)
    series_v = FI._series_index([n for n, s in validated.items() if isinstance(s, dict) and not FI._is_group(s)])
    series_r = FI._series_index([n for n, s in fields.items() if not FI._is_group(s)])
    both = [k for k in rr if k in vr]
    type_ok = sum(1 for k in both if rr[k][1].get("type") == vr[k][1].get("type"))
    sem_ok = sum(1 for k in both if (rr[k][1].get("semantic_type") or None) == (vr[k][1].get("semantic_type") or None))
    subj = collections.Counter()
    for k in both:
        a = subject_of(rr[k][0], rr[k][1], series_r)
        b = subject_of(vr[k][0], vr[k][1], series_v)
        subj["same" if a == b else "same words" if sorted(a.split("_")) == sorted(b.split("_")) else
             "overlap" if set(a.split("_")) & set(b.split("_")) else "different"] += 1
    loops = [x for x in r["rounds"] if x.get("stage") == "loop"]
    reviewed = sum((x.get("loop") or {}).get("review_run", {}).get("fields_reviewed") or 0 for x in loops)
    res = r.get("result") or {}
    dedup = ((r0.get("top") or {}).get("x_petey_dedup_log") or {}).get("duplicate_labels_reassigned")
    return {"fields": len(fields), "flags": sum(flags.values()), "flags_by": dict(flags),
            "matched": len(both), "type_ok": type_ok, "sem_ok": sem_ok, "subject": dict(subj),
            "tables": len(tabs), "on_pattern": sum(1 for t in tabs if t["on_pattern"]),
            "printed": sum(1 for s in fields.values() if s.get("x_petey_identifiers")),
            "label_calls": len(calls), "label_s": round(sum(c[0] for c in calls)), "label_tokens": sum(c[1] for c in calls),
            "rounds": len(loops), "reviewed": reviewed, "status": res.get("status") or "running", "collisions": dedup}


def main() -> int:
    paths = h.blueprint_paths()
    for form, (vid, std, simple) in FORMS.items():
        validated = h._load(h.working_path(vid, paths)).get("fields") or {}
        print(f"== {form} (validated: {vid}, {len(validated)} fields)")
        for label, tag in (("standard", std), ("simple", simple)):
            a = arm(tag, validated)
            if a is None:
                print(f"   {label:9} no record yet ({tag})")
                continue
            s = a["subject"]
            print(f"   {label:9} {a['fields']} fields | round 0: {a['flags']} flags {a['flags_by']} | vs validated ({a['matched']} matched by rect): "
                  f"type {a['type_ok']}, semantic {a['sem_ok']}, subject same {s.get('same', 0)} / same words {s.get('same words', 0)} / overlap {s.get('overlap', 0)} / different {s.get('different', 0)}")
            print(f"             tables {a['tables']} on pattern {a['on_pattern']}, printed {a['printed']} | labeler {a['label_calls']} calls {a['label_s']} s {a['label_tokens']} tokens | "
                  f"loop {a['rounds']} rounds, {a['reviewed']} reviewed, {a['status']} | collisions {a['collisions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
