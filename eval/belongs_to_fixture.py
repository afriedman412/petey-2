"""The 'belongs to another field' check against hand review (docs/TODO.md, "Distance when a tooltip belongs to
another field"). Every blueprint with hand-review verdicts; for each reviewed field, which text witnesses
(publisher, page, classifier) say its text belongs to another field, and what the person said.

The check exists for swaps and boxes placed one row off. Its targets are the fields the person flagged for their
NAME (`NAME_FLAGS`, picked by hand from the notes, 2026-10-09); its false alarms are the fields the person
accepted. A field counts once per witness. "Looked at" leaves out the verdicts written in bulk (`bulk: settled`,
`auto: only the tooltip check questioned it`): those were never seen, and the honed check found real slides among
them (ACORD 125 attachments, I-130 eye colour and race, f5500sf day / month).

A blueprint corrected by hand (`hand_review.apply_edits` leaves `x_petey_hand_edit` {from, to} on each field) is
judged as it was before: its renamed fields get their old names back in a copy saved under runs/belongs_to/before/
(`before_copy`), and every hand rename is a known name error alongside `NAME_FLAGS` (2026-10-13: ACORD 25's
corrected blocks). The catch rate is also given with each form weighted equally, so one form's many renames do not
swamp the rest.

    PYTHONPATH=. venv/bin/python eval/belongs_to_fixture.py --save runs/belongs_to/baseline.json
    PYTHONPATH=. venv/bin/python eval/belongs_to_fixture.py --against runs/belongs_to/baseline.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import yaml

from petey.paths import RUNS
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


def before_copy(bid: str, bpt: Path) -> tuple[Path, dict[str, str]]:
    """The blueprint as it was before its hand renames: each field whose `x_petey_hand_edit` changed its name gets
    the old name back (a chain A -> B -> C unwinds, since every field returns to its own `from`). Saved as
    runs/belongs_to/before/<bid>/<same file name>, so `witness.run_for` still finds the form's run. Returns the path
    to judge and {current name: old name}; the blueprint itself when nothing was renamed."""
    bp = yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}
    fields = bp.get("fields") or {}
    old = {}
    for n, spec in fields.items():
        he = spec.get("x_petey_hand_edit") if isinstance(spec, dict) else None
        was = ((he or {}).get("from") or {}).get("name")
        if was and was != n:
            old[n] = was
    if not old or len(set(old.values()) | (set(fields) - set(old))) != len(fields):
        return bpt, {}                      # nothing renamed, or the old names would collide: judge it as it is
    bp["fields"] = {old.get(n, n): spec for n, spec in fields.items()}
    out = BEFORE / bid / bpt.name
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return out, old


def collect(use_run: bool = True, only: set[str] | None = None) -> list[dict]:
    rows = []
    for vp in sorted((RUNS / "hand_review").glob("*.json")):
        bid = vp.stem
        if only and bid not in only:
            continue
        v = json.loads(vp.read_text())
        bpt = Path(v["blueprint"])
        if not bpt.exists():
            continue
        judged, old = before_copy(bid, bpt)
        res = witness.witnesses(judged, use_run=use_run)
        for name, rec in (v.get("verdicts") or {}).items():
            f = res["fields"].get(old.get(name, name))
            if f is None:
                continue
            note = rec.get("note") or ""
            wrong = rec["verdict"] == "flag" or bool(rec.get("edit"))
            # flags that count (an unconfirmed publisher flag is a hint: the page does not echo its tooltip)
            belongs = {k: d for k, (val, d) in f["witnesses"].items() if k in TEXT_WITNESSES and val is False
                       and "belongs to:" in (d or "") and not (d or "").startswith("unconfirmed")}
            # the model's other verdict: the text does not describe the name (5021: 'Parient Last Name')
            undescribed = {k: d for k, (val, d) in f["witnesses"].items() if k in TEXT_WITNESSES and val is False
                           and "does not describe" in (d or "") and not (d or "").startswith("unconfirmed")}
            rows.append({"bid": bid, "field": name, "before": old.get(name), "wrong": wrong or name in old,
                         "name_flag": (bid, name) in NAME_FLAGS,
                         "bulk": note.startswith(("auto:", "bulk")), "note": note[:80], "belongs": belongs,
                         "undescribed": undescribed})
        print(f"  {bid}", file=sys.stderr)
    return rows


def is_known(r: dict) -> bool:
    """A known name error: hand-picked (`NAME_FLAGS`, by its name then or now) or renamed by hand."""
    return bool(r.get("before")) or (r["bid"], r["field"]) in NAME_FLAGS or (r["bid"], r.get("before")) in NAME_FLAGS


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


def show(rows: list[dict], label: str, what: str = "belongs") -> None:
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
    for r in known:
        was = f" (was {r['before']})" if r.get("before") else ""
        print(f"    {'caught' if r.get(what) else 'missed'}  {r['bid']} {r['field']}{was}")


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
        show(rows, "now", "undescribed")
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
