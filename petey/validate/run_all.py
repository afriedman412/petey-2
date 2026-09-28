"""Run the validator over every ready target document.

Deliberately not clever. `source_survey.py` decides which documents the
labeler's method applies to; this runs the existing loop over all of them
and records what happens, including the failures. Coverage questions get
answered by the run rather than predicted before it.

For each ready form: 1 intact case + N flattened cases through
generate -> fill -> extract -> score. Ground truth generation is cached,
so re-runs only pay for forms that have none yet.

Usage:
    python run_all.py --n-flat 1
    python run_all.py --n-flat 1 --limit 5        # smoke test
    python run_all.py --only-missing-ground-truth
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

from petey.paths import REPO, RUNS, BLUEPRINTS, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent


def ready_targets() -> list[tuple[str, Path]]:
    """(blueprint_stem, blank_pdf) for every ready source document."""
    survey = json.loads((RUNS / "source_survey.json").read_text())
    ready = {r["file"] for r in survey if r["verdict"] == "ready"}
    out = []
    for p in sorted((BLUEPRINTS).glob("*.bpt")):
        try:
            bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        src = bp.get("source_pdf")
        if not src or src not in ready:
            continue
        blank = SOURCE_PDFS / str(src)
        if not blank.exists():
            # the survey records basenames; most PDFs live in subfolders
            hits = [h for h in SOURCE_PDFS.rglob(Path(str(src)).name)
                    if "source_pdfs_old" not in h.parts]
            blank = hits[0] if len(hits) >= 1 else blank
        if blank.exists():
            out.append((p.stem, blank))
    return out


def has_ground_truth(form: str) -> bool:
    return any((RUNS).glob(f"{form}_*/case_*/ground_truth.json"))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n-flat", type=int, default=1)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only-missing-ground-truth", action="store_true")
    ap.add_argument("--gen-model", type=str, default=None,
                    help="passed to validate; 'local' runs the loop with no API")
    ap.add_argument("--label-model", type=str, default=None,
                    help="passed to validate; 'none' labels without an API")
    ap.add_argument("--forms", type=str, default=None,
                    help="comma-separated blueprint stems to run instead of the survey's ready set")
    ap.add_argument("--out", type=Path,
                    default=RUNS / "run_all.json")
    args = ap.parse_args()

    targets = ready_targets()
    if args.forms:
        wanted = {f.strip() for f in args.forms.split(",") if f.strip()}
        targets = [t for t in targets if t[0] in wanted]
    if args.only_missing_ground_truth:
        targets = [t for t in targets if not has_ground_truth(t[0])]
    if args.limit:
        targets = targets[:args.limit]

    print(f"[run_all] {len(targets)} target forms, "
          f"{args.n_flat} flat case(s) each")
    results = []
    t_start = time.time()
    for i, (form, blank) in enumerate(targets, 1):
        t0 = time.time()
        cmd = [sys.executable, "-m", "petey.validate.validate",
               "--blank", str(blank), "--form-id", form,
               "--n-flat", str(args.n_flat), "--methods", "native"]
        if args.gen_model:
            cmd += ["--gen-model", args.gen_model]
        if args.label_model:
            cmd += ["--label-model", args.label_model]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True,
                                  timeout=900)
            ok = proc.returncode == 0
            tail = (proc.stdout or "")[-400:]
            err = (proc.stderr or "")[-300:]
        except subprocess.TimeoutExpired:
            ok, tail, err = False, "", "timeout after 900s"

        rec = {"form": form, "ok": ok, "seconds": round(time.time() - t0, 1)}
        # Pull the summary the orchestrator already wrote.
        runs = sorted((RUNS).glob(f"{form}_*/summary.json"))
        if runs:
            try:
                rec["summary"] = json.loads(runs[-1].read_text())
            except Exception:
                pass
        if not ok:
            rec["error"] = (err or tail)[-200:]
        results.append(rec)

        v = ((rec.get("summary") or {}).get("intact") or {}).get("native")
        note = (f"agree={v['agree']} differ={v['differ']} "
                f"miss={v['extract_miss']}" if v else
                (rec.get("error", "")[:60] or "no summary"))
        print(f"  [{i:>3}/{len(targets)}] {form:<22} "
              f"{rec['seconds']:>6.1f}s  {'ok ' if ok else 'FAIL'}  {note}")
        args.out.write_text(json.dumps(results, indent=2, default=str))

    n_ok = sum(1 for r in results if r["ok"])
    print(f"\n[run_all] {n_ok}/{len(results)} succeeded in "
          f"{(time.time() - t_start) / 60:.1f} min -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
