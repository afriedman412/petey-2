"""Which forms are cleared: through the automated passes (scripts/validate_passes.sh), for the home page's pipeline
generated -> cleared -> validated (Andrew, 2026-10-16: generation is the generation pipeline and its loops, clearing the
automated passes, validation the manual check). One file for every form,
runs/hand_review/passes.json `{bid: {when, steps}}`, apart from the blueprints so recording it changes no file's sha.

    PYTHONPATH=. venv/bin/python eval/passes_record.py ID ...        # the passes just ran on these (validate_passes.sh)
    PYTHONPATH=. venv/bin/python eval/passes_record.py --backfill    # from the passes' own reports
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

from petey.paths import RUNS
from petey.validate import hand_review as h

PATH = h.OUT / "passes.json"
STEPS = ["mechanical", "naming", "captions", "page check", "jev"]


def load() -> dict[str, dict]:
    try:
        return json.loads(PATH.read_text(encoding="utf-8")) if PATH.exists() else {}
    except (OSError, ValueError):
        return {}


def save(rec: dict) -> None:
    tmp = PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(PATH)


def _bids(path: Path) -> set[str]:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {r["bid"] for r in d if isinstance(r, dict) and r.get("bid")} if isinstance(d, list) else set()


def _date(path: Path) -> str:
    m = re.search(r"\d{4}-\d{2}-\d{2}", path.name)
    return m.group(0) if m else time.strftime("%Y-%m-%d", time.localtime(path.stat().st_mtime))


def backfill() -> dict[str, dict]:
    """A form passed when a mechanical-pass report lists it; its other steps from the captions and Jev reports and
    a page-check stamp on the file no older than that report."""
    rec = load()
    mech: dict[str, str] = {}
    for p in sorted((RUNS / "mechanical").glob("*.json")):
        for b in _bids(p):
            mech[b] = max(mech.get(b, ""), _date(p))
    caps = set().union(*[_bids(p) for p in (RUNS / "group_review").glob("reread_captions_*.json")])
    jev = set().union(*[_bids(p) for p in (RUNS / "jev").glob("*.json") if not p.name.startswith(("page_", "cheap_", "is_field"))])
    paths = h.blueprint_paths()
    for b, day in mech.items():
        if b not in paths or (b in rec and rec[b].get("how") != "backfill"):    # an explicit record wins
            continue
        steps = ["mechanical", "naming"]                  # the naming standard runs right after, on the same forms
        if b in caps:
            steps.append("captions")
        try:
            bp = h._load(h.working_path(b, paths))
            if ((bp.get("x_petey_page_check") or {}).get("when") or "")[:10] >= day:
                steps.append("page check")
        except Exception:
            pass
        if b in jev:
            steps.append("jev")
        rec[b] = {"when": day, "steps": steps, "how": "backfill"}
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--backfill", action="store_true")
    args = ap.parse_args()
    if args.backfill:
        rec = backfill()
    else:
        rec = load()
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for b in args.ids:
            rec[b] = {"when": now, "steps": STEPS}
    save(rec)
    print(f"{len(rec)} forms recorded as cleared", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
