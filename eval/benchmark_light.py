"""The light path as a flat-structure benchmark baseline (Andrew, 2026-10-30: "ok let's see how light path does"): each
key page's flat PDF (runs/benchmark/key/pages) through `flat_light.build` (finder, Jev screen, line splits, type
model, option groups, printed fields, split values), as one arm:

    light          the light path as it is; its split values come off its blueprint's Split Field tags (one arm
                   since 2026-11-04; the light_splits arm, the detector added on the side, is gone)

Predictions go to runs/benchmark/predictions/<arm>/<page id>.json, a line a page (Jev tokens, seconds) to
runs/benchmark/predictions/light_log.jsonl; pages already done are skipped.

    PYTHONPATH=. venv/bin/python eval/benchmark_light.py [--limit N] [--procs 4] [--key DIR --out DIR] [--keep]

`--key` / `--out` (2026-11-03): another key in the same shape, e.g. the tuning set (runs/benchmark/dev_key, written
by `benchmark_key.py --spare`) into runs/benchmark/dev_predictions. `--keep`: also each page's whole light-path
blueprint (<out>/light_bp/<page id>.json: the Jev is-field score of every box, line splits), to look into what the
light path got wrong and why.
    PYTHONPATH=. venv/bin/python eval/benchmark_score.py runs/benchmark/predictions/light

`--derive` (2026-11-04): rewrite the light arm's kinds (choice / text by the type model, printed by each box's own
caption) and the light_splits arm
from the light arm's boxes and the key's page PDFs with no Jev (both readers take boxes and words only), after a
change to the detector, its taxonomy or the printed rule:

    PYTHONPATH=. venv/bin/python eval/benchmark_light.py --derive [--key DIR --out DIR]
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
ARMS = ("light",)


def to_prediction(bp: dict, splits: Optional[list[dict]] = None) -> dict:
    """The key's shape from a blueprint: every widget a field (ids `name` or `name.option`; a text field tagged
    x_petey_printed is kind printed), option groups, and the split values as groups of text fields: `splits`
    ([{fields: [x_petey_id, ...]}]) when given, else the blueprint's Split Field tags (`compound_values.from_tags`,
    which the light path writes since 2026-11-04)."""
    from petey.validate.printed_fields import is_printed
    if splits is None:
        from petey.validate import compound_values as cv
        splits = cv.from_tags(bp)
    fields, groups, ids_of = [], [], {}
    for n, s in (bp.get("fields") or {}).items():
        ws = {f"{n}.{k}": w for k, w in s["widgets"].items()} if s.get("widgets") else {n: s.get("widget") or {}}
        ids = []
        for i, w in ws.items():
            if not w.get("rect"):
                continue
            choice = w.get("widget_type") in ("checkbox", "radiobutton") or s.get("type") == "boolean"
            fields.append({"id": i, "rect": [round(float(x), 2) for x in w["rect"]],
                           "kind": "choice" if choice else "printed" if is_printed(s) else "text"})
            ids.append(i)
        if s.get("widgets") and len(ids) >= 2:
            groups.append(ids)
        ids_of[str(s.get("x_petey_id"))] = ids
    for v in splits:
        g = [i for c in v["fields"] for i in ids_of.get(str(c), [])]
        if len(g) >= 2:
            groups.append(g)
    return {"fields": fields, "groups": groups}


def _pseudo_bp(pred: dict, pdf: Path) -> dict:
    """A prediction as a blueprint the page-only readers take: its boxes as one-box fields, the page PDF as the blank."""
    return {"source_pdf": str(Path(pdf).resolve()), "source_pages": [1], "fields": {
        f["id"]: {"x_petey_id": f["id"], "type": "boolean" if f.get("kind") == "choice" else "string",
                  "widget": {"page": 1, "rect": f["rect"],
                             "widget_type": "checkbox" if f.get("kind") == "choice" else "text"}}
        for f in pred.get("fields") or []}}


def retype(pred: dict, pdf: Path) -> int:
    """The prediction's boxes typed by the type model (`type_model`, when fitted): choice or text, in place; a box
    that flips leaves its group (a text box is no option, and a new choice box has no partners without the group
    question). Returns the number of boxes that changed."""
    from petey.validate import type_model as tm
    import pymupdf
    if tm.WEIGHTS is None:
        return 0
    doc = pymupdf.open(str(pdf))
    words = doc[0].get_text("words")
    doc.close()
    boxes = [{"rect": f["rect"], "kind": f.get("kind"), "code": f["id"]} for f in pred.get("fields") or []]
    flipped = set()
    for f, b in zip(pred["fields"], boxes):
        k = tm.kind(b, boxes, words)
        was = "choice" if f.get("kind") == "choice" else "text"
        if k != was:
            f["kind"] = k
            flipped.add(f["id"])
    if flipped:
        pred["groups"] = [g for g in ([i for i in g if i not in flipped] for g in pred.get("groups") or []) if len(g) >= 2]
    return len(flipped)


def printed_for(pred: dict, pdf: Path) -> set[str]:
    """The ids of the prediction's text boxes whose own caption says they are hand-written (`printed_caption`)."""
    from petey.validate import printed_caption
    return set(printed_caption.find(_pseudo_bp(pred, pdf)))


def splits_for(pred: dict, pdf: Path) -> list[dict]:
    """The split detector's values for a prediction (its text boxes, the page's words from `pdf`): [{fields: [box id,
    ...]}]. The detector reads boxes and printed words only, so an arm's joins can be re-derived from the light arm
    and the key's page PDF with no Jev (Andrew, 2026-11-04: "throw out the predicted groupings we don't care about"
    rather than rerun)."""
    from petey.validate import compound_values as cv
    return cv.find(_pseudo_bp(pred, pdf))


def derive_splits(key: Path = KEY, out: Path = OUT) -> int:
    """Rewrite the light arm from its own boxes: kinds (choice / text by the type model, printed by own caption) and
    the split values as groups (2026-11-04); every page with a light prediction and a page PDF."""
    n = 0
    for x in json.loads((key / "index.json").read_text()):
        pid = x["page_id"]
        src, pdf = out / "light" / f"{pid}.json", key / "pages" / f"{pid}.pdf"
        if not (src.exists() and pdf.exists()):
            continue
        pred = json.loads(src.read_text())
        retype(pred, pdf)
        printed = printed_for(pred, pdf)
        for f in pred["fields"]:
            if f.get("kind") != "choice":
                f["kind"] = "printed" if f["id"] in printed else "text"
        groups = [g for g in pred.get("groups") or []
                  if any(f.get("kind") == "choice" for f in pred["fields"] if f["id"] in g)]   # option groups stay
        for v in splits_for(pred, pdf):
            if len(v["fields"]) >= 2:
                groups.append(list(v["fields"]))
        src.write_text(json.dumps({"fields": pred["fields"], "groups": groups}))
        n += 1
    return n


def run_page(pid: str, key: Path = KEY, out: Path = OUT, keep: bool = False) -> dict:
    import flat_light as FL
    pdf = key / "pages" / f"{pid}.pdf"
    t0 = time.time()
    bp, info = FL.build(pdf, pid, workers=4)
    bp["source_pdf"] = str(pdf.resolve())
    (out / "light").mkdir(parents=True, exist_ok=True)
    (out / "light" / f"{pid}.json").write_text(json.dumps(to_prediction(bp)))     # its splits are on the blueprint
    if keep:
        (out / "light_bp").mkdir(parents=True, exist_ok=True)
        (out / "light_bp" / f"{pid}.json").write_text(json.dumps(bp, default=str))
    return {"page_id": pid, "tokens": info["tokens"], "seconds": round(time.time() - t0, 1),
            "finder_boxes": info["finder_boxes"], "kept": info["kept"], "splits": info["split_values"]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--limit", type=int)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--key", type=Path, default=KEY)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--keep", action="store_true", help="also keep each page's light-path blueprint")
    ap.add_argument("--derive", action="store_true", help="rewrite light_splits from the light arm, no Jev")
    args = ap.parse_args()
    if args.derive:
        print(f"{derive_splits(args.key, args.out)} light pages re-derived from their own boxes")
        return 0
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
