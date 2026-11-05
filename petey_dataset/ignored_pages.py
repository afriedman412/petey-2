"""Pages left out of the flat-structure benchmark, each with a reason (Andrew, 2026-10-31: an "ignore this page" tag on
the review page "along with a field to provide a reason"; checklists go this way, and the sweep of pages with no or few
fields). A bulk tagging record, not production data, so the blueprints are left alone:

    runs/benchmark/ignored_pages.json    {page id: {"reason": "...", "when": "YYYY-mm-dd HH:MM:SS"}}

A page id is the key's, `<review id>__p<page>` (pages from 1). `eval/benchmark_key.py` leaves these pages out before
it picks a form's pages, and `eval/benchmark_score.py` skips any still in an older key.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from petey_dataset import BENCHMARK

RECORD = BENCHMARK / "ignored_pages.json"
PAGE_ID = re.compile(r"^[\w.-]+__p[1-9]\d*$")
_LOCK = threading.Lock()


def load(record: Optional[Path] = None) -> dict:
    record = record or RECORD
    return json.loads(record.read_text()) if record.exists() else {}


def _write(rec: dict, record: Path) -> None:
    record.parent.mkdir(parents=True, exist_ok=True)
    tmp = record.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True))
    os.replace(tmp, record)


def put(page_id: str, ignore: bool, reason: str = "", record: Optional[Path] = None) -> dict:
    """Ignore the page (a reason is required) or take it back; the whole record back."""
    record = record or RECORD
    if not PAGE_ID.match(page_id):
        raise ValueError(f"not a page id: {page_id!r} (want <review id>__p<page>)")
    reason = " ".join((reason or "").split())
    if ignore and not reason:
        raise ValueError("say why the page is ignored")
    with _LOCK:
        rec = load(record)
        if ignore:
            rec[page_id] = {"reason": reason, "when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        else:
            rec.pop(page_id, None)
        _write(rec, record)
    return rec
