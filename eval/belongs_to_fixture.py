"""The 'belongs to another field' check against hand review (docs/TODO.md, "Distance when a tooltip belongs to
another field"). Every blueprint with hand-review verdicts; for each reviewed field, which text witnesses
(publisher, page, classifier) say its text belongs to another field, and what the person said.

The check exists for swaps and boxes placed one row off. Its targets are the fields the person flagged for their
NAME (`NAME_FLAGS`, picked by hand from the notes, 2026-10-09); its false alarms are the fields the person
accepted. A field counts once per witness. "Looked at" leaves out the verdicts written in bulk (`bulk: settled`,
`auto: only the tooltip check questioned it`): those were never seen, and the honed check found real slides among
them (ACORD 125 attachments, I-130 eye colour and race, f5500sf day / month).

    PYTHONPATH=. venv/bin/python eval/belongs_to_fixture.py --save runs/belongs_to/baseline.json
    PYTHONPATH=. venv/bin/python eval/belongs_to_fixture.py --against runs/belongs_to/baseline.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

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
}


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
        res = witness.witnesses(bpt, use_run=use_run)
        for name, rec in (v.get("verdicts") or {}).items():
            f = res["fields"].get(name)
            if f is None:
                continue
            note = rec.get("note") or ""
            wrong = rec["verdict"] == "flag" or bool(rec.get("edit"))
            belongs = {k: d for k, (val, d) in f["witnesses"].items()
                       if k in TEXT_WITNESSES and val is False and "belongs to:" in (d or "")}
            rows.append({"bid": bid, "field": name, "wrong": wrong, "name_flag": (bid, name) in NAME_FLAGS,
                         "bulk": note.startswith(("auto:", "bulk")), "note": note[:80], "belongs": belongs})
        print(f"  {bid}", file=sys.stderr)
    return rows


def table(rows: list[dict]) -> dict:
    out = {}
    for k in TEXT_WITNESSES + ("any",):
        hit = [r for r in rows if (r["belongs"] if k == "any" else k in r["belongs"])]
        out[k] = {"fired": len(hit),
                  "accepted": sum(1 for r in hit if not r["wrong"]),
                  "looked_at": sum(1 for r in hit if not r["wrong"] and not r["bulk"]),
                  "name_flags": sum(1 for r in hit if r["name_flag"]),
                  "other_flags": sum(1 for r in hit if r["wrong"] and not r["name_flag"])}
    return out


def show(rows: list[dict], label: str) -> None:
    t = table(rows)
    n_name = sum(1 for r in rows if r["name_flag"])
    print(f"\n{label}: {len(rows)} reviewed fields, {n_name} name flags")
    print(f"  {'witness':11} {'fired':>6} {'accepted':>9} {'(looked at)':>12} {'name flags':>11} {'other flags':>12}")
    for k, c in t.items():
        print(f"  {k:11} {c['fired']:>6} {c['accepted']:>9} {c['looked_at']:>12} {c['name_flags']:>8}/{n_name:<2} "
              f"{c['other_flags']:>12}")
    caught = {(r["bid"], r["field"]) for r in rows if r["name_flag"] and r["belongs"]}
    for bid, f in sorted(NAME_FLAGS):
        print(f"    {'caught' if (bid, f) in caught else 'missed'}  {bid} {f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--save", help="write the rows here")
    ap.add_argument("--against", help="a saved run to compare with")
    ap.add_argument("--no-run", action="store_true", help="publisher and page only (no class map, no judge)")
    ap.add_argument("--only", nargs="*", help="hand-review ids (e.g. lib__5021)")
    ap.add_argument("--list", action="store_true", help="every firing on an accepted field")
    args = ap.parse_args()
    rows = collect(use_run=not args.no_run, only=set(args.only) if args.only else None)
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(rows, indent=1))
    if args.against:
        old = json.loads(Path(args.against).read_text())
        keys = {(r["bid"], r["field"]) for r in rows}
        show([r for r in old if (r["bid"], r["field"]) in keys], f"before ({args.against})")
    show(rows, "now")
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
