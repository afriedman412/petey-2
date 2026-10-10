# Petey

Petey extracts data from filled PDF forms: tax, DMV, immigration, insurance, court and other standardized forms. For
each form it keeps a **blueprint** (`.bpt`, YAML; spec in `BPT SPEC v1.1.md`) that gives every field's location,
name, type and validation. Once a form has a blueprint, any filled copy of it can be read with no model at all.

This repo is the rebuild of Petey (the successor to the `petey` package, 0.5.1 on PyPI). It holds the extractor,
the code that builds and checks blueprints, and the blueprint library. The aim is to run fully offline; extraction
already does, and building blueprints still uses API models in places (see [Models](#models)).

## How it works

```
blank form ──► label ──► check & repair ──► review ──► blueprint (.bpt) ──► extract (offline, any filled copy)
```

1. **Locate** the fields (`petey/locate/`): from the AcroForm widgets on a fillable form, from a fillable twin of
   the same form, or from the page itself on a flat form (`step2flat/`, below).

2. **Label** (`petey/label/auto_label.py`): a model names and types every field from the text around it. Declared
   publisher data comes first: XFA captions, pictures and choice lists (`label/xfa.py`), tooltips, dropdown
   lists. Option groups (radio buttons, checkbox sets) become one field with a caption per option.

3. **Check and repair** (`petey/validate/`): the loop fills the blank with synthetic values, extracts them, scores
   the result, applies rule fixes, sends the rest to an LLM reviewer and an adjudicator, and repeats until stable
   (`form_run.py`, `iterate.py`). Independent **witnesses** (`witness.py`) say whether each field's name is
   supported: the publisher's tooltip, the printed text at the box, a vision classifier, the read-back, and a
   whole-page vision check (`page_check.py`).

4. **Review** (`blueprint_review.py`): a web page that draws every field on the page, sorts fields by how
   contested they are, and takes accept / flag / edit, regrouping of options, and adding or removing fields.
   Suggested fixes (a caption, a type, a pattern) apply with one click.

5. **Extract** (`petey/extract.py`): per field, the AcroForm value if the form layer survives, else the text
   clipped to the field's box, else ink in an option box, else zonal OCR (Tesseract).

### Name and caption checks

Two checks catch the most common blueprint errors, names slid one box over and captions taken from a neighbour:

- **Names** (`witness.py`): a field is questioned when its tooltip describes a nearby field better than itself
  (a swap, a one-row slip), or does not describe its name at all. Only near fields in the same section count,
  texts several fields share are ignored, and a flag counts only when the tooltip agrees with the text printed at
  the box. Word overlap and a local model (`label/text_match.py`) both judge; either one's flag counts.

- **Captions** (`label/caption_choice.py`): for each checkbox or radio option, the text printed around its box is
  scored against what the option means, and the best caption is offered on the review page. Captions the XFA
  declares or a person wrote are never replaced.

## Quick start

```
make venv && make hooks                       # Python 3.12 venv + the pre-push guard (see Branching)
                                              # also needs the tesseract binary for OCR and the flat-form finder

# extract a filled form
PYTHONPATH=. venv/bin/python -m petey.extract --blueprint blueprints/fw9.bpt --pdf filled.pdf --output values.json

# build or rebuild one form's blueprint: label, page check, loop; writes runs/judge_eval/blueprints/<form>.bpt
scripts/run_form.sh <form> <blank path under source_pdfs/>

# review blueprints in the browser (http://127.0.0.1:5005)
PYTHONPATH=. venv/bin/python -m petey.validate.blueprint_review

# witnesses for one blueprint, and their calibration against hand review
PYTHONPATH=. venv/bin/python -m petey.validate.witness blueprints/acord25.bpt --show
PYTHONPATH=. venv/bin/python -m petey.validate.witness --calibrate
```

API keys go in `.env` (never committed). Long batches run on a GCP VM: `docs/RUNNER.md`.

## Models

| step | model | where it runs |
|---|---|---|
| labeler, page check (round 0) | Gemini 3.8 Flash | API |
| loop reviewer, page check (loop) | Claude Opus 5 | API |
| page classifier, reader, adjudicator | Claude Sonnet 4.6 | API |
| name and caption matching (`label/text_match.py`) | MiniLM-L6 cross-encoder, fine-tuned | local (onnxruntime) |
| extraction | none | local |

The text-match weights live in `models/text_match/`, which is gitignored. Without them the checks fall back to word
overlap alone, so a fresh clone or the runner behaves as before until the model is copied in or retrained.
Retraining runs in a separate PyTorch venv and takes about 13 minutes on an M1:

```
PYTHONPATH=. venv/bin/python eval/text_match_data.py                      # pairs from blueprints + blanks
<training venv>/bin/python eval/text_match_train.py --epochs 1 --batch 128 # train, export ONNX
PYTHONPATH=. venv/bin/python eval/text_match_eval.py                      # held-out forms (and Jev, if keyed)
```

`PETEY_TEXT_MATCH=0` turns the model off. `PETEY_TEXT_MATCH_INT8=1` uses the int8 copy the training script also
writes: 2.3x faster, for long dev runs, but it shifts a few decisions at the "does not describe" cutoff, so it is not
the default.

## step2flat: fields on a flat form

A deterministic reader for forms with no form layer (`step2flat/`): it proposes entry fields (page, rect, kind)
with a confidence and the reasons behind it. Two readers feed it, a frozen raster reader and `lattice.py`, which
recovers the form's grid from its vector rules. No model; every decision is a named rule.

| R50 / P50 against widget ground truth | frozen reader | pipeline v2 |
|---|---|---|
| test: 9 untouched US state tax forms, scored once | 0.66 / 0.63 | **0.77 / 0.60** |
| development (28 forms) | 0.55 / 0.56 | 0.73 / 0.61 |

```
python -m step2flat.pipeline form.pdf -o fields.json --keep-all
python eval/evaluate.py path/to/fillable_pdfs --tag mybatch
```

## Repo layout

- `petey/`: the package. `extract.py` (extraction), `label/` (labeler, XFA, captions, text-match model),
  `locate/` (field geometry), `synth/` (synthetic cases: page classifier, value bank, filling), `validate/`
  (the loop, witnesses, checks, review pages).

- `blueprints/`: the library (153 blueprints). Fresh runs land in `runs/judge_eval/blueprints/` until promoted.

- `registry/`: form identity (issuer, form number, edition); `canonical_lookups/`: IRS MeF field names.

- `step2flat/`, `harness/`: the flat-form reader and its scoring harness.

- `eval/`: measurements, each a script with its result in `docs/RESULTS.md`.

- `scripts/`: running forms (`run_form.sh`), the GCP runner, syncing blanks and review records.

- `docs/`: start with `GLOSSARY.md` (the project's vocabulary), then the latest `HANDOFF_*.md`, `TODO.md`,
  `STRATEGY_v1.md` and `RESULTS.md`.

- Not in git: `runs/` (results, caches, hand-review records; the review records are backed up on the
  `review-records` branch), `source_pdfs/` (the blanks; `scripts/fetch_blanks.sh`), `models/`.

## Branching
`main` is release state; `dev` is where work lands. Nothing is pushed directly to `main` — it advances only through
a pull request merged on GitHub.

```
make hooks                                  # once per clone: installs the pre-push guard
git checkout dev && git push origin dev     # work lands here
gh pr create --base main --head dev         # then merge the PR on GitHub
git checkout main && git pull               # bring the merge back down
```

The guard is `.githooks/pre-push`, activated by `make hooks` setting `core.hooksPath`. It is not automatic on a
fresh clone, so run `make hooks` after cloning. To override it in an emergency:
`PETEY_ALLOW_MAIN_PUSH=1 git push origin main`.

GitHub-side branch protection would be the stronger guard, but it needs GitHub Pro on a private repo.
