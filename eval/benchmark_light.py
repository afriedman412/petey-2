"""The light path as a flat-structure benchmark baseline (Andrew, 2026-10-30: "ok let's see how light path does"): each
key page's flat PDF (runs/benchmark/key/pages) through `flat_light.build` (finder, Jev screen, line splits, option
groups), handed in two ways:

    light          the light path as it is (its option groups; it combines no splits)
    light_splits   the same, plus the page-only split detector's values (`compound_values.find`) as groups

Predictions go to runs/benchmark/predictions/<arm>/<page id>.json, a line a page (Jev tokens, seconds) to
runs/benchmark/predictions/light_log.jsonl; pages already done are skipped.

    PYTHONPATH=. venv/bin/python eval/benchmark_light.py [--limit N] [--procs 4] [--key DIR --out DIR] [--keep]

`--key` / `--out` (2026-11-03): another key in the same shape, e.g. the tuning set (runs/benchmark/dev_key, written
by `benchmark_key.py --spare`) into runs/benchmark/dev_predictions. `--keep`: also each page's whole light-path
blueprint (<out>/light_bp/<page id>.json: the Jev is-field score of every box, line splits), to look into what the
light path got wrong and why.
    PYTHONPATH=. venv/bin/python eval/benchmark_score.py runs/benchmark/predictions/light
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "eval"))
sys.path.insert(0, str(ROOT))
KEY = ROOT / "runs" / "benchmark" / "key"
OUT = ROOT / "runs" / "benchmark" / "predictions"
ARMS = ("light", "light_splits")


def to_prediction(bp: dict, splits: list[dict] = ()) -> dict:
    """The key's shape from a blueprint: every widget a field (ids `name` or `name.option`), option groups, and
    `splits` ([{fields: [x_petey_id, ...]}]) as groups of text fields."""
    fields, groups, ids_of = [], [], {}
    for n, s in (bp.get("fields") or {}).items():
        ws = {f"{n}.{k}": w for k, w in s["widgets"].items()} if s.get("widgets") else {n: s.get("widget") or {}}
        ids = []
        for i, w in ws.items():
            if not w.get("rect"):
                continue
            choice = w.get("widget_type") in ("checkbox", "radiobutton") or s.get("type") == "boolean"
            fields.append({"id": i, "rect": [round(float(x), 2) for x in w["rect"]],
                           "kind": "choice" if choice else "text"})
            ids.append(i)
        if s.get("widgets") and len(ids) >= 2:
            groups.append(ids)
        ids_of[str(s.get("x_petey_id"))] = ids
    for v in splits:
        g = [i for c in v["fields"] for i in ids_of.get(str(c), [])]
        if len(g) >= 2:
            groups.append(g)
    return {"fields": fields, "groups": groups}


def run_page(pid: str, key: Path = KEY, out: Path = OUT, keep: bool = False) -> dict:
    import flat_light as FL
    from petey.validate import compound_values as cv
    pdf = key / "pages" / f"{pid}.pdf"
    t0 = time.time()
    bp, info = FL.build(pdf, pid, workers=4)
    bp["source_pdf"] = str(pdf.resolve())               # the split detector reads the page's words from it
    splits = cv.find(bp)
    for arm, pred in (("light", to_prediction(bp)), ("light_splits", to_prediction(bp, splits))):
        (out / arm).mkdir(parents=True, exist_ok=True)
        (out / arm / f"{pid}.json").write_text(json.dumps(pred))
    if keep:
        (out / "light_bp").mkdir(parents=True, exist_ok=True)
        (out / "light_bp" / f"{pid}.json").write_text(json.dumps(bp, default=str))
    return {"page_id": pid, "tokens": info["tokens"], "seconds": round(time.time() - t0, 1),
            "finder_boxes": info["finder_boxes"], "kept": info["kept"], "splits": len(splits)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--key", type=Path, default=KEY)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--keep", action="store_true", help="also keep each page's light-path blueprint")
    args = ap.parse_args()
    key, out = args.key, args.out
    from petey.validate.jev_page import PRICE
    pids = [x["page_id"] for x in json.loads((key / "index.json").read_text())]
    todo = [p for p in pids if not all((out / a / f"{p}.json").exists() for a in ARMS)
            or (args.keep and not (out / "light_bp" / f"{p}.json").exists())]
    before = len(pids) - len(todo)
    todo = todo[:args.limit]
    log = out / "light_log.jsonl"
    out.mkdir(parents=True, exist_ok=True)
    t0, done, tokens = time.time(), 0, 0
    print(f"{len(todo)} pages to run ({before} done before)", flush=True)
    with cf.ProcessPoolExecutor(args.procs) as ex, log.open("a") as fh:
        futs = {ex.submit(run_page, p, key, out, args.keep): p for p in todo}
        for f in cf.as_completed(futs):
            try:
                r = f.result()
            except Exception as e:
                r = {"page_id": futs[f], "error": f"{type(e).__name__}: {e}"}
            fh.write(json.dumps(r) + "\n")
            fh.flush()
            done += 1
            tokens += r.get("tokens", 0)
            if done % 20 == 0 or done == len(todo):
                el = time.time() - t0
                print(f"{done}/{len(todo)}  {el:.0f} s  ({el / done:.1f} s a page)  Jev ${tokens / 1e6 * PRICE:.2f}",
                      flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
