"""Whole forms set aside, each with a reason (Andrew, 2026-11-03: an "ignored" status, "a little button next to the
'reset validation' button. there are a lot of fields that are just too messy or filled in or otherwise not valid right
now"; "this is for whole forms"). A review record, like `ignored_pages`, so the blueprints are left alone:

    runs/hand_review/ignored_forms.json    {review id: {"reason": "...", "when": "YYYY-mm-dd HH:MM:SS"}}

The home page shows an ignored form as its own status (the filter shows or hides it); `eval/benchmark_key.py` leaves
these forms out and `eval/benchmark_score.py` skips their pages still in an older key.
"""
from __future__ import annotations

import datetime
import threading
from pathlib import Path
from typing import Optional

from petey.validate import ignored_pages

ROOT = Path(__file__).resolve().parents[2]
RECORD = ROOT / "runs" / "hand_review" / "ignored_forms.json"
_LOCK = threading.Lock()
_CACHE: dict = {}


def load(record: Optional[Path] = None) -> dict:
    """The record, read again only when the file changed (the listing asks once a form)."""
    record = record or RECORD
    try:
        m = record.stat().st_mtime_ns
    except FileNotFoundError:
        return {}
    hit = _CACHE.get(record)
    if not hit or hit[0] != m:
        _CACHE[record] = hit = (m, ignored_pages.load(record))
    return hit[1]


def put(bid: str, ignore: bool, reason: str = "", record: Optional[Path] = None) -> dict:
    """Ignore the form (a reason is required) or take it back; the whole record back."""
    record = record or RECORD
    reason = " ".join((reason or "").split())
    if ignore and not reason:
        raise ValueError("say why the form is ignored")
    with _LOCK:
        rec = dict(load(record))
        if ignore:
            rec[bid] = {"reason": reason, "when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        else:
            rec.pop(bid, None)
        ignored_pages._write(rec, record)
    return rec


def page_form(page_id: str) -> str:
    """The review id of a key page id (`<review id>__p<page>`)."""
    return page_id.rsplit("__p", 1)[0]
