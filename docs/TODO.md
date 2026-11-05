# TODO

Edited in place; the history is `git log --follow -- docs/TODO.md`. Priorities are Andrew's; the ordering is a
proposal. Numbers and context: `docs/RESULTS.md`, `petey/validate/defect_taxonomy.py`; terms: `docs/GLOSSARY.md`.
Done items are removed, not kept (cleaned 2026-11-01 and 2026-11-04: everything built, decided or validated since
came out; on 2026-11-04 the printed-metadata check (printed is signatures and initials only, the sheet retired for the
S), lines of one answer (`_line_N` fields split at printed rules, the "split multi-line boxes" tool) and the
ca_courts_dv_110 re-save, validated 2026-11-02).

## Flat-structure benchmark: open judgement calls

In `docs/BENCHMARK_JUDGEMENT_QS.md` (2026-10-27): what a block is, what a grid is (grids by geometry), one line
holding several fields, fields with no widget, combs, anchoring, near-duplicates, novelty, the forms that failed the
cut. Scoring: `docs/BENCHMARK_SCORING.md`.

## Prompted structure reviewer (2026-11-04, Andrew deciding)

Replay of Andrew's structure reviews with Opus 5 and a prompt, no fine-tune: 88% of his removals and 93% of his
additions raised, 0.7% of kept boxes flagged, 0.2 cents a field (`docs/RESULTS.md`, last section;
`runs/review_replay/`). Possible next steps: judge the 77 false flags, add reshapes / groups / kinds to the prompt,
confirm on key pages, move the script into `eval/`.

## Structure errors: collect, then one design (2026-10-27, Andrew: "lets start accumulating these errors and fixes and see if we can't do something more cohesive when we have them all")

The cases found while reviewing the benchmark forms (option groups, grids, blocks) go into `docs/STRUCTURE_ERRORS.md`,
logged, not fixed one at a time.

## Tiny pale-edged circles not detectable as fields (2026-10-27, Andrew: "very tiny circles for 'please mail' and 'please fax' need to be detectible as possible fields")

bm__sd_311861 p1 (Kirkwood record request), "Please Mail" / "Please Fax": two printed radio circles, about 8.6 pt
across, drawn as four arcs, dark top-left and pale grey (grey 200-235) bottom-right. The original has no widget there,
so the blueprint has no field; nothing else finds them either (still none on 2026-11-01):

- **Add / remove's click** (`field_add.enclosed_box`): the fill stops only at ink darker than `INK` = 200, so it leaks
  out through the pale half and proposes nothing. Read-only check: at 230 or 240 both circles close, as
  [381.25, 499.25, 390.5, 508.75] and [471.25, 499.25, 480.5, 508.75]. Proposed fix: when the fill gets out at 200,
  try once more counting grey below ~235 as ink and use that box only if it closes (a click that works now gives the
  same box; shaded cells keep working). Re-run the 450-field corpus check of 071b1e2 (97 / 109 checkboxes, 150 / 341
  text fields) before and after. A test with a pale-edged circle.

- **The finder** (`petey/synth/finder_addons.py`, which since 9429ea6 reads underlines, small squares and hollow glyph
  boxes off the PDF's drawings): small pale circles as candidates go there.

## Check boxes that are just underlines (2026-10-27, Andrew: "there are check boxes that are just underlines that need to be figured out")

bm__sd_5228297 p1 (Cornerstone Wellness release of information). Two kinds, both short underlines doing a checkbox's
job:

- **"___ Coordination of Care  ___ Treatment Planning  ___ Transfer of Care  ___ Litigation  ___ Other: ____"**
  (purposes, y ~284-300): a three-underscore run before each option. No widget on the first four (only Other's
  write-in line is a text widget), so the blueprint has no field for them.

- **"Substance Abuse_____  Mental Health _____  HIV-related info _____"** (specific consent, y ~497): an underline after
  each label; the publisher put small text widgets (22 x 17 pt) there, so the blueprint has them as text.

To figure out: whether the benchmark counts such an underline as a choice (one of a set, ticked or initialled) or a
text field, and so its kind and its partners (the four purposes one group?); then how they are found from the page
(an underscore run or a short rule right before or after an option label, of about a word's width), by the finder,
Add / remove's click (`field_add.enclosed_box` proposes nothing on an open underline) or both. Related: "fields with
no widget" in `docs/BENCHMARK_JUDGEMENT_QS.md`.

## Names, captions and kinds (open since 2026-10-10)

The name checks, text-match model and caption chooser are on `main` (PR #3; RESULTS "Name checks, the text-match model
and the caption chooser").

- **Caption suggestions, then automatic (Andrew).** Andrew uses or skips the chooser's suggestions on the review page;
  if they come back clean, apply them automatically where the model and Jev pick the same caption (93.9% right when
  they agree). Same gate for automatic name fixes later.

- **Money vs `money_whole_dollar` (pinned, Andrew).** `money_retype.keep_reason`'s page rule is wrong both ways: a
  form-wide header does not reach pages that do not repeat it (Schedule H x3 p3-4, il1040 p2, it201 p3-4) and a
  one-line instruction makes a whole page whole-dollar (irs_8962 p1, 90 fields; ga500 p3; va760 p2; ca540 p1 / p5).
  Proposal: a general statement -> whole form; an instruction on a field's line -> that field; '.00' printed after a
  box -> that box. Cents-box mixes (IRS 94x, ACORD) are right.

- **Demote the classifier's 'class contradicts type'** to a hint: 2 flagged of 63 looked at. Its 'caption shares no
  words with the name' half is a good signal (6 flagged of 19).

- **Group names from their members** (Andrew): Schedule H `opinion` / `no_opinion` / `line4b_yes_no`, ACORD 125
  `additional_interest_1` / `_1_2`, CMS-1500's `amended_return_ind` (over Medicare / Medicaid / ...) need descriptive
  names; derive from the members' common part or the question.

- **Shared-prefix trimming** between a field and its rivals (Andrew's idea): judge 'belongs to' on the part of the
  tooltip that differs, so a long shared preamble does not drown 'Hazel' vs 'Green'. Not built.

- **Text-match model weak spots**: insurance paraphrase, rows differing by a number, abbreviations it was never shown
  (faa8710 `tol` = takeoff / landing). Next training data: the review corrections as they come in.

- **Text-match speed**: int8 is 2.3x faster but lost 2 of 15 real errors at the 'does not describe' cutoff, so it is
  opt-in (`PETEY_TEXT_MATCH_INT8=1`). Ideas: re-score at full precision only the pairs near a cutoff; trim shared
  tooltip preambles (above) to shorten inputs.

- **Fresh clones have no `models/text_match/`** (gitignored): copy it or retrain (`eval/text_match_train.py`) before a
  runner batch, or runs there use the rules alone.

- **Housekeeping**: remove the `../petey-2-belongs` worktree (branch `witness-belongs-to`, merged in PR #3) and its
  5006 review page; the training venv is `~/Documents/code/.venvs/petey-train`.

## Checks: ways they could work better (2026-10-07, Andrew)

Ideas, not plans; each wants a measurement on the hand-reviewed fields before it is built.

- **Ruled-line weight as relevance.** Forms mark sections and rows with heavier rules (ACORD 140: 0.96 / 0.72
  section, 0.48 row, 0.24 cell); text across a heavier rule is less likely to be about the box. Uses: the section for
  the item above, and caption candidates. Weights differ by form and within a page, so "heavier than this form's cell
  lines", not a fixed number; first count how many publishers in the launch library use two or more weights.

- **Option captions from the page (`petey/label/captions.py`).** ACORD 140 `1_126` (BOILER [ ] SOLID FUEL [ ] [ ]___)
  lost SOLID FUEL. Two guards are built and switched off (`GUARDS = False`): a box may not borrow a caption a sibling
  reads right of itself; a box followed by a text field is a write-in with no fallback. Measured: the first gained 81
  captions that fit and 77 that do not; the write-in rule lost 42 real column headers in grids. Before switching them
  on: (1) stop right-of readings that are part of a sentence; (2) narrow write-ins to boxes with no column header, or a
  tooltip that says other / specify; (3) bound the header-above fallback by a ruled line.

- **Repeated option blocks under one field name (labeler).** CBP 3461: `PartyType1[0..15]` / `HeaderID1[0..11]` are
  four party blocks repeating the same on-states; the labeler kept only the first block (the rest added by hand
  2026-10-07). Page 3 `BOLType1` / `BOLType2` (4 boxes each) still missing. Fix: when one field name repeats the same
  on-states in separate blocks, one group per block.

## Light path: open calls (2026-11-04, numbers in `docs/RESULTS.md`, the light path section)

- **Jev typing:** wire it in where the type model is unsure (typed-right errors 487 -> about 338 on the tuning set),
  confirmed once on the benchmark; or leave it. Andrew deciding.
- **The learned screen** (branch `light-screen`): port to numpy and wire it after the Jev screen, or leave it.
- **The finder's misses** (2,034 key fields with no box): picture sheets by kind, then candidates where they pay.
- **Score the publisher widgets** as a method on the benchmark (how wrong widgets are; a floor, since the key started
  from them). Next.
- **Domain tags** for the newer forms: 7,506 tuning-set key fields are untagged.
- **Retraining the type model:** `eval/type_train.py` reads the light results' kinds as the finder's, but `--derive`
  now writes the type model's own kinds there, so a retrain would learn from its own answers. Read the finder's kinds
  from the saved blueprints (`light_bp`, as the Jev typing test did) first. 76 of the newest tuning pages were run
  without saved blueprints.

## Later (parked by Andrew)

- **Tuning set skewed to long forms and a few publishers** (2026-11-04, Andrew: "the training set mostly coming from
  overflow means it is more homogenous"). The tuning set (what the printed / split / type models train on) is each
  validated form's pages past the two the key takes, so a 1-2 page form never reaches it. Measured 2026-11-04 (889
  forms; key 1,478 pages, tuning 995): 1-2 page forms are 461 forms and 43% of the key, 0% of the tuning set; 6+
  page forms are 23% of the key and 75% of the tuning set; 317 forms make the whole tuning set, two CMS 855 forms
  7% of it; top ten publishers 36% of tuning vs 15% of the key (USCIS + CMS 21% vs 3%); immigration 17% vs 4%,
  health 10% vs 3%, private sector 19% vs 27%. No cost yet: on the key, 1-2 page forms score level with or above the
  rest (fields F1 86.9 vs 87.2 on 6+ pages; printed F1 72.3 vs 66.7; typed right 98.5 vs 96.6), the models being
  small. It will matter if the models grow, and the in-sample tuning numbers overstate the key. Fixes in order:
  (1) weight each form's pages to one unit (or cap at 3-4 pages a form) in the three trainers, key untouched;
  (2) route by form from now on: every third newly accepted 1-2 page form goes whole to the tuning set, existing
  picks stay permanent; (3) a one-time move of ~100 short forms (~140 pages) from key to tuning set, which shrinks
  the key a tenth and breaks the stable-pages rule, only with a stronger reason than today's numbers.

- **Labeling speed** (2026-10-26: "speed is not a huge issue right now, it can wait until later"). Per field
  (measured 2026-10-26): labeling 2.8 s with pages one after another, 0.85-1.1 s with pages at once; a call's
  time is the model's thinking. Ideas, neither run: (1) try `reasoning_effort` low / medium on GSE 1084, CASC 100,
  Form 8300 and compare names and time per field; (2) bulk "no answer": list the structure ids the answer must cover,
  so the follow-up call is not needed.

- **More text-field detection data, if needed** (2026-11-01, Andrew: "if we need more data for the text field
  detection, we can go back and split fields the light path put together on its own into their constituent blocks,
  but I am not going to do that now"). The source: fields the light path joined into one by itself; split each back
  into its pieces. Not now.

- **Tables as block types** (2026-10-22: "lets park these ideas and see how SIA does in production"). A table is a
  block type whose blocks are its rows. Missing: a table made a block type in one step; position wordings seeded from
  the printed column headers and block prefixes from the row labels; tables repeating across (a column per year) as a
  type whose blocks are columns. Then the Grids tab could go.

- **Printed labels in assign and drawing** (2026-10-22): assign's `fit` pairing boxes by their printed captions
  (`block_types._alike`) instead of field names; drawing recognising a near copy whose labels match as an existing
  type. Tolerant captions in SIA were tried and dropped (+61 right of ~2,700 fields, 6 new real errors).

- **Option names standardized across a block type's copies** (2026-10-24: "we can probably let this slide for now").
  je__uscourts_b_106d_check's "who owes the debt" (1_18, 1_35, 2_75, 2_74, 2_59) has four option sets across claims
  1-5; "nature of lien" (2_73, 2_77, 2_79) carries field names as option keys. Idea: each copy's options take the
  reference block's names by place. Check first whether a key is still the PDF's on-state anywhere (the harness fills
  by it): there, standardize the caption, not the key.

- **Suggested block types from the block-group finder** (2026-10-21: "park that and we can integrate it later"). On
  the Blocks tab, each group `block_groups.find` finds proposed as a block type, dashed, accepted or dismissed. Also
  open: `block_groups.find` is still the labeler's structure finder (`petey/label/structure.py`), kept until Andrew
  says otherwise; 17 converted types hold one block and want "assign to type".

- **IRS 941-X page 2 as a grid** (2026-10-21: "leave it for now, come back to it"). (1) Each cell carries a line
  number (6-17) and a column number (1-4); the labelled-rows reading wants a run to start at 1, so the numbered reading
  takes the column as the iteration. Fix: a run on `line_` / `item_` may start anywhere. (2) Dollars / cents named two
  ways (`col_1_amt` + `col_1_cents_txt` vs `col_1_amt_dollars` + `col_1_amt_cents`); rename the first to the second.
  The page's three grids were set aside on 2026-10-21.

- **Gemini for the remaining model slots** (2026-10-06: costs some money, not quality). On Gemini: the labeler and the
  round-0 page check. Never tested on Gemini: the page classifier, the reader / judge, the adjudicator, the reviewer.
  Test each against its existing fixture before switching.

- Non-blueprint documents with standard content and bespoke layouts (medical intake, bank statements).

- Registry lifecycle states and the review list (STRATEGY_v1 §5 step 5).

## Parked: the generate-and-judge loop

Open items from the synthetic-case loop (cases from the bank or a blind generator, the reader as judge, the LLM
reviewer). The work moved to validating blueprints by hand on 2026-10-22 ("no generation", see the validation
strategy), so none of this is active; details in RESULTS under the named sections and in git history of this file.

- **Synthetic data steps left**: step 4 second half (class flags against reader flags on set 3; code in place,
  `eval/flags_overlap.py`, runs not done); step 5, blind-generator default (W-9 under-fill on the rect prompt first);
  step 6, regenerate the library's working set as a bank set, retiring the 134 imported non-blind cases (needs
  Andrew's go); step 7, relabel and judge against the new sets. Also 3-5 cases per set rather than 3.

- **Finder classes not built**: caption-anchored whitespace (10-10EZ p5 "FROM:" / "TO:" with no box); a
  `swapped_rects_same_family` taxonomy class (526EZ separation pay dollars / cents carry each other's rects).

- **Classifier**: re-run agreement per box before the class check gates anything; the closed vocabulary plus a
  free-text `reading` beside the class (Andrew decides); untyped fields taking the page class as their semantic type;
  a repeated-identifier check from its `entity` slugs.

- **Reader / judge**: text mode marks empty text boxes as it marks option boxes, so a row with an empty first cell
  reads unambiguously; per-field reader cache entries, and key the cache on the text sent, not the PDF bytes; bug:
  text mode reads a form with no option boxes in stored order (OCC 1003), fix with the cache key; filter the judge's
  flags by cause (layout shift, implausible case value) before the reviewer.

- **Reviewer**: run it on the `page_class` and `option_group` flags (I-765, 526EZ); an apply-side operation that
  splits or merges `widgets` maps; refuse removing publisher descriptions; a cheap check that stops style-only
  renames; rename opaque `control` names from the page; swaps to the rebind, not to descriptions (ND 1TP); compare it
  across vendors.

- **Emitter**: stop typing every `_nm` field `person_name` (89 reviewer deletions over 65 forms); emit the retype
  pass's semantic types directly; route its declared unknowns (uncaptioned option, ungroupable run) to an `unresolved`
  detector with per-option evidence; 12 uncaptioned options left in the library.

- **Flat forms through the loop** (built 2026-10-05): finder recall on the weak twins (six at or below 0.23);
  duplicate finder squares (an option box inside another is one box); the judge sliding repeated rows; option captions
  that repeat (W-3X); flat `category` groups never `multi_category`.

- **Other**: a reader-mode guard on text-layer coverage (a missing ground-truth string sends the page to image mode);
  the corpus probe excluding XFA-only pages; Form 5500's sub-point borders; the class-stage caption pass (7006: 27
  fields); the migration path for unchanged forms has never run on a real form; registry per-form option-group fact;
  naming without Claude and LLM as the loop's repair tier; the finished meaning-arm run and the local-generator
  fixes; `implausible_case_value` rows in `runs/judge_eval/implausible_case_values.csv` (decide later).

## Open taxonomy gaps (no in-place fix yet)

- `repeated_section_ambiguity`, `nonnumeric_in_numeric_field`, `short_shape_on_wide_box`.

- `yn_column`: radio groups keyed by export code that a text-mode reader cannot see; image mode or rendering checked
  states into the page text.

## Low

- Text-layer refusal (OCR / VLM fallback).

- Filled values missing from the text layer on 21-526EZ, MA Form 1, VA 760: image mode handles it; parked.

- `id_part` semantic type defaults to `^\d{1,5}$`; the emitter's `part_by_maxlen` only narrows when the widget carries
  MaxLen, the retype pass also used box length.

- The DeepSeek thinking switch (would need reasoning off or capped before those models can be compared fairly).
