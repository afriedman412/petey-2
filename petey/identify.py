"""Identify a blank form from the document itself. Hard-coded rules, no model.

Reads the first and last page text, the PDF /Info title and the XFA template
root, and emits issuer, form number, edition, OMB control number and IRS
catalog number. Every value carries the rule and the text that produced it,
so the output is checkable by eye.

Canonical id generation is one rule, not a lookup:

    canonical = slug(issuer) + "_" + slug(form_number)      e.g. irs_1040,
    irs_w_2, irs_1065_sch_k_1, uscis_i_765, cms_1500, acord_125, va_21_526ez

Edition is kept separately: one form has many editions, and the registry
tracks forms. Existing registry ids (`1040`, `acord_125`, `i130`) are
compared to the canonical by normalisation; nothing here renames them.

Usage:
    python -m petey.identify form.pdf
    python -m petey.identify --src source_pdfs --out runs/identity.json
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import pymupdf

from petey.paths import REPO, SOURCE_PDFS

def _yy(y: str) -> str:
    """Two-digit year -> four: 68 is 1968, not 2068."""
    return y if len(y) == 4 else ("19" if int(y) >= 50 else "20") + y


MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
STATES = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar", "california": "ca", "colorado": "co",
    "connecticut": "ct", "delaware": "de", "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks", "kentucky": "ky", "louisiana": "la",
    "maine": "me", "maryland": "md", "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
    "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne", "nevada": "nv",
    "new hampshire": "nh", "new jersey": "nj", "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or", "pennsylvania": "pa",
    "rhode island": "ri", "south carolina": "sc", "south dakota": "sd", "tennessee": "tn", "texas": "tx",
    "utah": "ut", "vermont": "vt", "virginia": "va", "washington": "wa", "west virginia": "wv",
    "wisconsin": "wi", "wyoming": "wy", "district of columbia": "dc",
}
STATE_RX = re.compile(r"\b(" + "|".join(sorted(STATES, key=len, reverse=True)) + r")\b", re.I)

# ---- issuers: ordered, first match wins. (issuer_slug, jurisdiction, regex) ----
# Specific publishers before generic agencies; state agencies resolve the state from nearby text.
ISSUERS = [
    ("acord",    "industry", r"\bACORD\b"),
    ("ato",      "au", r"Australian Taxation Office|\bNAT\s+\d{4}\b"),
    ("cfpb",     "us-federal", r"Consumer Financial Protection|\bCFPB\b|TILA RESPA"),
    ("iaiabc",   "industry", r"\bIAIABC\b"),
    ("gse",      "industry", r"Fannie Mae|Freddie Mac"),
    ("uscis",    "us-federal", r"\bUSCIS\b|U\.?S\.? Citizenship and Immigration"),
    ("cbp",      "us-federal", r"Customs and Border Protection|\bCBP Form\b"),
    ("cms",      "us-federal", r"Centers for Medicare|\bCMS-\d|NUCC|MEDICARE\s+MEDICAID"),
    ("fincen",   "us-federal", r"\bFinCEN\b|Financial Crimes Enforcement Network"),
    ("hud",      "us-federal", r"Housing and Urban Development|\bHUD-?\d"),
    ("ssa",      "us-federal", r"Social Security Administration"),
    ("dod",      "us-federal", r"\bDD\s+FORM\b|Department of Defense"),
    ("va",       "us-federal", r"\bVA\s+FORM\b|Department of Veterans Affairs"),
    ("fec",      "us-federal", r"Federal Election Commission"),
    ("eeoc",     "us-federal", r"\bEEO-?1\b|Equal Employment Opportunity"),
    ("dol",      "us-federal", r"Employee Benefits Security Administration|Department of Labor"),
    ("sec",      "us-federal", r"Securities and Exchange Commission"),
    ("uscourts", "us-federal", r"\bAO\s+\d{2,3}[A-Z]?\b|United States (?:District|Bankruptcy) Court|Official Form \d|Administrative Office of the United States Courts"),
    ("irs",      "us-federal", r"Internal Revenue Service|irs\.gov|Department of the Treasury"),
    ("fmcsa",    "us-federal", r"Federal Motor Carrier Safety|\bMCS-?\d{3}\b"),
    ("tx_rrc",   "us-tx", r"Railroad Commission of Texas"),
    ("nm_ocd",   "us-nm", r"Oil Conservation Division"),
    ("ok_occ",   "us-ok", r"Oklahoma Corporation Commission|OIL AND GAS CONSERVATION DIVISION[\s\S]{0,120}Oklahoma City|occ\.ok\.gov"),
    ("id_dor",   "us-id", r"Idaho State Tax Commission|\bE[A-Z]{2}\d{5}\b"),
    ("fl_dfs",   "us-fl", r"FLORIDA DEPARTMENT OF FINANCIAL SERVICES"),
    ("nd_ndic",  "us-nd", r"North Dakota Industrial Commission|Industrial Commission of North Dakota|\bNDIC\b|Department of Mineral Resources"),
    ("cra",      "ca", r"Canada Revenue Agency|Agence du revenu du Canada"),
    ("hmrc",     "uk", r"HM Revenue\s*(?:&|and)\s*Customs|\bHMRC\b"),
    ("ie_revenue", "ie", r"Revenue Commissioners|revenue\.ie"),
    ("hk_ird",   "hk", r"Inland Revenue Department"),
    ("__state_dor", None, r"Department of Revenue|Department of Taxation|Tax Commission|Franchise Tax Board|Department of Treasury|Comptroller|Department of Finance and Administration|Tax Division|Revenue Division"),
    ("__state_dmv", None, r"Division of Motor Vehicles|Department of Motor Vehicles|Motor Vehicle (?:Division|Commission|Administration)|Bureau of Motor Vehicles|Department of Transportation"),
    ("__state_wc",  None, r"Workers'?\s+Compensation (?:Board|Commission|Division|Bureau|Court)|Industrial Commission"),
    ("__state_opm", None, r"Office of Personnel Management|Department of Transformation and Shared Services"),
    ("__muni",      None, r"City and County of ([A-Z][a-z]+(?: [A-Z][a-z]+){0,2})|City of ([A-Z][a-z]+(?: [A-Z][a-z]+){0,2})|County of ([A-Z][a-z]+(?: [A-Z][a-z]+){0,2})|\b([A-Z][a-z]+(?: [A-Z][a-z]+)? County)\b"),
]
MUNI_DEPT_RX = re.compile(r"Office of Buildings|Building Inspection|Building Department|Planning (?:Department|Division)|Public Works|Permit", re.I)
ADDR_CITY_RX = re.compile(r"\b([A-Z][A-Za-z .]{2,30}),\s*(" + "|".join(sorted(STATES, key=len, reverse=True)) + r"|[A-Z]{2})\s+\d{5}\b", re.I)

# ---- form numbers: ordered. Each yields the number text; some carry a prefix to keep. ----
NUMBER_RULES = [
    ("fannie",       r"Fannie Mae\s+Form\s+(\d{3,4}[A-Z]?)\b", lambda m: m.group(1)),
    ("irs_schedule", r"Schedule\s+([A-Z0-9]{1,4}(?:-\d)?)\s*\(Form\s+([0-9A-Z-]{2,10})\)", lambda m: f"{m.group(2)}_sch_{m.group(1)}"),
    ("acord",        r"ACORD\s+(\d{2,3})\b", lambda m: m.group(1)),
    ("uscis",        r"\b(?:Form\s+)?([IN]-\d{3}[A-Z]{0,2})\b", lambda m: m.group(1)),
    ("cms",          r"\bCMS-?\s?(\d{3,5}[A-Z]?)\b", lambda m: m.group(1)),
    ("dd",           r"\bDD\s+FORM\s+(\d+(?:-\d+)?)", lambda m: f"dd_{m.group(1)}"),
    ("va",           r"\bVA\s+FORM\s+([\d-]+[A-Z]*)", lambda m: m.group(1)),
    ("sf",           r"\b(?:Standard Form|SF)[- ]?(\d{2,4}[A-Z]?)\b", lambda m: f"sf_{m.group(1)}"),
    ("ao",           r"\bAO\s+(\d{2,3}[A-Z]?)\b", lambda m: f"ao_{m.group(1)}"),
    ("official",     r"\bOfficial Form\s+(\d{3}[A-Z0-9-]{0,6})\b", lambda m: f"b_{m.group(1)}"),
    ("agency_form",  r"\b(?:FEC|SEC|FCC|EPA|OSHA|SBA|CBP|FEMA|GSA|OPM|NRC)\s+FORM\s+([A-Z0-9-]{1,8})\b", lambda m: m.group(1)),
    ("nat",          r"\bNAT\s+(\d{4})\b", lambda m: f"nat_{m.group(1)}"),
    ("cfpb_h",       r"\b(H-\d{2}(?:\([A-Z]\))?)", lambda m: m.group(1).replace("(", "_").replace(")", "")),
    ("id_code",      r"\b(E[A-Z]{2}\d{5})\b", lambda m: m.group(1)),
    ("state_w4",     r"\bForm\s+([A-Z]{2}-W-?\d[A-Z]?)\b", lambda m: m.group(1)),
    ("num_then_form", r"^(\d{3,4}[A-Z]?)\s+Form\b", lambda m: m.group(1)),
    ("ia_code",      r"\b(IA-\d{1,2})\b", lambda m: m.group(1)),
    ("hud",          r"\bHUD-?(\d{3,5}[A-Z]?)\b", lambda m: m.group(1)),
    ("mcs",          r"\bMCS-?(\d{3}[A-Z]?)\b", lambda m: f"mcs_{m.group(1)}"),
    ("nd_sfn",       r"\bSFN\s*(\d{4,5})\b", lambda m: f"sfn_{m.group(1)}"),
    ("co_dr",        r"\b(DR|CR)\s?(\d{4}[A-Z]?)\b", lambda m: f"{m.group(1)}_{m.group(2)}"),
    ("hk_ir",        r"\b(IR\s?\d{2,4}[A-Z]?)\b", lambda m: m.group(1).replace(" ", "")),
    ("form_w",       r"\bForm\s+(W-?\d[A-Za-z]{0,3}(?:-[A-Za-z]{1,3})?)\b", lambda m: m.group(1).upper()),
    ("form_alpha",   r"\bForm\s+([A-Z]{1,4}-?\d{1,5}[A-Z]{0,3}(?:-[A-Z0-9]{1,4})?)\b", lambda m: m.group(1)),
    ("form_num",     r"\bForm\s+(\d{3,5}(?:-?[A-Z]{1,4})?)\b", lambda m: m.group(1)),
    ("bare_alpha",   r"^\s*([A-Z]{1,3}-\d{1,4}[A-Z]?)\s*$", lambda m: m.group(1)),
    ("first_line_code", r"^(?:Form\s+)?([A-Z]{2,5}[- ]?\d{1,4}[A-Z]{0,2}|[A-Z]&[A-Z]\s+[A-Z]{2,3}|\d{3,4}[A-Z])\s*(?:\((?:R(?:ev)?\.?\s*)?[\d/.-]+\)|Revised\b|20\d\d\b|$)", lambda m: m.group(1).replace(" ", "-")),
]

EDITION_RULES = [
    ("rev_month_year", r"\(?\bRev(?:ised|\.)?\s*([A-Za-z]{3,9})\.?\s+(\d{4})\)?", lambda m: f"{m.group(2)}_{MONTHS.get(m.group(1)[:3].lower(), 0):02d}"),
    ("rev_mm_yyyy",    r"\(?\bRev(?:ised|\.)?\s*(\d{1,2})[-/](\d{4})\)?", lambda m: f"{m.group(2)}_{int(m.group(1)):02d}"),
    ("rev_mm_yy",      r"\(?\bRev(?:ised|\.)?\s*(\d{1,2})[-/](\d{2})\)?", lambda m: f"{_yy(m.group(2))}_{int(m.group(1)):02d}"),
    ("acord_edition",  r"ACORD\s+\d+\s*\((\d{4})/(\d{2})\)", lambda m: f"{m.group(1)}_{m.group(2)}"),
    ("uscis_edition",  r"Edition\s+(\d{2})/(\d{2})/(\d{2,4})", lambda m: f"{_yy(m.group(3))}_{m.group(1)}_{m.group(2)}"),
    ("rev_mdy",        r"\(?\b(?:R(?:ev(?:ised)?)?\.?\s*)?(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})\)?", lambda m: f"{_yy(m.group(3))}_{int(m.group(1)):02d}_{int(m.group(2)):02d}"),
    ("rev_month_d_y",  r"\bRevised\s+([A-Za-z]{3,9})\.?\s+\d{1,2},?\s+(\d{4})", lambda m: f"{m.group(2)}_{MONTHS.get(m.group(1)[:3].lower(), 0):02d}"),
    ("year_paren",     r"\((20\d{2})\)", lambda m: m.group(1)),
    ("year_form",      r"\b(20\d{2})\s+(?:Form|Schedule)\b", lambda m: m.group(1)),
    ("form_year",      r"\bForm\s+[0-9A-Z-]+\s*\(?(20\d{2})\)?", lambda m: m.group(1)),
    ("mm_yyyy_tail",   r"\b(\d{1,2})/(20\d{2})\s*$", lambda m: f"{m.group(2)}_{int(m.group(1)):02d}"),
]

# rules that only make sense once the issuer is known (bare codes are too loose otherwise)
ISSUER_RULES = {
    "hmrc":   [("hmrc_code", r"\b(SA\d{3}[A-Z]?|P\d{2}[A-Z]?|CT\d{3}[A-Z]?|CA\d{4}|VAT\d{1,3}[A-Z]?|R\d{2}|IHT\d{3})\b", lambda m: m.group(1))],
    "ok_occ": [("okcc_bare", r"^(\d{3,4}[A-Z]{0,4}(?:-[A-Z])?)$", lambda m: m.group(1))],
    "tx_rrc": [("rrc_alpha", r"\bForm\s+([A-Z]{1,3}(?:-\d{1,3}[A-Z]?)?)\b", lambda m: m.group(1)),
               ("rrc_bare", r"\b([A-Z]{1,2}-\d{1,3}[A-Z]?)\b", lambda m: m.group(1))],
    "sec":    [("sec_form", r"\bForm\s+(\d{1,2}-?[A-Z]?|[A-Z]{1,2}(?:-[A-Z0-9]{1,3})?)\b", lambda m: m.group(1))],
    "hk_ird": [("hk_code", r"\b(IRSD\s?\d{2,4}[A-Z]?|IR\s?\d{2,4}[A-Z]?|BIR\d{2}[A-Z]?)\b", lambda m: m.group(1).replace(" ", ""))],
}

OMB_RX = re.compile(r"OMB\s*(?:No\.?|Number|Control\s*(?:No\.?|Number)|#)?\s*:?\s*(\d{4}-\d{4})", re.I)
CAT_RX = re.compile(r"Cat(?:alog)?\.?\s*No\.?\s*(\d{4,6}[A-Z]?)", re.I)


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


@dataclass
class Identity:
    path: str
    sha256: str = ""
    pages: int = 0
    issuer: Optional[str] = None
    jurisdiction: Optional[str] = None
    form_number: Optional[str] = None
    edition: Optional[str] = None
    omb: Optional[str] = None
    catalog: Optional[str] = None
    title: Optional[str] = None
    xfa_root: Optional[str] = None
    form_name: Optional[str] = None
    text_layer: bool = True
    canonical: Optional[str] = None
    evidence: dict = field(default_factory=dict)

    def note(self, key: str, rule: str, text: str) -> None:
        self.evidence[key] = {"rule": rule, "text": text.strip()[:80]}


def _xfa_root(doc: pymupdf.Document) -> Optional[str]:
    try:
        cat = doc.pdf_catalog()
        t, af = doc.xref_get_key(cat, "AcroForm")
        if t == "xref":
            af_x = int(af.split()[0])
            tx, arr = doc.xref_get_key(af_x, "XFA")
        else:
            tx, arr = doc.xref_get_key(cat, "AcroForm/XFA")
        if tx != "array":
            return None
        parts = re.findall(r"\((\w+)\)\s*(\d+)\s+0\s+R", arr)
        for name, xref in parts:
            if name == "template":
                xml = doc.xref_stream(int(xref)).decode("utf-8", "replace")
                m = re.search(r"<subform[^>]*\bname=\"([^\"]+)\"", xml)
                return m.group(1) if m else None
    except Exception:
        return None
    return None


def _text(doc: pymupdf.Document) -> str:
    n = doc.page_count
    idx = sorted({0, n - 1} | ({1} if n > 2 else set()))
    return "\n".join(doc[i].get_text() for i in idx)


def _issuer(text: str, ident: Identity) -> None:
    """Earliest mention wins (an agency names itself in its header; forms it
    references appear in instructions), with list order as the tiebreak."""
    best = None  # (position, order, name, juris, match)
    for order, (name, juris, rx) in enumerate(ISSUERS):
        m = re.search(rx, text[:800] if name == "__muni" else text, 0 if name == "__muni" else re.I)
        if not m:
            continue
        pos = m.start() if name != "__muni" else m.start() + 200   # a state agency beats a bare city mention
        if best is None or (pos, order) < (best[0], best[1]):
            best = (pos, order, name, juris, m)
    if best is None or best[2] == "__muni":
        # an address line with a city plus a municipal department keyword is the publisher (beats a county mention)
        am = ADDR_CITY_RX.search(text[:1500])
        if am and MUNI_DEPT_RX.search(text[:1500]):
            city, st = am.group(1).strip(), am.group(2).lower()
            st = STATES.get(st, st)
            ident.issuer, ident.jurisdiction = f"{slug(city)}_{st}", f"us-{st}"
            ident.note("issuer", "muni_address", am.group(0))
            return
        if best is None:
            return
    _, _, name, juris, m = best
    if name.startswith("__state"):
        window = text[max(0, m.start() - 400): m.end() + 400]
        sm = STATE_RX.search(window) or STATE_RX.search(text)
        if sm:
            st, how = STATES[sm.group(1).lower()], sm.group(0)
        else:
            am = ADDR_CITY_RX.search(text[:2500])
            if not am or am.group(2).lower() not in set(STATES.values()):
                return
            st, how = am.group(2).lower(), am.group(0)
        ident.issuer, ident.jurisdiction = f"{st}_{name.split('_')[-1]}", f"us-{st}"
        ident.note("issuer", name, how + " … " + m.group(0))
        return
    if name == "__muni":
        place = next(g for g in m.groups() if g)
        am = ADDR_CITY_RX.search(text[:2000])
        st = STATES.get(am.group(2).lower(), am.group(2).lower()) if am else None
        sm = STATE_RX.search(text[:2000])
        st = st or (STATES[sm.group(1).lower()] if sm else None)
        ident.issuer = f"{slug(place)}_{st}" if st else slug(place)
        ident.jurisdiction = f"us-{st}" if st else None
        ident.note("issuer", "muni", m.group(0))
        return
    ident.issuer, ident.jurisdiction = name, juris
    ident.note("issuer", name, m.group(0))


def _form_number(text: str, ident: Identity, title: str | None = None, pages: list[str] | None = None) -> None:
    """Score every candidate from every rule by WHERE it appears.

    A form names itself in the page-1 header and in every page footer; forms it
    merely references appear mid-text. So position beats rule order.
    """
    pages = pages or [text]
    p1 = pages[0]
    zones = [("title", title or "", 3.0), ("body", text, 0.0)]  # (name, text, weight)
    for i, pg in enumerate(pages):
        hw = {0: 3.0, 1: 2.5}.get(i, 1.0)
        zones.append((f"p{i + 1}_header", pg[:250 if i == 0 else 400], hw))
        if i == 0:
            zones.append(("p1_head6", "\n".join(l.strip() for l in pg.splitlines() if l.strip())[:6 * 80] if False else "\n".join([l.strip() for l in pg.splitlines() if l.strip()][:10]), 3.0))
        zones.append((f"p{i + 1}_footer", pg[-300:], 2.0 if i in (0, len(pages) - 1) else 1.0))
    score: dict[str, float] = collections.defaultdict(float)
    first: dict[str, tuple[str, str]] = {}
    rules = NUMBER_RULES + ISSUER_RULES.get(ident.issuer or "", [])
    for rule, rx, fn in rules:
        flags = re.M if rule in ("bare_alpha", "first_line_code", "okcc_bare", "num_then_form") else (re.I if rule == "irs_schedule" else 0)
        for zone, ztext, w in zones:
            if rule in ("first_line_code", "okcc_bare", "num_then_form") and not zone.endswith("_head6"):
                continue
            if rule == "rrc_bare" and zone not in ("title", "p1_head6"):
                continue
            cnt: collections.Counter = collections.Counter()
            for m in re.finditer(rx, ztext, flags):
                v = fn(m); cnt[v] += 1
                first.setdefault(v, (rule + "@" + zone, m.group(0)))
            for v, n in cnt.items():
                score[v] += w + min(n, 10) * 0.2
                if rule == "irs_schedule" and ("header" in zone or zone == "title"):
                    score[v] += 1.0
    if not score:
        return
    # a bare alphanumeric token needs a positional anchor to count at all
    for v, (src, _) in first.items():
        if src.startswith("bare_alpha@body"):
            score[v] -= 1.0
    hdr = {v for v, (src, _) in first.items() if "header" in src or "title" in src}
    for a in hdr:
        for b in hdr:
            if a != b and len(a) > len(b) and re.sub(r"[^a-z0-9]", "", a.lower()).endswith(re.sub(r"[^a-z0-9]", "", b.lower())):
                score[b] -= 3.0
    v = max(score, key=lambda k: (score[k], -text.find(first[k][1])))
    if os.environ.get("PETEY_IDENTIFY_DEBUG"):
        for k in sorted(score, key=lambda k: -score[k])[:8]:
            print(f"    {score[k]:5.1f}  {k!r:22s} {first[k][0]:26s} {first[k][1]!r}", file=sys.stderr)
    if score[v] <= 0:
        return
    ident.form_number = v
    ident.note("form_number", first[v][0], first[v][1])


def _edition(text: str, ident: Identity) -> None:
    for rule, rx, fn in EDITION_RULES:
        m = re.search(rx, text)
        if m:
            v = fn(m)
            if v.endswith("_00"):
                continue
            ident.edition = v
            ident.note("edition", rule, m.group(0))
            return


FORM_WORDS = r"(FORM|AFFIDAVIT|APPLICATION|REPORT|REQUEST|DECLARATION|WORKSHEET|AGREEMENT|BOND|CERTIFICATE|NOTICE|STATEMENT|REGISTRATION|VOUCHER|RETURN|QUESTIONNAIRE|AUTHORIZATION|PERMIT|CLAIM|SCHEDULE|ESTIMATE|DISCLOSURE|DESCRIPTION|LETTER OF CREDIT|RECEIPT|ACKNOWLEDGE?MENT)"
SKIP_LINE_RX = re.compile(
    r"^(page\s+\d|revised|rev\.|version|clear form|type or print|please (print|answer|complete)|instructions?\b|omb\b|expires|for official|office use|received|see\b|\d+\s*$)"
    r"|\bP\.?O\.? box\b|@|www\.|https?:|\btel\b|phone|fax|\bsuite\b|\bfloor\b|\d{5}(-\d{4})?\s*$|^\W*$"
    r"|\b(last|first|middle)\s+(name|initial)\b|\bzip\b|\bcity,\s*state\b|^name\b|\bsignature\b|\bdate of birth\b|\bprint\b"
    r"|\b(street|st\.|ave\.?|avenue|road|rd\.|drive|dr\.|blvd|boulevard|centre|center|plaza|main office|\d+/f)\b|^\d+\s+[A-Z]"
    r"|skip to main|clear form|layout \d|^untitled|^scan|^\d{1,2}[.)]?\s|here's how|etc\.?\s*$", re.I)
AGENCY_LINE_RX = re.compile(r"\b(department|division|office of|commission|state of|city of|county of|administration|agency|bureau|service|internal revenue)\b", re.I)


def _form_name(pages: list[str], ident: Identity) -> None:
    """The first title-like line of page 1: at least two words, not an address,
    phone, agency or boilerplate line; lines ending in a form-type word win."""
    raw = [l.strip() for l in pages[0].splitlines() if l.strip()][:14]
    lines: list[str] = []
    for l in raw:  # a line starting with punctuation or lowercase continues the previous one
        if lines and re.match(r"^[,;:)\-–]|^[a-z]", l):
            lines[-1] = lines[-1] + " " + l
        else:
            lines.append(l)
    cands = []
    for i, l in enumerate(lines):
        l = re.sub(r"\((?:R(?:ev(?:ised)?)?\.?\s*)?[\d/.\-]+\)\s*$", "", l).strip()
        nxt = lines[i + 1] if i + 1 < len(lines) else ""
        if re.match(r"^(Governor|Lt\.? Governor|Secretary|Director|Commissioner|Chair|Cabinet|Mayor|Executive Director)\b", nxt):
            continue  # letterhead: a person's name above their title
        if AGENCY_LINE_RX.search(nxt) and len(l.split()) <= 5 and not re.search(FORM_WORDS + r"\s*$", l, re.I):
            continue  # letterhead: an agency name wrapped over two lines
        words = re.findall(r"[A-Za-z][A-Za-z'’-]+", l)
        if len(words) < 2 or len(words) > 14 or SKIP_LINE_RX.search(l) or AGENCY_LINE_RX.search(l):
            continue
        if sum(c.isdigit() for c in l) > 4:
            continue
        typed = bool(re.search(FORM_WORDS + r"\s*$", l, re.I))
        if not typed and len(words) < 3:
            continue  # an untyped two-word line is more often a name or a label than a title
        caps = sum(1 for w in words if w[0].isupper()) / len(words)
        if not typed and len(words) >= 5 and caps < 0.6:
            continue  # sentence case with five or more words is prose, not a title
        if l.rstrip().endswith((":", ",", ";")) or re.search(r"\b(is|are|be|to be|must|may|shall|should|will)\b", l) and not typed:
            continue
        cands.append((0 if typed else 1, i, l))
    if not cands:
        return
    _, i, l = min(cands)
    ident.form_name = re.sub(r"\s+", " ", l)
    ident.note("form_name", f"p1_line{i + 1}", l)


def identify(path: str | Path) -> Identity:
    p = Path(path)
    ident = Identity(path=str(p))
    ident.sha256 = hashlib.sha256(p.read_bytes()).hexdigest()
    doc = pymupdf.open(str(p))
    ident.pages = doc.page_count
    n = doc.page_count
    pages = [doc[i].get_text() for i in sorted({0, n - 1} | ({1} if n > 2 else set()))]
    text = "\n".join(pages)
    ident.title = ((doc.metadata or {}).get("title") or "").strip() or None
    ident.xfa_root = _xfa_root(doc)
    ident.text_layer = len(text.split()) >= 12
    _issuer(text + "\n" + (ident.title or ""), ident)
    _form_number(text, ident, title=ident.title, pages=pages)
    _form_name(pages, ident)
    _edition(text, ident)
    m = OMB_RX.search(text)
    if m:
        ident.omb = m.group(1); ident.note("omb", "omb", m.group(0))
    m = CAT_RX.search(text)
    if m:
        ident.catalog = m.group(1); ident.note("catalog", "cat", m.group(0))
    iss = slug(ident.issuer) if ident.issuer else ""
    if ident.form_number:
        num = slug(ident.form_number)
        head = iss.split("_")[0]
        if head and (num == head or num.startswith(head + "_")):
            num = num[len(head):].strip("_")          # il_dor + il_1040 -> il_dor_1040
        ident.canonical = f"{iss}_{num}" if iss else num
    elif ident.form_name or (ident.title and not SKIP_LINE_RX.search(ident.title) and not AGENCY_LINE_RX.search(ident.title)
                             and not re.search(r"\.(xls|doc|pdf)|nocheckboxes|^\d", ident.title, re.I)
                             and not (len(ident.title.split()) >= 5 and sum(w[0].isupper() for w in ident.title.split()) / len(ident.title.split()) < 0.6)):
        # a named-but-unnumbered form: the header title line (or /Info title), minus dates and noise, six words max
        t = re.sub(r"\((?:R(?:ev(?:ised)?)?\.?\s*)?[\d/.-]+\)|\bRevised\b.*$|\.pdf$|Microsoft Word -", "", (ident.form_name or ident.title), flags=re.I)
        words = [w for w in re.findall(r"[A-Za-z0-9]+", t) if w.lower() not in ("form", "fillable", "the", "of", "for", "and")][:8]
        while words and words[-1].lower() in ("from", "to", "a", "an", "by", "or", "in", "no", "on", "with", "under", "at", "as", "be"):
            words.pop()
        head = iss.split("_")[0]
        if words and head and words[0].lower() == head:
            words = words[1:]
        if len(words) >= 2 and not re.match(r"^(404|untitled|document|microsoft)", words[0], re.I):
            ident.canonical = f"{iss}_{slug(' '.join(words))}" if iss else slug(" ".join(words))
            ident.note("canonical", "form_name" if ident.form_name else "title_name", ident.form_name or ident.title)
    return ident


# ---- reconcile with the registry (read-only) ----
def _norm(s: str) -> str:
    """Normalise a form id or number for comparison: lower, drop punctuation,
    'schedule'->'sch', strip zero-padding inside numeric runs, drop a leading
    'form'/'<issuer>_form' wrapper the registry sometimes carries."""
    s = s.lower().replace("schedule", "sch")
    s = re.sub(r"^(?:[a-z]{2,6}_)?form_", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    s = re.sub(r"(?<![0-9])0+(\d)", r"\1", s)      # leading zeros only: ao_030 -> ao30, 1005 stays 1005
    return s


def reconcile(idents: list[Identity], db: Path) -> dict[str, str]:
    """Compare each identity with what the registry already knows (read-only).
    Uses the one resolver (`petey.registry_lookup`), the same one apply_identity uses."""
    from petey.registry_lookup import resolve_form_id
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    by_sha = {s: f for s, f in conn.execute("SELECT sha256, form_id FROM source_pdfs")}
    conn.close()
    verdict: dict[str, str] = {}
    for it in idents:
        reg = by_sha.get(it.sha256)
        if not it.canonical:
            verdict[it.path] = "unidentified" + ("" if reg else ",registry-unidentified")
            continue
        state = (it.jurisdiction or "").startswith("us-") and it.jurisdiction != "us-federal"
        cands = [it.canonical] + ([] if state else [it.form_number or "", "form_" + (it.form_number or "")])
        hit = next((f for f in (resolve_form_id(c, db) for c in cands if c) if f), None)
        if reg and hit == reg:
            verdict[it.path] = "agree"
        elif reg and hit and hit != reg:
            verdict[it.path] = f"DISAGREE registry={reg} identified={hit}"
        elif reg and not hit:
            verdict[it.path] = f"registry={reg} identified-as-new={it.canonical}"
        elif hit:
            verdict[it.path] = f"newly-identified -> {hit}"
        else:
            verdict[it.path] = f"new form {it.canonical}"
    return verdict


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", nargs="?", type=Path)
    ap.add_argument("--src", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--registry", type=Path, default=REPO / "registry" / "registry.db")
    a = ap.parse_args()
    if a.pdf:
        print(json.dumps(asdict(identify(a.pdf)), indent=2)); return 0
    src = a.src or SOURCE_PDFS
    idents: list[Identity] = []
    for dp, _, fs in os.walk(src):
        for f in sorted(fs):
            if f.lower().endswith(".pdf"):
                try:
                    idents.append(identify(os.path.join(dp, f)))
                except Exception as e:
                    idents.append(Identity(path=os.path.join(dp, f), evidence={"error": {"rule": "open", "text": str(e)[:80]}}))
    n = len(idents)
    cov = {k: sum(1 for i in idents if getattr(i, k)) for k in ("issuer", "form_number", "edition", "omb", "catalog", "title", "xfa_root", "canonical")}
    print(f"[identify] {n} PDFs")
    for k, v in cov.items():
        print(f"  {k:12s} {v:4d}  {v / n:5.0%}")
    verdicts = reconcile(idents, a.registry) if a.registry.exists() else {}
    if verdicts:
        kinds = collections.Counter(v.split(" ")[0].split(",")[0] for v in verdicts.values())
        print("[reconcile]", dict(kinds))
    if a.out:
        a.out.parent.mkdir(parents=True, exist_ok=True)
        rows = [dict(asdict(i), registry=verdicts.get(i.path)) for i in idents]
        a.out.write_text(json.dumps(rows, indent=1))
        print(f"[ok] wrote {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
