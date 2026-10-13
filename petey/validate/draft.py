"""The review page's working copy of a blueprint (Andrew, 2026-10-13: "work from the in-progress copy completely until
you hit save; everything should be reading from the same source").

Review corrections, Groups and Add / remove used to keep three separate pending records, each with its own apply
button, and they went out of step (a Groups record left stale by a Review apply; saved groups that never reached the
file). Now the page's first change to a blueprint copies it to `runs/drafts/<id>/<file>.bpt`, every change after
that is applied to the copy at once, and all three modes read the copy (`hand_review.working_path`). One Save copies
it over the blueprint; Discard throws it away.

The copy starts with snapshots of the three modes' records (`runs/hand_review`, `runs/group_review`,
`runs/field_add`), so Discard puts them back as they were: verdicts and notes made while the copy was open go with
it. The records keep the real blueprint's path; their shas are the copy's, which Save makes the blueprint's (the
bytes are copied as they are). Save refuses when the blueprint changed on disk since the copy was made (a loop run,
an edit by hand), unless forced.

    runs/drafts/<id>/<file>.bpt        the working copy
    runs/drafts/<id>/draft.json        {real, base_sha, made, log: [change lines], records: {kind: had a record}}
    runs/drafts/<id>/records/<kind>.json
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Optional

from petey.paths import RUNS

DRAFTS = RUNS / "drafts"


def _dir(bid: str) -> Path:
    return DRAFTS / bid


def meta(bid: str) -> Optional[dict]:
    m = _dir(bid) / "draft.json"
    try:
        return json.loads(m.read_text(encoding="utf-8")) if m.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def _write_meta(bid: str, m: dict) -> None:
    (_dir(bid) / "draft.json").write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")


def working(bid: str, real: Path) -> Path:
    """The copy while one is open, else the blueprint itself."""
    m = meta(bid)
    if m is None:
        return real
    p = _dir(bid) / Path(m["real"]).name
    return p if p.exists() else real


def _records(bid: str) -> dict[str, Path]:
    from petey.validate import field_add, group_review, hand_review
    return {"hand_review": hand_review.verdict_path(bid), "group_review": group_review.record_path(bid),
            "field_add": field_add.record_path(bid)}


def _sha(p: Path) -> str:
    from petey.validate.hand_review import _sha
    return _sha(p)


def ensure(bid: str, real: Path) -> Path:
    """Open the copy (if it is not open) and return it: the blueprint's bytes, its sha, and the records' snapshots."""
    if meta(bid) is not None and working(bid, real) != real:
        return working(bid, real)
    d = _dir(bid)
    (d / "records").mkdir(parents=True, exist_ok=True)
    had = {}
    for kind, rp in _records(bid).items():
        had[kind] = rp.exists()
        if rp.exists():
            shutil.copyfile(rp, d / "records" / f"{kind}.json")
    shutil.copyfile(real, d / real.name)
    _write_meta(bid, {"real": str(real), "base_sha": _sha(real), "made": time.strftime("%Y-%m-%d %H:%M:%S"),
                      "log": [], "records": had})
    return d / real.name


def log(bid: str, mode: str, lines) -> None:
    m = meta(bid)
    if m is None:
        return
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    m["log"] += [{"when": now, "mode": mode, "change": ln.strip()} for ln in lines if ln and ln.strip()]
    _write_meta(bid, m)


def follow(bid: str, before: str, after: str) -> None:
    """After a change made through the page or Claude's pass (both checked by Andrew before he saves), the Review and
    Add / remove records written against the file before it move to the file after it, so a finished check does
    not read as stale. The Groups record is left alone: its units name fields, and a stale one is rebased."""
    for kind, rp in _records(bid).items():
        if kind == "group_review" or not rp.exists():
            continue
        rec = json.loads(rp.read_text(encoding="utf-8"))
        if rec.get("blueprint_sha") != before:
            continue
        rec["blueprint_sha"] = after
        ck = rec.get("checked")
        if isinstance(ck, dict) and ck.get("blueprint_sha") == before:
            ck["blueprint_sha"] = after
        rp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")


def status(bid: str, real: Path) -> Optional[dict]:
    """What the page shows in its header: None when no copy is open."""
    m = meta(bid)
    if m is None or working(bid, real) == real:
        return None
    return {"made": m["made"], "changes": len(m["log"]), "log": [f"{x['mode']}: {x['change']}" for x in m["log"]],
            "real_changed": real.exists() and _sha(real) != m["base_sha"]}


def save(bid: str, real: Path, force: bool = False) -> dict:
    """Copy the working copy over the blueprint and close it."""
    m = meta(bid)
    w = working(bid, real)
    if m is None or w == real:
        raise ValueError(f"{bid}: no working copy open")
    if not force and real.exists() and _sha(real) != m["base_sha"]:
        raise ValueError(f"{bid}: {real} changed on disk since the working copy was made ({m['made']})")
    shutil.copyfile(w, real)
    shutil.rmtree(_dir(bid))
    return {"saved": str(real), "changes": len(m["log"])}


def discard(bid: str, real: Path) -> dict:
    """Throw the working copy away and put the three records back as they were when it was made."""
    m = meta(bid)
    if m is None:
        raise ValueError(f"{bid}: no working copy open")
    d = _dir(bid)
    for kind, rp in _records(bid).items():
        snap = d / "records" / f"{kind}.json"
        if (m.get("records") or {}).get(kind) and snap.exists():
            shutil.copyfile(snap, rp)
        elif rp.exists():
            rp.unlink()
    shutil.rmtree(d)
    return {"discarded": len(m["log"])}
