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

from petey.label import text_match as TM  # noqa: E402
from petey.validate import grid_check as gc, hand_review as h  # noqa: E402

# per form: the validated blueprint, and each arm's runs. standard: the bulk runs of 15:38-16:42 and the _final
# runs of 17:27 (round 0 only: their loops died of the stream timeout), then _std on today's code (level with the
# simple arms on the loop and timing columns). simple v1 (17:51): no identifier kind, an indicator on a Y / N text box
# typed boolean. simple2 (18:02 on): those fixed.
FORMS = {"acord_90_ny": ("je__acord_90_ny", {"standard": ["acord_90_ny_bulk5", "acord_90_ny_std"],
                                             "simple v1": ["acord_90_ny_simple"],
                                             "simple2": ["acord_90_ny_simple2", "acord_90_ny_simple2b"]}),
         "f8825": ("je__f8825", {"standard": ["f8825_bulk3", "f8825_final", "f8825_std"], "simple v1": ["f8825_simple"],
                                 "simple2": ["f8825_simple2", "f8825_simple2b"]}),
         "ao040b": ("je__ao040b", {"standard": ["ao040b_bulk5", "ao040b_final", "ao040b_std"], "simple v1": [],
                                   "simple2": ["ao040b_simple2", "ao040b_simple2b"]}),
         "imm5645": ("je__ircc_imm_5645", {"standard": ["imm5645_bulk3", "imm5645_final", "imm5645_std"],
                                           "simple v1": ["imm5645_simple"],
                                           "simple2": ["imm5645_simple2", "imm5645_simple2b"]})}


# the kind of value, in either scheme's spelling: left out of the subject comparison on both sides (the plan: the
# suffix is not part of what is compared). Abbreviations are spelled out first (text_match.name_words, the name
# checks' table) so `birth_dt` and `birth_date` meet.
KIND = set(SUFFIXES) | {"name", "date", "number", "amount", "count", "code", "quantity", "year", "percent", "text",
                        "indicator", "checkbox", "flag", "description", "identification"}
FILLER = {"a", "an", "the", "of", "and", "or", "from", "for", "to", "in", "on", "at", "by", "with", "if", "is"}


def _stem(t: str) -> str:
    for end in ("ing", "ed", "es", "s"):
        if len(t) > len(end) + 3 and t.endswith(end):
            t = t[: -len(end)]
            break
    return t[:-1] if len(t) > 4 and t.endswith("e") else t


def words(name: str) -> list[str]:
    """The name's subject words, in order: copy prefixes, iteration and part numbers, single letters (column /
    property letters), filler words and kind-of-value words left out, the same way for both arms."""
    s = name.split(".")[0].lower()
    toks = TM.name_words(s).split()
    return [_stem(t) for t in toks if not t.isdigit() and len(t) > 1 and t not in KIND and t not in FILLER
            and not (t[:-1].isdigit() and t[-1:].isalpha()) and not (t.startswith("copy") and t[4:].isdigit())]


def _meet(xs: list[str], ys: list[str]) -> set:
    """xs's words with abbreviations and acronyms of ys's words written as ys's words ('csl' against 'combined
    single limit', 'veh' against 'vehicle')."""
    out = set()
    for t in xs:
        if t in ys:
            out.add(t)
            continue
        hit = next((w for w in ys if TM.abbreviates(t, w)), None)
        if hit:
            out.add(hit)
            continue
        acro = next((ys[i:i + len(t)] for i in range(len(ys) - len(t) + 1)
                     if len(t) >= 2 and "".join(w[0] for w in ys[i:i + len(t)]) == t), None)
        out.update(acro or [t])
    return out


def subject_class(a: str, b: str) -> str:
    wa0, wb0 = words(a), words(b)
    wa, wb = _meet(wa0, wb0), _meet(wb0, wa0)
    if wa == wb:
        return "same"
    if not wa or not wb:              # one name says nothing of the subject (`q2_description`)
        return "different"
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
    # text says nothing; `address` is the registry's street_address in an older blueprint's spelling
    sem = lambda f: (None if f.get("semantic_type") in (None, "", "text") else
                     {"address": "street_address"}.get(f["semantic_type"], f["semantic_type"]))
    sem_ok = sum(1 for k in both if sem(rr[k][1]) == sem(vr[k][1]))
    # where they differ: the run more specific than the validated blueprint (added), less (dropped), or both set and
    # different (conflict); validated blueprints leave many semantic types unset, so only dropped and conflict count
    # against an arm
    sem_added = sum(1 for k in both if sem(rr[k][1]) and not sem(vr[k][1]))
    sem_dropped = sum(1 for k in both if not sem(rr[k][1]) and sem(vr[k][1]))
    sem_conflict = sum(1 for k in both if sem(rr[k][1]) and sem(vr[k][1]) and sem(rr[k][1]) != sem(vr[k][1]))
    subj = collections.Counter(subject_class(rr[k][0], vr[k][0]) for k in both)
    loops = [x for x in r["rounds"] if x.get("stage") == "loop"]
    reviewed = sum((x.get("loop") or {}).get("review_run", {}).get("fields_reviewed") or 0 for x in loops)
    res = r.get("result") or {}
    from datetime import datetime
    mins = None
    if res.get("finished") and r.get("started"):
        f = "%Y-%m-%d %H:%M:%S"
        mins = round((datetime.strptime(res["finished"], f) - datetime.strptime(r["started"], f)).total_seconds() / 60, 1)
    last = r["rounds"][-1]
    pages = len({k[0] for k in rr})
    dlog = (r0.get("top") or {}).get("x_petey_dedup_log") or {}
    dedup = dlog.get("duplicate_labels_reassigned")
    kind = lambda n: ((fields.get(n) or {}).get("type"), (fields.get(n) or {}).get("semantic_type"))
    # the case a suffix separated: two fields with one subject and different kinds (a phone text box, a phone checkbox)
    by_kind = sum(1 for c in dlog.get("collisions") or [] if c.get("original_label") in fields
                  and kind(c["original_label"]) != kind(c.get("assigned_label")))
    return {"fields": len(fields), "flags": sum(flags.values()), "flags_by": dict(flags),
            "matched": len(both), "type_ok": type_ok, "sem_ok": sem_ok, "sem_added": sem_added,
            "sem_dropped": sem_dropped, "sem_conflict": sem_conflict, "subject": dict(subj),
            "tables": len(tabs), "on_pattern": sum(1 for t in tabs if t["on_pattern"]),
            "printed": sum(1 for s in fields.values() if s.get("x_petey_identifiers")),
            "label_calls": len(calls), "label_s": round(sum(c[0] for c in calls)), "label_tokens": sum(c[1] for c in calls),
            "rounds": len(loops), "reviewed": reviewed, "status": res.get("status") or "running", "collisions": dedup, "by_kind": by_kind,
            "minutes": mins, "pages": pages, "finished": bool(res.get("finished"))}


def main() -> int:
    paths = h.blueprint_paths()
    summary = []
    for form, (vid, arms) in FORMS.items():
        validated = h._load(h.working_path(vid, paths)).get("fields") or {}
        print(f"== {form} (validated: {vid}, {len(validated)} fields)")
        for label, tags in arms.items():
            for tag in tags:
                a = arm(tag, validated)
                if a is None:
                    continue
                s = a["subject"]
                summary.append((form, label, tag, a))
                print(f"   {label:9} {tag}: {a['fields']} fields | round 0: {a['flags']} flags {a['flags_by']} | vs validated ({a['matched']} matched by rect): "
                      f"type {a['type_ok']}, semantic {a['sem_ok']} (+{a['sem_added']} -{a['sem_dropped']} x{a['sem_conflict']}), subject same {s.get('same', 0)} / nested {s.get('nested', 0)} / overlap {s.get('overlap', 0)} / different {s.get('different', 0)}")
                print(f"             tables {a['tables']} on pattern {a['on_pattern']}, printed {a['printed']} | labeler {a['label_calls']} calls {a['label_s']} s {a['label_tokens']} tokens | "
                      f"loop {a['rounds']} rounds, {a['reviewed']} reviewed, {a['status']}, {a['minutes']} min | collisions {a['collisions']} ({a['by_kind']} between kinds)")
    # per page and per field, so forms of different sizes read on one scale (feedback: per page, not per form)
    print("\nsummary: round-0 flags per 100 fields; type / semantic agreement, semantic dropped (sem-) and "
          "conflicting (semx), subject same or nested, subject different: % of matched fields; labeler tokens and end-to-end minutes per page")
    print(f"   {'form':12} {'arm':9} {'run':24} {'flags':>6} {'type':>6} {'sem':>6} {'sem-':>6} {'semx':>6} {'subj':>6} {'diff':>6} {'tok/pg':>7} {'min/pg':>7}")
    for form, label, tag, a in summary:
        m = a["matched"] or 1
        s = a["subject"]
        pct = lambda n: f"{100 * n / m:.1f}"
        mp = f"{a['minutes'] / a['pages']:.1f}" if a["minutes"] else "-"
        print(f"   {form:12} {label:9} {tag:24} {100 * a['flags'] / max(1, a['fields']):6.1f} {pct(a['type_ok']):>6} {pct(a['sem_ok']):>6} "
              f"{pct(a['sem_dropped']):>6} {pct(a['sem_conflict']):>6} {pct(s.get('same', 0) + s.get('nested', 0)):>6} {pct(s.get('different', 0)):>6} {a['label_tokens'] / a['pages']:7.0f} {mp:>7}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
