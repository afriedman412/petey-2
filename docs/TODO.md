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

- Ink-mark detection: robustness experiment passed on Andrew's 12 pages (precision 0.984, recall 0.952 at
  threshold 0.01; RESULTS "Ink-mark detection"). The text reader gets a `[x]` / `[ ]` token at every option box,
  from the widget state with ink as the fallback (RESULTS "Radio and checkbox states in the text reader").

## Synthetic data (self-contained; pick up here)

### Where it stands (2026-09-30, late)

Case generation reads nothing from the AcroForm layer or the blueprint,
not even where the boxes are; widgets are touched only to fill. Set 3 (bank, three cases, rect-keyed, finder v2)
is the current set, read with the `not_generated` verdict so coverage is a number: W-9 21 + 2, ACORD 25 98 + 30,
I-765 138 + 2, 526EZ 324 + 4, 10-10EZ 114 + 8, no disagreements (RESULTS "Finder list re-read, and set 3"). Set 2
was the same keying before the finder tier and the guard fix (RESULTS "Inventory cross-reference"); set 1, the
path-keyed first pass, is retired, its class-check findings in RESULTS "Page-grounded classification, value bank
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

### Principles (Andrew, 2026-09-30)

- Generation takes nothing from the widget layer or the blueprint; the class check and every comparison against
  the blueprint are scoring steps.

- A value of the right type is enough; realistic prose is a later problem. "Extract a correct value" and "fix a
  malformed value" stay separate problems.

- The generator is dev-time: cases are cached and frozen per set, refreshed as a batch when the generator or its
  prompt changes. Product scale is a handful of forms; cost and latency are dev numbers. Inputs are clean digital
  PDFs.

### Open

- **Inventory cross-reference as a scoring step (Andrew, 2026-09-30; before trusting set 2's numbers): done.**
  `petey/validate/inventory_check.py` runs beside the class check and writes `inventory_check.json` per case with
  `box_unreached`, `merged_box`, `split_box`, `uncovered_widget`, `unbacked_box`, `option_group_mismatch` and
  `tie` (two case boxes over one field rect at equal overlap, recorded not resolved). The scorer has the verdict
  `not_generated` for a field no value landed on (`rect_join.unreached_fields`, stored as `case_unreached.json`;
  rescore derives it for older rect runs); it stays out of agreement and is summed over a set. Widget layer read
  only here, after the case exists, for attribution. Set 2 honestly: W-9 21 + 2 not generated of 23; ACORD 25
  93 + 35 of 128; I-765 138 + 2 of 140; 526EZ 320 + 8 of 328; 10-10EZ 114 + 8 of 122. Numbers and per-form
  tables: RESULTS.md "Inventory cross-reference". Follow-ups:

  - **Finder list, re-read against the raw candidates (2026-09-30, late).** Less of it is the finder than it
    looked. (a) W-9 combs: the raster pass has the right 3-2-4 and 2-7 groups; the lattice's single cells won the
    overlap at equal confidence. Fixed: `fz:comb` tier 0.60 -> 0.65 (`step2flat/confidence.py`), finder version
    `step2flat-2`. (b) ACORD 25's INSR LTR / ADDL INSD / SUBR WVD cells ARE found at the right granularity (one
    tall cell per coverage section, as printed); the classifier called them `none` or `option` and the geometry
    guard then rejected the tall narrow ones. Fixed: the guard now spares any cell up to 30 pt wide whatever its
    height. (c) ACORD's address blocks and 526EZ's three-part dates and dollars / cents pair are ONE box on the
    page; the lines and parts exist only in the widget layer, so the finder is right and the filler now splits a
    value over the widgets under one box by its natural parts (date -> month / day / year, money -> dollars /
    cents, phone 3-3-4, SSN 3-2-4, else commas), driven by the box's class. (d) 10-10EZ page-5 dates have no box
    on the page at all: "FROM:" and "TO:" with whitespace, the widget invisible when baked. A new finder class,
    caption-anchored whitespace (caption, then blank run to the next caption or rule); not built; `box_unreached`
    counts it honestly meanwhile. (e) `insr_ltr_2_cd`'s cell read as `none` with caption AUTOMOBILE LIABILITY: a
    classifier miss, left as is. (f) Two filler rules from the set-3 rerun: a text widget is written once (later
    boxes over it report the page's value); the comb-cell join only gathers cells smaller than the widget.
    (g) Labeler finding: 526EZ `separation_pay_amount_dollars` / `_cents` carry each other's rects; neither the
    class check nor the inventory check can see a swap within one family. Candidate taxonomy class:
    `swapped_rects_same_family`; detector = a by-path differ on two same-family fields whose values are each
    other's.

  - **526EZ option groups**: 14 `option_group_mismatch` rows, none on the other four forms; most are one blueprint
    field over two printed questions (14A/14B, 21A/21B, 24A/24B, 24C/25, 19A/19B): the three-way rule's labeler
    merge. Hand them to the reviewer as the next test case alongside the `page_class` flags.

  - **Ties**: 65 on 526EZ, 13 on I-765, 2 on W-9; all comb cells (several small case boxes fully inside one field
    rect, each at overlap 1.0). Harmless while the filler concatenates; worth watching if a tie ever crosses two
    fields.

  - **Option groups: metadata after agreement (Andrew).** Rule as written stands; `_option_groups` in
    `inventory_check.py` implements the three-way classification with the widget layer as attribution only
    (`one_path` / `several_paths` / `flat_blank_no_metadata`). Not yet used to drive mechanics; the filler still
    marks one box per page group and relies on the widget's own on-state at write time.

- **Rebinds over the set**: done (2026-09-30, late). `correct.analyse_run` builds edges per intact case and keeps
  only those every case draws; `stats["edges_unstable"]` counts the rest. `load_case` stays for one-case callers.

- **Step 4, second half: class flags against the reader's flags** per field on set 3, with the reader arm (text
  mode; image on 526EZ). W-9, ACORD 25 and I-765 were run on the retired set 1 (disjoint flag sets on ACORD 25,
  one overlap on I-765). Code is in place (2026-09-30, late): `iterate --bpt` runs 10-10EZ from its side copy;
  `eval/flags_overlap.py` prints reader / class / option-group flags and their overlaps per run. Left: the runs.

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

- **Reader stability, measured, not floored (Andrew).** The loop's judge is the name-based reader, an LLM call (a
  dev-time judge of the blueprint's names; product extraction is the native path, no LLM). The same blueprint and
  filled PDF once gave 40 and 45 detections (I-765, temperature 0). Andrew: no noise floor; measure what is and is
  not stable and debug it.

  - **Step 1 done (2026-09-30; RESULTS "Reader stability").** `eval/reader_stability.py`, I-765 set 3, three cases
    x five fresh reads (cache bypassed by salt), Sonnet 4.6, $1.55. 125 of 138 fields stable and right, 9 stable
    and wrong, 4 flip on some case, none on every case; detections per read 4-6 / 4 / 7-8. Flips are not scattered:
    three of the four flipping fields are stable-wrong on the other cases and the fourth is the neighbour of a slid
    cell, so a flip marks the borderline case of a systematic fault. The faults: (a) the Part 6 page / part / item
    number rows, where the text layer gives "475 206" under three headers with no sign of which cell is empty, so
    the reader shifts values left (6 of the 9 stable-wrong fields and 2 of the 4 flips); (b) unit type read as the
    printed caption against ground truth from the export word (`export_caption_mismatch`, known); (c)
    `attorney_state_bar_num`, typed state_abbr (a class-check row already) with bank values like 'ACCT450740399';
    (d) the reader filling an empty field from context (place of last arrival 'Richmond'; one unit-type read).
    The numbered-sibling / shared-description proxies are too crude to test the hypothesis (2 / 32 vs 2 / 106).

  - **Three forms, two judges (2026-09-30; RESULTS "Three forms, two judges").** ACORD 25 and 10-10EZ added,
    Haiku 4.5 beside Sonnet 4.6, $5.04. No field flips on every case anywhere; Sonnet's flips are fields Haiku is
    stuck wrong on; Haiku is as repeatable but stably wrong far more often, so Sonnet 4.6 stays the judge and
    stability alone cannot choose one. Most wrong verdicts are not about names: empty cells in rows and columns
    (largest group on all three forms), ground-truth defects from case generation (ACORD's uncaptioned blocks,
    10-10EZ's home address slid one box), typed-X mark cells and checkbox grids. Until the presentation fixes
    land, the judge's flags on those fields should not reach the reviewer as name defects.

  - **Step 2, from step 1:** fix the causes before building voting. (1) Text mode marks empty text boxes the way
    it marks option boxes (`[ ]` or a blank token at every empty box, from the widget state), so a row with an
    empty first cell reads unambiguously; rerun step 1 to confirm the Part 6 cluster goes. (2) The whole-form check
    in `iterate` compares only fields whose verdict held, and confirms any field whose verdict changed in a round by
    two extra reads of that field (cheap), restoring the round when a confirmed stable field got worse; no
    threshold. (3) Before generalising, the same measurement on ACORD 25 (uncaptioned blocks) and 526EZ (image
    mode). Voting over every read stays in reserve: on I-765 it would buy little.

  - **Why the 40 / 45 happens in the loop:** the reader cache keys on the PDF bytes, model, parser and the batch
    of up to 120 fields sent in the call (`extract_llm._ask`). An unchanged rerun replays; one edited field
    re-keys its whole batch, so every other field in it is read fresh. A review round's before / after therefore
    compares mostly re-read fields, which fits I-765 going 37 -> 51 while every reviewed field scored "same".
    Per-field cache entries (the document plus that field's name, type, description and values; one cache file
    per document holding the per-field table; still one call per batch) would stop the spread to untouched
    fields, with any untouched field whose fresh answer moved reported as "moved without an edit". That hides
    noise, it does not remove it; it comes after step 1. Same-key loose end: in text mode the document sent
    depends on the blueprint (pages, `[x]` tokens at its option boxes) but the key hashes the PDF bytes; hash the
    text sent.

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

- **Reviewer on the class and option-group flags.** The reviewer receives `page_class` flags (caption read, page
  class, blueprint type) and, since 2026-09-30 late, `option_group` flags from the inventory check (the page's
  question vs the blueprint's `widgets`, with the widget-layer attribution). Run one review round on I-765 and
  526EZ with set 3 and judge as usual; the disability names, the bar number and the fields spanning two printed
  questions are the test cases. Missing on the apply side: an operation that splits one `widgets` map into two
  fields or merges two, which is what the option-group rows call for; the reviewer can only report them today.

- **Reader-mode guard: text-layer coverage.** Per run, count ground-truth strings present in the filled PDF's text
  layer; any missing -> that page reads in image mode, recorded. (The other half, option marks in the text the
  reader sees, is done: see Done.)

- **Synthetic data**: its own Open list above, plus two leftovers from older items here: 3-5 cases per set rather
  than 3, and one value for repeated copies of an identifier in blind cases (bank cases already do it, one persona
  per entity).

- **Route the emitter's blind spots to the validator.** Emitter-declared unknowns (uncaptioned option, page-text
  caption, ungroupable run) -> an `unresolved` detector with classes `uncaptioned_option`, `ungrouped_options`,
  `group_name_mismatch` (deterministic: `amended_return_ind` over Medicare / Medicaid / ...) -> per-option reviewer
  evidence (every option's on-state, caption, nearby text, a page crop). The two grouping classes are now aliases
  of the taxonomy's `option_group_mismatch`, which the synthetic inventory check reports; the text reader sees
  radio and checkbox states through its `[x]` / `[ ]` tokens, so image mode is no longer the only judge of them.

- **Reviewer across vendors** — the one slot compared only among Anthropic models.

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

- **Flat forms through the loop** (part of FLAT_PLAN_v1; parked 2026-09-30, Andrew). No flat form has been
  through the loop (153 in the corpus, verdict `no_widgets`). The library's two path-less blueprints
  (`osha300a`, `cms1500_fillable`) are empty (`fields: {}`). Where each stage stands (2026-09-30):

  - Labeling: `auto_label` takes step2flat geometry when there is no AcroForm layer (`petey.locate`; fields get
    `path: None` and a confidence); not yet used to build a flat blueprint. Geometry confidence is uncalibrated.

  - Case generation and fill: flat-ready since the page-only rebuild (finder, classifier, bank; `render_case`
    draws text and an X on a widget-less blank, so values land in the text layer). Extraction: the meaning
    reader works on any PDF; native has text_clip / OCR by rect.

  - Scoring: blocked. `rect_join.case_to_paths` skips fields without a path and the scorer keys ground truth by
    path, so a flat blueprint scores nothing. Fix: path-less fields keyed by field name (or rect).

  - Option boxes: the radio-recall run (146 AcroForm forms, finder on the unbaked PDF) found 50% of 2,936 option
    boxes; with widget appearances baked in, the five test forms gave 234 / 234; real flat forms sit between.
    Grouping still the aligned-runs rule (over-proposes on grids); caption join not built; thin circles need a
    shape fix. The 153-form `flat_option_survey` run of 2026-09-30 crashed at about form 130 on a non-PDF
    (overlay drawing) and wrote no results; `overnight.log`'s "exit 0" is masked by `$(date)`.

  - Plan when unparked: (1) label one flat form with step2flat geometry; (2) score path-less fields by field
    name; (3) calibrate on AcroForm forms baked flat: run the whole flat pipeline and compare with the widget
    layer (structure) and the existing blueprint (meaning), giving error rates to attach to real flat forms,
    where blueprint and ground truth both come from the page (one finder for both sides; text vs image readers of
    one page). Extras: different models for labeler and classifier, so their misreadings do not coincide;
    Andrew's eleven-form review as the human check on structure.

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
