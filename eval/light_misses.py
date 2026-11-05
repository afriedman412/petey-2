"""What the light path misses and the junk it keeps, page by page on the tuning set, for the review page's "light
misses" and "light junk" layers (Andrew, 2026-11-04: "could you add the misses in a layer on the review page?").

For every key field the light path's prediction does not find (the benchmark scorer's match), the cause:

    no box     the finder proposed no box over it
    jev        the finder did, and Jev's screen scored every such box under the keep line
    one box    a kept box covers it and another key field too (one box over several fields)
    later      a kept box was there, lost after the screen (line splits, typing)

and every kept light box that matches no key field (junk), with its Jev score. Jev's answers are read from its
cache only (the requests the light run made): a request not cached is never sent, its boxes count as unanswered.

2026-11-04, tuning set (1,071 pages, 33,206 key fields): missed 3,616 (no box 2,034, jev 1,293, one box 285, later 4);
finder 44,647 boxes, 14,145 junk, of which Jev kept 5,571 (AUC 0.90). Rebuild after the key or the light path changes.

    PYTHONPATH=. venv/bin/python eval/light_misses.py [--key DIR --pred DIR --out FILE --procs 6]
-> runs/benchmark/dev_analysis/light_misses.json {built: {...}, forms: {form id: {page: {missed: [...], junk: [...]}}}}
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from benchmark_score import IOU, match, overlap  # noqa: E402

from petey.paths import RUNS  # noqa: E402

KEY = RUNS / "benchmark" / "dev_key"
PRED = RUNS / "benchmark" / "dev_predictions"
OUT = RUNS / "benchmark" / "dev_analysis" / "light_misses.json"


def classify(key_fields: list[dict], finder: list[dict], score: dict, pred: list[dict], keep: float) -> list[dict]:
    """[{code, rect, kind, cause}] for the key fields the prediction misses. `finder` the finder's boxes [{id, rect}],
    `score` Jev's {box id: score}, `pred` the light path's final fields [{id, rect}]."""
    kf = {f["id"]: f for f in key_fields}
    found = set(match({k: f["rect"] for k, f in kf.items()}, {f["id"]: f["rect"] for f in pred}, IOU).values())
    out = []
    for k, f in kf.items():
        if k in found:
            continue
        cands = [b for b in finder if overlap(b["rect"], f["rect"]) >= IOU]
        kept = [b for b in cands if (score.get(b["id"]) or 0) >= keep]
        if not cands:
            cause = "no box"
        elif not kept:
            cause = "jev"
        elif any(sum(overlap(b["rect"], g["rect"]) >= IOU for g in kf.values()) >= 2 for b in kept):
            cause = "one box"
        else:
            cause = "later"
        out.append({"code": k, "rect": f["rect"], "kind": f.get("kind"), "cause": cause})
    return out


def junk(key_fields: list[dict], pred: list[dict], jev: dict) -> list[dict]:
    """[{rect, jev}] for the light path's fields that match no key field."""
    m = match({f["id"]: f["rect"] for f in key_fields}, {f["id"]: f["rect"] for f in pred}, IOU)
    return [{"rect": f["rect"], "jev": jev.get(f["id"])} for f in pred if f["id"] not in m]


def jev_of(bp: dict) -> dict:
    """{prediction id: Jev's is-field score} from a kept light blueprint (ids as `benchmark_light.to_prediction`'s)."""
    out = {}
    for n, s in (bp.get("fields") or {}).items():
        j = (s.get("x_petey_geometry") or {}).get("jev_is_field")
        if s.get("widgets"):
            for k, v in zip(s["widgets"], j if isinstance(j, list) else [j] * len(s["widgets"])):
                out[f"{n}.{k}"] = v
        else:
            out[n] = j
    return out


class CachedOnly:
    """Jev's screen answered from its cache alone: `jev_page.ask` swapped for a lookup while the block runs."""

    def __enter__(self):
        from petey.validate import jev_page
        self.jp, self.ask, self.uncached = jev_page, jev_page.ask, 0

        def cached(client, key, body, imgs):
            h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()
                               + b"".join(hashlib.sha256(imgs[r]).digest() for r in sorted(imgs))).hexdigest()
            if not (jev_page.CACHE / f"img_{h}.json").exists():
                self.uncached += 1
                return {"answers": {}, "usage": {"input_tokens": 0}}
            return self.ask(client, key, body, imgs)
        jev_page.ask = cached
        return self

    def __exit__(self, *exc):
        self.jp.ask = self.ask


def page(args: tuple) -> dict:
    pid, key_dir, pred_dir = args
    import flat_light as FL
    from petey.synth import boxes as B
    raw = key_dir / "pages" / f"{pid}.pdf"
    key = json.loads((key_dir / f"{pid}.json").read_text())
    pred = json.loads((pred_dir / "light" / f"{pid}.json").read_text())["fields"]
    bpf = pred_dir / "light_bp" / f"{pid}.json"
    jev = jev_of(json.loads(bpf.read_text())) if bpf.exists() else {}
    finder = B.find_boxes(raw)
    with CachedOnly() as c:
        score, _ = FL.screen(raw, finder, 4)
    return {"page_id": pid, "missed": classify(key["fields"], finder, score, pred, FL.KEEP),
            "junk": junk(key["fields"], pred, jev), "uncached": c.uncached}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--key", type=Path, default=KEY)
    ap.add_argument("--pred", type=Path, default=PRED)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--procs", type=int, default=6)
    a = ap.parse_args()
    index = json.loads((a.key / "index.json").read_text())
    forms: dict[str, dict] = {}
    uncached = 0
    t0 = time.time()
    with cf.ProcessPoolExecutor(a.procs) as ex:
        for n, r in enumerate(ex.map(page, [(x["page_id"], a.key, a.pred) for x in index], chunksize=4), 1):
            form, pg = r["page_id"].rsplit("__p", 1)
            forms.setdefault(form, {})[pg] = {"missed": r["missed"], "junk": r["junk"]}
            uncached += r["uncached"]
            if n % 200 == 0:
                print(f"{n}/{len(index)} pages, {time.time() - t0:.0f} s", flush=True)
    built = {"when": time.strftime("%Y-%m-%d %H:%M"), "key": str(a.key), "pages": len(index),
             "key_index_mtime": (a.key / "index.json").stat().st_mtime, "uncached_requests": uncached}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps({"built": built, "forms": forms}))
    missed = sum(len(p["missed"]) for f in forms.values() for p in f.values())
    print(f"{len(index)} pages: {missed} missed, {sum(len(p['junk']) for f in forms.values() for p in f.values())} "
          f"junk; uncached Jev requests {uncached} -> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
