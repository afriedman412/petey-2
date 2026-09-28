"""Add the meaning-based arm to every finished VLM-ground-truth run.

For each form that `run_all --gen-model <model>` completed, take its latest
run dir and, if it has no `score_petey*.json` yet, re-extract with
`native,petey:<parser>` (validate --reextract). Each form is one to three
model calls over its page text; responses are cached, so re-running is free.
Then `method_delta` reads the whole library.

    venv/bin/python eval/meaning_arm_all.py [--runs-json runs/run_all_vlm.json] [--parser pymupdf] [--limit N]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from petey.paths import RUNS


def latest_run(form: str) -> Path | None:
    dirs = sorted(d for d in RUNS.glob(f"{form}_*") if d.is_dir() and (d / "case_001_intact").exists())
    return dirs[-1] if dirs else None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs-json", type=Path, default=RUNS / "run_all_vlm.json")
    ap.add_argument("--parser", default="pymupdf", choices=["pymupdf", "image"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", type=Path, default=RUNS / "meaning_arm_all.json")
    args = ap.parse_args()
    forms = [r["form"] for r in json.loads(args.runs_json.read_text()) if r.get("ok")]
    if args.limit:
        forms = forms[:args.limit]
    log = json.loads(args.out.read_text()) if args.out.exists() else {}
    t0 = time.time()
    for i, form in enumerate(forms, 1):
        d = latest_run(form)
        if d is None:
            continue
        if any(d.glob("case_*/score_petey*.json")):
            log.setdefault(form, {"run": str(d), "status": "present"})
            continue
        cmd = [sys.executable, "-m", "petey.validate.validate", "--reextract",
               "--run-dir", str(d), "--methods", f"native,petey:{args.parser}"]
        t = time.time()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
        ok = proc.returncode == 0 and any(d.glob("case_*/score_petey*.json"))
        log[form] = {"run": str(d), "status": "ok" if ok else "failed",
                     "seconds": round(time.time() - t, 1),
                     "tail": (proc.stdout or proc.stderr or "")[-300:]}
        print(f"[{i}/{len(forms)}] {form:<24} {'ok' if ok else 'FAIL'} {log[form]['seconds']}s", flush=True)
        args.out.write_text(json.dumps(log, indent=1))
    print(f"done in {(time.time() - t0) / 60:.1f} min -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
