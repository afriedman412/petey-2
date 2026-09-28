# step2flat: a deterministic flat-form field reader

A non-VLM path to **generating .bpt blueprints** for PDF forms. Given a flat (or fillable) form, it proposes entry
fields (page, rect, kind) with a confidence score and the reasons behind it. Extraction still runs off the .bpt; this
code only helps build blueprints, and low-confidence fields are candidates for the synthetic-fill validation loop.

Everything is programmatic: no trained model, no VLM. Each decision is a named rule with a structural reason.

## Quick start
```
pip install -r requirements.txt          # also needs the tesseract binary
python -m step2flat.pipeline form.pdf -o fields.json --keep-all
python eval/evaluate.py path/to/fillable_pdfs --tag mybatch   # score against widget ground truth
```

## How it works
1. **Flatten like a printer**: bake widget appearances into the page, then strip widgets.
   Guideline: anything visible on a real printed form is fair input.
2. **Two readers, union of candidates**
   - `frozen_reader.py`: the original raster reader (boxes, cells, combs, underlines). Frozen; hash in `FROZEN_SHA256`.
   - `lattice.py`: grid-first structure recovery. Recover the form's lattice from vector rules, close open edges
     with virtual lines (only from long rules, never through printed text), treat contrasting fills as structure
     (including white boxes cut out of a tinted panel), group runs of character boxes, enforce writable sizes,
     then take the entry area within each cell from the label's position.
3. **Programmatic confidence** (`confidence.py`): tier by cue type plus named adjustments (text-filled, blocked
   gray, header, height matches the form's dominant heights, underline outside the lattice = genuine outlier).
   Overlaps are resolved by confidence. Every constant is a knob with a reason; see the module.

## Results (R50 / P50: recall and precision at IoU 0.5 against widget ground truth)
| set | frozen reader | pipeline v2 |
|---|---|---|
| test: 9 untouched US state tax forms, scored once | 0.66 / 0.63 | **0.77 / 0.60** |
| development (28 forms) | 0.55 / 0.56 | 0.73 / 0.61 |
| fresh (8 forms, partly used for diagnosis) | 0.79 / 0.79 | 0.82 / 0.79 |

The recall gain generalizes; precision does not yet. See `docs/RESULTS.md`.

## Repo layout
- `step2flat/`: the pipeline (`pipeline.py` is the entry point).
- `harness/`: sealing widget GT, flattening, scoring (`blind_run.py`, `score.py`, `failmap.py`).
- `eval/`: end-to-end evaluation on fillable PDFs.
- `candidates/`: experiments not in the pipeline (e.g. `reader_v8_boxguard.py`).
- `docs/`: conventions, error taxonomy, results, decision log.

## Evaluation protocol
Test forms are scored once, before any diagnosis. Anything diagnosed from them moves them into development, and the
next batch becomes the test set. Changes are single, named, and justified by structure, not by a score.

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
