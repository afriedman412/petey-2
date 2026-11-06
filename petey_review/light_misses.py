"""The review page's "light misses" and "light junk" layers (Andrew, 2026-11-04): what the light path missed on a
tuning-set page and the junk it kept, read from the file `eval/light_misses.py` writes. Read again when the file
changes; marked stale when the tuning set was rebuilt after it."""
from __future__ import annotations

import json
from pathlib import Path

from petey.paths import RUNS

FILE = RUNS / "benchmark" / "dev_analysis" / "light_misses.json"
KEY_INDEX = RUNS / "benchmark" / "dev_key" / "index.json"
_cache: dict = {"mtime": None, "data": None}


def _load(path: Path = FILE) -> dict | None:
    try:
        mt = path.stat().st_mtime
    except OSError:
        return None
    if _cache["mtime"] != mt or _cache.get("path") != path:
        _cache.update(mtime=mt, path=path, data=json.loads(path.read_text()))
    return _cache["data"]


def for_form(bid: str, path: Path = FILE, key_index: Path = KEY_INDEX) -> dict | None:
    """{missed: [{page, rect, cause, kind, code}], junk: [{page, rect, jev}], built, stale} for one form, or None
    when the form has no tuning-set page (or there is no file)."""
    data = _load(path)
    pages = (data or {}).get("forms", {}).get(bid)
    if not pages:
        return None
    built = data.get("built") or {}
    try:
        stale = key_index.stat().st_mtime > (built.get("key_index_mtime") or 0) + 1
    except OSError:
        stale = False
    return {"missed": [dict(m, page=int(pg)) for pg, p in pages.items() for m in p.get("missed") or []],
            "junk": [dict(j, page=int(pg)) for pg, p in pages.items() for j in p.get("junk") or []],
            "built": built.get("when"), "stale": stale}


def counts(path: Path = FILE) -> dict[str, dict]:
    """{form id: {missed, junk}} over the tuning-set forms, for the home list's filter and column."""
    data = _load(path)
    return {bid: {"missed": sum(len(p.get("missed") or []) for p in pages.values()),
                  "junk": sum(len(p.get("junk") or []) for p in pages.values())}
            for bid, pages in ((data or {}).get("forms") or {}).items()}
