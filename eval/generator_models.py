"""Which frontier model should be the blind generator? Same forms, same loop, only the generator changes.

For each (form, model) the loop runs once: blind generation from the page
image (cached per model, so reruns are free), fill, by-path extraction,
name-based reader, score. What a generator is judged on:

  filled      values it produced for the form's fields (coverage)
  fill_agree  by-path readback == ground truth (the values survived filling:
              on-states exist, comb lengths fit, dates parse)
  rule_viol   values that break the blueprint's declared rules (enum, pattern,
              mutex)
  shape       declared-shape contradictions the values caused
  reader      the Sonnet 4.6 name-based reader's agreement (a realism proxy:
              values a reader can find beside the right caption)
  tokens/s    from runs/_calls/generate/<form>/<model>/

    PYTHONPATH=. venv/bin/python eval/generator_models.py --forms fw9,acord25,i765 \
        --models claude-sonnet-4-6,gpt-5.5,gemini-3.8-flash,deepseek-v4-pro
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

from petey.paths import RUNS

OUT = RUNS / "genmodels"
# $/1M tokens (input, output), vendor list prices fetched 2026-09-30; DeepSeek at peak rates
PRICES = {"claude-sonnet-4-6": (3.0, 15.0), "claude-sonnet-5": (2.0, 10.0), "claude-haiku-4-5": (1.0, 5.0), "claude-opus-5": (5.0, 25.0),
          "gpt-5.5": (5.0, 30.0), "gpt-4.1": (2.0, 8.0),
          "gemini-3.1-pro-preview": (2.0, 12.0), "gemini-3.8-flash": (0.75, 3.75),
          "deepseek-flash": (0.3, 1.2), "deepseek-v4-pro": (1.32, 3.96)}
IMAGE_FORMS = {"vba21526ez", "ma1", "va760", "va_form_10_10ez"}


def run_one(form: str, model: str, blank: str | None) -> Path:
    out = OUT / f"iterate_{form}_{model.replace('/', '_')}.json"
    if out.exists():
        return out
    reader = "petey:image" if form in IMAGE_FORMS else "petey:pymupdf"
    cmd = [sys.executable, "-u", "-m", "petey.validate.iterate", "--form", form, "--gen-model", model,
           "--gen-key", f"{form}_gm", "--methods", f"native,{reader}", "--n-flat", "0", "--max-iter", "1",
           "--out", str(out)]
    if blank:
        cmd += ["--blank", blank]
    log = out.with_suffix(".log")
    with open(log, "w") as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=False)
    return out


def usage_for(form: str, model: str) -> dict:
    d = RUNS / "_calls" / "generate" / f"{form}_gm_intact_001" / model.replace("/", "_")
    tot = collections.Counter()
    for f in d.glob("*.json") if d.exists() else []:
        r = json.load(open(f)); u = r.get("usage") or {}
        tot["in"] += u.get("input_tokens") or 0; tot["out"] += u.get("output_tokens") or 0
        tot["s"] += r.get("elapsed_s") or 0; tot["calls"] += 1
        tot["truncated"] += 1 if r.get("truncated") else 0
    pi, po = PRICES.get(model, (0, 0))
    tot["usd"] = round((tot["in"] * pi + tot["out"] * po) / 1e6, 4)
    return dict(tot)


def row(form: str, model: str, it_json: Path) -> dict:
    if not it_json.exists():
        return {"form": form, "model": model, "error": "no output (see log)"}
    d = json.load(open(it_json))
    if not d.get("iterations"):
        return {"form": form, "model": model, "error": d.get("status", "no iterations")}
    it = d["iterations"][0]
    run = RUNS / it["run"] / "case_001_intact"
    gt = json.load(open(run / "ground_truth.json")) if (run / "ground_truth.json").exists() else {}
    vals = gt.get("values", gt) if isinstance(gt, dict) else {}
    filled = sum(1 for v in vals.values() if v not in (None, "", False, "Off"))
    summ = json.load(open(RUNS / it["run"] / "summary.json"))
    native = summ["intact"].get("native", {})
    readers = [m for m in summ.get("methods", []) if m != "native"]
    rd = summ["intact"].get(readers[0], {}) if readers else {}
    sc = json.load(open(run / "score_native.json")) if (run / "score_native.json").exists() else {}
    return {"form": form, "model": model, "fields": summ.get("n_fields"), "filled": filled,
            "fill_agree": native.get("agree"), "fill_miss": native.get("extract_miss"), "fill_differ": native.get("differ"),
            "rule_viol": len(sc.get("gt_rule_violations") or []), "shape": native.get("gt_shape_mismatch"),
            "reader_agree": rd.get("agree"), "reader_defect": it.get("delta", {}).get("defect", 0),
            "usage": usage_for(form, model), "seconds_loop": it.get("seconds")}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", default="fw9,acord25,i765")
    ap.add_argument("--models", default="claude-sonnet-4-6,gpt-5.5,gemini-3.8-flash,deepseek-v4-pro")
    ap.add_argument("--blank", default=None, help="blank PDF when the form has no blueprint yet")
    ap.add_argument("--no-run", action="store_true", help="tabulate existing outputs only")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for form in args.forms.split(","):
        for model in args.models.split(","):
            out = OUT / f"iterate_{form}_{model.replace('/', '_')}.json"
            if not args.no_run:
                out = run_one(form, model, args.blank)
            r = row(form, model, out); rows.append(r)
            print(json.dumps(r), flush=True)
    (OUT / "generator_models.json").write_text(json.dumps(rows, indent=1))
    print("\n| form | generator | filled/fields | fill agree / miss / differ | rule viol | shape | reader agree (defects) | tokens in/out | $ | gen s |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        if "error" in r:
            print(f"| {r['form']} | {r['model']} | {r['error']} | | | | | | |"); continue
        u = r["usage"]
        print(f"| {r['form']} | {r['model']} | {r['filled']}/{r['fields']} | {r['fill_agree']} / {r['fill_miss']} / {r['fill_differ']} | {r['rule_viol']} | {r['shape']} | "
              f"{r['reader_agree']} ({r['reader_defect']}) | {u.get('in', 0):,}/{u.get('out', 0):,}{' TRUNC' if u.get('truncated') else ''} | {u.get('usd', 0):.3f} | {u.get('s', 0):.0f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
