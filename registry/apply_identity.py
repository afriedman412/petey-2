"""Apply a `petey.identify` run to the registry. Idempotent; never overwrites a hand-set value.

  identities     one row per PDF: canonical, issuer, number, edition, OMB, name, evidence (the document's facts)
  forms          issuer / jurisdiction filled where NULL; omb_number only when every PDF of the form agrees;
                 title only on forms this run creates. Edition is per document and stays in identities.
  aliases        canonical id -> form_id
  source_pdfs    form_id where missing (an exclusion is not an unknown identity); status=identified only for unidentified rows
  new forms      created (status=planned) ONLY for number-based identities; name-derived ones stay unidentified
  external_refs  source=sensible: Sensible configs whose stem resolves to a registry form

Usage:
    venv/bin/python registry/apply_identity.py --identity runs/identity.json [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import registry as R  # noqa: E402
from petey.paths import SENSIBLE_DIR  # noqa: E402
from petey.registry_lookup import resolve_form_id, norm  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--identity", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    rows = json.loads(a.identity.read_text())
    conn = R.connect() if hasattr(R, "connect") else R.init()
    c = Counter()

    def resolve(row):
        j = row.get("jurisdiction") or ""
        state = j.startswith("us-") and j != "us-federal"
        cands = [row.get("canonical")]
        if not state:  # a bare number may cross into a federal/industry form; a state form's may not
            cands += [row.get("form_number"), "form_" + (row.get("form_number") or "")]
        for cand in cands:
            f = resolve_form_id(cand) if cand else None
            if f:
                return f
        return None

    # 1. identities, aliases, source_pdfs; new planned forms for numbered identities
    conn.executescript(R.SCHEMA) if hasattr(R, "SCHEMA") else None
    omb_by_form: dict[str, set] = {}
    for r in rows:
        if not r.get("canonical"):
            continue
        numbered = bool(r.get("form_number"))
        fid = resolve(r)
        if fid is None and numbered:
            fid = r["canonical"]
            if not a.dry_run:
                R.upsert_form(conn, fid, status="planned", issuer=r.get("issuer"), jurisdiction=r.get("jurisdiction"),
                              title=r.get("form_name"), notes="created by apply_identity from the document")
            c["form_created"] += 1
        if fid is None:
            c["name_only_left_unidentified"] += 1
        if a.dry_run:
            c["would_link" if fid else "would_record_only"] += 1
            continue
        conn.execute("""INSERT OR REPLACE INTO identities
            (sha256, path, form_id, canonical, issuer, jurisdiction, form_number, edition, omb_number, catalog_number,
             form_name, xfa_root, text_layer, evidence) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (r["sha256"], os.path.relpath(r["path"], str(Path(__file__).resolve().parents[1])), fid, r["canonical"],
             r.get("issuer"), r.get("jurisdiction"), r.get("form_number"), r.get("edition"), r.get("omb"), r.get("catalog"),
             r.get("form_name"), r.get("xfa_root"), int(bool(r.get("text_layer", True))), json.dumps(r.get("evidence") or {})))
        c["identity_recorded"] += 1
        if fid is None:
            continue
        for col, val in (("issuer", r.get("issuer")), ("jurisdiction", r.get("jurisdiction"))):
            if val:
                c[f"forms.{col}_filled"] += conn.execute(
                    f"UPDATE forms SET {col}=? WHERE form_id=? AND ({col} IS NULL OR {col}='')", (val, fid)).rowcount
        if r.get("omb"):
            omb_by_form.setdefault(fid, set()).add(r["omb"])
        if r["canonical"] != fid:
            R.add_alias(conn, r["canonical"], fid); c["alias"] += 1
        c["source_pdf_linked"] += conn.execute(
            "UPDATE source_pdfs SET form_id=? WHERE sha256=? AND (form_id IS NULL OR form_id='')",
            (fid, r["sha256"])).rowcount
        conn.execute("UPDATE source_pdfs SET status='identified' WHERE sha256=? AND status='unidentified'", (r["sha256"],))
    if not a.dry_run:
        for fid, ombs in omb_by_form.items():
            if len(ombs) == 1:
                c["forms.omb_number_filled"] += conn.execute(
                    "UPDATE forms SET omb_number=? WHERE form_id=? AND (omb_number IS NULL OR omb_number='')",
                    (next(iter(ombs)), fid)).rowcount
            else:
                c["omb_conflict_skipped"] += 1

    # 2. Sensible configs -> external_refs
    if Path(SENSIBLE_DIR).exists():
        for p in sorted(Path(SENSIBLE_DIR).rglob("*.json")):
            if "configurations" not in p.parts or ".git" in p.parts:
                continue
            base = re.sub(r"(_\d{4}_\d{2})+(_[a-z]{2})?$", "", p.stem)
            fid = resolve_form_id(base) or resolve_form_id(p.stem)
            if not fid:
                continue
            rel = str(p.relative_to(SENSIBLE_DIR))
            if not a.dry_run:
                if not conn.execute("SELECT 1 FROM external_refs WHERE source='sensible' AND ref=?", (rel,)).fetchone():
                    R.add_external_ref(conn, fid, "sensible", rel, json.dumps({"category": "/".join(p.parts[-4:-2])}))
                    c["sensible_ref_added"] += 1
            c["sensible_matched"] += 1
    else:
        print(f"[apply_identity] Sensible library not found at {SENSIBLE_DIR}; set PETEY_SENSIBLE_DIR", file=sys.stderr)

    if not a.dry_run:
        conn.commit()
    print(("[dry-run] " if a.dry_run else "[applied] ") + json.dumps(dict(c), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
