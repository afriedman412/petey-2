"""Which frontier model should be the labeler? Same forms, same loop, only the labeler changes.

For each (form, model): relabel the blank into a side copy (`--no-register
--no-retrieval --model M`), run the loop once against the form's cached
ground truth (`--gen-key <form>`, same values for every labeler), tabulate
shape contradictions, name-based reader agreement, real name defects, and
the labeler's tokens, dollars and seconds. Side copies end up under
runs/labelmodels/blueprints/.

    PYTHONPATH=. venv/bin/python eval/labeler_models.py --forms fw9,acord25,i765 \
        --models claude-sonnet-4-6,gpt-5.5,gemini-3.1-pro-preview
"""
from __future__ import annotations

import argparse
import collections
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from petey.paths import BLUEPRINTS, RUNS
from eval.generator_models import PRICES, reader_on_filled
from petey.validate.test_forms import TEST_FORMS, forms

OUT = RUNS / "labelmodels"
IMAGE_FORMS = {"ma1", "va760"} | {f.stem for f in TEST_FORMS if f.reader == "petey:image"}
BLANKS = {f.stem: str(f.blank_path) for f in TEST_FORMS}


def safe(model: str) -> str:
    return model.replace("/", "_").replace(".", "_")


def run_one(form: str, model: str) -> tuple[Path, Path]:
    stem = f"{form}_lm_{safe(model)}"
    bpt = BLUEPRINTS / f"{stem}.bpt"
    kept = OUT / "blueprints" / f"{stem}.bpt"
    out = OUT / f"iterate_{stem}.json"
    if out.exists():
        return out, kept
    log = OUT / f"{stem}.log"
    with open(log, "w") as fh:
        if not bpt.exists() and not kept.exists():
            subprocess.run([sys.executable, "-u", "-m", "petey.label.auto_label", "--blank", BLANKS[form],
                            "--name", stem, "--output", str(bpt), "--no-register", "--no-retrieval", "--model", model],
                           stdout=fh, stderr=subprocess.STDOUT, check=False)
        if kept.exists() and not bpt.exists():
            shutil.copy(kept, bpt)
        if bpt.exists():
            reader = "petey:image" if form in IMAGE_FORMS else "petey:pymupdf"
            subprocess.run([sys.executable, "-u", "-m", "petey.validate.iterate", "--form", stem, "--gen-model",
                            "claude-sonnet-4-6", "--gen-cache-only", "--gen-key", form, "--methods", f"native,{reader}",
                            "--n-flat", "0", "--max-iter", "1", "--out", str(out)],
                           stdout=fh, stderr=subprocess.STDOUT, check=False)
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(bpt), str(kept))
    return out, kept


def usage_for(stem: str, model: str) -> dict:
    d = RUNS / "_calls" / "auto_label" / stem / model.replace("/", "_")
    tot = collections.Counter()
    for f in d.glob("*.json") if d.exists() else []:
        r = json.load(open(f)); u = r.get("usage") or {}
        tot["in"] += u.get("input_tokens") or 0; tot["out"] += u.get("output_tokens") or 0
        tot["s"] += r.get("elapsed_s") or 0; tot["calls"] += 1; tot["truncated"] += 1 if r.get("truncated") else 0
    pi, po = PRICES.get(model, (0, 0))
    tot["usd"] = round((tot["in"] * pi + tot["out"] * po) / 1e6, 4)
    return dict(tot)


def row(form: str, model: str, out: Path, bpt: Path) -> dict:
    stem = f"{form}_lm_{safe(model)}"
    r = {"form": form, "model": model, "usage": usage_for(stem, model)}
    if not bpt.exists():
        r["error"] = "labeling failed (see log)"; return r
    bp = yaml.safe_load(open(bpt))
    r["fields"] = len(bp["fields"]); r["emit_fixes"] = bp.get("x_petey_emit_fixes") or {}
    if not out.exists():
        r["error"] = "loop failed (see log)"; return r
    d = json.load(open(out))
    if not d.get("iterations"):
        r["error"] = d.get("status"); return r
    it = d["iterations"][0]
    summ = json.load(open(RUNS / it["run"] / "summary.json"))
    readers = [m for m in summ.get("methods", []) if m != "native"]
    rd = summ["intact"].get(readers[0], {}) if readers else {}
    r.update({"shape": sum(it.get("shape", {}).values()), "shape_by": it.get("shape", {}),
              "reader_agree": rd.get("agree"), "reader_differ": rd.get("differ"), "reader_miss": rd.get("extract_miss"),
              "name_defects": it.get("delta", {}).get("defect", 0), "detected": it.get("detected"), **reader_on_filled(it["run"])})
    return r


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", default=None, help="comma-separated stems; default: the --tier's forms")
    ap.add_argument("--tier", default="core", choices=("smoke", "core", "full"))
    ap.add_argument("--models", default="claude-sonnet-4-6,gpt-5.5,gpt-4.1,gemini-3.8-flash,gemini-3.1-pro-preview,deepseek-flash")
    ap.add_argument("--no-run", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    stems = args.forms.split(",") if args.forms else [f.stem for f in forms(args.tier)]
    for form in stems:
        for model in args.models.split(","):
            stem = f"{form}_lm_{safe(model)}"
            out, bpt = (OUT / f"iterate_{stem}.json", OUT / "blueprints" / f"{stem}.bpt") if args.no_run else run_one(form, model)
            r = row(form, model, out, bpt); rows.append(r); print(json.dumps(r), flush=True)
    (OUT / "labeler_models.json").write_text(json.dumps(rows, indent=1))
    print("\n| form | labeler | fields | emit fixes | shape contradictions | reader agree on filled / miss | name defects | tokens in/out | $ | label s |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        u = r["usage"]
        if "error" in r:
            print(f"| {r['form']} | {r['model']} | {r.get('fields', '')} | | {r['error']} | | | {u.get('in', 0):,}/{u.get('out', 0):,}{' TRUNC' if u.get('truncated') else ''} | {u.get('usd', 0):.3f} | {u.get('s', 0):.0f} |"); continue
        print(f"| {r['form']} | {r['model']} | {r['fields']} | {', '.join(f'{k} {v}' for k, v in r['emit_fixes'].items()) or 'none'} | {r['shape']} {r['shape_by'] or ''} | "
              f"{r.get('agree_filled')}/{r.get('filled')} / {r.get('miss_filled')} | {r['name_defects']} | {u.get('in', 0):,}/{u.get('out', 0):,}{' TRUNC' if u.get('truncated') else ''} | {u.get('usd', 0):.3f} | {u.get('s', 0):.0f} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
