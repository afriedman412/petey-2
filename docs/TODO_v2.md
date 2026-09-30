# TODO v2 (2026-09-30)

Supersedes TODO_v1 (kept). Priorities are Andrew's; the ordering below is a proposal from the 2026-09-29/30
work, for him to reorder. Numbers and context: `docs/RESULTS.md` (relabel test, option groups, model comparisons),
`petey/validate/defect_taxonomy.py`.

## Done since v1
- Loop repairs baked into the emitter; registry ingestion in the generator (v1 "Now").
- Relabel test of the new emitter (five forms): the emitter matches or beats the retyped blueprints; ACORD 25's six
  "phone" fields are misnamed state/ZIP boxes (still misnamed in the library).
- Reviewer follow-ups: I-765 rerun; Sonnet 5 / Haiku 4.5 compared as reviewer and reader.
- Option groups: one field per radio / checkbox-kid group with per-option widgets keyed by on-state (box, on-state,
  caption); library migrated (43 forms, 376 groups); captions from XFA, on-state text, or the printed text beside
  the box; XFA captions refused from shape-fallback joins; filler fixed for checkbox-flagged groups.
- Model comparisons through the loop, first passes: generator (7 models, 5 forms) and labeler (6 models, 3 forms).
  Generator: fill count is a prompt knob; on precision of filled boxes Gemini 3.1 Pro / 3.8 Flash >= Sonnet 4.6;
  gpt-4.1 and DeepSeek v4-pro over-fill; DeepSeek reasoning exhausts output caps. Labeler: a wash among the top
  four. Defaults unchanged. The generator runs once per new form and is cached; it is never on the extraction path.

## Now
- **Judge: whole-form guard.** The per-field judgment scored every reviewed field "same" while the form went from
  37 to 51 detections (Haiku stripped 25 descriptions on I-765; sixteen other fields collided). Restore the round
  when detections rise past the noise floor.
- **Reviewer: never delete publisher-sourced descriptions** (tooltip, XFA captions). Haiku removed 25 on I-765 and
  10 on 10-10EZ; the emitter's rules put them back a round later.
- **Flat-form option groups — the join.** The frozen reader already finds boxes AND reads OCR / text-layer captions
  beside them; nothing groups them. Aligned same-size runs where each box has a short caption -> one field with a
  `widgets` map (no path); runs without captions are table cells (cuts the over-proposal on form11 / 1073). Inputs:
  Andrew's pass over `runs/flat_review/eleven.html` and the overnight survey / recall (`runs/flat_review/`).
- **Thin circles in the shape detector** (MCS-150: 1 of 9 found). Contour + circularity at higher dpi; not OCR.

## Next
- **Route the emitter's blind spots to the validator.** Emitter-declared unknowns (uncaptioned option, page-text
  caption, ungroupable run) -> an `unresolved` detector with classes `uncaptioned_option`, `ungrouped_options`,
  `group_name_mismatch` (deterministic: `amended_return_ind` over Medicare / Medicaid / ...) -> per-option reviewer
  evidence (every option's on-state, caption, nearby text, a page crop) -> image-mode reading for pages that carry
  option groups, the only judge that sees a radio state.
- **Generator default.** Decide between Sonnet 4.6 (fills most) and Gemini 3.1 Pro / 3.8 Flash (most precise). If
  more evidence is wanted first: precision at controlled density (typical vs complete case prompt variants, two or
  three draws each) on ACORD 25 and I-765; and more than one cached case per form, so the judge is not one draw.
- **Reviewer across vendors** — the one slot compared only among Anthropic models.
- **Generator: repeated copies of one identifier** (the SSN on every 526EZ page should hold one value). Unchanged
  from v1.
- **Library fixes waiting on a decision:** rename ACORD 25's six phone fields (or replace the blueprint with the
  relabel); add 10-10EZ (`runs/relabel/blueprints/va_form_10_10ez_relabel2.bpt`, 0 contradictions, 0 name defects
  after one review round) as the first new-emitter form; rename CMS-1500's `amended_return_ind` group.
- **Uncaptioned options** (12 left in the library) and the labeler naming options of ordinal-state groups that no
  declaration or page text covers.
- **Registry: per-form option-group fact** (has groups, how many) once Andrew's flat-form checklist exists; today
  the registry records widget_count, fillable, xfa_root and text_layer only.
- **Naming without Claude** (ranking wrapper; `publisher_name.py` covers 38% unwired) and **LLM as the loop's
  repair tier** — unchanged from v1.
- **Analyse the finished meaning-arm run**; **recheck the local-generator fixes** — unchanged from v1.

## Medium — wanted for launch
- Non-blueprint documents with standard content and bespoke layouts (medical intake, bank statements) — unchanged.
- **Flat forms through the loop.** Nothing after the labeler has ever run on a flat form (153 in the corpus,
  verdict `no_widgets`; five flat blueprints in the library, never validated). Needs geometry confidence
  calibration, then the flat-page fill renderer and anchored ground truth (STRATEGY_v1 §5 step 4, ~100 lines with
  pymupdf plus a small scorer change). Moved up from Later because the option-group work now needs it to be
  judged on flat forms at all.

## Open taxonomy gaps (no in-place fix yet)
- `repeated_section_ambiguity`, `nonnumeric_in_numeric_field`, `short_shape_on_wide_box` — unchanged from v1.
- `yn_column`: radio groups keyed by export code that a text-mode reader cannot see; image mode or rendering
  checked states into the page text.

## Later
- Registry lifecycle states and the review list (STRATEGY_v1 §5 step 5) — unchanged.

## Low
- Text-layer refusal (OCR / VLM fallback) — unchanged.
- Filled values missing from the text layer on 21-526EZ, MA Form 1, VA 760 — image mode handles it; parked.
- `id_part` semantic type defaults to `^\d{1,5}$`; the emitter's `part_by_maxlen` only narrows when the widget
  carries MaxLen, the retype pass also used box length.
- Registry column for option groups (see Next) and the DeepSeek thinking switch (would need reasoning off or
  capped before those models can be compared fairly).
