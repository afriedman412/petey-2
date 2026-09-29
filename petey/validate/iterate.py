"""Iterate a blueprint to completion: validate -> detect -> fix -> validate again.

One pass of the loop finds defects and applies the mechanical fixes; this
repeats it until a fix pass changes nothing, and then says what is left and
which taxonomy class it belongs to. The blueprint on disk
(`blueprints/<form>.bpt`) is the state that advances; every validate run
copies it, so each iteration is scored against its own snapshot.

    python -m petey.validate.iterate --form fw9 --gen-model local
    python -m petey.validate.iterate --form va_form_10_10ez --blank "source_pdfs/VA Form 10-10EZ.pdf" \\
        --label-model none --gen-model local           # no blueprint yet: label first, no API
    python -m petey.validate.iterate --form vba21526ez --gen-model claude-sonnet-4-6 --gen-cache-only \\
        --methods native,petey:pymupdf --apply-correct  # with the meaning arm and cycle rebinds

Per iteration:
  1. validate  — `petey.validate.validate` (label if the blueprint is missing;
                 generate; fill; extract with each method; score).
  2. detect    — from the intact case: verdicts, `gt_shape_mismatch` by reason,
                 rule violations; if a meaning-arm score exists, `method_delta`
                 findings by cause and `correct.analyse_run` cycles.
  3. fix       — `retype` rules + descriptions on the blueprint; with
                 `--apply-correct`, closed cycles whose every rebind the
                 oracle graded `confirmed`.
Stops when step 3 changes nothing (`clean` if nothing was detected,
`converged_with_residue` otherwise) or at `--max-iter`. The residue is
reported by detector reason and mapped to `defect_taxonomy` class names, so
what remains is a decision list, not a mystery.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

from petey.label import xfa as xfa_mod
from petey.paths import BLUEPRINTS, RUNS
from petey.synth.local import widget_limits
from petey.validate import correct as correct_mod
from petey.validate import method_delta
from petey.validate.retype import describe_blueprint, resolve_blank, retype_blueprint

# detector reason -> taxonomy classes it can be (the class that applies is a
# per-field question; the loop reports the reason and the candidates)
CLASS_OF = {
    "pattern_vs_value": ("part_typed_as_whole", "short_shape_on_wide_box", "value_overflows_box"),
    "date_type_vs_value": ("part_typed_as_whole", "approximate_date_month_year"),
    "number_type_vs_value": ("nonnumeric_in_numeric_field",),
    "name_vs_value": ("name_slide",),
    "value_not_in_values": ("yn_column",),
    "rule_violation": ("rule_violation",),
    "defect": ("name_rotation", "name_slide", "repeated_section_ambiguity"),
    "unlocatable": ("missing_description", "repeated_section_ambiguity"),
    "substring": ("value_overflows_box", "compound_widget"),
    "boolean": ("yn_column",),
    "phantom": ("phantom",),
}


def run_validate(form: str, blank: Optional[Path], *, gen_model: str, methods: str,
                 n_flat: int, gen_cache_only: bool, label_model: Optional[str],
                 gen_key: Optional[str]) -> Path:
    if blank is None:
        bp = yaml.safe_load((BLUEPRINTS / f"{form}.bpt").read_text(encoding="utf-8"))
        blank = resolve_blank(bp)
        if blank is None:
            raise SystemExit(f"{form}: no blank PDF found for source_pdf={bp.get('source_pdf')!r}")
    cmd = [sys.executable, "-m", "petey.validate.validate", "--blank", str(blank),
           "--form-id", form, "--n-flat", str(n_flat), "--methods", methods,
           "--gen-model", gen_model]
    if gen_cache_only:
        cmd.append("--gen-cache-only")
    if label_model:
        cmd += ["--label-model", label_model]
    if gen_key:
        cmd += ["--gen-key", gen_key]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    m = re.search(r"run_dir=(\S+)", proc.stdout or "")
    if proc.returncode != 0 or not m:
        raise RuntimeError(f"validate failed for {form}:\n{(proc.stdout or '')[-800:]}\n{(proc.stderr or '')[-800:]}")
    return Path(m.group(1))


def detect(form: str, run_dir: Path) -> dict:
    intact = run_dir / "case_001_intact"
    out: dict = {"run": run_dir.name, "verdicts": {}, "shape": {}, "rule_violations": 0,
                 "delta": {}, "confirmed_cycles": [], "generation": None}
    score_path = intact / "score_native.json"
    if not score_path.exists():
        summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {}
        out["generation"] = "no_ground_truth" if not summary.get("intact", {}).get("native") else "no_score"
        return out
    r = json.loads(score_path.read_text())
    out["verdicts"] = r.get("verdicts", {})
    out["shape"] = dict(collections.Counter((r.get("gt_shape_mismatches") or {}).values()))
    out["rule_violations"] = len(r.get("rule_violations") or [])
    if any(intact.glob("score_petey*.json")):
        res = method_delta.compare_run(run_dir, "auto")
        out["delta"] = dict(collections.Counter(f["verdict"] for f in res["findings"] if not f.get("flat_only")))
        ana = correct_mod.analyse_run(form, run_dir)
        if ana:
            for c in ana["cycles"]:
                if c["rebinds"] and all(rb.get("grade") == "confirmed" for rb in c["rebinds"]):
                    out["confirmed_cycles"].append(c)
    out["total"] = (sum(out["shape"].values()) + out["rule_violations"]
                    + sum(v for k, v in out["delta"].items() if k in ("defect", "unlocatable"))
                    + out["verdicts"].get("differ", 0) + out["verdicts"].get("extract_miss", 0))
    return out


def fix(form: str, detection: dict, *, describe: bool, apply_correct: bool) -> collections.Counter:
    bp_path = BLUEPRINTS / f"{form}.bpt"
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
    blank = resolve_blank(bp)
    limits = widget_limits(blank) if blank else {}
    changes = retype_blueprint(bp, limits)
    if describe and blank:
        try:
            tpl = xfa_mod.parse(blank)
        except Exception:
            tpl = None
        changes.update(describe_blueprint(bp, limits, tpl))
    if changes:
        bp_path.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True,
                                          default_flow_style=False), encoding="utf-8")
    if apply_correct:
        for c in detection.get("confirmed_cycles") or []:
            n = correct_mod.apply_rebinds(bp_path, c["rebinds"])
            if n:
                changes[f"rebind_cycle:{len(c['names'])}"] += n
    return changes


def residue(detection: dict) -> list[tuple[str, int, tuple[str, ...]]]:
    rows = []
    for reason, n in detection.get("shape", {}).items():
        rows.append((reason, n, CLASS_OF.get(reason, ())))
    if detection.get("rule_violations"):
        rows.append(("rule_violation", detection["rule_violations"], CLASS_OF["rule_violation"]))
    for cause, n in detection.get("delta", {}).items():
        if cause in ("defect", "unlocatable", "substring", "boolean", "phantom"):
            rows.append((f"delta:{cause}", n, CLASS_OF.get(cause, ())))
    v = detection.get("verdicts", {})
    for k in ("differ", "extract_miss"):
        if v.get(k):
            rows.append((f"native:{k}", v[k], ("extraction mechanics",)))
    return sorted(rows, key=lambda t: -t[1])


def iterate(form: str, blank: Optional[Path], *, gen_model: str, methods: str, n_flat: int,
            gen_cache_only: bool, label_model: Optional[str], gen_key: Optional[str],
            max_iter: int, describe: bool, apply_correct: bool) -> dict:
    history = []
    status = "max_iter"
    for i in range(1, max_iter + 1):
        t0 = time.time()
        run_dir = run_validate(form, blank, gen_model=gen_model, methods=methods, n_flat=n_flat,
                               gen_cache_only=gen_cache_only, label_model=label_model, gen_key=gen_key)
        det = detect(form, run_dir)
        if det.get("generation"):
            history.append({"iteration": i, "run": run_dir.name, "blocked": det["generation"]})
            status = "blocked:" + det["generation"]
            print(f"[{form}] iter {i}: {status}")
            break
        changes = fix(form, det, describe=describe, apply_correct=apply_correct)
        rec = {"iteration": i, "run": run_dir.name, "seconds": round(time.time() - t0, 1),
               "verdicts": det["verdicts"], "shape": det["shape"], "delta": det["delta"],
               "rule_violations": det["rule_violations"], "detected": det["total"],
               "fixed": dict(changes)}
        history.append(rec)
        print(f"[{form}] iter {i}: detected={det['total']} verdicts={det['verdicts']} "
              f"shape={det['shape']} delta={det['delta']} -> fixed={dict(changes)} ({rec['seconds']}s)")
        if not changes:
            status = "clean" if det["total"] == 0 else "converged_with_residue"
            break
    result = {"form": form, "status": status, "iterations": history,
              "residue": residue(history[-1] if history and "detected" in history[-1] else {})}
    if result["residue"]:
        print(f"[{form}] {status}; residue by detector reason -> taxonomy classes:")
        for reason, n, classes in result["residue"]:
            print(f"    {n:>5}  {reason:<26} {' / '.join(classes)}")
    else:
        print(f"[{form}] {status}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", default=None, help="blueprint stem (created by labeling if missing)")
    ap.add_argument("--forms", default=None, help="comma-separated stems")
    ap.add_argument("--all", action="store_true", help="every ready blueprint (run_all's target set)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--blank", type=Path, default=None, help="blank PDF (needed when the blueprint does not exist)")
    ap.add_argument("--gen-model", default="local", help="'local' (no API) or a model id")
    ap.add_argument("--gen-cache-only", action="store_true")
    ap.add_argument("--gen-key", default=None)
    ap.add_argument("--methods", default="native")
    ap.add_argument("--n-flat", type=int, default=1)
    ap.add_argument("--label-model", default=None, help="'none' labels without an API when the blueprint is missing")
    ap.add_argument("--max-iter", type=int, default=4)
    ap.add_argument("--no-describe", action="store_true")
    ap.add_argument("--apply-correct", action="store_true",
                    help="also apply closed cycles graded confirmed by correct.py")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    if args.all or args.forms:
        from petey.validate.run_all import ready_targets
        targets = ready_targets()
        if args.forms:
            wanted = {f.strip() for f in args.forms.split(",") if f.strip()}
            targets = [t for t in targets if t[0] in wanted]
        if args.limit:
            targets = targets[:args.limit]
        out = args.out or (RUNS / "iterate_all.json")
        results = []
        t0 = time.time()
        for i, (form, blank) in enumerate(targets, 1):
            try:
                res = iterate(form, blank, gen_model=args.gen_model, methods=args.methods,
                              n_flat=args.n_flat, gen_cache_only=args.gen_cache_only,
                              label_model=args.label_model, gen_key=args.gen_key,
                              max_iter=args.max_iter, describe=not args.no_describe,
                              apply_correct=args.apply_correct)
            except Exception as e:  # one form must not stop the library
                res = {"form": form, "status": f"error: {str(e)[:200]}", "iterations": [], "residue": []}
                print(f"[{form}] {res['status']}")
            results.append(res)
            out.write_text(json.dumps(results, indent=1, default=str))
            print(f"  [{i}/{len(targets)}] {form:<24} {res['status']}", flush=True)
        c = collections.Counter(r["status"].split(":")[0] for r in results)
        print(f"[iterate] {len(results)} forms in {(time.time() - t0) / 60:.1f} min: {dict(c)} -> {out}")
        return 0
    if not args.form:
        ap.error("--form, --forms or --all is required")
    res = iterate(args.form, args.blank, gen_model=args.gen_model, methods=args.methods,
                  n_flat=args.n_flat, gen_cache_only=args.gen_cache_only,
                  label_model=args.label_model, gen_key=args.gen_key, max_iter=args.max_iter,
                  describe=not args.no_describe, apply_correct=args.apply_correct)
    out = args.out or (RUNS / f"iterate_{args.form}.json")
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
