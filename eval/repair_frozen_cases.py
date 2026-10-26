"""Repair frozen bank cases that hold the filler's joined strings (2026-10-20).

Until 60b5d12 a frozen case was saved AFTER filling: the cells of a widget the page finder split (a two-line box, a
comb) carried the widget's joined string, and every reuse joined it again. The draw itself is reproducible (a seed
from the case key, the cached class map, the value bank), so each frozen case is drawn again and compared:

  * the same                                   -> clean
  * a stored fill of the same draw             -> the file gets the draw (--apply): the frozen file's cells all
                                                  agree with it, allowing for cells the fill dropped, values a
                                                  widget's MaxLen cut short, and split widgets' joined strings
  * differs elsewhere too                      -> the class map or the bank changed since, so the draw cannot be
                                                  had again: a split widget whose cells all hold one string keeps
                                                  it on its first cell, the rest emptied (it stops growing)

    PYTHONPATH=. venv/bin/python eval/repair_frozen_cases.py            # report
    PYTHONPATH=. venv/bin/python eval/repair_frozen_cases.py --apply    # rewrite the stored joins
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

import pymupdf
import yaml

from petey.paths import RUNS
from petey.synth import seed_from_key
from petey.synth.bank import generate_from_bank
from petey.synth.classify import classify_form
from petey.synth.render import _widgets_by_page, widget_cells
from petey.validate import provenance
from petey.validate.retype import resolve_blank
from petey.validate.validate import SETS_DIR, _bank_cache_path

GEN_CACHE = RUNS / "_gen_cache"
BACKUP = GEN_CACHE / "_backup_frozen_2026-10-20"      # every file rewritten, as it was


def write(cp: Path, case: dict) -> None:
    BACKUP.mkdir(parents=True, exist_ok=True)
    if not (BACKUP / cp.name).exists():
        (BACKUP / cp.name).write_bytes(cp.read_bytes())
    cp.write_text(json.dumps(case, indent=2))


def blank_of(manifest: dict):
    for run in manifest.get("runs") or []:
        bp = RUNS / run / "blueprint.bpt"
        if bp.exists():
            try:
                b = resolve_blank(yaml.safe_load(bp.read_text()) or {})
            except Exception:
                b = None
            if b is not None and Path(b).exists():
                return Path(b)
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    tally = collections.Counter()
    repaired_forms = set()
    for mp in sorted(SETS_DIR.glob("*.json")):
        m = json.loads(mp.read_text())
        if m.get("generator") != "bank":
            tally["set not bank"] += 1
            continue
        blank = blank_of(m)
        if blank is None:
            tally["set: blank not found"] += 1
            continue
        cmap = classify_form(blank, cache_only=True)
        if cmap is None:
            tally["set: no cached class map"] += 1
            continue
        basis = provenance.manifest_basis(m)
        with pymupdf.open(str(blank)) as doc:
            widgets, n_pages = _widgets_by_page(doc), len(doc)
        for key in m.get("cases") or []:
            cp = _bank_cache_path(GEN_CACHE, blank, key, basis)
            if cp is None or not cp.exists():
                tally["case: no frozen file"] += 1
                continue
            frozen = json.loads(cp.read_text())
            draw = generate_from_bank(cmap, seed=seed_from_key(key))
            if frozen == draw:
                tally["clean"] += 1
                continue
            # a frozen file saved after filling holds the EFFECTIVE case: cells the fill dropped are missing, a
            # widget's MaxLen cut values short, and the cells of a split widget carry its joined string. It is a
            # stored fill of this very draw when every cell it has agrees with the draw on those terms.
            members = {k for ks in widget_cells({k: v for k, v in draw.items() if ':' in k}, widgets, n_pages).values()
                       for k in ks}

            def agrees(k):
                f, d = frozen[k], draw.get(k)
                if f == d or k in members:
                    return True
                return isinstance(f, str) and isinstance(d, str) and d.startswith(f)
            if all(agrees(k) for k in frozen):
                tally["stored join"] += 1
                repaired_forms.add(m["form"])
                if args.apply:
                    write(cp, draw)
            else:
                # the inputs changed since, so the draw cannot be had again; a split widget whose cells all hold one
                # string (the stored join) keeps it on its first cell and the rest go empty: a refill writes it
                # once, the value of the first fill, and it no longer grows
                fixed = dict(frozen)
                rect_keyed = {k: v for k, v in frozen.items() if ":" in k and k.startswith("p")}
                n_groups = 0
                for ks in widget_cells(rect_keyed, widgets, n_pages).values():
                    vals = {str(frozen[k]) for k in ks}
                    if len(vals) == 1 and len(next(iter(vals))) >= 2:
                        for k in ks[1:]:
                            fixed[k] = ""
                        n_groups += 1
                if n_groups:
                    tally["drifted, stored joins emptied"] += 1
                    repaired_forms.add(m["form"])
                    if args.apply:
                        write(cp, fixed)
                else:
                    tally["drifted, nothing joined (left alone)"] += 1
    print(dict(tally))
    print(f"{len(repaired_forms)} sets with stored joins{' rewritten' if args.apply else ''}:",
          ", ".join(sorted(repaired_forms)[:40]) + (" ..." if len(repaired_forms) > 40 else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
