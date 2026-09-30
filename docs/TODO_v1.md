# TODO v1 (2026-09-29)

Priorities set by Andrew on 2026-09-29. Numbers and context for each item are in `docs/RESULTS.md`
and `petey/validate/defect_taxonomy.py`.

## Now
- Bake the loop's deterministic repairs into the generator (retype + descriptions at emit).
- Registry ingestion in the generator: identify the blank, resolve or register the form, name the
  blueprint by form id, record edition and OMB, link the blueprint as an artifact.

## Next — under discussion
- **Naming without Claude.** Today names come from the Claude labeler (tooltip, then AcroForm/XFA path,
  then printed words, all as evidence in one prompt) or are placeholders. Build the ranking wrapper
  (STRATEGY_v1 §5 step 2) so publisher evidence names fields on its own where it can, and the model only
  handles the rest; decide which model that is.
- **LLM as the loop's repair tier.** Deterministic detectors say where to look; a model proposes the
  corrected field spec from an evidence bundle; the loop re-validates and reverts fixes that do not reduce
  detections; recurring accepted repairs get promoted to rules. Replaces growing the taxonomy by hand.
- **Relabel test of the new emitter.** No blueprint has gone through the LLM labeler with the new
  emitter yet. Relabel ~5 forms (526EZ, 10-10EZ, one IRS, one ACORD, one immigration) and compare
  against the retyped originals through the loop.
- **Analyse the finished meaning-arm run** on the final blueprints (`runs/meaning_arm_final.json`)
  against the 589-candidate baseline.
- **Recheck the local-generator fixes** (dates change format instead of truncating; radio members get
  their on-state; categories draw real widget states) on the forms that left residue.

## Medium — wanted for launch
- **Non-blueprint documents with standard content and bespoke layouts:** medical intake forms, bank
  statements. Many examples in the Digital Corpora set. No fixed field geometry to register; needs a
  different route than per-form blueprints.

## Open taxonomy gaps (no in-place fix yet)
- `repeated_section_ambiguity` — names must carry the copy / row (veteran vs claimant, table rows).
- `nonnumeric_in_numeric_field` — rate columns printing "Free" / "Various".
- `short_shape_on_wide_box` — fixed in place, but `semantic_types` token matching still produces it
  (`_state` inside `city_state_zip`); needs a compound-name guard.

## Later
- Registry lifecycle states (planned -> located -> named -> validated -> active) and the review list
  (STRATEGY_v1 §5 step 5). Ingestion now moves planned -> in_progress.
- Geometry confidence (`x_petey_geometry.confidence`, step2flat only): calibrate against the flat/fillable
  twins, then use it to order review and to decide which rects flat-page fill trusts.
- Anchored ground truth + flat-page fill renderer (STRATEGY_v1 §5 step 4).

## Low
- **Text-layer refusal.** Pages that have widgets but no text layer have their widgets dropped (all such
  pages -> the form is refused), because the labeler names from page words. Rare: 2 of 512 widgeted pages
  in the corpus. Also fires under `--no-llm`, where no text is needed. Fix: OCR or VLM fallback.
- **Filled values missing from the text layer** on 21-526EZ, MA Form 1, VA 760: a text-layer reader cannot
  see them; image mode can. Parked (2026-09-29).
