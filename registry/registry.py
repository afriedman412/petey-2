"""Blueprint registry: single source of truth for form/blueprint lifecycle state.

The SQLite db (registry.db) is authoritative and written only through this
module. A deterministic per-table JSONL export (export/) is what gets
committed to git; `lint` fails if db and filesystem disagree.

Usage:
    python registry.py init          # create empty db (idempotent)
    python registry.py stats         # counts by table / status
    python registry.py lint          # cross-check db vs blueprints/ on disk
    python registry.py export        # regenerate export/*.jsonl
    python registry.py query "SQL"   # read-only ad-hoc query
"""
from __future__ import annotations

import datetime
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(__file__).resolve().parent / "registry.db"
EXPORT_DIR = Path(__file__).resolve().parent / "export"

SCHEMA = """
CREATE TABLE IF NOT EXISTS forms (
    form_id        TEXT PRIMARY KEY,
    title          TEXT,
    description    TEXT,
    issuer         TEXT,
    omb_number     TEXT,
    edition        TEXT,
    vertical       TEXT,
    status         TEXT NOT NULL DEFAULT 'active'
                   CHECK (status IN ('planned', 'in_progress', 'active', 'retired')),
    site_published INTEGER NOT NULL DEFAULT 0,
    notes          TEXT
);

CREATE TABLE IF NOT EXISTS form_tags (
    form_id TEXT NOT NULL REFERENCES forms(form_id),
    tag     TEXT NOT NULL,
    PRIMARY KEY (form_id, tag)
);

CREATE TABLE IF NOT EXISTS aliases (
    alias   TEXT PRIMARY KEY,
    form_id TEXT NOT NULL REFERENCES forms(form_id)
);

CREATE TABLE IF NOT EXISTS artifacts (
    id           INTEGER PRIMARY KEY,
    form_id      TEXT REFERENCES forms(form_id),
    kind         TEXT NOT NULL
                 CHECK (kind IN ('bpt', 'widget_map', 'draft', 'site_copy')),
    spec_version TEXT,
    path         TEXT NOT NULL UNIQUE,
    status       TEXT NOT NULL
                 CHECK (status IN ('draft', 'superseded', 'promoted', 'published')),
    source_pdf   TEXT,
    source_pdf_hash TEXT,
    file_mtime   TEXT
);

CREATE TABLE IF NOT EXISTS source_pdfs (
    path            TEXT PRIMARY KEY,
    sha256          TEXT NOT NULL,
    form_id         TEXT REFERENCES forms(form_id),
    vertical        TEXT,
    pages           INTEGER,
    widget_count    INTEGER,
    fillable        INTEGER,
    status          TEXT NOT NULL DEFAULT 'unidentified'
                    CHECK (status IN ('unidentified', 'identified', 'excluded')),
    excluded_reason TEXT
);

CREATE TABLE IF NOT EXISTS external_refs (
    id      INTEGER PRIMARY KEY,
    form_id TEXT NOT NULL REFERENCES forms(form_id),
    source  TEXT NOT NULL CHECK (source IN ('extractbench', 'sensible', 'canonical')),
    ref     TEXT NOT NULL,
    detail  TEXT,
    UNIQUE (form_id, source, ref)
);

CREATE TABLE IF NOT EXISTS eval_runs (
    id            INTEGER PRIMARY KEY,
    form_id       TEXT NOT NULL REFERENCES forms(form_id),
    corpus        TEXT NOT NULL,
    cases         INTEGER,
    score         REAL,
    petey_version TEXT,
    run_date      TEXT
);
"""

TABLES = ["forms", "form_tags", "aliases", "artifacts", "source_pdfs",
          "external_refs", "eval_runs"]


def connect(readonly: bool = False) -> sqlite3.Connection:
    if readonly:
        conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init() -> sqlite3.Connection:
    conn = connect()
    conn.executescript(SCHEMA)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(forms)")}
    if "jurisdiction" not in cols:
        conn.execute("ALTER TABLE forms ADD COLUMN jurisdiction TEXT")
    conn.commit()
    return conn


# ── write API ────────────────────────────────────────────────────────

def upsert_form(conn, form_id: str, **cols) -> None:
    """Insert the form if new; update only the provided non-null columns."""
    conn.execute("INSERT OR IGNORE INTO forms (form_id) VALUES (?)", (form_id,))
    sets = {k: v for k, v in cols.items() if v is not None}
    if sets:
        assign = ", ".join(f"{k} = ?" for k in sets)
        conn.execute(f"UPDATE forms SET {assign} WHERE form_id = ?",
                     (*sets.values(), form_id))


def add_alias(conn, alias: str, form_id: str) -> None:
    conn.execute("INSERT OR REPLACE INTO aliases (alias, form_id) VALUES (?, ?)",
                 (alias, form_id))


def resolve(conn, name: str) -> str | None:
    """Resolve a name to a form_id via forms then aliases."""
    row = conn.execute("SELECT form_id FROM forms WHERE form_id = ?", (name,)).fetchone()
    if row:
        return row["form_id"]
    row = conn.execute("SELECT form_id FROM aliases WHERE alias = ?", (name,)).fetchone()
    return row["form_id"] if row else None


def add_artifact(conn, path: str, kind: str, status: str, form_id: str | None = None,
                 spec_version: str | None = None, source_pdf: str | None = None,
                 source_pdf_hash: str | None = None, file_mtime: str | None = None) -> None:
    conn.execute(
        """INSERT INTO artifacts (form_id, kind, spec_version, path, status,
                                  source_pdf, source_pdf_hash, file_mtime)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
               form_id = excluded.form_id, kind = excluded.kind,
               spec_version = excluded.spec_version, status = excluded.status,
               source_pdf = excluded.source_pdf,
               source_pdf_hash = excluded.source_pdf_hash,
               file_mtime = excluded.file_mtime""",
        (form_id, kind, spec_version, path, status, source_pdf, source_pdf_hash,
         file_mtime))


def add_source_pdf(conn, path: str, sha256: str, vertical: str | None,
                   pages: int, widget_count: int, form_id: str | None = None,
                   status: str = "unidentified",
                   excluded_reason: str | None = None) -> None:
    conn.execute(
        """INSERT INTO source_pdfs (path, sha256, form_id, vertical, pages,
                                    widget_count, fillable, status, excluded_reason)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(path) DO UPDATE SET
               sha256 = excluded.sha256, form_id = excluded.form_id,
               vertical = excluded.vertical, pages = excluded.pages,
               widget_count = excluded.widget_count, fillable = excluded.fillable,
               status = excluded.status, excluded_reason = excluded.excluded_reason""",
        (path, sha256, form_id, vertical, pages, widget_count,
         1 if widget_count > 0 else 0, status, excluded_reason))


def add_external_ref(conn, form_id: str, source: str, ref: str,
                     detail: str | None = None) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO external_refs (form_id, source, ref, detail)
           VALUES (?, ?, ?, ?)""",
        (form_id, source, ref, detail))


def add_eval_run(conn, form_id: str, corpus: str, cases: int, score: float,
                 petey_version: str | None = None,
                 run_date: str | None = None) -> None:
    """Record a scored eval run.

    Unlike every other table, eval_runs is not derivable by rescanning the
    filesystem — a score is a measured fact that costs API calls to reproduce.
    `backfill.py` therefore re-imports this table from the committed JSONL
    export instead of rebuilding it. Keep (form_id, corpus, run_date) unique
    enough to dedupe across rebuilds.
    """
    conn.execute(
        """INSERT INTO eval_runs (form_id, corpus, cases, score, petey_version,
                                  run_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (form_id, corpus, cases, score, petey_version,
         run_date or datetime.date.today().isoformat()))


# ── commands ─────────────────────────────────────────────────────────

def export() -> None:
    EXPORT_DIR.mkdir(exist_ok=True)
    conn = connect(readonly=True)
    for table in TABLES:
        rows = conn.execute(f"SELECT * FROM {table}").fetchall()
        dicts = sorted((dict(r) for r in rows), key=lambda d: json.dumps(d, sort_keys=True))
        for d in dicts:
            d.pop("id", None)  # surrogate ids are not stable across rebuilds
        out = EXPORT_DIR / f"{table}.jsonl"
        with out.open("w") as f:
            for d in dicts:
                f.write(json.dumps(d, sort_keys=True) + "\n")
    print(f"exported {len(TABLES)} tables to {EXPORT_DIR}")


def lint() -> int:
    conn = connect(readonly=True)
    problems: list[str] = []

    lib = {p.name for p in (ROOT / "blueprints").glob("*.bpt")}
    reg = {Path(r["path"]).name for r in conn.execute(
        "SELECT path FROM artifacts WHERE kind = 'bpt'"
        " AND path LIKE 'blueprints/%'")}
    for name in sorted(lib - reg):
        problems.append(f"orphan on disk (no registry row): blueprints/{name}")
    for name in sorted(reg - lib):
        problems.append(f"registry row without file: blueprints/{name}")

    for r in conn.execute("SELECT path FROM artifacts"):
        if not (ROOT / r["path"]).exists():
            problems.append(f"artifact path missing on disk: {r['path']}")

    n = conn.execute("SELECT COUNT(*) c FROM artifacts WHERE form_id IS NULL").fetchone()["c"]
    if n:
        problems.append(f"{n} artifacts with unresolved form_id")
    n = conn.execute("SELECT COUNT(*) c FROM source_pdfs WHERE status = 'unidentified'").fetchone()["c"]
    if n:
        problems.append(f"note: {n} source_pdfs awaiting identification")

    for p in problems:
        print(p)
    hard = [p for p in problems if not p.startswith("note:")]
    print(f"\n{len(hard)} problems, {len(problems) - len(hard)} notes")
    return 1 if hard else 0


def stats() -> None:
    conn = connect(readonly=True)
    q = conn.execute
    print("forms:", q("SELECT status, COUNT(*) c FROM forms GROUP BY status").fetchall() and
          {r["status"]: r["c"] for r in q("SELECT status, COUNT(*) c FROM forms GROUP BY status")})
    print("artifacts:", {f"{r['kind']}/{r['spec_version'] or '-'}/{r['status']}": r["c"] for r in
          q("SELECT kind, spec_version, status, COUNT(*) c FROM artifacts"
            " GROUP BY kind, spec_version, status")})
    print("source_pdfs:", {r["status"]: r["c"] for r in
          q("SELECT status, COUNT(*) c FROM source_pdfs GROUP BY status")},
          "| fillable:", q("SELECT COUNT(*) c FROM source_pdfs WHERE fillable = 1").fetchone()["c"])
    print("external_refs:", {r["source"]: r["c"] for r in
          q("SELECT source, COUNT(*) c FROM external_refs GROUP BY source")})
    print("aliases:", q("SELECT COUNT(*) c FROM aliases").fetchone()["c"],
          "| eval_runs:", q("SELECT COUNT(*) c FROM eval_runs").fetchone()["c"])


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"
    if cmd == "init":
        init(); print(f"initialized {DB_PATH}")
    elif cmd == "export":
        export()
    elif cmd == "lint":
        return lint()
    elif cmd == "stats":
        stats()
    elif cmd == "query":
        conn = connect(readonly=True)
        for row in conn.execute(sys.argv[2]):
            print(dict(row))
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
