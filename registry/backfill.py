"""One-shot idempotent backfill of registry.db from everything on disk plus
ExtractBench case references. Safe to rerun; every write is an upsert.

Sources:
  blueprints/*.bpt                v1.1 library (carry source_pdf_hash)
  source_pdfs/**/*.pdf            downloaded blanks (scanned for widgets)
  <scratchpad>/{short,medium,long}.jsonl  ExtractBench cases

Run from the repo root:
  venv/bin/python registry/backfill.py [--jsonl-dir DIR]
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry as R

ROOT = R.ROOT

# ── ExtractBench schema-title / case-id → form_id mapping ────────────
# (form_id, status if form must be created, vertical, title)
EB_TITLE_PREFIX = {
    "Form W-2 Wage and Tax Statement": ("w_2", None, "tax", None),
    "Form 1099-B": ("1099_b", None, "tax", None),
    "Schedule K-1 (Form 1065)": ("schedule_k_1", None, "tax", None),
    "Schedule K-1 (Form 1120S)": ("form_1120_s_schedule_k_1", "planned", "tax",
                                  "Schedule K-1 (Form 1120-S)"),
    "Form 1040": ("1040", None, "tax", None),
    "SEC Form 13F": ("form_13f", None, "finance", None),
    "BrokerageConsolidated1099": ("consolidated_1099", "planned", "finance",
                                  "Consolidated brokerage 1099 statement"),
    "CBPForm7501EntrySummary": ("cbp_form_7501", None, "immigration", None),
    "DD1155Schedule": ("dd_1155", "planned", "procurement",
                       "DD Form 1155 Order for Supplies or Services"),
    "SF1449": ("sf_1449", "planned", "procurement",
               "SF 1449 Solicitation/Contract/Order for Commercial Products"),
    "DoDClinSchedule": ("dod_clin_schedule", "planned", "procurement",
                        "DoD CLIN schedule"),
    "GsaMasItLaborPricelist": ("gsa_mas_pricelist", "planned", "procurement",
                               "GSA MAS labor category pricelist"),
    "RRCW1Extraction": ("rrc_w_1", "planned", "energy_rrc",
                        "Texas RRC Form W-1 Application for Permit to Drill"),
    "RRCW2Extraction": ("rrc_w_2", "planned", "energy_rrc",
                        "Texas RRC Form W-2 Oil Well Potential Test / Completion Report"),
    "RRCW14ReviewExtraction": ("rrc_w_14", "planned", "energy_rrc",
                               "Texas RRC Form W-14 Disposal Well Application"),
    "RRCH5Extraction": ("rrc_h_5", "planned", "energy_rrc",
                        "Texas RRC Form H-5 Injection Well Pressure Test"),
    "RRCH9Extraction": ("rrc_h_9", "planned", "energy_rrc",
                        "Texas RRC Form H-9 Injection/Disposal Well Monitoring"),
    "RRCH12Extraction": ("rrc_h_12", "planned", "energy_rrc",
                         "Texas RRC Form H-12 Enhanced Recovery Report"),
    "RRCP4Extraction": ("rrc_p_4", "planned", "energy_rrc",
                        "Texas RRC Form P-4 Certificate of Compliance / Operator Transfer"),
    "RRCP18Extraction": ("rrc_p_18", "planned", "energy_rrc",
                         "Texas RRC Form P-18 Skim Oil/Condensate Report"),
    "RRC2AExtraction": ("rrc_2a", "planned", "energy_rrc",
                        "Texas RRC Form 2A Plugging Application"),
    "CCCMarketValuationReport": ("ccc_valuation", "planned", "auto_valuation",
                                 "CCC ONE Market Valuation Report"),
    "MitchellVehicleValuationReport": ("mitchell_valuation", "planned", "auto_valuation",
                                       "Mitchell Vehicle Valuation Report"),
    "StateMedicaidRemittanceAdvice": ("medicaid_remittance_advice", "planned", "healthcare",
                                      "State Medicaid remittance advice"),
    "UtilityBill": ("utility_bill", "planned", "consumer",
                    "Residential utility bill"),
    "ClosingDisclosureTRID": ("closing_disclosure", None, "mortgage", None),
    "PurchaseOrder": ("purchase_order", "planned", "supply_chain",
                      "Purchase order / requisition"),
    "WholesaleCatalogPriceList": ("wholesale_price_list", "planned", "supply_chain",
                                  "Wholesale catalog price list"),
    "GovernmentFleetRateCard": ("fleet_rate_card", "planned", "supply_chain",
                                "Government fleet rate card"),
    "Product Spec Sheet": ("product_spec_sheet", "planned", "supply_chain",
                           "Product spec sheet / datasheet"),
    "Bankruptcy Schedule E/F": ("form_206ef", "planned", "us_courts",
                                "Bankruptcy Official Form 206E/F Creditors With Unsecured Claims"),
}
EB_ID_PREFIX = {
    "sched_i__": ("form_990_schedule_i", "planned", "tax",
                  "Form 990 Schedule I Grants and Other Assistance"),
    "nport__": ("form_nport", "planned", "finance", "SEC Form N-PORT"),
    "13f__": ("form_13f", None, "finance", None),
    "sec_13f_": ("form_13f", None, "finance", None),
}

DRAFT_SUFFIX = re.compile(r"_(canonical_v\d+|pre_verify|v\d+)$")

# hand-curated aliases: v1.1 / filename spellings → canonical form_id.
# Where the canonical form doesn't exist yet, this still fixes the id it
# will be created under (clean, convention-following).
HAND_ALIASES = {
    "cbp7501": "cbp_form_7501",
    "cbp3299": "cbp_form_3299",
    "cms1500": "cms_1500",
    "cms855a": "cms_855a", "cms855b": "cms_855b", "cms855i": "cms_855i",
    "fw2": "w_2", "fw2c": "form_w_2c", "fw2g": "form_w_2g",
    "fw4": "w_4", "fw4_pymupdf": "w_4", "fw9": "w_9",
    "fw8ben": "form_w_8_ben", "fw8bene": "form_w_8_ben_e",
    "f1040s": "1040_sr",
    "f1040sa": "schedule_a", "f1040sb": "schedule_b", "f1040sc": "schedule_c",
    "f1040sd": "schedule_d", "f1040se": "schedule_e", "f1040sse": "schedule_se",
    "f4506t": "form_4506_t",
    "f4562": "form_4562",
    "f1099b--2026": "1099_b",
    "1099_nec_blank": "1099_nec",
    "f5500sa": "form_5500_schedule_a", "f5500sh": "form_5500_schedule_h",
    "f5500sr": "form_5500_schedule_r",
    "2025-form-5500": "form_5500", "2025-form-5500-ez": "form_5500_ez",
    "2025-form-5500-sf": "form_5500_sf",
    "2025-schedule-a": "form_5500_schedule_a",
    "2025-schedule-h": "form_5500_schedule_h",
    "2025-schedule-r": "form_5500_schedule_r",
    "acord25": "acord_25", "acord25_blank": "acord_25",
    "acord27": "acord_27", "acord_27_2016_03": "acord_27",
    "f1099b_2026": "1099_b",
    "acord125": "acord_125", "acord130": "acord_130",
    "urla": "urla_form_1003",
    "hud1": "hud_1",
    "formd": "sec_form_d",
    "fecfrm3x": "fec_form_3x",
    "da4187": "da_form_4187",
    "vba21526ez": "va_form_21_526ez",
    "casc100": "ca_sc_100",
    "tx01114": "tx_01_114",
    "i-130": "i_130", "i-485": "i_485", "i-765": "i_765", "i-9": "i_9",
    "1040_nr": "form_1040_nr", "1040_x": "form_1040_x",
    "form_1120s": "form_1120_s", "w_2g": "form_w_2g",
    "form_1040_label_stub": "1040",
}

_BOUNDARY = re.compile(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)")


def id_variants(name: str) -> list[str]:
    """Ordered candidate form_ids for a raw blueprint/file name."""
    s = slugify(name)
    if name in HAND_ALIASES:
        return [HAND_ALIASES[name]]
    if s in HAND_ALIASES:
        return [HAND_ALIASES[s]]
    out = [name, s]
    t = re.sub(r"_(blank|fillable|pymupdf)$", "", s)
    t = re.sub(r"_?(19|20)\d{2}([a-z0-9_]*)$", "", t)
    for c in dict.fromkeys([s, t]):
        m = re.match(r"^f(\d.+)$", c)
        if m:
            core = _BOUNDARY.sub("_", m.group(1))
            out += [core, f"form_{core}"]
        else:
            out.append(_BOUNDARY.sub("_", c))
    return list(dict.fromkeys(out))


def resolve_or_pick(conn, name: str) -> tuple[str | None, str]:
    """Resolve name to an existing form_id, else return (None, best_new_id)."""
    cands = id_variants(name)
    for c in cands:
        fid = R.resolve(conn, c)
        if fid:
            return fid, fid
    return None, cands[-1]


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def mtime(p: Path) -> str:
    return datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(timespec="seconds")


def bpt_header(path: Path) -> dict:
    """Parse a .bpt's YAML; fall back to regex on the first lines."""
    try:
        data = yaml.safe_load(path.read_text())
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    head = path.read_text(errors="replace")[:2000]
    out = {}
    for key in ("bpt_version", "name", "source_pdf", "source_pdf_hash"):
        m = re.search(rf"^{key}:\s*['\"]?([^'\"\n]+)", head, re.M)
        if m:
            out[key] = m.group(1).strip()
    return out


def known_pdf_map() -> dict[str, str]:
    from known_pdfs import KNOWN_PDF_TO_FORM_ID
    return dict(KNOWN_PDF_TO_FORM_ID)


@functools.lru_cache(maxsize=None)
def manifest_identified(d: Path) -> frozenset[str]:
    """Files whose manifest (registry/sources/<dir>.json) carries an identity (registry/manifest_identity.py)."""
    mp = ROOT / "registry" / "sources" / f"{d.name}.json"
    if not mp.exists():
        return frozenset()
    return frozenset(f["file"] for f in json.loads(mp.read_text()).get("files", []) if f.get("identity"))


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--jsonl-dir", type=Path, default=None,
                    help="dir containing ExtractBench short/medium/long.jsonl")
    args = ap.parse_args()

    conn = R.init()
    pdf_map = known_pdf_map()  # 'fw2.pdf' -> 'w_2'
    counts: dict[str, int] = {}

    def bump(k):
        counts[k] = counts.get(k, 0) + 1

    # 1. v1.1 blueprints (the library) --------------------------------
    for p in sorted((ROOT / "blueprints").glob("*.bpt")):
        hdr = bpt_header(p)
        name = str(hdr.get("name") or p.stem)
        fid, new_id = resolve_or_pick(conn, name)
        if fid is None:
            fid = new_id
            R.upsert_form(conn, fid, status="in_progress",
                          notes="auto-created from v1.1 backfill")
            bump("form_created_v11")
        if name != fid:
            R.add_alias(conn, name, fid)
        R.add_artifact(conn, f"blueprints/{p.name}", "bpt", "draft",
                       form_id=fid, spec_version=str(hdr.get("bpt_version", "1.1")),
                       source_pdf=hdr.get("source_pdf"),
                       source_pdf_hash=hdr.get("source_pdf_hash"),
                       file_mtime=mtime(p))
        bump("bpt_v11")

    # seed aliases from the known pdf->form map ---------------------
    for pdf_name, fid in pdf_map.items():
        target = R.resolve(conn, fid)
        if target:
            R.add_alias(conn, Path(pdf_name).stem, target)

    # 6. source PDFs ------------------------------------------------
    import pymupdf
    for p in sorted((ROOT / "source_pdfs").rglob("*.pdf")):
        rel = p.relative_to(ROOT / "source_pdfs")
        if rel.parts[0].startswith("_"):
            continue  # _inbox, _flat_calibration: staging and test copies, not corpus
        vertical = rel.parts[0] if len(rel.parts) > 1 else "misc"
        try:
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
        except OSError:
            bump("pdf_unreadable")
            continue
        try:
            doc = pymupdf.open(p)
            pages = len(doc)
            widgets = sum(len(list(pg.widgets() or [])) for pg in doc)
            doc.close()
        except Exception:
            pages, widgets = -1, 0
        status, reason, fid = "unidentified", None, None
        if vertical == "rrc_raw":
            status, reason = "excluded", "detector_training"
        elif p.name in manifest_identified(p.parent):
            pass  # identity recorded at acquisition; apply_identity links it, no filename guess
        else:
            mapped = pdf_map.get(p.name)
            fid = R.resolve(conn, mapped) if mapped else None
            if fid is None:
                fid, _ = resolve_or_pick(conn, p.stem)
            if fid:
                status = "identified"
        if fid is None:
            # no filename guess: keep a link apply_identity made on an earlier run instead of erasing it
            prev = conn.execute("SELECT form_id FROM source_pdfs WHERE path = ?",
                                (f"source_pdfs/{rel}",)).fetchone()
            if prev and prev[0]:
                fid = prev[0]
                if status == "unidentified":
                    status = "identified"
        R.add_source_pdf(conn, f"source_pdfs/{rel}", sha, vertical, pages, widgets,
                         form_id=fid, status=status, excluded_reason=reason)
        bump(f"pdf_{status}")

    # 7. ExtractBench case refs -------------------------------------
    jsonl_dir = args.jsonl_dir
    if jsonl_dir:
        for split in ("short", "medium", "long"):
            f = jsonl_dir / f"{split}.jsonl"
            if not f.exists():
                print(f"warning: {f} missing, skipping split", file=sys.stderr)
                continue
            with f.open() as fh:
                for line in fh:
                    case = json.loads(line)
                    cid = case["id"]
                    try:
                        schema = json.loads(case["data_schema"]) if isinstance(
                            case["data_schema"], str) else case["data_schema"]
                        title = (schema or {}).get("title") or ""
                    except Exception:
                        title = ""
                    hit = None
                    for prefix, spec in EB_TITLE_PREFIX.items():
                        if title.startswith(prefix):
                            hit = spec
                            break
                    if hit is None:
                        base = cid.split("/", 1)[-1]
                        for prefix, spec in EB_ID_PREFIX.items():
                            if base.startswith(prefix):
                                hit = spec
                                break
                    if hit is None:
                        bump("eb_skipped")
                        continue
                    fid, create_status, vertical, ftitle = hit
                    target = R.resolve(conn, fid)
                    if target is None:
                        R.upsert_form(conn, fid, status=create_status or "planned",
                                      vertical=vertical, title=ftitle,
                                      notes="target sourced from ExtractBench")
                        bump("form_created_eb")
                        target = fid
                    detail = json.dumps({"split": split, "schema_title": title[:80],
                                         "pdf": case.get("pdf")}, sort_keys=True)
                    R.add_external_ref(conn, target, "extractbench", cid, detail)
                    bump("eb_case")

    # eval_runs is the one table a filesystem rescan cannot reconstruct: a
    # score is a measured fact, not a derived one, and re-deriving it means
    # paying for the extraction again. Restore it from the committed export so
    # the documented `rm registry.db && backfill.py` chain stays lossless.
    # Same problem for external_refs that don't come from ExtractBench. The
    # sweep above rebuilds only `extractbench` rows by re-reading the EB
    # jsonls; a `reddit` or `sensible` ref is measured signal that no
    # filesystem rescan can reproduce, so restore those from the export too.
    refs_export = R.EXPORT_DIR / "external_refs.jsonl"
    if refs_export.exists():
        for line in refs_export.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("source") == "extractbench":
                continue  # rebuilt from the jsonls, would duplicate
            if R.resolve(conn, row["form_id"]) is None:
                bump("ref_orphaned")
                continue
            R.add_external_ref(conn, row["form_id"], row["source"],
                               row["ref"], row.get("detail"))
            bump(f"ref_restored_{row['source']}")

    eval_export = R.EXPORT_DIR / "eval_runs.jsonl"
    if eval_export.exists():
        seen = set()
        for line in eval_export.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            key = (row.get("form_id"), row.get("corpus"), row.get("run_date"))
            if key in seen:
                continue
            seen.add(key)
            if R.resolve(conn, row["form_id"]) is None:
                bump("eval_run_orphaned")
                continue
            if conn.execute("SELECT 1 FROM eval_runs WHERE form_id=? AND corpus=? AND run_date IS ?",
                            key).fetchone():
                continue  # already in the db (a rerun on a live registry, not a fresh rebuild)
            R.add_eval_run(conn, row["form_id"], row["corpus"],
                           row.get("cases"), row.get("score"),
                           row.get("petey_version"), row.get("run_date"))
            bump("eval_run_restored")

    conn.commit()
    print(json.dumps(counts, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
