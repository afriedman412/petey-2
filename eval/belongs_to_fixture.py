"""The 'belongs to another field' check against hand review (docs/TODO.md, "Distance when a tooltip belongs to
another field"). Every blueprint with hand-review verdicts; for each reviewed field, which text witnesses
(publisher, page, classifier) say its text belongs to another field, and what the person said.

The check exists for swaps and boxes placed one row off. Its targets are the fields the person flagged for their
NAME (`NAME_FLAGS`, picked by hand from the notes, 2026-10-09); its false alarms are the fields the person
accepted. A field counts once per witness. "Looked at" leaves out the verdicts written in bulk (`bulk: settled`,
`auto: only the tooltip check questioned it`): those were never seen, and the honed check found real slides among
them (ACORD 125 attachments, I-130 eye colour and race, f5500sf day / month).

A corrected blueprint is judged as it was generated (`before_copy`): the copy in git at `BASE`, from before the
2026-10-13/14 review round, with any earlier hand renames undone, matched to today's fields by widget (2026-10-14:
`x_petey_hand_edit` keeps only a field's last edit, so a later type fix hid a rename). Every rename whose old name
said another field (kind 'wrong') is a known name error alongside `NAME_FLAGS`; rewordings (clarity, suffix) are
not. Forms not in git undo `x_petey_hand_edit` instead. The catch rate is given per form, per pattern (number,
swap, shift, other) and with each form weighted equally, so one form's many renames do not swamp the rest.

    PYTHONPATH=. venv/bin/python eval/belongs_to_fixture.py --save runs/belongs_to/baseline.json
    PYTHONPATH=. venv/bin/python eval/belongs_to_fixture.py --against runs/belongs_to/baseline.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

from petey.paths import REPO, RUNS
from petey.validate import witness

TEXT_WITNESSES = ("publisher", "page", "classifier")

# fields the person flagged or corrected for their name: a swap, a box one row off, a wrong neighbour's name
NAME_FLAGS = {
    ("lib__5021", "patient_sex_cd"), ("lib__5021", "patient_birth_dt"),
    ("lib__2025-form-5500-sf", "waiver_ruling_letter_day"), ("lib__2025-form-5500-sf", "waiver_ruling_letter_month"),
    ("lib__2022_rev_form_1014r", "state_abbreviation_cd"), ("lib__2022_rev_form_1014r", "email_address_txt"),
    ("je__cms_10883", "treating_dentist_phone_prefix"),
    ("je__rdt120", "partnership_partners_names_line1"),
    # 2026-10-09 review of the honed check's firings and of lib__acord125
    ("lib__i-130", "parent_1_country_of_birth"), ("lib__i-130", "race_native_hawaiian_pacific_islander_ind"),
    ("lib__i-130", "race_black_or_african_american_ind"), ("lib__i-130", "eye_color_green_ind"),
    ("lib__i-130", "eye_color_gray_ind"), ("lib__i-130", "current_marriage_country"),
    ("lib__i-130", "current_marriage_province"), ("lib__i-130", "preparer_street_address_line_1_txt"),
    ("lib__i-130", "preparer_city_nm"),
    ("lib__acord125", "additional_interest_1_vehicle_txt"), ("lib__acord125", "additional_interest_1_boat_txt"),
    ("lib__acord125", "additional_interest_1_aircraft_txt"), ("lib__acord125", "additional_interest_1_airport_txt"),
    # 2026-10-12: from earlier hand flags ("should be ..."), for forms not yet in the set, so I-130 (9) weighs less
    ("lib__acord130", "contact_name_nm"), ("lib__acord130", "increased_limits_factor"),
    ("lib__acord130", "expense_constant_factor"),
    ("lib__acord25", "gl_policy_insr_ltr_cd"), ("lib__acord25", "auto_policy_insr_ltr_cd"),
    ("lib__acord25", "umbrella_policy_insr_ltr_cd"),
    ("je__al_dor_2848a", "taxpayer_signature"),
}


BEFORE = RUNS / "belongs_to" / "before"

# review-draft's base (2026-10-13 11:27): the blueprints before the Claude pass and most of Andrew's review. A field's
# `x_petey_hand_edit` keeps only its latest edit, so a type or caption fix after a rename hid the rename; the base
# copy, matched by box, has them all (docs/HANDOFF_2026-10-14.md, step 1)
BASE = "5f285d6"
KINDS = ("wrong", "clarity", "suffix", "type")

# renames with no kind on record (Andrew's own, a Groups rename, or one hidden by a later edit, and not in Claude's
# proposals), read by hand 2026-10-14: (form, name before) -> kind. 'wrong' = the old name says another field
UNRECORDED = {
    ("lib__acord125", "retail_stores_or_service_operations_pct"): "wrong",
    ("lib__acord125", "installation_service_repair_work_pct"): "wrong",     # the off-premises line's neighbour
    **{("lib__acord125", f"violation_{i}_{p}"): "clarity" for i in (1, 2)
       for p in ("occur_dt", "explanation", "resolution", "resolve_dt")},
    ("lib__faa8710", "designated_examiner_application_status"): "wrong",
    ("lib__faa8710", "aviation_safety_inspector_report_result"): "wrong",
    ("lib__faa8710", "asi"): "clarity",
    # renamed by hand on 2026-10-13 before the base: the shifted flight-time blocks and the action-taken boxes
    **{("lib__faa8710", f"{c}_class_totals_{k}_amt"): "wrong" for c in ("glider", "lighter_than_air")
       for k in ("sel", "mel", "ses", "mes")},
    **{("lib__faa8710", f"{c}_class_totals_{a}_{r}_amt"): "wrong" for c in ("powered_lift", "rotorcraft")
       for a in ("helo", "gyro") for r in ("pic", "sic")},
    ("lib__faa8710", "glider_rotorcraft_class_totals_helicopter_amt"): "wrong",
    ("lib__faa8710", "glider_rotorcraft_class_totals_gyroplane_amt"): "wrong",
    ("lib__faa8710", "reissue_exchange_certificate_ind"): "wrong",
    ("lib__faa8710", "change_of_name_nationality_gender_dob_ind"): "wrong",
    ("lib__faa8710", "sic_type_rating_issued_ind"): "wrong",
    ("lib__faa8710", "ground_instructor_certificate_issued_ind"): "wrong",
    ("lib__faa8710", "other_info"): "clarity",
    ("lib__i130", "foreign_address_unit_type"): "wrong",                   # the native-alphabet address's box
    **{("lib__cms855a", n): "clarity" for n in ("q8_position_title_txt", "title_txt", "business_structure",
                                                "action_type", "affiliation_type")},
    ("lib__i485", "a_num"): "clarity",
    ("lib__cms855i", "specialty_type"): "clarity",
    ("lib__ca540", "apt_no_txt"): "clarity",
    ("lib__ca540", "line_31_tax_amt"): "clarity",
    ("lib__form_1004", "supervisory_appraiser_interior_exterior_inspection_dt"): "clarity",
    ("lib__form_1004", "supervisory_appraiser_comparable_sales_inspection_dt"): "clarity",
    ("lib__form_1004", "effective_age_yr"): "suffix",
    ("lib__i765", "previously_filed_i765"): "clarity",
    ("je__cms_10883", "treating_dentist_phone_num"): "wrong",               # the phone boxes one place off
    ("je__cms_10883", "treating_dentist_phone_area_cd"): "wrong",
}


def _boxes(spec: dict) -> list:
    ws = [spec["widget"]] if isinstance(spec.get("widget"), dict) else []
    ws += [w for w in (spec.get("widgets") or {}).values() if isinstance(w, dict)]
    return [(w.get("page"), w.get("path") or tuple(round(x) for x in w.get("rect") or ())) for w in ws]


def _at_base(bpt: Path) -> dict | None:
    try:
        rel = bpt.resolve().relative_to(REPO)
    except ValueError:
        return None
    r = subprocess.run(["git", "show", f"{BASE}:{rel}"], cwd=REPO, capture_output=True, text=True)
    return (yaml.safe_load(r.stdout) or {}) if r.returncode == 0 else None


def _kind(bid: str, spec: dict, was: str, props: dict) -> str:
    """Why `was` became this field's name: its edit's kind when the edit starts from `was`, else Claude's proposal
    for `was`, else `UNRECORDED`. Unknown counts as wrong (a warning), as hand renames did before."""
    he = spec.get("x_petey_hand_edit") or {}
    if ((he.get("from") or {}).get("name") == was) and he.get("kind") in KINDS:
        return he["kind"]
    if (props.get(was) or {}).get("kind") in KINDS[:3]:
        return props[was]["kind"]
    if (bid, was) in UNRECORDED:
        return UNRECORDED[(bid, was)]
    print(f"  warning: {bid} {was}: rename with no kind on record, counted as wrong", file=sys.stderr)
    return "wrong"


def _unwind(fields: dict) -> dict[str, str]:
    """{name: name before its `x_petey_hand_edit` rename}; a chain A -> B -> C unwinds, since every field returns to
    its own `from`. Empty when the old names would collide."""
    old = {}
    for n, spec in fields.items():
        was = (((spec or {}).get("x_petey_hand_edit") or {}).get("from") or {}).get("name")
        if was and was != n:
            old[n] = was
    if len(set(old.values()) | (set(fields) - set(old))) != len(fields):
        return {}
    return old


def _save(bid: str, bpt: Path, bp: dict) -> Path:
    """Saved as runs/belongs_to/before/<bid>/<same file name>, so `witness.run_for` still finds the form's run."""
    out = BEFORE / bid / bpt.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return out


def before_copy(bid: str, bpt: Path) -> tuple[Path, dict[str, str | None], dict[str, str]]:
    """The blueprint as generated, to judge, with {current name: name in it (None: no one field there holds the same
    boxes, e.g. a group made from loose boxes)} and {current name: kind of rename} for the fields renamed since.

    From git: the blueprint at `BASE` with its own hand renames undone (FAA 8710's were made that morning), each
    current field matched to the base field holding the same widgets. A rename's kind is 'wrong' when either step
    (before the base, after it) was. Forms not in git (the judge-eval side copies) undo `x_petey_hand_edit`."""
    now = (yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}).get("fields") or {}
    base = _at_base(bpt)
    pp = RUNS / "claude_pass" / "proposals" / f"{bid}.json"
    props = {c.get("field"): c for c in json.loads(pp.read_text())["changes"]} if pp.exists() else {}
    if base is None:
        old = _unwind(now)
        kinds = {n: _kind(bid, now[n], w, props) for n, w in old.items()}
        if not old:
            return bpt, {}, {}
        bp = yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}
        bp["fields"] = {old.get(n, n): s for n, s in now.items()}
        return _save(bid, bpt, bp), {n: old.get(n, n) for n in now}, kinds
    bfields = base.get("fields") or {}
    undo = _unwind(bfields)
    base["fields"] = {undo.get(n, n): s for n, s in bfields.items()}
    owner = {k: n for n, s in bfields.items() if isinstance(s, dict) for k in _boxes(s)}
    claimed = collections.Counter()
    match = {}
    for n, s in now.items():
        src = {owner.get(k) for k in _boxes(s) if isinstance(s, dict)} - {None}
        match[n] = next(iter(src)) if len(src) == 1 else None
        claimed[match[n]] += 1
    names, kinds = {}, {}
    for n, b in match.items():
        if b is None or claimed[b] > 1:          # a split box set: no one field to compare
            names[n] = None
            continue
        names[n] = undo.get(b, b)
        steps = ([_kind(bid, bfields[b], undo[b], {})] if b in undo else []) + \
                ([_kind(bid, now[n], b, props)] if b != n else [])
        if steps:
            kinds[n] = "wrong" if "wrong" in steps else steps[-1]
    return _save(bid, bpt, base), names, kinds


def collect(use_run: bool = True, only: set[str] | None = None) -> list[dict]:
    rows = []
    for vp in sorted((RUNS / "hand_review").glob("*.json")):
        bid = vp.stem
        if only and bid not in only:
            continue
        v = json.loads(vp.read_text())
        if "blueprint" not in v:                 # runs/hand_review/focus.json: the picker's list, not a record
            continue
        bpt = Path(v["blueprint"])
        if not bpt.exists():
            continue
        judged, old, kinds = before_copy(bid, bpt)
        res = witness.witnesses(judged, use_run=use_run)
        for name, rec in (v.get("verdicts") or {}).items():
            if old and old.get(name) is None:
                continue                         # not in the copy judged (deleted since, or no one field then)
            was = old.get(name, name)
            f = res["fields"].get(was)
            if f is None:
                continue
            note = rec.get("note") or ""
            kind = kinds.get(name)
            # a wrong NAME: renamed because the old name said another field, flagged (unless the rename only
            # reworded it), or a rename not yet applied; a type-only edit leaves the name right (2026-10-13, FAA
            # 8710's money -> count)
            wrong = (kind == "wrong" or (rec["verdict"] == "flag" and kind not in KINDS[1:])
                     or ("name" in (rec.get("edit") or {}) and not rec.get("applied")))
            # flags that count (an unconfirmed publisher flag is a hint: the page does not echo its tooltip)
            belongs = {k: d for k, (val, d) in f["witnesses"].items() if k in TEXT_WITNESSES and val is False
                       and "belongs to:" in (d or "") and not (d or "").startswith("unconfirmed")}
            # the model's other verdict: the text does not describe the name (5021: 'Parient Last Name')
            undescribed = {k: d for k, (val, d) in f["witnesses"].items() if k in TEXT_WITNESSES and val is False
                           and "does not describe" in (d or "") and not (d or "").startswith("unconfirmed")}
            rows.append({"bid": bid, "field": name, "before": was if was != name else None, "kind": kind,
                         "pattern": pattern(name, was, old) if kind == "wrong" else None,
                         "wrong": wrong, "name_flag": (bid, name) in NAME_FLAGS,
                         "bulk": note.startswith(("auto:", "bulk")), "note": note[:80], "belongs": belongs,
                         "undescribed": undescribed})
        print(f"  {bid}", file=sys.stderr)
    return rows


def pattern(name: str, was: str, old: dict) -> str:
    """What kind of name error: 'number' (only a number differs: line 1 for line 2), 'swap' (two fields had each
    other's names), 'shift' (the old name is another field's now: a block one row off), 'other' (a name no field
    has: a misreading, or a combined name)."""
    if re.sub(r"\d+", "#", was) == re.sub(r"\d+", "#", name):
        return "number"
    if was in old:                               # another field is called that now
        return "swap" if old[was] == name else "shift"
    return "other"


def is_known(r: dict) -> bool:
    """A known name error: hand-picked (`NAME_FLAGS`, by its name then or now) or renamed because the old name said
    another field. Rows saved before kinds were recorded count any rename."""
    renamed = r.get("kind") == "wrong" if "kind" in r else bool(r.get("before"))
    return renamed or (r["bid"], r["field"]) in NAME_FLAGS or (r["bid"], r.get("before")) in NAME_FLAGS


def table(rows: list[dict], what: str = "belongs") -> dict:
    for r in rows:
        r["name_flag"] = is_known(r)
    out = {}
    for k in TEXT_WITNESSES + ("any",):
        hit = [r for r in rows if (r.get(what) if k == "any" else k in (r.get(what) or {}))]
        out[k] = {"fired": len(hit),
                  "accepted": sum(1 for r in hit if not r["wrong"]),
                  "looked_at": sum(1 for r in hit if not r["wrong"] and not r["bulk"]),
                  "name_flags": sum(1 for r in hit if r["name_flag"]),
                  "other_flags": sum(1 for r in hit if r["wrong"] and not r["name_flag"])}
    return out


def show(rows: list[dict], label: str, what: str = "belongs", detail: bool = True) -> None:
    t = table(rows, what)
    n_name = sum(1 for r in rows if r["name_flag"])
    print(f"\n{label} [{what}]: {len(rows)} reviewed fields, {n_name} name flags")
    print(f"  {'witness':11} {'fired':>6} {'accepted':>9} {'(looked at)':>12} {'name flags':>11} {'other flags':>12}")
    for k, c in t.items():
        print(f"  {k:11} {c['fired']:>6} {c['accepted']:>9} {c['looked_at']:>12} {c['name_flags']:>8}/{n_name:<2} "
              f"{c['other_flags']:>12}")
    known = sorted((r for r in rows if r["name_flag"]), key=lambda r: (r["bid"], r["field"]))
    by_form = collections.defaultdict(list)
    for r in known:
        by_form[r["bid"]].append(bool(r.get(what)))
    if by_form:
        print(f"  caught, each form weighted equally: {sum(sum(v) / len(v) for v in by_form.values()) / len(by_form):.0%} "
              f"over {len(by_form)} forms")
    if detail:
        for r in known:
            was = f" (was {r['before']})" if r.get("before") else ""
            print(f"    {'caught' if r.get(what) else 'missed'}  {r['bid']} {r['field']}{was}  [{r.get('pattern') or 'flag'}]")
    print(f"\n  {'form':28} {'caught':>8} {'false alarms (looked at)':>25}")
    for bid in sorted({r["bid"] for r in rows}):
        rs = [r for r in rows if r["bid"] == bid]
        k = [r for r in rs if r["name_flag"]]
        fa = [r for r in rs if r.get(what) and not r["wrong"]]
        if k or fa:
            print(f"  {bid:28} {sum(bool(r.get(what)) for r in k):>3}/{len(k):<4} "
                  f"{len(fa):>10} ({sum(not r['bulk'] for r in fa)})")
    pats = collections.defaultdict(list)
    for r in known:
        pats[r.get("pattern") or "flag"].append(bool(r.get(what)))
    print("  by pattern: " + ", ".join(f"{p} {sum(v)}/{len(v)}" for p, v in sorted(pats.items())))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--save", help="write the rows here")
    ap.add_argument("--against", help="a saved run to compare with")
    ap.add_argument("--no-run", action="store_true", help="publisher and page only (no class map, no judge)")
    ap.add_argument("--only", nargs="*", help="hand-review ids (e.g. lib__5021)")
    ap.add_argument("--list", action="store_true", help="every firing on an accepted field")
    ap.add_argument("--load", help="show a saved run (--save) instead of computing one")
    args = ap.parse_args()
    rows = (json.loads(Path(args.load).read_text()) if args.load
            else collect(use_run=not args.no_run, only=set(args.only) if args.only else None))
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(rows, indent=1))
    if args.against:
        old = json.loads(Path(args.against).read_text())
        keys = {(r["bid"], r["field"]) for r in rows}
        show([r for r in old if (r["bid"], r["field"]) in keys], f"before ({args.against})")
    show(rows, "now")
    if any(r.get("undescribed") for r in rows):
        show(rows, "now", "undescribed", detail=False)
    if args.against:
        was = {(r["bid"], r["field"]): r["belongs"] for r in old}
        gone = collections.Counter()
        for r in rows:
            for k in set(was.get((r["bid"], r["field"]), {})) - set(r["belongs"]):
                gone["name flag" if r["name_flag"] else ("accepted" if not r["wrong"] else "other flag")] += 1
        print(f"\n  firings removed: {dict(gone)}")
    if args.list:
        for r in rows:
            if r["belongs"] and not r["wrong"]:
                for k, d in r["belongs"].items():
                    print(f"  {r['bid']:32} {r['field']:45} {k:10} {d[-110:]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
