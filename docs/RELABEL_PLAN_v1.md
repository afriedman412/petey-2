# Relabel test plan v1 (2026-09-29)

**Question.** Does the generator as it now stands (XFA declarations, part types, box-geometry rules at emit,
tooltips and captions as descriptions, mutex rules, registry ingestion) produce better blueprints than the
committed, retyped ones? Every committed blueprint was labeled by the old emitter; the new one has only ever
run with placeholder names, where most of its rules have nothing to act on.

**Yardstick.** The loop (`petey.validate.iterate`): shape contradictions, name-based reader agreement, real name
defects, reviewer flags. Same PDF, same cached ground truth for both versions, so the blueprint is the only variable.

## Forms (five, one per family; small first)

| form id (committed) | blank | why |
|---|---|---|
| `fw9` | `source_pdfs/tax/fw9.pdf` | one page, cheapest; IRS |
| `acord25` | `source_pdfs/acord25_blank.pdf` | one page, 128 fields; came out clean under review |
| `i765` | `source_pdfs/immigration/i-765.pdf` | XFA hybrid, 7 pages; the hard reference form |
| `vba21526ez` | `source_pdfs/vba-21-526ez-are.pdf` | XFA hybrid, 15 pages, 328 fields; 35 date parts, radio captions |
| `va_form_10_10ez` | `source_pdfs/VA Form 10-10EZ.pdf` | **no blueprint yet**; XFA with 123 pictures, 30 validate rules |

## Steps per form

Check `git status` first (an interrupted multi-step command leaves its early steps applied).

1. **Relabel into a side copy.** The side id keeps the library and the registry untouched.
   ```
   venv/bin/python -m petey.label.auto_label --blank <blank> --name <form>_relabel \
       --output blueprints/<form>_relabel.bpt --no-register --no-retrieval
   ```
   Default labeler model is `claude-sonnet-4-6` (auto_label `MODEL`). Note in the results which model labeled.
   The emitter prints `[emit] loop rules applied at emit: {...}` — record it; this is the first time those rules
   see real names. `petey/label/call_log.py` records each labeler call's usage: sum input/output tokens per form
   for the naming-cost row (the one estimated, never measured, in RESULTS.md).
2. **Baseline the relabel through the loop, no review.** `--gen-key <form>` reuses the original's cached
   ground truth (cache key = pdf bytes + model + `<gen_key>_intact_001`), so both versions are scored against
   identical values. Reader: `petey:pymupdf`, except 526EZ which needs `petey:image` (values missing from its
   text layer).
   ```
   venv/bin/python -u -m petey.validate.iterate --form <form>_relabel --gen-model claude-sonnet-4-6 \
       --gen-cache-only --gen-key <form> --methods native,petey:pymupdf --n-flat 0 --max-iter 2 \
       --out runs/relabel/iterate_<form>_relabel.json
   ```
   10-10EZ has no cached ground truth: drop `--gen-cache-only` for it (one blind generation, ~30 cents) and
   use `--gen-key va_form_10_10ez` so later runs hit the cache.
3. **Same loop on the committed version** (skip if a recent run exists under `runs/<form>_2026*` with
   `score_petey*.json`): `--form <form>`, same flags, `--out runs/relabel/iterate_<form>_committed.json`.
4. **One review round on the relabel** with the cheap reviewer:
   add `--review flagged --review-model claude-haiku-4-5` to the step-2 command; `--max-iter 4`.
5. **Compare names** (informational): token overlap between relabeled and committed names joined by widget
   path — `eval/xfa_declared.py --emitted blueprints/<form>_relabel.bpt --committed blueprints/<form>.bpt`
   joins by path and reports patterns/types; extend or script the name overlap alongside.

## What to record (one table, RESULTS.md)

Per form, committed vs relabel: fields; `x_petey_emit_fixes` (relabel only); shape contradictions; reader agree;
name defects; reviewer flags and outcome (better / worse / restored); labeling tokens and dollars; wall-clock.
Plus the 10-10EZ row alone (no committed version): does a fresh XFA form come out clean?

## Success criteria

- Relabel has no more shape contradictions than the retyped original and no fewer reader agreements, within the
  judge's noise floor (~5 fields on a 140-field form; run twice if it is close).
- The emit-time rules fire on real names (nonzero `x_petey_emit_fixes` where the original needed retype).
- Naming cost measured per page; compare with the 15¢ (Opus) / 6¢ (Sonnet 5) / 9¢ (Sonnet 4.6) estimates.
- No regression class appears that the taxonomy lacks; if one does, register it (`defect_taxonomy.py`).

## Cost and time

Labeling ~30 pages across the five forms at Sonnet 4.6: roughly $3. Validations and reviews: $1-2. Under $6.
Wall-clock ~40 minutes, mostly 526EZ. Run with `python -u` and background it; do not interrupt mid-command.

## Cleanup

Keep `blueprints/<form>_relabel.bpt` only until the numbers are recorded, then move them to `runs/relabel/`
(the library and `run_all`'s target set glob `blueprints/*.bpt`). Nothing was registered (`--no-register`).

## Decisions this feeds

- Whether new forms should be generated with the current labeler as is, or wait for the naming wrapper
  (publisher names first, model for the rest — `petey/validate/publisher_name.py` covers 38% unwired).
- The default labeler model (Sonnet 4.6 today; Sonnet 5 / Haiku untested for naming).
- Whether 10-10EZ's blueprint goes into the library as the first fully new-emitter form.
