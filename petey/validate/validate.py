"""End-to-end validation orchestrator: label → gen → fill → extract → score.

For a blank AcroForm PDF, run N cases through the pipeline:

  1. Auto-label the blank into a `.bpt` (once, reused if --relabel omitted).
  2. Per case: generate LLM ground truth from the blank + AcroForm inventory
     (`petey-synthetic.generate_from_pdf`); fill the blank via pymupdf.
     (Node/pdf-lib until 2026-07-06; `node_tools/*.mjs` is now dead code.)
  3. Extract with each requested method (see below).
  4. Score each method's output against the same ground truth.

Two case variants:
  - intact:    the filled AcroForm PDF, untouched — sanity check.
  - flattened: filled PDF with AcroForm flattened via `pdf-lib` — this is
               where the LLM-free path's `text_clip`/`ocr` fallbacks are
               actually tested.

Two extraction methods:
  - native:    widget-mapper/extract.py directly (AcroForm + text_clip +
               OCR dispatch; no LLM at extraction time).
  - datalab:   Petey CLI with `--parser datalab --model <model>` (Datalab's
               fast native OCR + LLM interprets against the .bpt schema).

Usage:
    python validate.py --blank <blank.pdf> [--form-id name] [--relabel]
        [--n-flat 5] [--methods native,datalab] [--out runs/]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from statistics import mean
from typing import Optional


from petey.synth import generate_from_pdf, render_pdf, generate_local, seed_from_key  # noqa: E402
from petey.synth.bank import class_map_from_blueprint, generate_from_bank  # noqa: E402
from petey.synth.classify import classify_form  # noqa: E402

from petey.extract import extract, load_blueprint  # noqa: E402
from petey.extract_llm import extract_llm  # noqa: E402
from petey.validate.score import score  # noqa: E402

from petey.paths import REPO, RUNS, BLUEPRINTS
DEFAULT_MODEL = "claude-sonnet-4-6"


PETEY_CACHE_DIR = RUNS / "_petey_cache"


def _flatten_pdf(src: Path, dst: Path) -> None:
    """Bake form widgets into permanent page content via pymupdf.

    Previously shelled to `flatten.mjs` (pdf-lib), which crashed on Adobe
    LiveCycle-authored widgets missing the N (Normal) appearance stream.
    pymupdf.Document.bake regenerates any missing appearances on demand
    and handles XFA-hybrid documents natively.
    """
    import pymupdf
    doc = pymupdf.open(str(src))
    try:
        doc.bake(annots=True, widgets=True)
        doc.save(str(dst), incremental=False, deflate=True)
    finally:
        doc.close()


def _extract_native(bpt: dict, pdf: Path) -> tuple[dict, dict]:
    """Returns `(extracted_values_with_meta, dispatch_per_field)`.

    Leaves `_meta` (with `dispatch_per_field`) inside the returned dict
    so it gets persisted to `extract_native.json` on disk. Necessary for
    ad-hoc rescoring — the scorer's class-6 empty-tolerance branch and
    class-11 diagnosis both need per-field dispatch info.
    """
    ex = extract(bpt, pdf)
    meta = ex.get("_meta", {}) or {}
    dispatch = meta.get("dispatch_per_field") or {}
    return ex, dispatch


def _extract_petey(
    bpt_path: Path, pdf: Path, *, parser: str, model: str,
) -> dict:
    """The meaning-based arm, in-process (`petey/extract_llm.py`).

    Reads by field NAME with no access to the widget layer, so it can see
    a mislabeled field that the geometry arm cannot. Used to shell out to
    the external `petey` CLI; everything runs in this repo now. Responses
    are cached by (fields, pdf bytes, parser, model) inside extract_llm.
    """
    bpt = load_blueprint(bpt_path)
    out_path = pdf.with_suffix(f".petey_{parser}.json")
    values = extract_llm(bpt, pdf, parser=parser, model=model)
    out_path.write_text(json.dumps(values, indent=2, default=str))
    return values


def _bank_cache_path(cache_dir: Optional[Path], blank_pdf: Path, key: Optional[str]) -> Optional[Path]:
    """Where a bank case's ground truth is frozen: same directory as the
    generator cache, keyed on the blank's bytes, the generator name and the
    case key (`<gen_key>_set<N>_case<K>` for a set member)."""
    if cache_dir is None:
        return None
    import hashlib
    h = hashlib.sha256()
    h.update(blank_pdf.read_bytes())
    h.update(b"\x00bank\x00")
    h.update((key or "").encode("utf-8"))
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{h.hexdigest()}.json"


SETS_DIR = RUNS / "_gen_cache" / "sets"


def _record_set(form_id: str, set_id: int, keys: list[str], gen_model: str, run_dir: Path) -> None:
    """The set manifest: which case keys make up `<form>_set<N>`, under which
    generator. Written once; later runs of the same set append themselves
    and a generator change is recorded, not silently absorbed."""
    SETS_DIR.mkdir(parents=True, exist_ok=True)
    mp = SETS_DIR / f"{form_id}_set{set_id}.json"
    if mp.exists():
        m = json.loads(mp.read_text(encoding="utf-8"))
        if m.get("generator") != gen_model:
            print(f"[set   ] WARNING: {mp.name} was created with generator {m.get('generator')!r}, "
                  f"this run uses {gen_model!r}; the cached ground truth is the frozen one")
            m.setdefault("generator_conflicts", []).append({"generator": gen_model, "run": run_dir.name})
        m.setdefault("runs", []).append(run_dir.name)
    else:
        m = {"form": form_id, "set": set_id, "generator": gen_model, "cases": keys,
             "created": time.strftime("%Y-%m-%d %H:%M:%S"), "runs": [run_dir.name]}
    mp.write_text(json.dumps(m, indent=1))


def _run_case(
    *,
    bpt_path: Path, bpt: dict, blank_pdf: Path,
    case_dir: Path, variant: str, methods: list[str], model: str,
    gen_model: Optional[str] = None,
    gen_cache_dir: Optional[Path] = None,
    gen_cache_key: Optional[str] = None,
    datalab_max_fields: int = 400,
    gen_cache_only: bool = False,
) -> dict:
    """Run one case end-to-end. Returns the case's scores per method."""
    case_dir.mkdir(parents=True, exist_ok=True)

    # 1. Ground truth
    print(f"    [{variant}] gen ground truth...")
    if (gen_model or model) == "local":
        # Model-free: values drawn from the blueprint's own types,
        # patterns, semantic types and rules (STRATEGY_v1 §3.6). Keyed
        # on the case key so reruns reproduce.
        gt = generate_local(bpt, blank_pdf, seed=seed_from_key(gen_cache_key))
    elif (gen_model or model) == "bank":
        # Value bank keyed by the page-grounded class map (TODO v6 synthetic
        # data, steps 1-2). The classification is one cached call per form;
        # with --gen-cache-only an uncached form falls back to the
        # blueprint's own typing, and the run records which it was.
        cmap = classify_form(blank_pdf, cache_only=gen_cache_only,
                             form_id=(gen_cache_key or "").rsplit("_intact", 1)[0] or None)
        if cmap is None:
            cmap = class_map_from_blueprint(bpt)
            print(f"    [{variant}] no cached classification; class map from the blueprint")
        donor = None
        if gen_cache_dir is not None:
            for blind in (True, False):
                hit = generate_from_pdf(blank_pdf, n=1, model=DEFAULT_MODEL, cache_dir=gen_cache_dir,
                                        cache_key_prefix=gen_cache_key, blind=blind, cache_only=True)
                if hit:
                    donor = hit[0]
                    break
        # Frozen once written: a case set must not drift when the class map
        # or the bank changes; regenerate a new set instead.
        bank_cp = _bank_cache_path(gen_cache_dir, blank_pdf, gen_cache_key)
        if bank_cp is not None and bank_cp.exists():
            gt = json.loads(bank_cp.read_text(encoding="utf-8"))
        else:
            gt = generate_from_bank(cmap, blank_pdf, seed=seed_from_key(gen_cache_key), donor=donor)
            if bank_cp is not None:
                bank_cp.write_text(json.dumps(gt, indent=2))
        (case_dir / "class_map.json").write_text(json.dumps(
            {k: v for k, v in cmap.items() if k != "raw"}, indent=1))
        if cmap.get("model") != "blueprint":
            from petey.validate.class_check import check_run_case
            rows = check_run_case(bpt, cmap, case_dir)
            t = collections.Counter(r["tier"] for r in rows)
            print(f"    [{variant}] class check: {t[1]} contradictions, {t[2]} type suggestions, "
                  f"{t[3]} uncaptioned")
    else:
        if gen_cache_only and not generate_from_pdf(
                blank_pdf, n=1, model=gen_model or model,
                cache_dir=gen_cache_dir, cache_key_prefix=gen_cache_key,
                cache_only=True):
            print(f"    [{variant}] no cached ground truth; skipping "
                  f"(--gen-cache-only)")
            return {"_gen_error": "no_cached_ground_truth"}
        gt = generate_from_pdf(
            blank_pdf, n=1, model=gen_model or model,
            cache_dir=gen_cache_dir, cache_key_prefix=gen_cache_key,
        )[0]
    (case_dir / "ground_truth.json").write_text(json.dumps(gt, indent=2))

    # 2. Fill intact
    filled = case_dir / "filled_intact.pdf"
    try:
        fill_report = render_pdf(gt, blank_pdf=blank_pdf, out=filled)
    except RuntimeError as e:
        # render_pdf shells to fill_pdf.mjs (pdf-lib), which crashes on
        # XFA-hybrid or broken-xref PDFs. Log and skip this case; the
        # whole form is dead-on-arrival to the pdf-lib fill path.
        msg = str(e).splitlines()[0][:200]
        print(f"    [{variant}] fill FAILED: {msg}")
        return {"_fill_error": msg}
    (case_dir / "fill_report.json").write_text(
        json.dumps(fill_report, indent=2)
    )
    print(f"    [{variant}] filled: text={fill_report.get('text_filled')} "
          f"cb={fill_report.get('checkbox_filled')} "
          f"radio={fill_report.get('radio_filled')} "
          f"skipped_radio={fill_report.get('radio_skipped')}")

    # 3. Variant transformation
    if variant == "flat":
        target = case_dir / "filled_flat.pdf"
        try:
            _flatten_pdf(filled, target)
        except Exception as e:
            # pymupdf's bake() should handle missing-N and XFA-hybrids, but
            # keep this tolerance in place for any residual pathologies
            # (extremely damaged PDFs, unrecognized field types).
            msg = str(e).splitlines()[0][:200] if str(e) else repr(e)
            print(f"    [{variant}] flatten FAILED, skipping methods: {msg}")
            return {"_flatten_error": msg}
    else:
        target = filled

    # 4. Extract + score per method
    per_method_scores: dict[str, dict] = {}
    for method in methods:
        try:
            if method == "native":
                ex, dispatch = _extract_native(bpt, target)
            elif method.startswith("petey") or method == "datalab":
                # `petey` runs the .bpt-dependent, meaning-based path. The
                # parser is a suffix — `petey:pymupdf` reads the page's
                # text layer, `petey:image` its rendered pages. `datalab`
                # is a historical alias that now means the text layer.
                parser = ("pymupdf" if method == "datalab"
                          else (method.split(":", 1) + ["pymupdf"])[1])
                # Skip on forms known to overflow Petey's LLM output tokens
                # (760+ missing rate on >=400-field forms in prior runs).
                # See --datalab-max-fields. Silent truncation is worse than
                # an explicit skip.
                n_fields = len(bpt.get("fields", {}))
                if datalab_max_fields and n_fields > datalab_max_fields:
                    print(f"    [{variant}] method={method} skipped "
                          f"(field count {n_fields} > "
                          f"{datalab_max_fields}; expect token-truncation)")
                    per_method_scores[method] = {
                        "error": f"skipped_large_form_{n_fields}_fields",
                        "verdicts": None,
                    }
                    continue
                ex = _extract_petey(
                    bpt_path, target, parser=parser, model=model,
                )
                dispatch = {}
            else:
                raise ValueError(f"Unknown method: {method}")
        except subprocess.CalledProcessError as e:
            print(f"    [{variant}] method={method} FAILED:\n"
                  f"      stdout: {e.stdout}\n      stderr: {e.stderr}")
            per_method_scores[method] = {"error": str(e), "verdicts": None}
            continue
        except Exception as e:
            print(f"    [{variant}] method={method} FAILED: {e!r}")
            per_method_scores[method] = {"error": str(e), "verdicts": None}
            continue

        (case_dir / f"extract_{method}.json").write_text(
            json.dumps(ex, indent=2, default=str)
        )
        report = score(bpt, gt, ex, dispatch_per_field=dispatch)
        (case_dir / f"score_{method}.json").write_text(
            json.dumps(report, indent=2, default=str)
        )
        per_method_scores[method] = report
        v = report["verdicts"]
        conf = report["agree_confirmed_count"]
        print(f"    [{variant}] method={method}: "
              f"agree={v['agree']} differ={v['differ']} "
              f"miss={v['extract_miss']} defect={v['gt_defect']} "
              f"conf={'n/a' if conf is None else conf}")

    return per_method_scores


def _aggregate(case_reports: list[dict], method: str) -> dict:
    """Average per-verdict counts across the cases where this method
    produced a valid score."""
    valid = [r[method] for r in case_reports
             if r.get(method, {}).get("verdicts") is not None]
    if not valid:
        return {"n_cases": 0}
    verdicts_keys = ["agree", "differ", "extract_miss", "gt_defect",
                     "rule_violation"]
    # .get: reports scored before a verdict existed lack its key
    avg = {k: mean(r["verdicts"].get(k, 0) for r in valid)
           for k in verdicts_keys}
    # These are None for uninstrumented methods (the Petey CLI emits no
    # per-widget dispatch); averaging None raises, and defaulting it to 0
    # would reassert the very claim the tri-state exists to avoid.

    def _mean_or_none(key: str):
        vals = [r[key] for r in valid if r.get(key) is not None]
        return mean(vals) if vals else None

    avg["agree_confirmed"] = _mean_or_none("agree_confirmed_count")
    avg["agree_by_absence"] = _mean_or_none("agree_by_absence_count")
    avg["labeler_miss"] = mean(
        r.get("labeler_miss_count", 0) for r in valid
    )
    avg["n_cases"] = len(valid)
    return avg


def _run_rescore(
    run_dir: Path, methods: list[str], reextract: bool = False,
    model: str = "", datalab_max_fields: int = 400,
) -> int:
    """Re-run scoring (and optionally extraction) against an existing run.

    Zero API cost. Walks every `case_XXX_*` dir, loads the persisted
    ground_truth.json and filled PDF, and either:
    - re-scores against the saved extract_METHOD.json (default), or
    - re-runs extract() then re-scores (with `reextract=True`).

    Useful for picking up extract-side fixes without paying for another
    gen/fill/flatten pass. Only the `native` method supports re-extract
    (datalab goes through Petey CLI which is cached separately).
    """
    if not run_dir.exists():
        print(f"[rescore] run dir not found: {run_dir}")
        return 1
    bpt_path = run_dir / "blueprint.bpt"
    if not bpt_path.exists():
        print(f"[rescore] blueprint.bpt not found in {run_dir}")
        return 1
    import yaml
    bpt = yaml.safe_load(bpt_path.read_text(encoding="utf-8"))
    form_id = run_dir.name.rsplit("_", 2)[0]

    print(f"[{'reextract' if reextract else 'rescore'}] "
          f"run_dir={run_dir} methods={methods}")

    case_dirs = sorted(
        d for d in run_dir.iterdir()
        if d.is_dir() and d.name.startswith("case_")
    )
    case_reports: list[dict] = []
    for case_dir in case_dirs:
        gt_path = case_dir / "ground_truth.json"
        if not gt_path.exists():
            print(f"  [{case_dir.name}] missing ground_truth.json — skip")
            case_reports.append({})
            continue
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        variant = "flat" if "flat" in case_dir.name else "intact"
        pdf_name = ("filled_flat.pdf" if variant == "flat"
                    else "filled_intact.pdf")
        pdf_path = case_dir / pdf_name

        per_method: dict[str, dict] = {}
        for method in methods:
            ex_path = case_dir / f"extract_{method}.json"

            if reextract and (method.startswith("petey")
                              or method == "datalab") and not ex_path.exists():
                # The whole point of the sweep: `native` reads back through
                # the same AcroForm path the generator wrote by, so it cannot
                # see a mislabeled field. Only this arm can, and it had run
                # on 74 of 796 cases because it is metered and off by
                # default. The filled PDFs and ground truth already exist, so
                # producing it here costs one extract call and no generation.
                if not pdf_path.exists():
                    per_method[method] = {"error": "no_filled_pdf",
                                          "verdicts": None}
                    continue
                n_fields = len(bpt.get("fields", {}))
                if datalab_max_fields and n_fields > datalab_max_fields:
                    print(f"  [{case_dir.name}] {method} skipped "
                          f"({n_fields} fields > {datalab_max_fields})")
                    per_method[method] = {
                        "error": f"skipped_large_form_{n_fields}_fields",
                        "verdicts": None}
                    continue
                parser = ("datalab" if method == "datalab"
                          else (method.split(":", 1) + ["pymupdf"])[1])
                try:
                    ex = _extract_petey(bpt_path, pdf_path, parser=parser,
                                        model=model or DEFAULT_MODEL)
                except Exception as e:
                    print(f"  [{case_dir.name}] {method} FAILED: {e!r}")
                    per_method[method] = {"error": str(e)[:200],
                                          "verdicts": None}
                    continue
                ex_path.write_text(json.dumps(ex, indent=2, default=str))
                ex_scoreable = {k: v for k, v in ex.items()
                                if not k.startswith("_")}
                dispatch = {}      # petey reports no per-field dispatch
            elif reextract and method == "native":
                if not pdf_path.exists():
                    per_method[method] = {
                        "error": "no_filled_pdf", "verdicts": None,
                    }
                    continue
                try:
                    ex, dispatch = _extract_native(bpt, pdf_path)
                except Exception as e:
                    per_method[method] = {
                        "error": str(e)[:200], "verdicts": None,
                    }
                    continue
                ex_path.write_text(
                    json.dumps(ex, indent=2, default=str)
                )
                # Strip _meta for score input; dispatch already extracted
                ex_scoreable = {k: v for k, v in ex.items()
                                if not k.startswith("_")}
            else:
                if not ex_path.exists():
                    per_method[method] = {
                        "error": "no_extract_json", "verdicts": None,
                    }
                    continue
                ex = json.loads(ex_path.read_text(encoding="utf-8"))
                meta = ex.pop("_meta", {}) or {}
                dispatch = meta.get("dispatch_per_field") or {}
                ex_scoreable = ex

            report = score(bpt, gt, ex_scoreable,
                           dispatch_per_field=dispatch)
            (case_dir / f"score_{method}.json").write_text(
                json.dumps(report, indent=2, default=str)
            )
            per_method[method] = report
            v = report["verdicts"]
            print(f"  [{case_dir.name}] method={method} "
                  f"agree={v['agree']} differ={v['differ']} "
                  f"miss={v['extract_miss']} defect={v['gt_defect']}")
        case_reports.append(per_method)

    n_fields = len(bpt.get("fields", {}))
    intact_reports = [r for r, d in zip(case_reports, case_dirs)
                      if "intact" in d.name]
    flat_reports = [r for r, d in zip(case_reports, case_dirs)
                    if "flat" in d.name]
    summary = {
        "form_id": form_id,
        "n_fields": n_fields,
        "methods": methods,
        "intact": ({m: intact_reports[0].get(m, {}).get("verdicts")
                    for m in methods} if intact_reports else {}),
        "flat_avg": {m: _aggregate(flat_reports, m) for m in methods},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\n[rescore] wrote {run_dir}/summary.json")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--blank", required=False, type=Path,
                    help="path to blank AcroForm PDF (omit with --rescore)")
    ap.add_argument("--form-id", type=str, default=None,
                    help="form ID (default: blank PDF stem)")
    ap.add_argument("--gen-key", default=None,
                    help="override the form-id used in the ground-truth "
                         "cache key. Two blueprints for the same blank can "
                         "then be scored against IDENTICAL ground truth, "
                         "making the blueprint the only variable — the A/B "
                         "any 'did this fix work' question needs. Without "
                         "it, a second form-id regenerates ground truth and "
                         "the comparison is confounded.")
    ap.add_argument("--relabel", action="store_true",
                    help="re-run auto_label even if .bpt exists")
    ap.add_argument("--n-flat", type=int, default=5,
                    help="number of flattened cases (default 5)")
    ap.add_argument("--methods", type=str, default="native",
                    help="comma-separated: native, petey[:parser], datalab. "
                         "native reads back through AcroForm paths and so "
                         "cannot see a mislabeled field; petey:<parser> "
                         "navigates by meaning and can. "
                         "Default 'native' — the petey methods are metered; "
                         "opt in explicitly when comparing methods.")
    ap.add_argument("--model", type=str, default=DEFAULT_MODEL,
                    help="datalab-side LLM model (default sonnet-4.6)")
    ap.add_argument("--gen-model", type=str, default=None,
                    help="override model for ground-truth gen. Default: "
                         "same as --model. Use haiku for cheap exploration; "
                         "'local' draws values from the blueprint with no API.")
    ap.add_argument("--label-model", type=str, default=None,
                    help="override model for auto_label. Default: --model. "
                         "'none' emits a geometry-only draft with no API.")
    ap.add_argument("--datalab-max-fields", type=int, default=0,
                    help="skip datalab method on forms exceeding this "
                         "field count (Petey LLM output-token-truncates "
                         "on large forms). 0 to disable.")
    ap.add_argument("--rescore", action="store_true",
                    help="re-score existing case dirs in the run dir "
                         "without re-generating / re-filling / re-extracting. "
                         "Requires --run-dir to point to an existing run.")
    ap.add_argument("--reextract", action="store_true",
                    help="like --rescore, but also re-runs extraction on the "
                         "filled PDFs before scoring. Picks up extract-side "
                         "fixes. For petey methods it PRODUCES the extract "
                         "when absent (metered), which is how the "
                         "meaning-based arm gets added to runs that only "
                         "have native.")
    ap.add_argument("--gen-cache-only", action="store_true",
                    help="never call the generator API: use cached ground "
                         "truth or skip the case")
    ap.add_argument("--case-set", type=int, default=None, metavar="N",
                    help="run a versioned case set: --n-cases intact cases keyed "
                         "<gen-key>_setN_caseK, frozen once generated (TODO v6 step 3)")
    ap.add_argument("--n-cases", type=int, default=None,
                    help="intact cases in the set (default 3 with --case-set, else 1)")
    ap.add_argument("--fresh-flat-gt", action="store_true",
                    help="generate separate ground truth per flat case "
                         "(default: flat cases reuse the intact case's)")
    ap.add_argument("--run-dir", type=Path, default=None,
                    help="existing run dir to rescore (with --rescore/--reextract)")
    ap.add_argument("--out", type=Path,
                    default=RUNS,
                    help="output dir root")
    args = ap.parse_args()
    is_rescore_mode = args.rescore or args.reextract
    if not is_rescore_mode and args.blank is None:
        ap.error("--blank is required unless --rescore/--reextract is set")
    if is_rescore_mode and args.run_dir is None:
        ap.error("--rescore/--reextract requires --run-dir")

    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass

    methods = [m.strip() for m in args.methods.split(",") if m.strip()]

    # Rescore/reextract mode: skip gen/fill/flatten entirely; walk
    # existing case dirs, reload gt (+ optionally re-extract), re-score.
    if args.rescore or args.reextract:
        return _run_rescore(
            args.run_dir, methods, reextract=args.reextract,
            model=args.model, datalab_max_fields=args.datalab_max_fields,
        )

    form_id = args.form_id or args.blank.stem
    # Defaults to form_id, so behaviour is unchanged unless asked for.
    gen_key = args.gen_key or form_id
    ts = time.strftime("%Y%m%d_%H%M%S")
    run_dir = args.out / f"{form_id}_{ts}"
    run_dir.mkdir(parents=True, exist_ok=True)
    gen_cache_dir = args.out / "_gen_cache"

    n_cases = args.n_cases or (3 if args.case_set is not None else 1)
    print(f"[validate] form_id={form_id} methods={methods} "
          f"cases={n_cases} intact + {args.n_flat} flat"
          + (f" (case set {args.case_set})" if args.case_set is not None else ""))
    print(f"[validate] run_dir={run_dir}")

    # 1. Labeling
    label_model = args.label_model or args.model
    bpt_path = BLUEPRINTS / f"{form_id}.bpt"
    if args.relabel or not bpt_path.exists():
        print(f"[label ] running auto_label → {bpt_path}")
        label_cmd = [
            sys.executable, "-m", "petey.label.auto_label",
            "--blank", str(args.blank),
            "--output", str(bpt_path),
            "--form-version",
            form_id.split("-")[0] if "-" in form_id else "unknown",
        ]
        if label_model in ("none", "local"):
            label_cmd += ["--no-llm"]  # geometry-only draft, placeholder names
        elif label_model:
            label_cmd += ["--model", label_model]
        subprocess.run(label_cmd, check=True)
    else:
        print(f"[label ] reusing existing .bpt at {bpt_path}")
    shutil.copy(bpt_path, run_dir / "blueprint.bpt")
    bpt = load_blueprint(bpt_path)

    # 2. Cases: K intact (1, or a case set) + N flat
    if args.case_set is not None:
        intact_keys = [f"{gen_key}_set{args.case_set}_case{k:03d}" for k in range(1, n_cases + 1)]
    else:
        intact_keys = [f"{gen_key}_intact_001"] + [f"{gen_key}_intact_{k:03d}" for k in range(2, n_cases + 1)]
    case_reports: list[dict] = []
    for k, key in enumerate(intact_keys, start=1):
        intact_dir = run_dir / f"case_{k:03d}_intact"
        print(f"\n[case  ] {k:03d} (intact, {key})")
        case_reports.append(_run_case(
            bpt_path=bpt_path, bpt=bpt, blank_pdf=args.blank,
            case_dir=intact_dir, variant="intact",
            methods=methods, model=args.model,
            gen_model=args.gen_model,
            gen_cache_dir=gen_cache_dir,
            gen_cache_key=key,
            datalab_max_fields=args.datalab_max_fields,
            gen_cache_only=args.gen_cache_only,
        ))
    if args.case_set is not None:
        _record_set(form_id, args.case_set, intact_keys, args.gen_model or args.model, run_dir)
    intact_reports = list(case_reports)

    for i in range(args.n_flat):
        cnum = n_cases + i + 1
        flat_dir = run_dir / f"case_{cnum:03d}_flat"
        print(f"\n[case  ] {cnum:03d} (flat)")
        case_reports.append(_run_case(
            bpt_path=bpt_path, bpt=bpt, blank_pdf=args.blank,
            case_dir=flat_dir, variant="flat",
            methods=methods, model=args.model,
            gen_model=args.gen_model,
            gen_cache_dir=gen_cache_dir,
            gen_cache_key=(f"{gen_key}_flat_{cnum:03d}" if args.fresh_flat_gt
                           else intact_keys[0]),
            datalab_max_fields=args.datalab_max_fields,
            gen_cache_only=args.gen_cache_only,
        ))

    # 3. Aggregate summary
    n_fields = len(bpt.get("fields", {}))
    summary = {
        "form_id": form_id,
        "n_fields": n_fields,
        "methods": methods,
        "intact": {m: case_reports[0].get(m, {}).get("verdicts")
                   for m in methods},
        "set": ({"id": args.case_set, "n_cases": n_cases, "keys": intact_keys,
                 "per_method": {m: _aggregate(intact_reports, m) for m in methods},
                 "per_case": [{m: r.get(m, {}).get("verdicts") for m in methods} for r in intact_reports]}
                if n_cases > 1 else None),
        "flat_avg": {m: _aggregate(case_reports[n_cases:], m) for m in methods},
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print(f"\n{'=' * 70}")
    print(f"SUMMARY — {form_id} ({n_fields} bpt fields)")
    print(f"{'=' * 70}")
    print("\nINTACT (1 case):")
    print(f"  {'method':<10} {'agree':<8} {'differ':<8} {'miss':<8} "
          f"{'defect':<8} {'confirmed':<10}")
    for m in methods:
        v = case_reports[0].get(m, {})
        vd = v.get("verdicts")
        if vd is None:
            print(f"  {m:<10} ERROR: {v.get('error', 'unknown')[:50]}")
            continue
        c = v.get("agree_confirmed_count")
        conf = "n/a" if c is None else str(c)
        print(f"  {m:<10} {vd['agree']:<8} {vd['differ']:<8} "
              f"{vd['extract_miss']:<8} {vd['gt_defect']:<8} {conf:<10}")

    if summary["set"]:
        print(f"\nCASE SET {args.case_set} ({n_cases} intact cases, mean):")
        for m in methods:
            a = summary["set"]["per_method"][m]
            if a.get("n_cases", 0) == 0:
                print(f"  {m:<10} no valid cases")
                continue
            print(f"  {m:<10} agree {a['agree']:.1f}  differ {a['differ']:.1f}  "
                  f"miss {a['extract_miss']:.1f}  defect {a['gt_defect']:.1f}")

    if args.n_flat:
        print(f"\nFLATTENED ({args.n_flat} cases, mean):")
        print(f"  {'method':<10} {'agree':<8} {'differ':<8} {'miss':<8} "
              f"{'defect':<8} {'confirmed':<10}")
        for m in methods:
            a = summary["flat_avg"][m]
            if a.get("n_cases", 0) == 0:
                print(f"  {m:<10} no valid cases")
                continue
            c = a.get("agree_confirmed")
            conf = f"{'n/a':<10}" if c is None else f"{c:<10.1f}"
            print(f"  {m:<10} {a['agree']:<8.1f} {a['differ']:<8.1f} "
                  f"{a['extract_miss']:<8.1f} {a['gt_defect']:<8.1f} {conf}")

    print("\n  confirmed = agree verdicts where extract's dispatch reached "
          "the widget. 'n/a' means the method emits no dispatch (the Petey "
          "CLI does not) — it is not a count of zero.")

    print(f"\n[ok    ] wrote {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
