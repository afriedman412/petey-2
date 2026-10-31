"""Printed fields in the flat-structure benchmark's key (Andrew, 2026-10-31: a third field type, "printed": "anything
that is expected to be hand-written -- signatures, printed names, etc."). Initials are printed; the date of signing and
a signer's title stay text.

The blueprints do not say which fields are printed, and are left alone (a change would un-validate them). The answer
is this record, one entry a key page, written from the review server's printed sheet (/printed):

    runs/benchmark/field_types.json    {page id: {"printed": [field id, ...], "when": "YYYY-mm-dd HH:MM:SS"}}

A page in the record is confirmed: its printed fields are exactly those listed. The sheet shows each key page with
candidates (eval/benchmark_printed.py: runs/benchmark/printed/candidates.json) with every text field drawn, the
candidates marked; Andrew clicks to unmark or mark, then confirms the page. `eval/benchmark_key.py` reads the record.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "runs" / "benchmark"
RECORD = BENCH / "field_types.json"
CANDIDATES = BENCH / "printed" / "candidates.json"
KEY = BENCH / "key"
HTML_PATH = Path(__file__).with_name("printed_fields.html")
_LOCK = threading.Lock()


def load(record: Path = RECORD) -> dict:
    return json.loads(record.read_text()) if record.exists() else {}


def printed_ids(page_id: str, record: Optional[dict] = None) -> Optional[set]:
    """The page's printed field ids, None when the page is not confirmed."""
    e = (load() if record is None else record).get(page_id)
    return None if e is None else set(e.get("printed") or [])


def confirm(page_id: str, printed: list, record: Path = RECORD, key_dir: Path = KEY) -> dict:
    """Write the page's printed fields (text fields of its key only)."""
    key = json.loads((key_dir / f"{page_id}.json").read_text())
    text = {f["id"] for f in key["fields"] if f.get("kind") != "choice"}
    bad = [f for f in printed if f not in text]
    if bad:
        raise ValueError(f"not text fields of {page_id}: {bad}")
    entry = {"printed": sorted(set(printed)), "when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    with _LOCK:
        rec = load(record)
        rec[page_id] = entry
        record.parent.mkdir(parents=True, exist_ok=True)
        tmp = record.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1, sort_keys=True))
        os.replace(tmp, record)
    return {"page_id": page_id, **entry}


def sheet(key_dir: Path = KEY, candidates: Path = CANDIDATES, record: Path = RECORD) -> dict:
    """The pages to confirm: every key page with a candidate, or already in the record."""
    import pymupdf
    cand = json.loads(candidates.read_text()) if candidates.exists() else {}
    rec = load(record)
    sets = {x["page_id"]: x["set"] for x in json.loads((key_dir / "index.json").read_text())}
    pages = []
    for pid in sorted(set(cand) | set(rec), key=lambda p: (sets.get(p, ""), p)):
        if pid not in sets:
            continue
        key = json.loads((key_dir / f"{pid}.json").read_text())
        size = key.get("size")
        if not size:
            with pymupdf.open(str(key_dir / "pages" / f"{pid}.pdf")) as doc:
                size = [doc[0].rect.width, doc[0].rect.height]
        signals = cand.get(pid) or {}
        pages.append({"page_id": pid, "form": key["form"], "page": key["page"], "set": sets[pid], "size": size,
                      "fields": [{"id": f["id"], "rect": f["rect"]} for f in key["fields"] if f.get("kind") != "choice"],
                      "signals": signals, "proposed": sorted(signals),
                      "confirmed": rec[pid]["printed"] if pid in rec else None})
    return {"pages": pages, "done": sum(p["confirmed"] is not None for p in pages)}


def page_png(page_id: str, key_dir: Path = KEY, zoom: float = 1.5) -> Optional[bytes]:
    import pymupdf
    pdf = key_dir / "pages" / f"{page_id}.pdf"
    if "/" in page_id or not pdf.exists():
        return None
    with pymupdf.open(str(pdf)) as doc:
        return doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
