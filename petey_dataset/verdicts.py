"""A form's review record (`runs/hand_review/<id>.json`): the person's verdict on each field, and the structure stamp
("accept structure", 2026-10-31) that says its fields, their kinds, groups, grids and blocks are right. What the
benchmark key takes is `structure_ok`. Lifted from the review page's `hand_review` (2026-11-05)."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Optional

from petey_dataset import HAND_REVIEW
from petey_dataset.blueprints import reviewable, sha

OUT = HAND_REVIEW

# the server answers requests on threads: two saves of one record at once (je__cra_t2, 2026-10-19 16:20:42) wrote
# over each other, the shorter on top of the longer, and left the file unreadable. Saves read, change and write the
# record under one lock, and write it whole (a temporary file put in its place).
LOCK = threading.RLock()


def verdict_path(bid: str) -> Path:
    return OUT / f"{bid}.json"


def load_verdicts(bid: str) -> dict:
    p = verdict_path(bid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write_verdicts(bid: str, rec: dict) -> None:
    p = verdict_path(bid)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def reset_verdicts(bid: str) -> dict:
    """Every verdict on the form cleared (Andrew, 2026-10-22: "can you add a button to reset validations? (and a 'are
    you sure?' screen)"): the record moved to runs/hand_review/_reset/<bid>_<when>.json, so nothing is lost.
    {cleared, backup}."""
    with LOCK:
        p = verdict_path(bid)
        if not p.exists():
            return {"cleared": 0, "backup": None}
        n = len(load_verdicts(bid).get("verdicts") or {})
        bk = OUT / "_reset" / f"{bid}_{time.strftime('%Y%m%d_%H%M%S')}.json"
        bk.parent.mkdir(parents=True, exist_ok=True)
        p.replace(bk)
        return {"cleared": n, "backup": str(bk)}


def checked(v: dict, p: Path, bp: dict) -> Optional[dict]:
    """`{when, fields, flagged, stale}` when every reviewable field has a verdict, else None. Read from the verdicts
    themselves, so a review finished before the record existed counts (its `when` is the file's last save); `stale`
    when the blueprint changed after it was checked."""
    vs = v.get("verdicts") or {}
    names = reviewable(bp)
    if not names or not all(vs.get(n, {}).get("verdict") for n in names):
        return None
    c = v.get("checked") or {"when": v.get("updated"), "blueprint_sha": v.get("blueprint_sha")}
    flagged = sum(1 for n in names if vs[n]["verdict"] == "flag")
    pending = sum(1 for x in vs.values() if x.get("edit") and not x.get("applied"))
    stale = c.get("blueprint_sha") != sha(p)
    # validated (Andrew, 2026-10-07): every field has a verdict, nothing is flagged (a flag = needs work), every
    # saved correction is applied, and the file is the one that was checked
    return {"when": c.get("when"), "fields": len(names), "flagged": flagged, "pending": pending, "stale": stale,
            "validated": not stale and not flagged and not pending}


def structure(v: dict, p: Path) -> Optional[dict]:
    """`{when, stale}` once the form's structure is validated, else None (Andrew, 2026-10-31: "since we are currently
    only looking at structure, in the service of building the data set, let's encode that status"): "accept structure"
    on the review page says its fields, their kinds, groups, grids and blocks are right, names not looked at. Shown as
    STRUCTURE VALIDATED until every name is accepted too (`checked` validated), which supersedes it. Stale when the
    blueprint changed after it, as `checked` is (the page's own changes carry it along: `draft.follow`)."""
    s = v.get("structure")
    if not s:
        return None
    return {"when": s.get("when"), "by": s.get("by"), "stale": s.get("blueprint_sha") != sha(p)}


def structure_ok(v: dict, p: Path, bp: dict) -> bool:
    """Validated in full, or its structure validated and the file unchanged since: what the benchmark key takes."""
    c, s = checked(v, p, bp), structure(v, p)
    return bool((c and c["validated"]) or (s and not s["stale"]))


def stamp_structure(bid: str, p: Path, real: Path, by: str = "accept structure") -> dict:
    """The form's structure validated against the file the page reads (`p`, its working copy if open)."""
    with LOCK:
        rec = load_verdicts(bid) or {"blueprint": str(real), "form": real.stem, "verdicts": {}}
        s = sha(p)
        rec.setdefault("blueprint_sha", s)
        rec["structure"] = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "blueprint_sha": s, "by": by}
        OUT.mkdir(parents=True, exist_ok=True)
        write_verdicts(bid, rec)
        return rec["structure"]


def unstamp_structure(bid: str) -> None:
    """"accept structure" clicked again: the form's structure no longer validated (Andrew, 2026-10-31)."""
    with LOCK:
        rec = load_verdicts(bid)
        if rec.pop("structure", None) is not None:
            write_verdicts(bid, rec)


def new_to_check(v: dict, p: Path, bp: dict) -> Optional[int]:
    """How many fields await a verdict on a form that was once fully checked (Andrew, 2026-11-02: "is there a way for
    me to know what needs to be revisited?"): a sweep or an edit added or renamed fields after every field had its
    verdict. None when the form was never fully checked, or is fully checked now."""
    if not (v.get("checked") or v.get("was_checked")) or checked(v, p, bp):
        return None
    vs = v.get("verdicts") or {}
    n = sum(1 for name in reviewable(bp) if not vs.get(name, {}).get("verdict"))
    return n or None


FORM_NOTES = OUT / "form_notes.json"


def form_notes() -> dict[str, dict]:
    """{bid: {text, updated}}: Andrew's notes on a whole form (2026-10-15), one file for every form, kept apart from
    the per-form records so a working copy's discard (which puts those back) leaves them."""
    try:
        return json.loads(FORM_NOTES.read_text(encoding="utf-8")) if FORM_NOTES.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def set_form_note(bid: str, text: str) -> dict:
    notes = form_notes()
    text = (text or "").rstrip()
    if text:
        notes[bid] = {"text": text, "updated": time.strftime("%Y-%m-%d %H:%M:%S")}
    else:
        notes.pop(bid, None)
    FORM_NOTES.parent.mkdir(parents=True, exist_ok=True)
    tmp = FORM_NOTES.with_suffix(".tmp")
    tmp.write_text(json.dumps(notes, indent=1, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(FORM_NOTES)
    return notes.get(bid) or {"text": "", "updated": None}

