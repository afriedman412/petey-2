"""Library-wide: where label-grounded ground truth contradicts the blueprint.

Walks every run dir that carries an intact ground truth and reports, per
form and per class, the fields whose generated value the blueprint's own
type / pattern / values reject (`score.shape_mismatch`). Only runs whose
ground truth came from a model are meaningful: the local generator draws
values FROM the declarations, so it contradicts nothing.

    venv/bin/python eval/shape_vs_declared.py [--runs-json runs/run_all_vlm.json] [--out runs/shape_vs_declared.json]
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import yaml

from petey.paths import RUNS
from petey.validate.score import _normalize_ground_truth, shape_mismatch


def latest_runs(forms: list[str] | None) -> dict[str, Path]:
    latest: dict[str, Path] = {}
    for d in sorted(RUNS.iterdir()):
        if not d.is_dir() or not (d / "case_001_intact" / "ground_truth.json").exists():
            continue
        form = d.name.rsplit("_", 2)[0]
        if forms is not None and form not in forms:
            continue
        latest[form] = d
    return latest


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--runs-json", type=Path, default=RUNS / "run_all_vlm.json",
                    help="run_all output naming the forms to include")
    ap.add_argument("--out", type=Path, default=RUNS / "shape_vs_declared.json")
    ap.add_argument("--top", type=int, default=15)
    args = ap.parse_args()
    forms = None
    if args.runs_json.exists():
        forms = [r["form"] for r in json.loads(args.runs_json.read_text()) if r.get("ok")]
    runs = latest_runs(forms)
    by_class: collections.Counter = collections.Counter()
    by_form: dict[str, dict] = {}
    total_fields = 0
    examples: dict[str, list] = collections.defaultdict(list)
    for form, d in sorted(runs.items()):
        bpt = yaml.safe_load((d / "blueprint.bpt").read_text(encoding="utf-8"))
        gt = json.loads((d / "case_001_intact" / "ground_truth.json").read_text())
        fields = bpt.get("fields", {})
        total_fields += len(fields)
        hits: collections.Counter = collections.Counter()
        for name, spec in fields.items():
            value, _ = _normalize_ground_truth(spec, gt)
            why = shape_mismatch(spec, value)
            if why:
                hits[why] += 1
                if len(examples[why]) < 8:
                    examples[why].append((form, name, spec.get("type"), spec.get("semantic_type"), str(value)[:30]))
        by_class.update(hits)
        by_form[form] = {"fields": len(fields), "mismatch": sum(hits.values()), **hits}
    n_mismatch = sum(by_class.values())
    print(f"{len(runs)} forms, {total_fields} fields, {n_mismatch} contradict the blueprint "
          f"({n_mismatch / max(total_fields, 1):.1%})")
    for k, v in by_class.most_common():
        print(f"  {k:<24} {v}")
    print("worst forms:")
    for form, rec in sorted(by_form.items(), key=lambda kv: -kv[1]["mismatch"])[:args.top]:
        print(f"  {form:<24} {rec['mismatch']:>4} / {rec['fields']:<4} "
              + " ".join(f"{k}={v}" for k, v in rec.items() if k not in ("fields", "mismatch")))
    print("examples:")
    for why, rows in examples.items():
        for r in rows[:4]:
            print(f"  {why:<22} {r}")
    args.out.write_text(json.dumps({"by_class": by_class, "by_form": by_form}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
