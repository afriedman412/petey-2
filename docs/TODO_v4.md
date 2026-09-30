# TODO v4 (2026-09-30, afternoon)

Supersedes TODO_v3 (kept). v4 adds the value bank, the ink-mark experiment, the reader-mode guards and the multi-case sets from the 2026-09-30 discussion. Priorities are Andrew's; the ordering below is a proposal from the 2026-09-29/30
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
- **Reader stability, measured, not floored.** The loop's judge is the name-based reader, an LLM call; the same
  blueprint and filled PDF gave 40 and 45 detections on two runs (I-765, temperature 0). Andrew: no noise floor;
  find out what is and is not stable and debug it. Step 1: read the same I-765 document five times and record,
  per field, whether the verdict holds or flips. Hypothesis to test: flips concentrate on fields the blueprint
  leaves ambiguous (repeated sections, identical captions), so instability is blueprint signal, not model noise.
  Step 2, depending on what step 1 shows: the judge treats a flipping field as unresolved rather than better or
  worse; a change on a stable field is signal; and the whole-form check (I-765 went 37 -> 51 while every reviewed
  field scored "same") becomes "any stable field got worse -> restore the round", with no threshold.
- **Reviewer: publisher descriptions are not removable.** The description is its own field on the spec (verbatim
  tooltip or XFA caption text, tagged `x_petey_description_source: tooltip | xfa_choices`); names are separate
  slugs the labeler derives with the tooltip as evidence. The reviewer's apply step honours `remove: [description]`
  and any replacement string. Change: when the source tag says publisher, refuse removal and refuse a replacement
  that drops the publisher text; allow appending. Tell the prompt the same.
- **Flat forms: write the plan** (`docs/FLAT_PLAN_v1.md`) after Andrew's pass over `runs/flat_review/eleven.html`
  and the overnight survey / recall. Its own set of problems: shape detection (thin circles), the grouping join
  (boxes + the captions the reader already reads), geometry confidence, flat-page fill and anchored ground truth
  so a flat form can go through the loop at all. Not part of the AcroForm work above.

## Next
- **Value bank for the local generator (Andrew).** A file of a few dozen names, addresses, phone numbers, SSNs,
  dates, amounts; the local generator draws by the blueprint's semantic type, keeps one person's details consistent
  across a case, and builds cases with no model call. Limit: it trusts the blueprint's typing, so it cannot catch a
  mistyped box the way the blind generator (which reads the page) can. Cheap cases for the loop and tests; the blind
  VLM stays the source of leak-free ground truth.
- **Ink-mark detection — its own experiment before it becomes the reader's eyes (Andrew).** Draw marks into a
  blank's option boxes: shape (check, X, dot, filled square, tick), size as a fraction of the box, colour (black,
  blue, grey, red), stroke and density (heavy pen to faint pencil), placement offset; pair every variant with
  untouched boxes, thick and thin borders and adjacent printed text for the false-positive side; then the same
  detector on real filled PDFs (AcroForm appearance glyphs: check, circle, cross, square, star). Report precision /
  recall per variant and the ink threshold that holds. Method: pymupdf pixmap of each option box against the
  blank's same crop, numpy dark-pixel count.
- **Reader-mode guards.** Per run, count ground-truth strings present in the filled PDF's text layer; any missing
  -> that page reads in image mode, recorded. Once ink detection passes its experiment: inject detected marks into
  the text-mode document beside the caption so radio states are visible without image tokens.
- **Multi-case sets per form.** Several blind cases per form (3-5), versioned as a set: fixed within any
  before/after comparison, refreshed as a batch when the generator or its prompt changes; regenerate the
  petey-master-imported (non-blind) cases in blind mode. Coverage audit 2026-09-30: 14-23 cases cover 94-97% of a
  form's fields; one case covers 60-80%.
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
- **Flat forms through the loop** (part of FLAT_PLAN_v1). Nothing after the labeler has ever run on a flat form (153 in the corpus,
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
