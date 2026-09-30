# TODO v7 (2026-09-30, night)

Supersedes TODO_v6 (kept). v7 adds the library regeneration as the closing step of the synthetic-data workstream. v6 added a self-contained **Synthetic data** section (the next workstream, to be picked up in a fresh session) and records the reader wiring. v5 corrected the value-bank item (classification from the page, not the blueprint's typing). v4 added the value bank, the ink-mark experiment, the reader-mode guards and the multi-case sets from the 2026-09-30 discussion. Priorities are Andrew's; the ordering below is a proposal from the 2026-09-29/30
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

**Steps, in order.**
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
