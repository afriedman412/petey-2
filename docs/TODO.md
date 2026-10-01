# TODO

Edited in place; the history is `git log --follow -- docs/TODO.md`. Priorities are Andrew's; the ordering is a
proposal. Numbers and context: `docs/RESULTS.md`, `petey/validate/defect_taxonomy.py`.

## Done

- Loop repairs baked into the emitter; registry ingestion in the generator.

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

## Synthetic data (self-contained; pick up here)

**Where it stands (2026-09-30, late).** Case generation reads nothing from the AcroForm layer or the blueprint,
not even where the boxes are; widgets are touched only to fill. Set 2 (bank, three cases, rect-keyed) scores by
path W-9 23/23, ACORD 25 128/128, I-765 140/140, 10-10EZ 122/122, 526EZ 327/328 mean (RESULTS "Synthetic cases
from the page alone"); see the cross-reference item below before trusting those numbers. The path-keyed first pass
(set 1) is retired; its numbers and class-check findings are in RESULTS "Page-grounded classification, value bank
and case sets".

- Boxes: `petey/synth/boxes.py` runs step2flat's finder on the rendered blank, so AcroForm and flat blanks share
  one path; cached per blank. `eval/finder_vs_widgets.py` compares the finder to the widget layer, a debugging
  yardstick that feeds nothing.

- Classifier `petey/synth/classify.py` (prompt v4): numbered page image and box ids only; per box `{label, class,
  entity, group}` from a closed vocabulary (38 value classes plus `option` and `none`); cached per blank + finder +
  model + prompt version under `runs/_gen_cache/classify/`.

- Value bank `petey/synth/bank.yaml` + `bank.py`: 24 personas, 12 businesses, pools, `id_kinds`; one persona per
  entity per case; part runs split by cell boundaries; marks for options; free text from the bank's lines (no
  donor). `--gen-model bank`; no API.

- Blind generator `petey/synth/generate.py` on the same footing (ids and image only, cases by rect); its
  full-inventory mode is debugging only.

- Filler `render.render_case` (rect to widget by best overlap, or drawn on a widget-less blank; reports where each
  value landed) and `validate/rect_join.case_to_paths` (fields joined to the landing rects for the scorer).

- Case sets: `validate --case-set N [--n-cases K]`, frozen per key, manifests in `runs/_gen_cache/sets/`;
  `validate --bpt` for side-copy blueprints.

- Class check `petey/validate/class_check.py`: a scoring step for any generator; page class vs blueprint type by
  rect, tiers 1 / 2 / 3; tier 1 reaches the reviewer as `page_class`.

- Taxonomy: six inventory-mismatch classes (`box_unreached`, `merged_box`, `split_box`, `uncovered_widget`,
  `unbacked_box`, `option_group_mismatch`), no detectors yet.

- Legacy: `runs/_gen_cache/imported.json` (134 forms, NON-blind, path-keyed) is still what `--gen-cache-only` runs
  without a set fall back to, until step 6. `--gen-model local` stays as the API-free smoke path; it reads the
  blueprint, so it never judges one. `eval/generator_models.py` compares generators through the loop (reader
  agreement on FILLED fields, tokens, dollars).

**Principles (Andrew, 2026-09-30).**

- Generation takes nothing from the widget layer or the blueprint; the class check and every comparison against
  the blueprint are scoring steps.

- A value of the right type is enough; realistic prose is a later problem. "Extract a correct value" and "fix a
  malformed value" stay separate problems.

- The generator is dev-time: cases are cached and frozen per set, refreshed as a batch when the generator or its
  prompt changes. Product scale is a handful of forms; cost and latency are dev numbers. Inputs are clean digital
  PDFs.

**Open.**

- **Inventory cross-reference as a scoring step (Andrew, 2026-09-30; before trusting set 2's numbers).** Score the
  case inventory (finder boxes the classifier kept) against the blueprint inventory (fields and option widgets, by
  rect), both directions plus many-to-one, and give every mismatch its taxonomy class: `box_unreached` (field, no
  case box), `merged_box` (one case box holds two or more field rects), `split_box` (several case boxes in one
  field; benign, `rect_join` concatenates), `uncovered_widget` (case box, no field, a widget under it),
  `unbacked_box` (case box, no field, no widget), `option_group_mismatch` (the classifier's `group` and the
  blueprint's groups partition the boxes differently; 526EZ `living_situation_14b` is one). Today `rect_join`
  returns only the unclaimed boxes; a field no box reached is left out of the ground truth and scored as AGREE on
  empty, which is why 10-10EZ reads 122/122 while the finder misses seven of its page-5 boxes. Such fields get
  their own verdict (`not_generated`), stay out of agreement, and are reported per form as a coverage count beside
  the value verdicts. Measured on the five forms (`eval/finder_vs_widgets.py` plus an ambiguity pass): 14 widgets
  with no finder box, 21 finder boxes that contain two or more widgets (ACORD 25 address lines, 526EZ
  date-of-birth parts, 10-10EZ), 93 widgets split across several boxes, 442 finder boxes with no widget.

  - **Which box ate which** is resolvable without the widget layer: the blueprint's own field rects inside a merged
    case box name exactly the fields it swallowed, so it works on flat forms too. `boxes.match_rect` scores
    intersection over the smaller area, so containment ties at 1.0 and list order picks the widget; record the
    tie (both candidates) instead of resolving it silently. The repair stays in the finder (next item).

  - **Attribution**: on an AcroForm the widget layer is the third reference that says whether the finder or the
    labeler is wrong (a diagnosis after the case is made, never an input to it); on a flat form the mismatch is a
    flag for review.

  - **Option groups: metadata after agreement (Andrew, 2026-09-30).** Membership is settled by the page (the
    classifier's `group`) and the blueprint (`widgets`) agreeing on the same member boxes; only then may the
    metadata (shared radio path, on-states) drive the mechanics: one mark per radio path at fill time, which
    on-state to write, marks to field value at scoring. Three-way rule: page, blueprint and metadata agree ->
    confirmed, metadata drives; page and blueprint agree, metadata silent (I-765 marital status and unit type,
    a distinct path per box) -> confirmed, the page drives; page and blueprint disagree (526EZ
    `living_situation_14b`) -> `option_group_mismatch`, and the metadata only attributes it (a page group across
    several radio paths is a publisher split; a blueprint field across several page groups is a labeler merge).
    Never take option MEANING from the metadata: captions and option identity come from the page, because export
    words can contradict the printed captions (`export_caption_mismatch`: I-765's "Apt." box exports `FLR`).

- **Finder granularity** (fix in the finder, not with more fill-time rules): comb cells returned as uneven groups
  (W-9 SSN); one box over stacked line widgets (ACORD address blocks); duplicate boxes over one checkbox; 526EZ 27D
  dollars / cents pair; 10-10EZ page-5 date boxes missed; small cells missed on ACORD 25.

- **Rebinds over the set**: `correct.load_case` reads `case_001` only, so `name_rotation` / `name_slide` edges
  never benefit from the case set. Build edges per case and require them to hold across cases. Code, not a rerun.

- **Step 4, second half: class flags against the reader's flags** per field on set 2, with the reader arm (text
  mode; image on 526EZ). W-9, ACORD 25 and I-765 were run on the retired set 1 (disjoint flag sets on ACORD 25,
  one overlap on I-765); rerun on set 2, and add 526EZ and 10-10EZ (`iterate` still needs to pass `--bpt`
  through).

- **Step 5: blind-generator default** (Sonnet 4.6 vs Gemini 3.1 Pro / 3.8 Flash). The bank covers most boxes, so
  the blind generator's job narrows to being generator (b) in the per-box comparison; decide after step 4 says
  how much the blind values add. Part of it: the blind generator under-fills on the rect prompt (W-9: 14 of 26
  fillable boxes, the name boxes null; one draw, not diagnosed; likely the "null for a rectangle that is not a
  fillable box" line meeting captions printed above the box). One draw per form on the five forms (about $1) to
  tell the W-9 from the prompt, then fix the prompt text, then the controlled-density comparison on the rect
  prompt (typical vs complete case prompts, 2-3 draws, ACORD 25 and I-765). Until then the bank is the only generator the loop judges with.

- **Step 6: regenerate the library's working set** as a bank set (a classification per form, about 2 cents a
  page at Sonnet 4.6), retiring the 134 imported non-blind cases. Needs Andrew's go-ahead. **Step 7**, after it:
  relabel the whole library with the current emitter and judge each fresh blueprint against the new sets beside
  its old blueprint; a form where the old blueprint wins gets looked at, not overwritten. Order matters:
  relabeling against the old non-blind cases would fit new blueprints to values invented from publisher names.

- **Classifier stability**: the same page classified twice (v2 -> v3 prompt) moved ACORD 25's uncaptioned insured
  block from a two-line slide to the conventional order; measure re-run agreement per box before the class check
  gates anything automatically. Same question as the reader-stability item below.

- **Vocabulary.** Position: keep it closed (the bank needs keys with values behind them; two runs of one form must
  name a box the same way) and add a free-text `reading` beside the class (one prompt line, the model's own words
  for the box), used as evidence in the reviewer bundle and the class-check rows, never as a key. Identifiers stay
  one class (`other_id`) with `id_kinds` picking the shape. Andrew decides; the cost is one prompt version. Gaps
  seen: a split dollars / cents amount reads as `id_part` (526EZ 27D); `unit` vs the blueprint's `text` for Apt /
  Ste / Flr numbers is a tier-1 row that is really a suggestion; `signature` sits in the name family.

- **Untyped fields (tier 2)**: 4 / 21 / 10 / 52 / 11 on the five forms. The page's class is a free semantic type
  for each; an emitter rule could take it when the blueprint has none (page class -> `semantic_type` via
  `SEMANTIC_TO_CLASS` inverted), keeping the blueprint's own typing where it exists.

- **Entities**: the classifier's `entity` slugs are consistent within a form; only the bank uses them. A
  repeated-identifier check (the SSN on every 526EZ page) falls out of them for free.

- Decided, no action: the classifier spends calls on instruction pages (the W-9's five pages say "none" 40 times).
  Accepted as dev-time cost; skipping low-confidence pages would also skip a signature page. Revisit only if step
  6's bill says otherwise.

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

- **Reviewer on the class flags.** The reviewer now receives `page_class` flags with the caption the model read.
  Run one review round on I-765 and 526EZ with set 1 and judge as usual; the disability-name and bar-number rows
  are the test cases.

- **Ink-mark detection — its own experiment before it becomes the reader's eyes (Andrew).** Draw marks into a
  blank's option boxes: shape (check, X, dot, filled square, tick), size as a fraction of the box, colour (black,
  blue, grey, red), stroke and density (heavy pen to faint pencil), placement offset; pair every variant with
  untouched boxes, thick and thin borders and adjacent printed text for the false-positive side; then the same
  detector on real filled PDFs (AcroForm appearance glyphs: check, circle, cross, square, star). Report precision /
  recall per variant and the ink threshold that holds. Andrew is picking pages with varied box styles and,
  if available, hand-marked scans for the uncontrolled half. Method: pymupdf pixmap of each option box against the
  blank's same crop, numpy dark-pixel count.

- **Reader-mode guards.** Per run, count ground-truth strings present in the filled PDF's text layer; any missing
  -> that page reads in image mode, recorded. Once ink detection passes its experiment: inject detected marks into
  the text-mode document beside the caption so radio states are visible without image tokens.

- **Multi-case sets per form**: done as case sets (set 2, bank, three cases, five forms). Still open from this
  item: 3-5 cases rather than 3, and the blind regeneration of the imported non-blind cases (step 6).

- **Route the emitter's blind spots to the validator.** Emitter-declared unknowns (uncaptioned option, page-text
  caption, ungroupable run) -> an `unresolved` detector with classes `uncaptioned_option`, `ungrouped_options`,
  `group_name_mismatch` (deterministic: `amended_return_ind` over Medicare / Medicaid / ...) -> per-option reviewer
  evidence (every option's on-state, caption, nearby text, a page crop) -> image-mode reading for pages that carry
  option groups, the only judge that sees a radio state.

- **Generator default**: step 5 above; the rect prompt's under-fill is part of it.

- **Reviewer across vendors** — the one slot compared only among Anthropic models.

- **Generator: repeated copies of one identifier** (the SSN on every 526EZ page should hold one value). Done for
  bank cases (one persona per entity); still open for blind cases.

- **Library fixes waiting on a decision:** rename ACORD 25's six phone fields (or replace the blueprint with the
  relabel); add 10-10EZ (`runs/relabel/blueprints/va_form_10_10ez_relabel2.bpt`, 0 contradictions, 0 name defects
  after one review round) as the first new-emitter form; rename CMS-1500's `amended_return_ind` group.

- **Uncaptioned options** (12 left in the library) and the labeler naming options of ordinal-state groups that no
  declaration or page text covers.

- **Registry: per-form option-group fact** (has groups, how many) once Andrew's flat-form checklist exists; today
  the registry records widget_count, fillable, xfa_root and text_layer only.

- **Naming without Claude** (ranking wrapper; `publisher_name.py` covers 38% unwired) and **LLM as the loop's
  repair tier**.

- **Analyse the finished meaning-arm run**; **recheck the local-generator fixes**.

## Medium — wanted for launch

- Non-blueprint documents with standard content and bespoke layouts (medical intake, bank statements) — unchanged.

- **Flat forms through the loop** (part of FLAT_PLAN_v1). Nothing after the labeler has ever run on a flat form (153 in the corpus,
  verdict `no_widgets`; five flat blueprints in the library, never validated). Needs geometry confidence
  calibration, then the flat-page fill renderer and anchored ground truth (STRATEGY_v1 §5 step 4, ~100 lines with
  pymupdf plus a small scorer change). Moved up from Later because the option-group work now needs it to be
  judged on flat forms at all.

## Open taxonomy gaps (no in-place fix yet)

- `repeated_section_ambiguity`, `nonnumeric_in_numeric_field`, `short_shape_on_wide_box`.

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
