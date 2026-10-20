"""Checks on the test harness itself, not the blueprint.

Within one loop the same frozen cases are filled every round, so a widget's expected value (ground_truth.json,
keyed by widget path) must not change from round to round whatever the blueprint does: the blueprint decides which
widgets a field reads, never what was written into them. A change means the test drifted (2026-10-20: frozen cases
held the filler's joined strings, so Form 8825's address values doubled each round and were scored as the
blueprint's misses for three weeks)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _ground_truths(run_dir: Path) -> dict[str, dict[str, Any]]:
    out = {}
    for p in sorted(Path(run_dir).glob("case_*/ground_truth.json")):
        try:
            g = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(g, dict):
            out[p.parent.name] = g
    return out


def expected_drift(prev_run: Path, cur_run: Path) -> list[dict]:
    """Every (case, widget path) whose expected value differs between two runs of the same cases. A path present in
    only one run is not drift (the blueprint gained or lost a field that reads it)."""
    prev, cur = _ground_truths(prev_run), _ground_truths(cur_run)
    out = []
    for case in sorted(prev.keys() & cur.keys()):
        a, b = prev[case], cur[case]
        for path in sorted(a.keys() & b.keys()):
            if a[path] != b[path]:
                out.append({"case": case, "path": path, "before": a[path], "after": b[path]})
    return out


def repeated(value: Any) -> bool:
    """A string that is one piece said over and over ("5C5C", "Omar Fischer, 1120Omar Fischer, 1120"): no drawn
    value looks like that, a fill that joined a joined string does. Digit runs and one repeated character
    ("1212", "0000") can be real and are not counted."""
    if not isinstance(value, str) or len(value) < 4:
        return False
    for p in range(2, len(value) // 2 + 1):
        unit = value[:p]
        if len(value) % p == 0 and value == unit * (len(value) // p) and not unit.isdigit() and len(set(unit)) > 1:
            return True
    return False


def repeated_values(run_dir: Path) -> list[dict]:
    """Every expected value in one run that repeats itself (see `repeated`); a check that needs no second round."""
    return [{"case": case, "path": path, "value": v}
            for case, gt in _ground_truths(run_dir).items() for path, v in sorted(gt.items()) if repeated(v)]
