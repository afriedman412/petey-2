"""Read-only form-id resolution against the registry.

The registry is the identity layer: every "which form is this" question
goes through here, never through a filename. Resolution order: exact
form_id, alias, then normalised comparison (case/punctuation,
'schedule'->'sch', leading zeros, a leading 'form_' wrapper).
"""
from __future__ import annotations

import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Optional

from petey.paths import REPO

DB = REPO / "registry" / "registry.db"


def norm(s: str) -> str:
    s = s.lower().replace("schedule", "sch")
    s = re.sub(r"^(?:[a-z]{2,6}_)?form_", "", s)
    s = re.sub(r"[^a-z0-9]", "", s)
    return re.sub(r"(?<![0-9])0+(\d)", r"\1", s)


@lru_cache(maxsize=1)
def _tables(db: str) -> tuple[dict, dict, dict, dict]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    forms = {r[0] for r in conn.execute("SELECT form_id FROM forms")}
    aliases = {a: f for a, f in conn.execute("SELECT alias, form_id FROM aliases")}
    conn.close()
    return ({f: f for f in forms}, aliases, {norm(f): f for f in forms}, {norm(a): f for a, f in aliases.items()})


def resolve_form_id(name: str, db: Path | str = DB) -> Optional[str]:
    """Registry form_id for a filename stem, blueprint name, Sensible key or canonical id; None if unknown."""
    if not name or not Path(db).exists():
        return None
    forms, aliases, nf, na = _tables(str(db))
    if name in forms:
        return name
    if name in aliases:
        return aliases[name]
    n = norm(name)
    hit = nf.get(n) or na.get(n)
    if hit:
        return hit
    # The older registry named state-agency forms without the state (`rrc_h_12`);
    # the identifier writes `tx_rrc_h_12`. Bridge that only when an agency token
    # remains after the state code, never for a bare number (il_1040 is not 1040).
    m = re.match(r"^[a-z]{2}_([a-z]{3,}_.+)$", name)
    if m:
        n2 = norm(m.group(1))
        return nf.get(n2) or na.get(n2)
    return None
