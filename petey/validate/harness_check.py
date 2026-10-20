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
