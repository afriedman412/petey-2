"""Jev's "is this a table?" for every grid only the geometric test finds (grid_check.found_by == "geometry"), on the
forms whose review ids start with the given prefixes, into runs/hand_review/grid_jev.json for the Grids tab to show
(2026-10-27). Grids already scored are skipped.

    PYTHONPATH=. venv/bin/python eval/grid_jev_scores.py bm__ fl__
"""
import sys
import time

import yaml

from petey.validate import grid_check as gc, grid_naming as G, hand_review as h
from petey.validate.jev_page import PRICE


def main() -> int:
    prefixes = tuple(sys.argv[1:]) or ("bm__", "fl__")
    paths = h.blueprint_paths()
    done = gc.jev_scores()
    items = []
    for bid in sorted(paths):
        if not bid.startswith(prefixes):
            continue
        try:
            bp = yaml.safe_load(open(h.working_path(bid, paths)))
        except Exception:
            continue
        for g in G.grids(bp, blocks=False):
            if gc.found_by(bp, g) == "geometry" and gc.grid_key(bp, g) not in done.get(bid, {}):
                items.append((bid, bp, g))
    t0 = time.time()
    print(f"{len(items)} geometry-only grids to score", flush=True)
    n, tokens = gc.score_tables(items) if items else (0, 0)
    print(f"scored {n}, {tokens:,} tokens = ${tokens / 1e6 * PRICE:.3f}, {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
