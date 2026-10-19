"""The simple-naming benchmark (docs/PLAN_SIMPLE_NAMES.md): the standard arm (today's bulk runs) against the simple
arm (<form>_simple), per form, from the run records and the validated blueprints.

    PYTHONPATH=. venv/bin/python eval/simple_names_bench.py

Measures, per arm: round-0 flags by problem; type and semantic-type agreement with the validated blueprint (matched
by widget rect); subject agreement with the validated names (word sets, the kind of value left out of both sides); tables on pattern
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
from standardize_names import SUFFIXES  # noqa: E402

from petey.validate import grid_check as gc, hand_review as h  # noqa: E402

FORMS = {"acord_90_ny": ("je__acord_90_ny", "acord_90_ny_bulk5", "acord_90_ny_simple"),
         "f8825": ("je__f8825", "f8825_bulk3", "f8825_simple"),
         "ao040b": ("je__ao040b", "ao040b_bulk5", "ao040b_simple"),
         "imm5645": ("je__ircc_imm_5645", "imm5645_bulk3", "imm5645_simple")}


# the kind of value, in either scheme's spelling: left out of the subject comparison on both sides (the plan: the
# suffix is not part of what is compared). Abbreviations are spelled out first so `birth_dt` and `birth_date` meet.
SPELL = {"nm": "name", "dt": "date", "nbr": "number", "no": "number", "num": "number", "amt": "amount", "cnt": "count",
         "cd": "code", "qty": "quantity", "yr": "year", "pct": "percent", "txt": "text", "ind": "indicator"}
PHRASES = {"social_security_number": "ssn", "employer_identification_number": "ein",
           "taxpayer_identification_number": "tin", "employer_id_number": "ein"}
KIND = set(SUFFIXES) | {"name", "date", "number", "amount", "count", "code", "quantity", "year", "percent", "text",
                        "indicator", "checkbox", "flag"}
FILLER = {"a", "an", "the", "of", "and", "or", "from", "for", "to", "in", "on", "at", "by", "with", "if", "is"}


def words(name: str) -> frozenset:
    """The name's subject words: copy prefixes, iteration and part numbers, single letters (column / property
    letters), filler words and kind-of-value words left out, the same way for both arms."""
    s = name.split(".")[0].lower()
    for ph, ab in PHRASES.items():
        s = s.replace(ph, ab)
    toks = [SPELL.get(t, t) for t in s.split("_")]
    return frozenset(t for t in toks if t and not t.isdigit() and len(t) > 1 and t not in KIND and t not in FILLER
                     and not (t[:-1].isdigit() and t[-1].isalpha()) and not (t.startswith("copy") and t[4:].isdigit()))


def subject_class(a: str, b: str) -> str:
    wa, wb = words(a), words(b)
    if wa == wb:
        return "same"
    if wa < wb or wb < wa:
        return "nested"
    return "overlap" if wa & wb else "different"


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
    both = [k for k in rr if k in vr]
    type_ok = sum(1 for k in both if rr[k][1].get("type") == vr[k][1].get("type"))
    sem_ok = sum(1 for k in both if (rr[k][1].get("semantic_type") or None) == (vr[k][1].get("semantic_type") or None))
    subj = collections.Counter(subject_class(rr[k][0], vr[k][0]) for k in both)
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
                  f"type {a['type_ok']}, semantic {a['sem_ok']}, subject same {s.get('same', 0)} / nested {s.get('nested', 0)} / overlap {s.get('overlap', 0)} / different {s.get('different', 0)}")
            print(f"             tables {a['tables']} on pattern {a['on_pattern']}, printed {a['printed']} | labeler {a['label_calls']} calls {a['label_s']} s {a['label_tokens']} tokens | "
                  f"loop {a['rounds']} rounds, {a['reviewed']} reviewed, {a['status']} | collisions {a['collisions']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
