"""Record each staged blank's identity (issuer, form number, canonical id) in its manifest,
registry/sources/<dir>.json (the blanks themselves live in the S3 bucket, see scripts/fetch_blanks.sh).

At acquisition time the publisher is known (one directory per publisher) and the form number is in the filename,
so identity is written down here instead of re-derived from page text. petey.identify reads it back and prefers
it over its rules; the old corpus, with no manifest identity, keeps going through the rules unchanged.

Each rule maps a filename stem to (issuer, form_number) with the same slugs petey.identify uses (irs, uscis, va,
uscourts, ...); the canonical id follows identify's one rule: slug(issuer) + "_" + slug(form_number), with the
issuer prefix not repeated. A form number that cannot be found in the page text or /Info title is reported, not
dropped. REGISTRY_ID names an existing registry form where its id style differs (e.g. schedule_1).

    venv/bin/python registry/manifest_identity.py            # report only
    venv/bin/python registry/manifest_identity.py --write    # write into the manifests
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from petey.identify import slug  # noqa: E402

JURIS = {"irs": "us-federal", "uscis": "us-federal", "cbp": "us-federal", "cms": "us-federal", "ssa": "us-federal",
         "va": "us-federal", "opm": "us-federal", "gsa": "us-federal", "dod": "us-federal", "gse": "industry",
         "hud": "us-federal", "faa": "us-federal", "fmcsa": "us-federal", "phmsa": "us-federal", "uscourts": "us-federal",
         "ca_courts": "us-ca", "cra": "ca", "ircc": "ca", "hmrc": "uk", "uk_ch": "uk", "acord": "industry"}

IRS_SCHED_BASE = ("1040", "1065", "1120", "5471", "940", "941", "990")
IRS_SPECIAL = {"f1040s8": "1040 Sch 8812", "f1040sei": "1040 Sch EIC", "f1065sb1": "1065 Sch B-1",
               "f1065sk2": "1065 Sch K-2", "f1065sk3": "1065 Sch K-3", "f1120ssk": "1120-S Sch K-1",
               "f990ezb": "990 Sch B", "f5498e": "5498-ESA", "f1099ptr": "1099-PATR", "f1040es": "1040-ES"}


def irs(stem):
    if stem in IRS_SPECIAL:
        return "irs", IRS_SPECIAL[stem]
    if m := re.fullmatch(r"fw(\w+)", stem):
        return "irs", "W-" + m.group(1).upper()
    if (m := re.fullmatch(r"f(\d+)s([a-z0-9]+)", stem)) and m.group(1) in IRS_SCHED_BASE:
        return "irs", f"{m.group(1)} Sch {m.group(2).upper()}"
    if m := re.fullmatch(r"f(\d+)([a-z]+)", stem):
        return "irs", f"{m.group(1)}-{m.group(2).upper()}"
    return "irs", re.fullmatch(r"f(\d+)", stem).group(1)


def uscis(stem):
    if stem == "i-193":
        return "cbp", "I-193"
    m = re.fullmatch(r"([a-z]+)-(\d+[a-z0-9]*?)(?:sup(\w+))?", stem)
    num = f"{m.group(1).upper()}-{m.group(2).upper()}"
    num = re.sub(r"^I-129H2A$", "I-129 H-2A", num)
    return "uscis", num + (f" Supplement {m.group(3).upper()}" if m.group(3) else "")


def cbp(stem):
    t = re.sub(r"(?i)^cbp_form_", "", stem)
    t = re.sub(r"(?i)(_english)?_0$", "", t)
    return "cbp", t.upper()


CA_SPECIAL = {"pldpi001": "PLD-PI-001", "pldc001": "PLD-C-001"}


def ca_courts(stem):
    if stem in CA_SPECIAL:
        return "ca_courts", CA_SPECIAL[stem]
    m = re.fullmatch(r"([a-z]+)(\d+[a-z]?)", stem)
    return "ca_courts", f"{m.group(1).upper()}-{m.group(2).upper()}"


CMS_SPECIAL = {"application-medicare-part-part-b-special-enrollment-period-exceptional-conditions": "10797",
               "cms-18f5": "18-F-5", "cms-l564e": "L564", "cms-r-131-abn-english-fillable": "R-131",
               "cms1490s-english": "1490S", "cms40b-e": "40B", "cms4040-english": "4040"}


def cms(stem):
    return "cms", CMS_SPECIAL.get(stem) or re.sub(r"^cms-?", "", stem).upper()


def ssa(stem):
    return "ssa", {"ssa-561-u2": "SSA-561"}.get(stem, stem.upper())


def va(stem):
    t = re.sub(r"^(VBA-|VA_Form_|VA-Form-|VA)", "", stem)
    t = re.sub(r"(-ARE|-fill)$", "", t)
    return "va", t.upper()


FED = {"declaration-for-federal-employment-optional-form-august-2023": ("opm", "OF-306")}


def fed_forms(stem):
    if stem in FED:
        return FED[stem]
    m = re.fullmatch(r"(sf|SF|OF)(\d+[a-zA-Z]?)(?:-[0-9a-z]+)?", stem)
    return ("opm" if stem.startswith("sf") else "gsa"), f"{m.group(1).upper()}-{m.group(2).upper()}"


def dod(stem):
    m = re.fullmatch(r"dd0*(\d+(?:-\d+)?)", stem.lower())
    return "dod", "DD-" + m.group(1)


GSE = {"91": ("gse", "91"), "92": ("gse", "92"),
       "urla_additional_borrower": ("gse", "1003 Additional Borrower"),
       "urla_continuation_sheet": ("gse", "1003 Continuation Sheet"),
       "urla_lender_loan_information": ("gse", "1003 Lender Loan Information"),
       "urla_unmarried_addendum": ("gse", "1003 Unmarried Addendum"),
       "9548b": ("hud", "9548-B"), "50059-a": ("hud", "50059-A")}


def mortgage_gse(stem):
    if stem in GSE:
        return GSE[stem]
    if m := re.fullmatch(r"form-(\w+)", stem):
        return "gse", m.group(1).upper()
    return "hud", stem.upper()


FAA = {"8110-12": "8110-12", "AC8050_5_11-15-2023": "8050-5", "AC8060-68": "8060-68",
       "AC_8050-1_revised_08-2026_pra": "8050-1", "AC_8050-1B_pra_update": "8050-1B", "AC_8050-2_pra_ext": "8050-2",
       "AC_8050-4_pra_update": "8050-4", "AC_8050-88_pra_update": "8050-88", "AC_8050-88A_pra_update": "8050-88A",
       "AC_8060-55_8282017_": "8060-55", "AC_Form_8050-98_09-2024_final": "8050-98",
       "faa-form-7480-1-notice-for-construction-2020": "7480-1", "FAA-Form_8710-3": "8710-3", "FAA7140-1_02-25": "7140-1",
       "FAA_7460-1": "7460-1", "FAA_8060-13_6-16-2025_final_v5": "8060-13", "FAA_8120-11": "8120-11",
       "FAA_8400-3_PRA_extension_09-30-2029": "8400-3", "FAA_8610-1_02-24-26_final": "8610-1",
       "FAA_8610-2_05-28-2026_final": "8610-2", "FAA_8610-3_12-19-2025_v36_final": "8610-3",
       "FAA_8700-2_OMB_EXP_09-2026": "8700-2", "FAA_8710-11_12-03-25_final": "8710-11",
       "FAA_Form_337_PRA_extension_July_31_2026": "337", "FAA_Form_8010-4_": "8010-4", "FAA_Form_8060-14": "8060-14",
       "FAA_Form_8130-3": "8130-3", "FAA_Form_8130-6": "8130-6", "FAA_Form_8130-9": "8130-9",
       "FAA_Form_8310-3_": "8310-3", "FAA_Form_8420-8_PRA_Extension_01-2025": "8420-8",
       "FAA_Form_8710-13_OMB_EXP_08-31-2025.__3_": "8710-13"}


def fmcsa(stem):
    return "fmcsa", {"op-1ff": "OP-1(FF)", "op-1mx": "OP-1(MX)", "op-1p": "OP-1(P)"}.get(stem, stem.upper())


def phmsa(stem):
    return "phmsa", {"dot_f_5800_2": "5800.2", "dot_f_5800_2_addendum": "5800.2 Addendum"}[stem]


def cra(stem):
    t = stem.split("-fill")[0]
    t = re.sub(r"^t2sch(\d+)", r"T2 Sch \1", t)
    return "cra", t.upper()


def ircc(stem):
    return "ircc", "IMM " + re.fullmatch(r"imm(\d+)e", stem).group(1)


HMRC = {"64-8": "64-8", "D31": "D31", "Form_IHT100c_April_2026": "IHT100C", "iht100d_fillable": "IHT100D",
        "IHT217": "IHT217", "iht400-fillable": "IHT400", "IHT402": "IHT402", "IHT403-06-26": "IHT403",
        "IHT405": "IHT405", "IHT411_form_English": "IHT411", "P87": "P87"}


def hmrc(stem):
    if stem in HMRC:
        return "hmrc", HMRC[stem]
    m = re.fullmatch(r"(LL_)?([A-Z]+\d+)_[vV].*", stem)
    return "uk_ch", ("LL " if m.group(1) else "") + m.group(2)


def acord(stem):
    return "acord", {"acord_90_ny": "90 NY"}.get(stem, stem.split("_")[1])


USC = {"form_b106ab": "B 106A/B", "form_b106ef": "B 106E/F", "form_b106sum": "B 106Sum", "form_b106dec": "B 106Dec",
       "form_b206ab_0": "B 206A/B", "form_b2400a": "B 2400A", "form_b_101_0624_fillable_clean": "B 101",
       "form_ao_10a_revd_3.2024": "AO 10A", "js_044_-_civil_cover_sheet_1": "JS 44",
       "ao_078-08-2024_1": "AO 78", "ao_089b_0": "AO 89B", "ao_093c_0818_0": "AO 93C", "ao100a_0": "AO 100A"}


def us_courts(stem):
    if stem in USC:
        return "uscourts", USC[stem]
    if m := re.fullmatch(r"ao0*(\d+[a-z]?)", stem):
        return "uscourts", "AO " + m.group(1).upper()
    t = re.sub(r"^(form_b_?|form[-_]|b_)", "", stem)
    t = re.sub(r"(_0425-form|-form|_0|_1)$", "", t)
    return "uscourts", "B " + t.upper()


RULES = {"irs": irs, "uscis": uscis, "cbp": cbp, "ca_courts": ca_courts, "cms": cms, "ssa": ssa, "va_benefits": va,
         "fed_forms": fed_forms, "dod": dod, "mortgage_gse": mortgage_gse, "faa": lambda s: ("faa", FAA[s]),
         "fmcsa": fmcsa, "phmsa": phmsa, "cra": cra, "ircc": ircc, "hmrc": hmrc, "acord": acord, "us_courts": us_courts}

# existing registry rows whose id style differs from the canonical (checked by eye against the registry, 2026-10-06)
REGISTRY_ID = {
    ("irs", "1040 Sch 1"): "schedule_1", ("irs", "1040 Sch 2"): "schedule_2", ("irs", "1040 Sch 3"): "schedule_3",
    ("irs", "1040 Sch F"): "schedule_f", ("irs", "1040 Sch H"): "schedule_h", ("irs", "1040 Sch R"): "schedule_r",
    ("irs", "1120-S Sch K-1"): "form_1120_s_schedule_k_1",
    ("uscourts", "B 206E/F"): "form_206ef", ("uscourts", "JS 44"): "js_44_civil_cover_sheet",
}


def canonical(issuer: str, number: str) -> str:
    iss, num = slug(issuer), slug(number)
    head = iss.split("_")[0]
    if head and (num == head or num.startswith(head + "_")):
        num = num[len(head):].strip("_")
    return f"{iss}_{num}"


def on_page(pdf: Path, number: str) -> bool:
    """The form number's core token appears in the first two pages' text or the /Info title."""
    d = pymupdf.open(pdf)
    text = " ".join(d[i].get_text() for i in range(min(2, d.page_count))) + " " + (d.metadata.get("title") or "")
    d.close()
    flat = re.sub(r"[^a-z0-9]", "", text.lower())
    core = re.sub(r"^(b|ao|js|sf|of|dd|ssa|ss|imm|cms)\s*", "", number.lower().split(" sch ")[0].split(" supplement")[0])
    return re.sub(r"[^a-z0-9]", "", core) in flat


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    seen: dict[str, str] = {}
    bad = 0
    for d, rule in RULES.items():
        mp = ROOT / "registry" / "sources" / f"{d}.json"
        m = json.loads(mp.read_text())
        for f in m["files"]:
            pdf = ROOT / "source_pdfs" / d / f["file"]
            if f.get("widgets", 0) < 8:
                continue  # flat copies in us_courts: not part of the blank set
            issuer, number = rule(Path(f["file"]).stem)
            can = canonical(issuer, number)
            ident = {"issuer": issuer, "jurisdiction": JURIS[issuer], "form_number": number, "canonical": can}
            if (issuer, number) in REGISTRY_ID:
                ident["registry_id"] = REGISTRY_ID[(issuer, number)]
            if can in seen:
                print(f"DUPLICATE canonical {can}: {seen[can]} and {d}/{f['file']}"); bad += 1
            seen[can] = f"{d}/{f['file']}"
            if not on_page(pdf, number):
                print(f"not on page: {d}/{f['file']} -> {issuer} {number!r}")
            f["identity"] = ident
        if a.write:
            mp.write_text(json.dumps(m, indent=1))
    print(f"{len(seen)} identities, {bad} duplicate canonicals" + ("" if a.write else " (report only; --write to save)"))
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
