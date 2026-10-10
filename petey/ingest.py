"""Registry ingestion for a blank form: identify it, resolve or register it.

The generator used to take the form id from its caller (`--name`) and never
touch the registry; identity lived in a separate batch (`petey.identify` ->
`registry/apply_identity.py`). This puts the per-document half of that batch
in the generator's path:

  1. sha256 of the PDF -> an existing `source_pdfs` / `identities` row?
  2. else `petey.identify` -> canonical id (issuer + number, or a title-derived
     name) -> `registry_lookup.resolve_form_id` (forms, aliases, normalized)
  3. else register: a `forms` row (status planned) when the identity is
     number-based — the same rule apply_identity uses, so title-only guesses
     do not mint forms — and an alias canonical -> form_id when they differ
  4. always: the `identities` row and the `source_pdfs` row for this file

`record_blueprint` then links the written blueprint as an artifact and moves
the form from planned to in_progress. The registry db is the authority;
`registry/registry.py export` regenerates the committed JSONL.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import pymupdf

from petey.identify import identify, slug
from petey.paths import BLUEPRINTS, REPO
from petey.registry_lookup import resolve_form_id

sys.path.insert(0, str(REPO / "registry"))
import registry as R  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def ingest(blank_pdf: Path, *, name: Optional[str] = None, dry_run: bool = False) -> dict:
    """Resolve (or register) the form a blank PDF belongs to.

    `name` — the caller's own id for this form (a blueprint stem). It never
    overrides what the document resolves to: if the PDF is known (by hash)
    or its canonical id resolves, that registry form wins and `name` is
    recorded as an alias of it. Only when nothing resolves does `name`
    become the new form's id. Blueprint stems and registry ids differ by
    convention across the library, and the registry is the join.
    Returns {form_id, via, canonical, issuer, form_number, edition, omb, title, created}.
    """
    blank_pdf = Path(blank_pdf)
    sha = _sha256(blank_pdf)
    conn = R.init()
    try:
        known = conn.execute(
            "SELECT form_id FROM source_pdfs WHERE sha256 = ? AND form_id IS NOT NULL "
            "UNION SELECT form_id FROM identities WHERE sha256 = ? AND form_id IS NOT NULL",
            (sha, sha)).fetchone()
        ident = identify(blank_pdf)
        created = False
        hit = resolve_form_id(ident.canonical) if ident.canonical else None
        name_hit = resolve_form_id(name) if name else None
        if known:
            form_id, via = known["form_id"], "sha256"
        elif hit:
            form_id, via = hit, "canonical"
        elif name_hit:
            form_id, via = name_hit, "name"
        elif name:
            form_id, via = name, "new_from_name"
        elif ident.canonical:
            form_id, via = ident.canonical, "new"
        else:
            form_id, via = slug(blank_pdf.stem), "file_stem"

        number_based = bool(ident.form_number)
        exists = conn.execute("SELECT 1 FROM forms WHERE form_id = ?", (form_id,)).fetchone()
        if not dry_run:
            if not exists and (number_based or via == "new_from_name"):
                R.upsert_form(conn, form_id, status="planned", issuer=ident.issuer,
                              title=ident.form_name or ident.title)
                conn.execute("UPDATE forms SET jurisdiction = ? WHERE form_id = ? AND jurisdiction IS NULL",
                             (ident.jurisdiction, form_id))
                created = True
            registered = exists or created
            if registered:
                for col, val in (("issuer", ident.issuer), ("omb_number", ident.omb)):
                    if val:
                        conn.execute(f"UPDATE forms SET {col} = ? WHERE form_id = ? "
                                     f"AND ({col} IS NULL OR {col} = '')", (val, form_id))
                # Aliases are added, never repointed: an alias that already
                # names another form keeps it.
                for alias in (ident.canonical, name):
                    if alias and alias != form_id:
                        conn.execute("INSERT OR IGNORE INTO aliases (alias, form_id) VALUES (?, ?)",
                                     (alias, form_id))
            conn.execute(
                """INSERT OR REPLACE INTO identities
                   (sha256, path, form_id, canonical, issuer, jurisdiction, form_number, edition,
                    omb_number, catalog_number, form_name, xfa_root, text_layer, evidence)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sha, _rel(blank_pdf), form_id if registered else None, ident.canonical,
                 ident.issuer, ident.jurisdiction, ident.form_number, ident.edition, ident.omb,
                 ident.catalog, ident.form_name, ident.xfa_root, int(ident.text_layer),
                 json.dumps(ident.evidence)))
            doc = pymupdf.open(str(blank_pdf))
            try:
                pages = doc.page_count
                widgets = sum(len(list(p.widgets() or [])) for p in doc)
            finally:
                doc.close()
            prior = conn.execute("SELECT vertical, status, excluded_reason FROM source_pdfs WHERE path = ?",
                                 (_rel(blank_pdf),)).fetchone()
            R.add_source_pdf(conn, _rel(blank_pdf), sha, prior["vertical"] if prior else None,
                             pages, widgets, form_id=form_id if registered else None,
                             status=(prior["status"] if prior and prior["status"] == "excluded"
                                     else ("identified" if registered else "unidentified")),
                             excluded_reason=prior["excluded_reason"] if prior else None)
            conn.commit()
        return {"form_id": form_id, "via": via, "canonical": ident.canonical,
                "issuer": ident.issuer, "form_number": ident.form_number,
                "edition": ident.edition, "omb": ident.omb,
                "title": ident.form_name or ident.title, "created": created}
    finally:
        conn.close()


def record_blueprint(form_id: str, bpt_path: Path, blank_pdf: Path, *,
                     placeholder_names: bool, spec_version: Optional[str] = None) -> bool:
    """Link a written blueprint to its form. Only files in the library
    (`blueprints/`) are registered — a scratch output is not an artifact,
    and `registry.py lint` checks the library against the db."""
    bpt_path = Path(bpt_path).resolve()
    if bpt_path.parent != BLUEPRINTS.resolve():
        return False
    conn = R.init()
    try:
        if not conn.execute("SELECT 1 FROM forms WHERE form_id = ?", (form_id,)).fetchone():
            return False
        mtime = datetime.datetime.fromtimestamp(bpt_path.stat().st_mtime).isoformat(timespec="seconds")
        R.add_artifact(conn, _rel(bpt_path), "draft" if placeholder_names else "bpt", "draft",
                       form_id=form_id, spec_version=spec_version,
                       source_pdf=Path(blank_pdf).name, source_pdf_hash=_sha256(Path(blank_pdf)),
                       file_mtime=mtime)
        conn.execute("UPDATE forms SET status = 'in_progress' WHERE form_id = ? AND status = 'planned'",
                     (form_id,))
        conn.commit()
        return True
    finally:
        conn.close()


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Identify a blank PDF and resolve or register its form.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--name", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    print(json.dumps(ingest(args.pdf, name=args.name, dry_run=args.dry_run), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
