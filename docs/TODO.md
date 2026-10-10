# TODO

Edited in place; the history is `git log --follow -- docs/TODO.md`. Priorities are Andrew's; the ordering is a
proposal. Numbers and context: `docs/RESULTS.md`, `petey/validate/defect_taxonomy.py`; terms: `docs/GLOSSARY.md`.

## Handoff: the two items, where they stand (2026-10-01, evening)

Numbers and the full reading: RESULTS "The rename adjudicator, and the box stage measured". Direction from Andrew
today: lean on the agentic side of the loop rather than on more hard-wired rules, do not fix one form's problem in a
way that moves another's, and do not over-index on a few difficult forms (every number below is over the 44 forms
in `runs/judge_eval/forms44.txt`).

- **1. Adjudicator for contested renames: built, tested, wired.** `petey/validate/adjudicate.py`; the fixture is
  `eval/adjudicator_test.py` (nineteen hand-checked fields; Sonnet 4.6 and Opus 5 agree with all nineteen once the
  SS-4 expectation was corrected: the widget is the header's EIN box, so `ein` was right and the batch-1 rename
  wrong; the side copy `runs/judge_eval/blueprints/form_ss_4.bpt` still carries `entity_legal_nm`). Default model
  Sonnet 4.6, about $0.006 a call. On by default in `review` and `iterate` (`--no-adjudicate`,
  `--adjudicator-model`). Two loop changes with it: class-stage fields reach the reviewer on judge flags again
  (caption withheld, rename contested) and `judge_review` keeps an adjudicated rename it would restore as 'same'.

  - Done 2026-10-01 evening (RESULTS "Batch 3"): twenty new forms and LA 7006 through the loop with the
    adjudicator; 12 renames on the new forms, 7 upheld, 3 stopped, 2 unclear. Open from it:

    - The corpus probe should exclude XFA-only pages (AL A-1: the page is the Adobe Reader notice, 247 fields
      with nothing printed to find).

    - Underline forms whose text widgets sit above the printed underscore run (TX RRC EP-5: 77 of 74 fields'
      rects unreached, 41 finder boxes with no widget under them): a yardstick family to look at.

    - The reviewer still proposes style-only renames (P-17 `rrc_identifier_row_42` -> `row42`, stopped by the
      adjudicator; `ou_manager` -> `ou_manager_nm`, upheld because the adjudicator judges the kind of value, not
      the style). The reviewer prompt forbids these; a cheap check in `apply_decisions` (same tokens after
      normalising underscores and MeF suffixes -> not a rename) would stop them without a call.

- **2. The box stage: measured; two finder patches ready, neither landed.** `eval/finder_vs_widgets.py` is
  size-aware (a hit is within 3x the widget's area; region boxes reported on their own). Before number over the 44
  forms: text 78%, options 52%, 250 widgets inside 45 region boxes, 832 missed; misses spread over the set (the six
  worst forms hold 44%). Families, from the finder's raw candidates:

  - **Region rows that exist only in the widget layer** (ND 10RR, SFN 18668: 188 of the 250 in-region widgets).
    Unlined list columns: a layout, not a finder defect. Andrew (2026-10-01): outliers, set aside. Their fields
    stay at the box stage (`merged_box`) and are reported as such.

  - **`$____` line cues** (B106I, B410): `eval/finder_experiment.py --patch linecue`, +61 text hits on those two
    forms, nothing else moves. Ready to land.

  - **Glyph checkboxes** (ZapfDingbats / Wingdings squares: LA 7006, TX RRC R-32, B410, KS DO-41, LA 16019 and
    1048, LIC100, HK IRD): `--patch glyph` adds them as candidates and stops them counting as text. Both patches
    together over the 44 forms: options 52% -> 85%, text 78% -> 80%, misses 832 -> 477, thirteen forms change
    and none gets worse; 32 new extras, 23 of them LIC100's printed squares that no widget backs. Ready to land
    with the line-cue patch.

  - **Form 5500's sub-point borders** (51 widgets with no candidate from either reader): not reduced to a fix.

  - Landing a patch = `FINDER_VERSION` bump in `petey/synth/boxes.py`. Not codified anywhere yet; checked in the
    code: the box, classifier and blind-generator caches re-key (every form classified again, one call per page),
    but the bank cases and the frozen case sets (`runs/_gen_cache/sets/`, 59 forms) do NOT, and their values are
    keyed by the old finder's rects, so set 1 would silently misalign (RESULTS, "What a FINDER_VERSION bump
    entails"). Before any bump: put the finder version into the bank case / set cache key so a stale set refuses
    to load, then bump once with both patches and regenerate set 1. Andrew's call on timing.
    **Done 2026-10-01 late (RESULTS "Versioning the finder", "step2flat-3 landed"):** the finder version is
    derived (label + AST sha + environment), bank cases and set manifests carry the case basis, a stale set
    refuses to load (`--rebuild-set`; a set whose boxes are identical under the new finder migrates with its
    files), runs and blueprints carry `x_petey_build`. Both patches landed as `step2flat-3`; set 1 rebuilt on the
    six diagnosis forms (B410, B106I, LA 7006, TX RRC R-32, KS DO-41, KS DO-10): box stage 289 -> 56 fields.

  - **Class stage now tests the class, not the caption** (RESULTS "The class stage tests the class"): a
    misattributed caption holds a field only when its class disagrees with the blueprint. On the six rebuilt forms
    the class stage went 171 -> 32 and the value stage 443 -> 582; LIC100 / SS-4 / WC-122 still held. What is
    left at the class stage (7006: 27, B106I: 1) is where the one-row-off caption did change the class. For those,
    the caption pass: the adjudicator's crop around the box, the model reads the caption, the class map is
    corrected; a versioned event on the classifier half of the basis. Agreed in principle 2026-10-01; not built,
    and smaller than it was.

  - `classify_form` has no retry on a malformed model reply (Form 5500 page 3, a stray brace); one retry with the
    parse error quoted back would have finished that form.

  - The migration path for unchanged forms (`validate._check_set`, identical boxes -> set and class map carried
    over) has not run on a real form yet; the first validate of any of the 31 will exercise it.

  - Rebuilt as a side effect before the loop was stopped: OCC 1014cs (old build in its manifest's history).

- **From the bpt-to-bpt diff (2026-10-02, RESULTS "Blueprint to blueprint"):**

  - Emitter: stop typing every `_nm` field `person_name`; thing-name columns (lease and field name, well name,
    formation name) should get no semantic type or a name class. 89 reviewer deletions over 65 forms came from
    this one rule.

  - Emitter: the semantic types the retype pass adds (`text` defaults, `year`, date parts) could be emitted
    directly; today a fresh label lacks 128 of 526EZ's committed types until the loop runs once.

  - ACORD 25: today's label (`runs/relabel/blueprints/acord25_relabel3.bpt`) fixes the library's known defects
    (phone -> ZIP, the coverage grid's column slide). Candidate to replace `blueprints/acord25.bpt` after one
    loop pass; Andrew's call.

  - **Promotion rule, proposed (2026-10-02):** a side copy enters the library when its loop converged, the chain
    puts most fields at the value stage, no field is left `unclear` or `needs_person`, it carries a build stamp,
    and a person has walked it in the hand-review page (`python -m petey.validate.hand_review`; verdicts in
    `runs/hand_review/`). ACORD 25 first, since its diff can be checked against known defects; then the 56 side
    copies with no library counterpart (A-1 and EP-5 excluded by their box-stage counts).

  - Library duplicates to resolve: `f5500` / `2025-form-5500`, `f5500ez` / `2025-form-5500-ez`, `i9` / `i-9`
    (diverged: 125 vs 128 fields), `fw4` / `fw4_pymupdf`.

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

  - **Bug: text mode reads a form with no option boxes in stored order (found 2026-09-30, OCC 1003).**
    `extract_llm` sorts words into reading order only on the `page_texts_with_marks` path, which runs when the
    blueprint has option boxes; otherwise `page_texts` passes `get_text()` through, and on a filled AcroForm the
    widget values come out as one block after the page's printed text, away from their labels. OCC 1003 (no
    option boxes): every filled value present in the text layer, the judge missed 73-81 of 113 judged fields per
    case. None of the five test forms lacks option boxes, so it never showed. Fix: the same line sort on every
    text-mode page, together with keying the cache on the text sent (above), or a fix would replay the cached
    answers. OCC 1003 was dropped from the judge-informativeness round (Andrew); rerun it after the fix.

- **Judge informativeness (2026-09-30; RESULTS "How informative is the judge?" and "Twenty more forms").** 24
  new forms, 1,740 fields, 308 judge disagreements; about 25 are naming defects (opaque `control` names on TX DMV
  1756, KS DO-10 widgets the publisher placed one row off, a swapped pair on ND 1TP), the rest presentation and
  case values. Follow-ups, in order:

  - **The page wins on position.** The labeler's evidence ranking (tooltip > path > nearby text, "the publisher
    wins") and the reviewer both defer to publisher metadata; on DO-10 and ACORD 25 the publisher put the widget
    in the wrong box and the blueprint copied it, and the reviewer then kept it. A box's printed caption decides
    what it holds; the publisher's name and tooltip are evidence, overruled when the page disagrees. Applies to
    the labeler prompt, the reviewer prompt, and the planned path-to-labeler change.

  - **Opaque names are a defect the reviewer must fix**: DMV 1756's 15 `control` fields were passed as "ok". The
    taxonomy has `opaque_widget_name`; the reviewer prompt should rename them from the page.

  - **Swaps go to the rebind, not to descriptions**: ND 1TP got two descriptions contradicting their names. Find
    why `correct.py` built no 2-cycle there, and stop the reviewer writing a description that contradicts the name.

  - **Case chain built (2026-10-01; RESULTS "The case chain").** `field_chain.py` stages every field box -> class ->
    value; box- and class-stage fields send no class / regex / judge signal, class and regex count once. 16 of 17
    hand-checked fields behave; SS-4 `ein` is the known loss (a right rename deferred). The adjudicator for contested
    renames (a vision model on the rendered crop) is the next step, held until Andrew says.

  - **Batch 2 (2026-09-30; RESULTS "Batch 2").** The page-wins fix repaired publisher misplacement (VA RDT-120
    three renames, Utah WC-122 three, all right on the page) and made two wrong renames from captions the
    classifier misattributed (`caption_misattributed`: LIC100, WC-122 `time_of_occurrence`). Next:
    (1) the caption for the gate and the reviewer comes from page geometry (words inside the box, else directly
    above it in its cell), cross-checked with the classifier's label; on disagreement no rename rests on it.
    (2) The path-to-labeler change (decided earlier, not built) would have prevented WC-122's misnames: its paths
    are readable ("Employer Tel #", "Location", "Time of Occ").

  - **implausible_case_value, logged, decide later (Andrew, 2026-09-30).** Boxes the classifier calls `other` /
    `free_text` get bank filler ("Services maintenance" as an Issuing Authority, "Maintenance" for a Month/Year),
    which the judge rightly refuses. No new classes for now (county and survey township / range considered and
    dropped). `eval/judge_informativeness.py` writes every hit to `runs/judge_eval/implausible_case_values.csv`
    (form, field, caption, page class, case value) with the commonest caption words; 46 in the first 24 forms.

  - **Filter the judge's flags by cause before the reviewer**: the layout-shift and implausible-value families
    (most of the 308) should not reach the reviewer as name defects until the presentation fixes land.

- **Reviewer: publisher descriptions are not removable.** The description is its own field on the spec (verbatim
  tooltip or XFA caption text, tagged `x_petey_description_source: tooltip | xfa_choices`); names are separate
  slugs the labeler derives with the tooltip as evidence. The reviewer's apply step honours `remove: [description]`
  and any replacement string. Change: when the source tag says publisher, refuse removal and refuse a replacement
  that drops the publisher text; allow appending. Tell the prompt the same.

- **Flat forms: built 2026-10-05** (RESULTS "Flat forms through the loop"). The plan was not written as a document;
  the build is the plan: `petey/label/flat_label.py`, `boxes.widget_key`, ink in `extract.py`,
  `eval/flat_calibration.py`. What remains is under "Flat forms through the loop" in Medium.

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

- **Flat forms through the loop: built 2026-10-05** (RESULTS "Flat forms through the loop"; glossary: flat
  blueprint, widget key, flat calibration). Two true flat copies (TX RRC EP-3, W-3X) ran end to end: the flat
  labeler makes the blueprint from the class map and a second model's names, bank cases are drawn on the page,
  the native reader reads text by clip and marks by ink, scoring joins by rect key, the witness tiers and the
  hand review (`fl__` source) take the blueprint. `validate --blank <flat pdf>` labels a flat blank itself and
  skips flattened cases. Calibration on the core test forms baked flat: the numbers in RESULTS.

  Open, from the first runs:

  - **Finder recall on the weak twins** (`p_15` 3 of 15 widgets, RESULTS twins table: six forms at or below
    0.23). A flat form the finder cannot read gives a blueprint with holes and no witness sees them; the twins
    table is the list to diagnose from. The calibration tool's `missed` rows per form are the starting point.
  - **Duplicate finder squares** (W-3X: a cell and the square drawn inside it both proposed and both classified
    `option`; `tie` and `option_group_mismatch` rows, 5 unbacked option rects against the twin). A finder or
    classifier-guard rule: an option box inside another option box on the same page group is one box.
  - **Names from the registry's suffix rules on flat forms**: `county_nm`, `lease_name`, `field_name` typed
    `person_name` by `semantic_types.lookup`; the class check flags them (page class `free_text`), so the loop's
    reviewer can fix them, but a flat form has no publisher witness to settle the rename.
  - **The judge on repeated rows** (EP-3: eight pit-table rows, the judge slid every row by one: 21 of 38
    differ while the native reader agreed on all 38). Not flat-specific; the ordinal-name weakness.
  - **Option captions that repeat** (W-3X's nine-box column captioned D, D, E, F, F, G, G, H, H): option slugs
    `d`, `d_2`. The classifier's caption for a box under a lettered item is the item letter, not the choice.
  - **A flat blueprint's `category` groups are never `multi_category`**: the classifier does not say whether a
    group allows several marks; the bank marks at most one, so the scorer never sees the difference.
  - The fix path for a flat form is the three pages (2026-10-05, all list the `fl__` side copies): hand review
    for names by witness tier, group review for option grouping, field add for the boxes the finder missed (on a
    flat form it has no suggestions, since every kept finder box is already a field; the person draws the box
    and the page names it from the text beside it; watch the caption on shared underline rows: EP-3's P-5 box
    got "Organization Name" from the left end of the line). Then `--apply` and validate again. The two twins and
    the 153-form checklist are the queue.

## Open taxonomy gaps (no in-place fix yet)

- `repeated_section_ambiguity`, `nonnumeric_in_numeric_field`, `short_shape_on_wide_box`.

- `yn_column`: radio groups keyed by export code that a text-mode reader cannot see; image mode or rendering
  checked states into the page text.

## Checks: ways they could work better (list started 2026-10-07, Andrew)

Ideas, not plans; each wants a measurement on the hand-reviewed fields (1,508) before it is built.

- **Distance when a tooltip "belongs to" another field.** The publisher check (`witness.Names.judge`) weighs a
  tooltip against every field name on the page, so a field in another section can win; any margin counts.
  ACORD 140 `1_25` (`subject_of_insurance`, PREMISES INFORMATION) was contested because its tooltip scored 0.489
  for `1_86` (`other_refrigerant_coverage_description`, ADDITIONAL COVERAGES / spoilage options) against 0.488 for
  its own name, on the generic words "coverages" and "other". The check exists for swaps and boxes placed one row
  off, which happen between near boxes: penalise distance, or only compare within the box's section, and require
  a margin. The widget path (`..._SubjectOfInsuranceCode_A`) would also have settled it and is not consulted.
  Measured 2026-10-07 on the current hand-review records: 102 fields contested this way, 94 accepted, 8 flagged
  and none of the 8 for the tooltip's reason, so it is now a hint (raw details only; `witness.grade`). Two more
  faults seen: the score is the share of the NAME the tooltip explains, so a specific name loses to a short one
  (`uscourts_b_106a_b_6_15` `retirement_account_institution_name` 0.76 vs `6_16` `retirement_account_amt` 0.86 on
  "Retirement account name": "institution" is rare and unmatched, "amount" common); and a tooltip several fields
  share ("Institution name or individual") cannot tell them apart. Before it returns as an error: a margin, the same
  section only, ignore tooltips shared by several fields, normalise by the tooltip as well as the name.
  **Built 2026-10-09 (branch `witness-belongs-to`):** all four, plus distance (a rival within an inch) and section =
  same XFA subform and no heavier-than-usual full-ish rule between the boxes (`witness.section_rules`). Fixture
  `eval/belongs_to_fixture.py` over every hand-reviewed field (3,738): firings 1,862 -> 118; on fields a person
  looked at (not bulk-accepted) 285 -> 12 (publisher 93 -> 8, page 183 -> 1, classifier 32 -> 3); the 5500-SF
  day / month swap still caught. Publisher belongs-to graded an error again. Of the bulk-accepted fields it still
  fires on, the page agrees with the tooltip on ACORD 125 attachments (a slide by one), I-130 eye colour / race /
  province-country, f5500sf day / month: library errors the bulk accept hid. Known false alarm: abbreviations the
  name tokens do not expand (faa8710 `tol` = takeoff / landing). The other 6 hand-flagged name errors are not
  belongs-to cases (5021: tooltip names a box no field claims; 1014r: no tooltip, the path says it; cms_10883:
  tooltip "undefined"); reading readable widget paths as publisher text would catch 1014r.
- **Ruled-line weight as relevance.** Forms mark sections and rows with heavier rules (ACORD 140: 0.96 / 0.72
  section, 0.48 row, 0.24 cell); text across a heavier rule is less likely to be about the box. Uses: the section
  for the item above, and caption candidates. Weights differ by form and within a page, so "heavier than this
  form's cell lines", not a fixed number; first count how many publishers in the launch library use two or more
  weights. Does not cover specificity (a section title applies to every box under it) or a misread neighbour in
  the same row (ACORD 140 `1_86`: "REFRIG MAINT AGREEMENT" is one 0.24 cell line away; it named the field
  "refrigerant" when the section is spoilage coverage).
- **Option captions from the page (`petey/label/captions.py`).** ACORD 140 `1_126` (secondary heat: BOILER [ ]
  SOLID FUEL [ ] [ ]______) lost SOLID FUEL: the last box, with nothing printed right of it, read SOLID FUEL from
  its left, and the duplicate rule dropped it from both. Two guards are built and switched off (`GUARDS = False`;
  with it off the output is the old code's on all 6,117 page-captioned boxes): a box may not borrow a caption a
  sibling reads right of itself; a box followed by a text field is a write-in with no fallback. Measured against
  the option keys: the first gained 81 captions that fit and 77 that do not (the duplicate rule had been hiding
  sentence fragments read right of a box: "or physical", "protective"); the write-in rule lost 42 real column
  headers in grids (990 Part VII "Highest compensated", Schedule A "No"). Before switching them on: (1) stop
  right-of readings that are part of a sentence, the source of the junk; (2) narrow write-ins to boxes with no
  column header, or a tooltip that says other / specify; (3) bound the header-above fallback by a ruled line
  (`1_126`'s last box reaches "FIREPLACE INSERT" across a section rule). Meanwhile captions are editable by hand
  on the review page.
- **Repeated option blocks under one field name (labeler).** CBP 3461 page 1: `PartyType1[0..15]` and
  `HeaderID1[0..11]` are four party blocks repeating the same on-states; the labeler grouped by on-state and kept
  only the first block. The six missing groups were added by hand 2026-10-07 (`cbp_form_3461_1_72`..`1_77`). Still
  open there: page 3 `BOLType1` / `BOLType2` (bill of lading type, 4 boxes each) are missing entirely. Labeler
  fix: when one field name repeats the same on-states in separate blocks, one group per block.

## Later

- Registry lifecycle states and the review list (STRATEGY_v1 §5 step 5) — unchanged.

- **Gemini for the remaining model slots** (parked 2026-10-06, Andrew: costs some money, not quality). Switched so
  far: labeler (`auto_label.MODEL`, Gemini 3.8 Flash) and the round-0 page check (`form_run.FIRST_MODEL`, page sent as
  three strips because Gemini 3 sees an image at ~1,100 tokens to Opus's ~4,800; on the dense fixture forms strips
  matched Opus, 16 vs 14 known errors, at $0.54 vs $1.94). Never tested on Gemini: the page classifier (Sonnet 4.6;
  whole-page vision, so it would likely need strips too; it is the page-reading step of today's blind generation,
  bank cases), the reader / judge (Sonnet 4.6; compared only against Sonnet 5 / Haiku 4.5, `eval/reader_models.py`;
  text layer, so the image limit matters little), the adjudicator (Sonnet 4.6; a crop, so the limit matters less;
  `eval/adjudicator_test.py`, 19 fields) and the reviewer (Opus 5). Gemini was tested on the blind generator only
  (RESULTS 2026-09-30), which is now an optional second source beside the bank. Test each against its existing
  fixture before switching.

## Low

- Text-layer refusal (OCR / VLM fallback) — unchanged.

- Filled values missing from the text layer on 21-526EZ, MA Form 1, VA 760 — image mode handles it; parked.

- `id_part` semantic type defaults to `^\d{1,5}$`; the emitter's `part_by_maxlen` only narrows when the widget
  carries MaxLen, the retype pass also used box length.

- Registry column for option groups (see Next) and the DeepSeek thinking switch (would need reasoning off or
  capped before those models can be compared fairly).
