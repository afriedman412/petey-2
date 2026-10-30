"""The reader (the loop's meaning-based judge, `petey/extract_llm.py`, text-layer mode) on saved test cases, for any
model, against Sonnet's saved readings of the same cases (2026-10-13: can a local model be the reader?).

Each case is a validate run's first intact case: the filled PDF, the values filled in (ground_truth.json), the boxes
the filler never reached (case_unreached.json) and the run's blueprint snapshot. The model reads the PDF's text
layer by field name (`extract_llm(..., parser="pymupdf")`); `validate.score` grades it as the loop does. Sonnet's
reading from the run (extract_judge:pymupdf.json) is graded the same way, so both see identical cases and scoring.
Right = agree / (agree + differ + extract_miss). A model under `--gate` on the first form stops there.

    PETEY_LOCAL_LLM_URL=http://127.0.0.1:8081/v1 PYTHONPATH=. venv/bin/python eval/local_vlm/reader_test.py local-...
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import yaml

from petey.extract_llm import extract_llm
from petey.paths import RUNS
from petey.validate.score import score

RUNS_USED = ["mvdb61_20261001_193038", "ut_wc_122_20260930_234733", "gse_1008_20261006_144452"]
OUT = RUNS / "local_vlm" / "reader"


def graded(bpt: dict, case: Path, values: dict) -> dict:
    gt = json.loads((case / "ground_truth.json").read_text())
    ur = case / "case_unreached.json"
    unreached = set(json.loads(ur.read_text())) if ur.exists() else set()
    v = score(bpt, gt, values, dispatch_per_field={}, unreached=unreached)["verdicts"]
    n = v.get("agree", 0) + v.get("differ", 0) + v.get("extract_miss", 0)
    return {"right": v.get("agree", 0), "scored": n, "share": v.get("agree", 0) / max(n, 1),
            "differ": v.get("differ", 0), "miss": v.get("extract_miss", 0)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("model")
    ap.add_argument("--runs", default=",".join(RUNS_USED))
    ap.add_argument("--gate", type=float, default=0.75)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for i, run in enumerate(args.runs.split(",")):
        case = RUNS / run / "case_001_intact"
        bpt = yaml.load((RUNS / run / "blueprint.bpt").read_text(), Loader=getattr(yaml, "CSafeLoader", yaml.SafeLoader))
        sonnet = graded(bpt, case, json.loads((case / "extract_judge:pymupdf.json").read_text()))
        t0 = time.time()
        try:
            values = extract_llm(bpt, case / "filled_intact.pdf", parser="pymupdf", model=args.model)
            mine, err = graded(bpt, case, values), None
        except Exception as e:
            values, mine, err = {}, {"share": 0.0, "right": 0, "scored": 0, "differ": 0, "miss": 0}, f"{type(e).__name__}: {e}"[:300]
        secs = round(time.time() - t0, 1)
        rec = {"model": args.model, "run": run, "seconds": secs, "error": err, "local": mine, "sonnet": sonnet}
        (OUT / f"{args.model}__{run}.json").write_text(json.dumps({**rec, "values": values}, indent=1, default=str))
        with (OUT / "results.jsonl").open("a") as f:
            f.write(json.dumps(rec) + "\n")
        print(f"{args.model} {run}: {mine['share']:.0%} right ({mine['right']}/{mine['scored']}, differ {mine['differ']}, "
              f"missed {mine['miss']}) | Sonnet {sonnet['share']:.0%} ({sonnet['right']}/{sonnet['scored']}) | "
              f"{secs} s{' | ' + err if err else ''}", flush=True)
        if i == 0 and mine["share"] < args.gate:
            print(f"{args.model}: under {args.gate:.0%} on the first form, stopping (the gate)", flush=True)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
