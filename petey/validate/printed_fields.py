"""Printed fields (Andrew, 2026-10-31: a third field type, "printed": "anything that is expected to be hand-written --
signatures, printed names, etc."). Initials are printed; the date of signing and a signer's title stay text.

Stored on the field in its blueprint (Andrew, 2026-10-31: "printed types should move to blueprints, they are fields
... if there is something on the page, we want to extract it"):

    x_petey_printed: {source: printed_sheet | review, when}

on text fields only. Set a page at a time from the review server's printed sheet (/printed), or one field from the
Review tab. An `x_petey_` key is bookkeeping (`page_check.spec_hash` leaves it out), so a field's verdict holds. A form
whose working copy is open gets the change in the copy, saved with it; the Review tab always works in the copy, as
every page edit does. Otherwise the sheet writes the blueprint and its review records follow it
(`field_ids._rehash`), so a validated form stays validated. `eval/benchmark_key.py` reads the tag.

The sheet's progress, the pages looked at (a page with no printed field counts too):

    runs/benchmark/field_types.json    {page id: {"when": "YYYY-mm-dd HH:MM:SS"}}

The sheet shows each key page with candidates (eval/benchmark_printed.py: runs/benchmark/printed/candidates.json)
with every text field drawn, the candidates marked; Andrew clicks to unmark or mark, then confirms the page.
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from pathlib import Path
from typing import Callable, Optional

import yaml

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "runs" / "benchmark"
RECORD = BENCH / "field_types.json"
CANDIDATES = BENCH / "printed" / "candidates.json"
KEY = BENCH / "key"
HTML_PATH = Path(__file__).with_name("printed_fields.html")
TAG = "x_petey_printed"
CHOICE = {"checkbox", "radio", "radiobutton", "combobox", "listbox"}
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def is_text(spec: dict) -> bool:
    """A field the benchmark counts as text: one box, not a choice."""
    w = spec.get("widget") if isinstance(spec, dict) else None
    return bool(w) and not spec.get("widgets") and w.get("widget_type") not in CHOICE and spec.get("type") != "boolean"


def is_printed(spec: dict) -> bool:
    return isinstance(spec, dict) and bool(spec.get(TAG)) and is_text(spec)


def load(record: Optional[Path] = None) -> dict:
    record = record or RECORD
    return json.loads(record.read_text()) if record.exists() else {}


def _dump(bp: dict) -> str:
    return yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False)


def write(bid: str, edit: Callable[[dict], list[str]], mode: str, real: Optional[Path] = None) -> list[str]:
    """Apply `edit` (changes the blueprint dict, returns change lines) to the form: in its working copy when one is
    open or `mode` is "review" (the page's edits always go there), else in the blueprint, its records following."""
    from petey.validate import draft, field_ids
    from petey.validate import hand_review as h
    real = real or h.blueprint_paths()[bid]
    if mode == "review" or draft.meta(bid) is not None:
        bp = h._load(h.working_path(bid, {bid: real}))
        if not edit(bp):                                    # nothing to change: no copy opened for it
            return []
        p = draft.ensure(bid, real)
        before = h._sha(p)
        bp = h._load(p)
        lines = edit(bp)
        p.write_text(_dump(bp), encoding="utf-8")
        draft.follow(bid, before, h._sha(p))
        draft.log(bid, mode, lines)
        return lines
    old, bp = h._sha(real), h._load(real)
    lines = edit(bp)
    if lines:
        real.write_text(_dump(bp), encoding="utf-8")
        field_ids._rehash(bid, old, h._sha(real))
    return lines


def _set(spec: dict, name: str, on: bool, source: str) -> Optional[str]:
    if on == bool(spec.get(TAG)):
        return None
    if on:
        spec[TAG] = {"source": source, "when": _now()}
    else:
        spec.pop(TAG, None)
    return f"{name}: {'printed (hand-written)' if on else 'not printed'}"


def set_field(bid: str, field: str, on: bool, real: Optional[Path] = None) -> list[str]:
    """The Review tab: one field printed or not, in the working copy."""
    def edit(bp):
        spec = (bp.get("fields") or {}).get(field)
        if not isinstance(spec, dict):
            raise KeyError(field)
        if not is_text(spec):
            raise ValueError(f"{field} is not a text field: only text fields are printed")
        ln = _set(spec, field, on, "review")
        return [ln] if ln else []
    return write(bid, edit, "review", real)


def set_page(bid: str, page: int, printed: set, real: Optional[Path] = None) -> list[str]:
    """The sheet: on one page, exactly the text fields whose codes are in `printed` are printed."""
    def edit(bp):
        lines = []
        for name, spec in (bp.get("fields") or {}).items():
            if not is_text(spec) or int(spec["widget"].get("page") or 0) != page:
                continue
            ln = _set(spec, name, str(spec.get("x_petey_id", name)) in printed, "printed_sheet")
            if ln:
                lines.append(ln)
        return lines
    return write(bid, edit, "printed", real)


def printed_on(bid: str, page: int, real: Optional[Path] = None) -> list[str]:
    """The codes of the page's printed fields, as the review page reads the form (its working copy if open)."""
    from petey.validate import hand_review as h
    p = h.working_path(bid, {bid: real}) if real else h.working_path(bid)
    bp = h._load(p)
    return sorted(str(s.get("x_petey_id", n)) for n, s in (bp.get("fields") or {}).items()
                  if is_printed(s) and int(s["widget"].get("page") or 0) == page)


def confirm(page_id: str, printed: list, record: Optional[Path] = None, key_dir: Path = KEY,
            real: Optional[Path] = None) -> dict:
    """The sheet's confirm: the page's printed fields (text fields of its key only) onto the blueprint."""
    record = record or RECORD
    key = json.loads((key_dir / f"{page_id}.json").read_text())
    text = {f["id"] for f in key["fields"] if f.get("kind") != "choice"}
    bad = [f for f in printed if f not in text]
    if bad:
        raise ValueError(f"not text fields of {page_id}: {bad}")
    with _LOCK:
        lines = set_page(key["form"], int(key["page"]), set(printed), real)
        rec = load(record)
        rec[page_id] = {"when": _now()}
        record.parent.mkdir(parents=True, exist_ok=True)
        tmp = record.with_suffix(".tmp")
        tmp.write_text(json.dumps(rec, indent=1, sort_keys=True))
        os.replace(tmp, record)
    return {"page_id": page_id, "printed": printed_on(key["form"], int(key["page"]), real), "changes": lines,
            **rec[page_id]}


def sheet(key_dir: Path = KEY, candidates: Path = CANDIDATES, record: Optional[Path] = None) -> dict:
    """The pages to confirm: every key page with a candidate, or already looked at."""
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
                      "confirmed": printed_on(key["form"], int(key["page"])) if pid in rec else None})
    return {"pages": pages, "done": sum(p["confirmed"] is not None for p in pages)}


def migrate(record: Optional[Path] = None) -> list[str]:
    """2026-10-31: pages confirmed into the old record ({printed: [ids]}) written onto their blueprints."""
    record = record or RECORD
    done = []
    for pid, e in load(record).items():
        if "printed" in e:
            confirm(pid, list(e["printed"]), record)
            done.append(pid)
    return done


def page_png(page_id: str, key_dir: Path = KEY, zoom: float = 1.5) -> Optional[bytes]:
    import pymupdf
    pdf = key_dir / "pages" / f"{page_id}.pdf"
    if "/" in page_id or not pdf.exists():
        return None
    with pymupdf.open(str(pdf)) as doc:
        return doc[0].get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).tobytes("png")
