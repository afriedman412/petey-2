"""Which model can be the loop's judge? Score candidate readers on the same runs.

For each form's latest run (a filled intact PDF plus its ground truth and
blueprint copy), run the name-based reader with each model, score it against
the ground truth the way validate does, classify disagreements the way
method_delta does, and log tokens and dollars. Same document, same fields,
same ground truth for every model — only the reader changes.

    PYTHONPATH=. venv/bin/python eval/reader_models.py --forms fw9,acord25,i765,vba21526ez \
        --models claude-sonnet-4-6,claude-sonnet-5,claude-haiku-4-5
"""
from __future__ import annotations

import argparse
import collections
import json
import time
from pathlib import Path

import yaml

from petey import extract_llm
from petey.paths import RUNS
from petey.validate import method_delta
from petey.validate.review import PRICES
from petey.validate.score import score

IMAGE_FORMS = {"vba21526ez", "ma1", "va760"}   # filled values missing from the text layer


def latest_run(form: str):
    dirs = sorted(d for d in RUNS.glob(f"{form}_2*")
                  if (d / "case_001_intact" / "filled_intact.pdf").exists()
                  and (d / "case_001_intact" / "score_native.json").exists())
    return dirs[-1] if dirs else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", default="fw9,acord25,i765,vba21526ez")
    ap.add_argument("--models", default="claude-sonnet-4-6,claude-sonnet-5,claude-haiku-4-5")
    ap.add_argument("--out", type=Path, default=RUNS / "reader_models.json")
    args = ap.parse_args()
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass
    rows = []
    for form in [f.strip() for f in args.forms.split(",") if f.strip()]:
        run = latest_run(form)
        if run is None:
            print(f"{form}: no run with a filled PDF")
            continue
        case = run / "case_001_intact"
        bpt = yaml.safe_load((run / "blueprint.bpt").read_text(encoding="utf-8"))
        gt = json.loads((case / "ground_truth.json").read_text())
        native = {p["field"]: p for p in json.loads((case / "score_native.json").read_text())["per_field"]}
        parser = "image" if form in IMAGE_FORMS else "pymupdf"
        for model in [m.strip() for m in args.models.split(",") if m.strip()]:
            extract_llm.USAGE.update({"input_tokens": 0, "output_tokens": 0, "calls": 0})
            t0 = time.time()
            try:
                values = extract_llm.extract_llm(bpt, case / "filled_intact.pdf", parser=parser, model=model)
            except Exception as e:
                rows.append({"form": form, "model": model, "error": str(e)[:200]})
                print(f"{form:<12} {model:<20} ERROR {str(e)[:120]}")
                continue
            rep = score(bpt, gt, values)
            causes = collections.Counter()
            for p in rep["per_field"]:
                if p["verdict"] in ("differ", "extract_miss") and native.get(p["field"], {}).get("verdict") == "agree":
                    causes[method_delta.classify(p["gt_value"], p["extracted_value"])] += 1
            u = dict(extract_llm.USAGE)
            pin, pout = PRICES.get(model, (0, 0))
            cost = u["input_tokens"] / 1e6 * pin + u["output_tokens"] / 1e6 * pout
            row = {"form": form, "model": model, "parser": parser, "run": run.name,
                   "fields": len(bpt.get("fields", {})), "agree": rep["verdicts"]["agree"],
                   "differ": rep["verdicts"]["differ"], "miss": rep["verdicts"]["extract_miss"],
                   "causes": dict(causes), "usage": u, "cost_usd": round(cost, 4),
                   "cached": u["calls"] == 0, "seconds": round(time.time() - t0, 1)}
            rows.append(row)
            print(f"{form:<12} {model:<20} agree {row['agree']:>4}/{row['fields']:<4} defect {causes.get('defect', 0):>3} "
                  f"unloc {causes.get('unlocatable', 0):>3} substr {causes.get('substring', 0):>3} "
                  f"${row['cost_usd']:.3f}{' (cached)' if row['cached'] else ''} {row['seconds']}s", flush=True)
    args.out.write_text(json.dumps(rows, indent=1))
    print(f"[ok] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
