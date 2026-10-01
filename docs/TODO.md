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

## Synthetic data — next workstream (self-contained; pick up here)

**What exists.**

- Blind generator `petey/synth/generate.py`: per page, the model sees the page image with numbered red boxes and an
  inventory of box ids + control types (no names, no export values); returns `{box: value}`; `unblind` maps back to
  AcroForm paths; cached in `runs/_gen_cache/<sha>.json` keyed on blank bytes + model + case key + blind flag.
  Backends: Anthropic plus OpenAI-compatible (OpenAI, Gemini, DeepSeek, Mistral, Fireworks; keys from `.env` or
  `petey-master/.env`; `PROVIDERS` table). Usage logged per call under `runs/_calls/generate/<key>/<model>/`.
  Since 2026-09-30 the inventory groups checkbox-flagged kid fields as radio groups.

- Local generator `petey/synth/local.py` (`--gen-model local`): API-free smoke path; draws values by type/name
  heuristics from the blueprint. The place the value bank goes.

- Filler `petey/synth/render.py`: fills by path; decodes escaped on-states (`#20APT#20`); checkbox-kid groups set
  only the matching kid.

- Working ground truth for the library: `runs/_gen_cache/imported.json` — 134 forms imported from petey-master
  runs, generated NON-blind (the model saw AcroForm field names). All four target forms' cached cases are from
  this set. This week's blind cases live under separate keys (`<form>_gm...`) and are not what the loop uses.

- Harness `eval/generator_models.py` (loop as judge; reports reader agreement on FILLED fields, tokens, dollars).

- Coverage audit (RESULTS.md 2026-09-30): 14-23 distinct cases per target form cover 94-97% of fields; one case
  covers 60-80%; never-filled fields are the legitimately rare ones.

**Findings that shape the design** (RESULTS.md, 2026-09-30 sections).

- Fill count is a prompt knob, not a model trait; the model's signal is precision on the boxes it filled. On that
  Gemini 3.1 Pro / 3.8 Flash >= Sonnet 4.6; gpt-5.5 ties 3.1 Pro at 10x price; gpt-4.1 / DeepSeek v4-pro over-fill
  with ill-formed values; DeepSeek reasoning exhausts the 32k output cap. Default (Sonnet 4.6) unchanged.

- The generator is dev-time: one cached case per form reused by every run; a poor case is baked in until
  regenerated. Product scale is a handful of forms; per-dollar and latency are dev numbers.

- Product inputs are clean digital PDFs; scans and handwriting are out of scope.

**The design (Andrew, 2026-09-30).**

1. Two generators, compared per box: (a) values from the blueprint's typing (the bank, below) and (b) values from
   the publisher metadata / the page itself (blind). A box the two disagree on is a labeler flag. This sits beside
   the extraction comparison the loop already runs.

2. Page-grounded classification, cached per form: the model classifies each box from the page image, blind (SSN,
   city, date, yes/no, money, free text); a value bank supplies the values. Any number of fresh cases then cost
   nothing; one person per case, so header copies of one identifier (the SSN on every 526EZ page) agree. The
   classification is also a blueprint-independent second opinion on every box's semantic type.

3. Value bank: a file of a few dozen names, addresses, phone numbers, SSNs, EINs, dates, amounts, emails; drawn by
   class; consistent within a case. Free-text boxes still take a generated value.

4. Multi-case sets per form (3-5), versioned: fixed within any before/after comparison, refreshed as a batch when
   the generator or its prompt changes. Regenerate the imported non-blind working set blind.

5. Keep "extract a correct value" and "fix a malformed value" as separate problems (a bank of malformed examples is
   a different, later dataset).

**Steps, in order** (1-4 done 2026-09-30 late, see below).

1. Classification pass: add a `--classify` mode to the blind generator (same page image + inventory; output
   `{box: class}`), cache per form beside the values cache; write the class map into the run.

2. Value bank file (`petey/synth/bank.yaml`) and a bank-backed case builder in `synth/local.py` keyed by the class
   map (fallback: blueprint semantic type when no class map exists).

3. Case sets: `runs/_gen_cache` gets a set id per form (`<form>_setN_caseK`); `validate`/`iterate` take `--case-set`;
   scores aggregate over the set.

4. Compare the two generators per box on the target forms (fw9, acord25, i765, vba21526ez, 10-10EZ); disagreement
   -> `unresolved` flag for the reviewer; compare with the reader's flags.

5. Decide the blind generator default (Sonnet 4.6 vs Gemini 3.1 Pro / 3.8 Flash); if more evidence is wanted,
   precision at controlled density (typical vs complete case prompts, 2-3 draws) on ACORD 25 and I-765.

6. Regenerate the library's working set blind with the chosen generator, as set 1 (retires the 134 imported
   non-blind cases).

7. **Regenerate everything from scratch (Andrew, 2026-09-30), in this order:** ground truth first (step 6), then
   relabel the whole library with the current emitter and judge each fresh blueprint against the new case sets
   alongside its old blueprint; a form where the old blueprint wins gets looked at, not overwritten. Order matters:
   relabeling against the old non-blind cases would fit new blueprints to values invented from publisher names.
   Dev-time batch: tens of dollars for both passes at Sonnet 4.6, a fraction on Gemini 3.8 Flash.

## Synthetic data — done 2026-09-30 late (steps 1-4)

- **Classifier** `petey/synth/classify.py`: blind (same annotated page image and id/type inventory as the blind
  generator), closed 40-class vocabulary, per box `{label, class, entity, group}`; cached once per (blank, model,
  prompt version) under `runs/_gen_cache/classify/`. Five forms, 776 boxes, every box classed, no off-vocabulary
  answers. `label` is the caption the model read (null when a box has none of its own: 40 of ACORD 25's 128);
  `group` names the question a set of checkboxes answers (W-9's seven tax-classification boxes as one group).

- **Value bank** `petey/synth/bank.yaml` + `petey/synth/bank.py`: 24 personas (state / ZIP / area code aligned,
  reserved 555-01xx phones), 12 businesses, pools. One persona and one business per entity per case; part runs
  (SSN 3-2-4, EIN 2-7, phone 3-3-4, date month/day/year) filled from one whole; checkbox groups tick at most one;
  free text from the cached blind case when there is one. `--gen-model bank` in validate/iterate; no API.

- **Case sets** (`validate --case-set N [--n-cases K]`, iterate passes through): intact cases keyed
  `<gen-key>_setN_caseK`; bank ground truth frozen on disk per key; manifest `runs/_gen_cache/sets/<form>_setN.json`.
  Over a set `iterate.detect` sums verdicts and counts a shape or class flag once per field; `field_status` takes
  the worst case per field.

- **Class check** `petey/validate/class_check.py`: page class vs blueprint type per field, family-level, three
  tiers (1 captioned contradiction -> detection + reviewer flag `page_class`; 2 blueprint untyped, page offers a
  type -> suggestion; 3 uncaptioned -> a guess on both sides). A scoring step (Andrew: not case generation), run
  for any generator whose form has a cached classification, on fresh runs and rescores; `class_disagreements.json`
  per case. Generation reads nothing from the blueprint: the blueprint-typed fallback class map is gone. Found: I-765 `attorney_state_bar_num` typed state_abbr, `employer_everify_company_id`
  typed business_name; 526EZ's 20+15 `disability_N_nm` typed person_name (the `_nm` slug rule), `va_file_number_2`
  captioned VETERAN'S NAME; ACORD 25's six insurer names typed person_name, seven policy numbers typed free text.

- Set 1 (bank, 3 cases) by path: W-9 23/23, ACORD 25 128/128, I-765 140/140, 526EZ 328/328, zero ground-truth
  defects after the group fix. Anthropic client now has a timeout (one stalled stream held a run for three hours).

## Synthetic data — the geometry change (2026-09-30, late; Andrew)
Case generation takes nothing from the AcroForm layer, including where the boxes are; widgets are touched only
to fill. Done: `petey/synth/boxes.py` (step2flat's finder on the rendered blank, cached), classifier v4 and blind
generator on ids-and-image only, cases keyed by page and rect with marks for options, `render.render_case`
(best-overlap rect to widget, or draw on a flat blank; reports where each value landed), `validate/rect_join.py`
(scorer joins on the landing rects), `validate --bpt` for side-copy blueprints, `eval/finder_vs_widgets.py` as the
debugging yardstick. Set 2 is the rect-keyed set: W-9 23/23, ACORD 25 128/128, I-765 140/140, 10-10EZ 122/122,
526EZ 327/328 mean. Numbers: RESULTS.md "Synthetic cases from the page alone".

- **Finder granularity list** (fix in the finder, not with more fill-time rules): comb cells returned as uneven
  groups (W-9 SSN); one box over stacked line widgets (ACORD address blocks); duplicate boxes over one checkbox;
  526EZ 27D dollars / cents pair; 10-10EZ page-5 date boxes missed; small cells missed on ACORD 25.

- **Blind generator under-fills on the rect prompt** (W-9: 14 of 26 boxes; names null). Prompt knob; turn it
  before the blind generator serves as generator (b) in the per-box comparison.

- **Classifier on instruction pages**: the W-9's five instruction pages cost five calls to say "none" 40 times.
  A page with no finder box above a confidence floor could be skipped.

- **Option grouping disagreements** (526EZ `living_situation_14b`: the page groups two marks the blueprint keeps
  apart) are a class-check row waiting for a tier: the page's grouping vs the blueprint's `widgets`.

- **Vocabulary**: still the closed 40 names plus `option` / `none`; Andrew's question on open vs closed is open.
  Keeping a free-text `reading` beside the class is the cheap middle.

## Synthetic data — what is left (steps 4b, 5, 6, 7)

- **Inventory cross-reference as a scoring step (Andrew, 2026-09-30; before trusting set 2's numbers).** Score the
  case inventory (finder boxes the classifier kept) against the blueprint inventory (fields and option widgets, by
  rect), both directions plus many-to-one, and give every mismatch a taxonomy class (added to
  `defect_taxonomy.py`, no detectors yet): `box_unreached` (field, no case box), `merged_box` (one case box holds
  two or more field rects), `split_box` (several case boxes in one field; benign, `rect_join` concatenates),
  `uncovered_widget` (case box, no field, a widget under it), `unbacked_box` (case box, no field, no widget),
  `option_group_mismatch` (the classifier's `group` and the blueprint's groups partition the boxes differently;
  the 526EZ `living_situation_14b` row above is one). Today `rect_join` returns only the unclaimed boxes; a field no
  box reached is left out of the ground truth and scored as AGREE on empty, which is why 10-10EZ reads 122/122
  while the finder misses seven of its page-5 boxes. Such fields get their own verdict (`not_generated`), stay out
  of agreement, and are reported per form as a coverage count beside the value verdicts. Measured on the five
  forms (`eval/finder_vs_widgets.py` plus an ambiguity pass): 14 widgets with no finder box, 21 finder boxes that
  contain two or more widgets (ACORD 25 address lines, 526EZ date-of-birth parts, 10-10EZ), 93 widgets split across
  several boxes, 442 finder boxes with no widget.

  - **Which box ate which** is resolvable without the widget layer: the blueprint's own field rects inside a merged
    case box name exactly the fields it swallowed, so it works on flat forms too. `boxes.match_rect` scores
    intersection over the smaller area, so containment ties at 1.0 and list order picks the widget; record the
    tie (both candidates) instead of resolving it silently. The repair stays in the finder (split a box at the
    rules printed inside it), per the finder granularity list above.

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

- **Rebinds over the set**: `correct.load_case` reads `case_001` only, so `name_rotation` / `name_slide` edges
  never benefit from the case set. Build edges per case and require them to hold across cases. Code, not a rerun.

- **Donor**: `validate` no longer passes one; the `donor` parameter left in `bank.generate_from_bank` is dead.
  Andrew: prose is a later problem, a value of the right type is enough, so free text stays on the bank's lines.

- **Step 4, second half: class flags against the reader's flags** per field on the five sets, with the reader arm
  (text mode; image on 526EZ). ACORD 25 and I-765 runs are in RESULTS; 526EZ and 10-10EZ still to run (10-10EZ's
  blueprint is a side copy: `validate` needs a `--bpt` override before it can go through the loop).

- **Step 5: blind-generator default** (Sonnet 4.6 vs Gemini 3.1 Pro / 3.8 Flash). Unchanged; the bank now covers
  most boxes, so the blind generator's job narrows to free text and to being generator (b) in the per-box
  comparison. Decide after step 4 says how much the blind values add.

- **Step 6: regenerate the library's working set** as set 1 — bank cases need only a classification per form
  (about 2 cents a page, Sonnet 4.6; the five forms cost $1.80 over three prompt versions). Blind cases per form
  stay optional. Needs Andrew's go-ahead: 134 forms. **Step 7**: relabel the library only after that, judged
  against the new sets.

- **Classifier stability**: the same page classified twice (v2 -> v3 prompt) moved ACORD 25's uncaptioned insured
  block from a two-line slide to the conventional order; measure re-run agreement per box before the class check
  gates anything automatically. Same question as the reader-stability item below.

- **Vocabulary gaps seen**: a split dollars/cents amount reads as `id_part` (526EZ 27D); `unit` vs the blueprint's
  `text` for Apt/Ste/Flr numbers is a tier-1 row that is really a suggestion; `signature` sits in the name family.

- **Untyped fields (tier 2)**: 4 / 21 / 10 / 52 / 11 on the five forms. The page's class is a free semantic type
  for each; an emitter rule could take it when the blueprint has none (page class -> `semantic_type` via
  `SEMANTIC_TO_CLASS` inverted), keeping the blueprint's own typing where it exists.

- **Entities**: the classifier's `entity` slugs (applicant / spouse / preparer / insured / producer / certificate
  holder ...) are consistent within a form; not yet used by anything but the bank. A repeated-identifier check
  (the SSN on every 526EZ page) falls out of them for free.

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

- **Value bank + page-grounded classification (Andrew).** Two steps replace blind value generation for most boxes:
  the model classifies each box from the page image, blind (SSN, city, date, yes/no, free text), cached per form;
  a bank of a few dozen names, addresses, phone numbers, SSNs, dates and amounts supplies the values, one person
  per case, so any number of fresh cases cost nothing and header copies of one identifier agree. The model's
  classification is also a blueprint-independent second opinion on every box's semantic type — a free labeler
  check. Free-text boxes still take a generated value. Trust is the same as today's blind generator (it reads the
  page, not the blueprint).

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
