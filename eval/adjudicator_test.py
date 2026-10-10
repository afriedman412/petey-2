"""The rename adjudicator against the fields checked by eye on 2026-09-30 / 10-01, before it is used in the loop.

Each case is a rename the reviewer proposed in batch 1 / 2 (or would have, had it followed the caption: KS DO-10,
where it kept the publisher's names), with the verdict a person reached on the rendered page (one of them, SS-4
`ein`, corrected after the adjudicator's crop showed the hand check was wrong). Sonnet 4.6 and Opus 5 both agree
with every case (2026-10-01; $0.12 and $0.22 for the nineteen). The adjudicator is
forced on every case (in the loop it runs only on contested renames; `contested` below says what the loop would
have done). Blueprints are the side copies before the loop (`runs/judge_eval/blueprints/<form>_v0.bpt`).

    PYTHONPATH=. venv/bin/python eval/adjudicator_test.py [--model claude-sonnet-4-6] [--only do10,rdt120]
        [--json runs/judge_eval/adjudicator_test_<model>.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.paths import RUNS  # noqa: E402
from petey.synth.local import widget_limits  # noqa: E402
from petey.validate import adjudicate  # noqa: E402
from petey.validate.field_chain import chain_for_run  # noqa: E402
from petey.validate.retype import resolve_blank  # noqa: E402

EVAL = RUNS / "judge_eval"

# (form, field, proposed name, expected verdict, the reviewer's reason as it would be put)
CASES = [
    # KS DO-10: five widgets the publisher placed one row off; captions print at the top of their own cell
    ("do10", "ein_ssn_ptin", "taxpayer_phone_number", "proposed",
     "the box is captioned Area Code & Phone Number; the EIN/SSN/PTIN cell is the next one"),
    ("do10", "representative1_phone_number", "representative1_ein_ssn_ptin", "proposed",
     "the box is captioned EIN/SSN/PTIN, not Phone Number"),
    ("do10", "representative1_ein_ssn_ptin", "representative1_fax_number", "proposed",
     "the box is captioned Fax Number"),
    ("do10", "representative2_phone_number", "representative2_ein_ssn_ptin", "proposed",
     "the box is captioned EIN/SSN/PTIN, not Phone Number"),
    ("do10", "representative2_ein_ssn_ptin", "representative2_fax_number", "proposed",
     "the box is captioned Fax Number"),
    # VA DMV RDT-120: tooltips one cell off (batch 2, renamed right)
    ("rdt120", "individual_account_nm", "legal_business_nm", "proposed",
     "the caption printed for this box is 'ENTER LEGAL BUSINESS NAME (individuals give full legal name)'"),
    ("rdt120", "doing_business_as_nm", "state_business_formed_in", "proposed",
     "the caption for this box is 'STATE BUSINESS FORMED IN'; the DBA name is the box to its left"),
    ("rdt120", "corporation_state_formed_in", "total_qualified_vehicles_count", "proposed",
     "the caption printed for this box is 'TOTAL NUMBER OF QUALIFIED VEHICLES', a count"),
    # Utah WC-122: three right renames and one wrong one from a neighbouring caption (batch 2)
    ("ut_wc_122", "claim_number", "employer_phone_number", "proposed",
     "publisher field name 'Employer Tel #' and the box caption 'PHONE #' identify a phone number"),
    ("ut_wc_122", "date_sent_to_labor_commission", "location_number", "proposed",
     "publisher name 'Location' and caption 'LOCATION #' show an identifier box, not a date"),
    ("ut_wc_122", "employer_name_address", "employer_location_address", "proposed",
     "publisher field name 'Employer Location' and the box caption say this holds the employer's location address"),
    ("ut_wc_122", "time_of_occurrence", "date_of_injury_illness", "current",
     "the caption printed for this box is DATE OF INJURY/ILLNESS; the caption wins over the misplaced tooltip"),
    # SS-4: batch 1 renamed `ein` to `entity_legal_nm` and the hand check called it right; the crop shows the widget
    # in the header's EIN box (under the printed 'EIN', beside the OMB number), not on line 1. Both models answered
    # `current` on 2026-10-01; the expectation was corrected to match the page. The classifier had read line 1's
    # caption for the header box, and the batch-1 reviewer followed it.
    ("form_ss_4", "ein", "entity_legal_nm", "current",
     "box f1_1 sits under the line 1 caption 'Legal name of entity (or individual) for whom the EIN is being requested'"),
    # ND 1TP: a swapped pair
    ("form1tp", "process_types", "primary_waste_streams", "proposed",
     "the caption above this box reads 'Identify the Primary Waste Streams to be Accepted'"),
    ("form1tp", "primary_waste_streams", "process_types", "proposed",
     "this box's caption is 'Process Type(s) (Shale Shaker, Centrifuge, ...)'"),
    # TX DMV 1756: opaque names in a Year / Make table column (the reviewer passed all fifteen as ok)
    ("tx_dmv_1756", "control", "vehicle_year_make", "proposed",
     "the name says nothing about the value; the column header over this cell reads Year / Make"),
    ("tx_dmv_1756", "control_2", "vehicle_year_make_2", "proposed",
     "the name says nothing about the value; the column header over this cell reads Year / Make"),
    ("tx_dmv_1756", "control_15", "vehicle_year_make_15", "proposed",
     "the name says nothing about the value; the column header over this cell reads Year / Make"),
    # MA LIC100: the classifier read 'B16. Name' two rows up for the box under C5. State (batch 2, renamed wrong)
    ("lic100_license_and_id_application_fillab", "out_of_state_state_abbreviation_cd", "applicant_nm", "current",
     "the caption printed for this box is 'B16. Name', so the widget labelled 'State' sits in the name box"),
]


def first_run_with(form: str, field: str):
    """The earliest run of the form whose blueprint copy still has the v0 field name (the pre-loop validate)."""
    for d in sorted(RUNS.glob(f"{form}_2*")):
        bp = d / "blueprint.bpt"
        if bp.exists() and field in ((yaml.safe_load(bp.read_text(encoding="utf-8")) or {}).get("fields") or {}):
            return d
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--model", default=adjudicate.MODEL)
    ap.add_argument("--only", default=None, help="comma-separated form stems")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--crops", type=Path, default=EVAL / "adjudicator_crops")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else None
    client = adjudicate._client()
    rows, agree = [], collections.Counter()
    cost = 0.0
    for form, field, proposed, expected, reason in CASES:
        if only and form not in only:
            continue
        bp = yaml.safe_load((EVAL / "blueprints" / f"{form}_v0.bpt").read_text(encoding="utf-8"))
        blank = resolve_blank(bp)
        limits = widget_limits(blank)
        run = first_run_with(form, field)
        chain = chain_for_run(run) if run else {}
        contested = adjudicate.contested_because(bp["fields"][field], chain.get(field), limits)
        d = {"field": field, "verdict": "fix", "name": proposed, "reason": reason}
        res = adjudicate.adjudicate_decisions(bp, blank, [d], chain, limits=limits, model=args.model, client=client,
                                              force=True, crop_dir=args.crops, tag="adjudicate_test")
        cost += res["cost_usd"]
        rec = res["records"][0] if res["records"] else {"verdict": "no_call", "reason": str(res["tally"])}
        ok = rec["verdict"] == expected
        agree["agree" if ok else "disagree"] += 1
        rows.append({"form": form, "field": field, "proposed": proposed, "expected": expected,
                     "verdict": rec["verdict"], "box_holds": rec.get("box_holds"), "reason": rec.get("reason"),
                     "contested_in_loop": contested, "chain": chain.get(field)})
        print(f"{'ok ' if ok else 'XX '} {form[:14]:14} {field[:34]:34} -> {proposed[:30]:30} "
              f"expected {expected:8} got {rec['verdict']:8} | holds: {str(rec.get('box_holds'))[:40]!r} | "
              f"{str(rec.get('reason'))[:120]}")
        print(f"      loop would {'contest: ' + contested if contested else 'land this without the adjudicator'}")
    print(f"\n{args.model}: {dict(agree)} over {len(rows)} cases, ${cost:.3f}")
    out = args.json or (EVAL / f"adjudicator_test_{args.model}.json")
    out.write_text(json.dumps({"model": args.model, "agree": dict(agree), "cost_usd": round(cost, 4), "rows": rows},
                              indent=1, default=str))
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
