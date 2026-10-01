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

**What exists (2026-09-30, late; after the geometry change).**

- Boxes from the page: `petey/synth/boxes.py` runs step2flat's finder on the rendered blank (widgets baked in,
  then stripped), so AcroForm and flat blanks share one path; `{id, page, rect, kind}`, cached per blank. Nothing
  from the widget layer reaches generation, not even box positions (Andrew). `eval/finder_vs_widgets.py` compares
  the finder to the widget layer per form; a debugging yardstick that feeds nothing.

- Classifier `petey/synth/classify.py` (prompt v4): the model sees the numbered page image and the box ids, nothing
  else; per box `{label, class, entity, group}` from a closed vocabulary (38 value classes plus `option` and
  `none`); cached per blank + finder + model + prompt version under `runs/_gen_cache/classify/`. Five forms, 1,228
  boxes, no off-vocabulary answer.

- Value bank `petey/synth/bank.yaml` + `bank.py`: 24 personas, 12 businesses, pools, `id_kinds` (caption keyword
  -> identifier shape, one YAML line per kind). Cases keyed by page and rect, True / False marks for options, one
  persona per entity, part runs split by cell boundaries. `--gen-model bank`; no API.

- Blind generator `petey/synth/generate.py` on the same footing: ids and image only, bools for marks, cases by
  rect; OpenAI-compatible backends unchanged. Its full-inventory mode (widget paths to the model) is debugging only.

- Filler `render.render_case`: rect to widget by best overlap, writes by widget type, draws on a widget-less blank;
  concatenates cells sharing a widget, splits a block across stacked lines, ORs duplicate marks; reports where each
  value landed. `validate/rect_join.case_to_paths` joins blueprint fields to the landing rects for the scorer.

- Case sets: `validate --case-set N [--n-cases K]` (iterate passes through), frozen per key under
  `runs/_gen_cache`, manifest in `runs/_gen_cache/sets/`. Set 2 is the rect-keyed set (set 1, path-keyed, is
  retired). `validate --bpt` runs a side-copy blueprint (10-10EZ).

- Class check `petey/validate/class_check.py`, a scoring step for any generator: page class vs blueprint type by
  rect, tiers 1 / 2 / 3; tier 1 reaches the reviewer as `page_class`.

- Legacy: `runs/_gen_cache/imported.json`, 134 forms generated NON-blind from petey-master (the model saw field
  names); path-keyed; still what `--gen-cache-only` runs without a set fall back to. Retired by step 6.
  `petey/synth/local.py` (`--gen-model local`, blueprint-typed values) stays as the API-free smoke path for a form
  with no classification yet; it reads the blueprint and is not a generator for judging one.

- Harness `eval/generator_models.py` (loop as judge; reader agreement on FILLED fields, tokens, dollars); coverage
  audit: 14-23 distinct cases per target form cover 94-97% of fields.

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

**Steps, in order** (1-4 done 2026-09-30, then rebuilt on page geometry the same night; 5-7 open).

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

## Synthetic data — done 2026-09-30 (steps 1-4, first pass, path-keyed; superseded the same night)

Classifier, bank, case sets and class check were first built keyed by AcroForm path with a widget inventory
(ids, control types, maxlen, choices, radio grouping) going to the model. Set 1 on that footing scored W-9 23/23,
ACORD 25 128/128, I-765 140/140, 526EZ 328/328 by path. The class check found real blueprint faults on that
pass: I-765 `attorney_state_bar_num` typed state_abbr and `employer_everify_company_id` typed business_name;
526EZ's 35 `disability_N_nm` typed person_name (the `_nm` slug rule) and `va_file_number_2` captioned VETERAN'S
NAME; ACORD 25's six insurer names typed person_name and seven policy numbers typed free text. Andrew's
corrections that reshaped it: the class check is a scoring step, not case generation; generation reads nothing
from the blueprint (the blueprint-typed fallback is gone); and the inventory itself was leakage (below). Numbers:
RESULTS.md "Page-grounded classification, value bank and case sets".

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

- **Blind generator under-fills on the rect prompt** (W-9: 14 of 26 fillable boxes; the name boxes came back
  null). Measured after the rebuild, one draw, one form; not diagnosed. Likely cause: the prompt now says "null
  for a rectangle that is not a fillable box", and the W-9's name boxes carry their caption on the line above
  rather than inside, so an uncaptioned box reads as decoration. Position: this is step 5's problem, not a
  separate one. Before touching the prompt, one draw per form on the five forms (about $1) to see whether it is
  the W-9 or the prompt; then the fix is in the prompt text (a box under a caption line is that caption's box),
  and the controlled-density comparison of step 5 runs on the rect prompt. Until then the bank is the only
  generator the loop should judge with.

- **Classifier on instruction pages**: the W-9's five instruction pages cost five calls to say "none" 40 times.
  Position: accept it. It is dev-time cost (ten cents on the W-9; perhaps a third of calls over the library,
  which product scale says is not a decision criterion), and the two ways to avoid it both carry risk: skipping
  pages whose finder boxes are all low-confidence underlines would also skip a signature page; a cheaper model
  for those pages adds a second model to the cache key for a saving of cents. Revisit only if step 6's bill says
  otherwise.

- **Option grouping disagreements** (526EZ `living_situation_14b`: the page groups two marks the blueprint keeps
  apart): folded into Andrew's inventory cross-reference below as `option_group_mismatch`.

- **Vocabulary, reconsidered.** The question is wider than identifiers: every box's class is one of 38 fixed value
  names plus `option` / `none`. Two things the closed list is for, and they hold: the bank needs a key it has
  values behind, and two runs of one form should name a box the same way (the class check and the finder
  diagnostic both depend on that). What the closed list loses is the model's own words for the box, and that
  is already half-kept: `label` carries the caption verbatim. Position: keep the vocabulary closed, and add a
  free-text `reading` beside the class (one prompt line; what the model thinks the box holds in its own words,
  e.g. "insurer's NAIC code"), used as evidence in the reviewer bundle and in the class-check rows, never as a
  key. Identifiers stay one class (`other_id`) with `id_kinds` picking the shape from the caption; a new kind is
  a YAML line, and a kind the bank lacks still gets a plausible generic. Andrew decides; the cost of the middle
  path is one prompt version.

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

- **Donor**: removed from `bank.generate_from_bank` (2026-09-30, late). Andrew: prose is a later problem, a value
  of the right type is enough, so free text stays on the bank's lines.

- **Step 4, second half: class flags against the reader's flags** per field on set 2, with the reader arm (text
  mode; image on 526EZ). W-9, ACORD 25 and I-765 were run on the path-keyed set 1 (RESULTS: disjoint flag sets on
  ACORD 25, one overlap on I-765); rerun on set 2, and add 526EZ and 10-10EZ (`validate --bpt` exists now; `iterate`
  still needs to pass it through).

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
