# Port plan v1 — what comes over from petey-master, and where it goes

Draft 2026-09-28. Scope: PLAN.md task 1. Sizes measured; closures computed from imports.

## Principles
- One package, `petey/`, that a consumer runs with no model and no network. Everything that calls a frontier model
  lives in a clearly named module and has a local-swap seam.
- Three routes, one schema. Every geometry source emits `{page, rect, kind, source, conf}` (step2flat's shape);
  every naming source emits one record per widget. Integration (task 3) is then a join, not a rewrite.
- `step2flat/`, `harness/`, `eval/` stay where they are. The frozen-reader hash discipline is unchanged.
- Data that is derivable is not committed. Runs, models and the 6GB archive stay out of band.

## Target layout
```
petey/
  extract.py          3-tier offline extractor            <- widget-mapper/extract.py
  semantic_types.py   slug -> type / pattern / whitelist  <- widget-mapper/semantic_types.py
  bpt_version.py      declare bpt_version from content    <- widget-mapper/_bpt_version.py
  bpt.py              load / validate / emit (slice 2)    new
  locate/             WHERE: acroform | programmatic (adapter over step2flat) | detector | vlm
  name/               WHAT: acroform tooltips+paths | retrieve (vocab, MiniLM) | llm | vlm | canonical
  synth/              values + AcroForm render            <- petey-synthetic (536 lines); flat-fill is new
  validate/           validate, score, shape_agree, method_delta, structural_defects, defect_taxonomy, worklist, remediate
registry/             registry.py + export/*.jsonl        <- registry/
blueprints/           active v1.0 (241) + v1.1 drafts (148)  15M + 11M
canonical_lookups/    IRS MeF canonical names              3.1M
docs/
```

## Slices (one PR each, dev -> main)
| # | contents | lines | verification |
|---|---|---|---|
| 1 | `petey/extract.py`, `semantic_types.py`, `bpt_version.py`; venv | ~1k | re-extract a `widget-mapper/runs/*/case_00N` and match `extract_native.json` |
| 2 | `registry/` + `blueprints/` + `canonical_lookups/`; `petey/bpt.py` | ~2k + data | `registry.py lint` passes against petey-2 paths; every bpt parses |
| 3 | `locate/`: AcroForm enumeration (from `auto_label.py`), `detect.py` + `widget_v1.onnx` (105M, out of band), `vlm_locate.py`, adapter over `step2flat.pipeline` | ~1k | all four sources emit the same schema on one fillable and one flat form |
| 4 | `name/`: `retrieve.py` + `_vocab.py` + MiniLM, `name_sources.py`, `publisher_name.py`, the LLM call from `auto_label.py` with `auto_label_local.py`'s swap seam, `vision_label.py`, `vlm_label.py`, `canonical_lookup.py` | ~3.5k | re-label one form, diff against its committed v1.1 bpt |
| 5 | `synth/` + `validate/` + `run_all.py` driver; `local_pseudo_bpt.py` swap seam | ~4k | reproduce one `summary.json` from `widget-mapper/runs` |
| 6 | manual labeler UI (`label_server.py/html`) as the human gate | ~0.5k | opens, loads a widget map |

## Left behind (with reason)
- `petey/` package (LLM extraction, 10 providers, 8k lines): the model-free path replaces it. The parser registry
  and `extract_direct.py` come back later as the *dev-tool* LLM arm, thin.
- `petey-eval/scripts/generate_form*.py` (40 files): Faker-era generators, retired 2026-07-01.
- `train_dpo.py`, `train_sft.py`, `build_dpo_corpus.py`, `build_pinwheel_corpus.py`: negative result, do not retry.
- `tile_and_ocr*.py`, `panel.py`, `render_page_html.py` (OCR substrate for LLM-in-the-loop labeling): superseded by
  grid-first step2flat for localization. Revisit only if a naming source needs it.
- `eval_llm_ceiling*`, `*_sweep.py`, `bench_tile_sizes.py`, survey scripts: one-off measurements; their findings are in
  the handoff docs.
- petey-web, petey-site, gtm, reddit-miner, benchmarks (out of band), `_archive.zip`.

## Data handling
- `sensible-configuration-library` (326M): upstream MIT repo. Git submodule at a pinned commit, not a copy.
- `petey-eval/widget_maps` (36M, 156 files): port the JSON (44 forms), not the PNGs.
- `petey-eval/labeler_runs` (45M) and `widget-mapper/runs` (567M): the VLM artifacts task 2 evaluates. Read in place
  from petey-master; not copied.
- `source_pdfs/` stays at the root, gitignored, as PLAN.md says.

## Open
- The package is named `petey`, shadowing PyPI `petey` 0.5.1. Fine if petey-2 is the successor; say so if not.
- `tesserocr` (tier-3 OCR) is optional in `extract.py`; installed only when a flat-scan case needs it.
