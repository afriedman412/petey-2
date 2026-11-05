"""Fields left out of the flat-structure benchmark, each with a reason (Andrew, 2026-11-03: fields stacked in one open
area with no printed line between them, "there is no way to know how to divide a field without any lines, can we just
ignore all fields like that? ... if they are valid metadata, we still need them on the bpt"). A side record like
`ignored_pages`, so the blueprints keep the fields:

    runs/benchmark/ignored_fields.json    {page id: {field id: {"reason", "source", "when"}}}

A page id is the key's, `<review id>__p<page>`; a field id is the key's (the field's code, `code.option` for an option
box). `source` names the batch that set it (a sweep), so one batch can be taken back in one step (`drop_source`).
`eval/benchmark_key.py` leaves these fields out of the key and keeps their boxes as the page's ignored areas;
`eval/benchmark_score.py` leaves out a system's boxes that sit mostly inside those areas, so no method gains or loses
there.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from pathlib import Path
from typing import Optional

from petey_dataset import BENCHMARK
from petey_dataset.ignored_pages import PAGE_ID

RECORD = BENCHMARK / "ignored_fields.json"
_LOCK = threading.Lock()


def load(record: Optional[Path] = None) -> dict:
    record = record or RECORD
    return json.loads(record.read_text()) if record.exists() else {}


def _write(rec: dict, record: Path) -> None:
    record.parent.mkdir(parents=True, exist_ok=True)
    tmp = record.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True))
    os.replace(tmp, record)


def put(page_id: str, field_ids: list[str], reason: str, source: str = "review page",
        record: Optional[Path] = None) -> dict:
    """Ignore these fields of the page (a reason is required); the whole record back."""
    record = record or RECORD
    if not PAGE_ID.match(page_id):
        raise ValueError(f"not a page id: {page_id!r} (want <review id>__p<page>)")
    reason = " ".join((reason or "").split())
    if not reason:
        raise ValueError("say why the fields are ignored")
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _LOCK:
        rec = load(record)
        page = rec.setdefault(page_id, {})
        for f in field_ids:
            page[str(f)] = {"reason": reason, "source": source, "when": when}
        if not page:
            rec.pop(page_id)
        _write(rec, record)
    return rec


def take_back(page_id: str, field_ids: list[str], record: Optional[Path] = None) -> dict:
    record = record or RECORD
    with _LOCK:
        rec = load(record)
        page = rec.get(page_id, {})
        for f in field_ids:
            page.pop(str(f), None)
        if page_id in rec and not page:
            rec.pop(page_id)
        _write(rec, record)
    return rec


def drop_source(source: str, record: Optional[Path] = None) -> int:
    """Take back every field one batch set; how many."""
    record = record or RECORD
    with _LOCK:
        rec, n = load(record), 0
        for pid in list(rec):
            for f in [f for f, v in rec[pid].items() if v.get("source") == source]:
                del rec[pid][f]
                n += 1
            if not rec[pid]:
                del rec[pid]
        _write(rec, record)
    return n
