"""Heuristic metadata enrichment: issuer / jurisdiction / vertical / tags.

Fills only NULL columns (never overwrites hand-set values). Rules are
ordered; first match on form_id wins. Rerunnable.

  widget-mapper/venv/bin/python registry/enrich.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry as R

# (form_id regex, issuer, jurisdiction, vertical, extra tags)
RULES: list[tuple[str, str | None, str | None, str | None, list[str]]] = [
    (r"^rrc_", "Texas Railroad Commission", "us-tx", "energy_rrc", ["industry:energy"]),
    (r"^cms_|^cms1500", "CMS", "us-federal", "healthcare", ["industry:healthcare"]),
    (r"^(i_\d+|n_400|i9$)", "USCIS", "us-federal", "immigration", ["industry:immigration"]),
    (r"^ds_11$", "US State Department", "us-federal", "immigration", ["industry:immigration"]),
    (r"^cbp_", "CBP", "us-federal", "immigration", ["industry:trade"]),
    (r"^acord_", "ACORD", "us-federal", "insurance", ["industry:insurance", "licensing:acord"]),
    (r"^osha_", "OSHA", "us-federal", "workers_comp", ["industry:employment"]),
    (r"^mcs_150", "FMCSA", "us-federal", "logistics", ["industry:trucking"]),
    (r"^faa_", "FAA", "us-federal", "aviation", ["industry:aviation"]),
    (r"^sba_", "SBA", "us-federal", "finance", ["industry:small-business"]),
    (r"^fec_", "FEC", "us-federal", "government", ["industry:politics"]),
    (r"^(sec_form_d|form_13f|schedule_13|form_nport)", "SEC", "us-federal", "finance",
     ["industry:finance"]),
    (r"^hud_", "HUD", "us-federal", "housing", ["industry:housing"]),
    (r"^(va_form_|vba_)", "VA", "us-federal", "benefits", ["industry:veterans"]),
    (r"^(dd_|da_form_|dod_|sf_1449)", "DoD/GSA", "us-federal", "procurement",
     ["industry:defense"]),
    (r"^gsa_", "GSA", "us-federal", "procurement", ["industry:procurement"]),
    (r"^form_5500", "DOL/IRS", "us-federal", "benefits", ["industry:retirement"]),
    (r"^urla_form_1003$", "Fannie Mae/Freddie Mac", "us-federal", "mortgage",
     ["industry:mortgage"]),
    (r"^(closing_disclosure|loan_estimate)$", "CFPB", "us-federal", "mortgage",
     ["industry:mortgage"]),
    (r"^(sec_|def_14a|form_adv|form_d$|s1$)", "SEC", "us-federal", "finance",
     ["industry:finance"]),
    (r"^fincen_", "FinCEN", "us-federal", "finance", ["industry:compliance"]),
    (r"^(sf_\d|of_306|opm_71)", "OPM/GSA", "us-federal", "government",
     ["industry:government-hr"]),
    (r"^(ub_04|ada_dental|eob$|medicare_summary|hipaa_)", None, None, "healthcare",
     ["industry:healthcare"]),
    (r"^(g_28|n_565|n_600|i485_)", "USCIS", "us-federal", "immigration",
     ["industry:immigration"]),
    (r"^js_44", "US Courts", "us-federal", "us_courts", ["industry:legal"]),
    (r"^ld_2", "US Congress", "us-federal", "government", ["industry:lobbying"]),
    (r"^commercial_invoice$", None, None, "supply_chain", ["industry:trade"]),
    (r"^property_disclosure", None, "us-state", "real_estate",
     ["industry:real-estate"]),
    (r"^form_ss_4$", "IRS", "us-federal", "tax", ["industry:tax"]),
    (r"^(w4|w8_)", "IRS", "us-federal", "tax", ["industry:tax"]),
    (r"^form_206ef$", "US Courts", "us-federal", "us_courts", ["industry:legal"]),
    (r"^(ccc|mitchell)_valuation$", None, "us-federal", "auto_valuation",
     ["industry:insurance", "no-blank:vendor"]),
    (r"^medicaid_", None, "us-state", "healthcare", ["industry:healthcare", "no-blank:vendor"]),
    (r"^(utility_bill|purchase_order|wholesale_price_list|fleet_rate_card|product_spec_sheet|consolidated_1099)$",
     None, None, None, ["no-blank:vendor"]),
    # state tax
    (r"^il_", "Illinois DoR", "us-il", "tax", ["industry:tax"]),
    (r"^nj_", "New Jersey DoT", "us-nj", "tax", ["industry:tax"]),
    (r"^it_201", "New York DTF", "us-ny", "tax", ["industry:tax"]),
    (r"^ca_540", "California FTB", "us-ca", "tax", ["industry:tax"]),
    (r"^ca_sc_100", "California Courts", "us-ca", "legal", ["industry:legal"]),
    (r"^ga_500", "Georgia DoR", "us-ga", "tax", ["industry:tax"]),
    (r"^pa_40", "Pennsylvania DoR", "us-pa", "tax", ["industry:tax"]),
    (r"^va_760", "Virginia Tax", "us-va", "tax", ["industry:tax"]),
    (r"^tx_01_114", "Texas Comptroller", "us-tx", "tax", ["industry:tax"]),
    # non-US
    (r"^(sa_100|p_60)", "HMRC", "uk", "tax", ["industry:tax"]),
    (r"^cra_", "CRA", "ca-federal", "tax", ["industry:tax"]),
    # IRS catch-all LAST (broad)
    (r"^(f?\d{3,4}|form_\d|schedule_|w_[249]|form_w|1040|1099|1098)", "IRS",
     "us-federal", "tax", ["industry:tax"]),
]


def main() -> None:
    conn = R.init()
    n_updated, n_unmatched, n_tags = 0, [], 0
    for row in conn.execute(
            "SELECT form_id, issuer, jurisdiction, vertical FROM forms"):
        fid = row["form_id"]
        hit = None
        for pat, issuer, juris, vertical, tags in RULES:
            if re.match(pat, fid):
                hit = (issuer, juris, vertical, tags)
                break
        if hit is None:
            n_unmatched.append(fid)
            continue
        issuer, juris, vertical, tags = hit
        R.upsert_form(conn, fid,
                      issuer=issuer if row["issuer"] is None else None,
                      jurisdiction=juris if row["jurisdiction"] is None else None,
                      vertical=vertical if row["vertical"] is None else None)
        for t in tags:
            conn.execute(
                "INSERT OR IGNORE INTO form_tags (form_id, tag) VALUES (?, ?)",
                (fid, t))
            n_tags += 1
        n_updated += 1
    conn.commit()
    print(f"updated {n_updated} forms, {n_tags} tag rows")
    print(f"unmatched ({len(n_unmatched)}):", " ".join(sorted(n_unmatched)))


if __name__ == "__main__":
    main()
