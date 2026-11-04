# Plan: printed type and split values in the light path (2026-11-04)

For a fresh session. Andrew wants the light path to do two things it does not do today:

1. **Printed type**: mark fields meant to be hand-written (signatures, initials, printed names) as `printed`.
2. **Split values**: join the parts of one value written in several boxes (a date in month / day / year boxes, a
   phone in area / prefix / line, an ID number in pieces) into one value.

Both are scored by the flat-structure benchmark (`eval/benchmark_score.py`). Background:
`docs/STRUCTURE_ERRORS.md`, `docs/BENCHMARK_JUDGEMENT_QS.md`, the docstrings of `eval/flat_light.py`,
`eval/benchmark_key.py`, `eval/benchmark_printed.py`, `petey/validate/compound_values.py`,
`petey/validate/printed_fields.py`.

## Ground rules (Andrew's, all standing)

- **Problem and fix first.** Before any code edit in the repo, give Andrew the problem, the proposed fix and what it
  touches, and wait for his go. Read-only checks and scratch scripts are fine without asking.
- **Tune on the tuning set only**: `runs/benchmark/dev_key` (925 pages, 291 forms since the 2026-11-04 rebuild). The benchmark key
  (`runs/benchmark/key`) is for confirming a finished change, never for tuning. The CommonForms sample
  (`runs/benchmark/cf_key`) is a check only, and its key has signature fields only, no printed names or splits.
- **The light path reads the page only.** No widgets, no widget names or tooltips, no publisher metadata.
- **No hard-coded tables** of domain words or form quirks. Very common words (sign, signature, initials, print, name,
  date) are fine as cues.
- **A test with every code change** (`tests/`, `make test`).
- **Measure per field**, not per form or page. Report P / R / F1 from the scorer.
- **Do not commit or push unless Andrew asks.** Another session shares the git index: test on a private index, then
  add + commit in one call.
- **Plain, short replies to Andrew.** No command lines or flags in them. Name forms by review-page id and field code,
  with links `http://localhost:5005/#review/<id>`.
- When a number depends on Claude's own by-eye judgment of what is a field, say so: Claude's calls run looser than
  Andrew's.

## Where things stand (tuning set as built 2026-11-03, 899 pages; rebuilt 2026-11-04, see Findings)

| | P | R | F1 |
|---|---|---|---|
| Fields found, light path alone | 80.8 | 89.3 | 84.8 |
| Printed fields (348 in the key) | 0 | 0 | 0 |
| Split values (210 in the key), light alone | none combined | | |
| Split values with `compound_values.find`, all kinds (856 joins) | 40.8 | 55.2 | |
| Fields found with those joins | 79.5 | 84.1 | 81.7 |
| Split values, find kept to date / phone / id_number (243 joins, scratch check 2026-11-04) | 51.0 | 55.2 | |
| Fields found with those joins | 81.1 | 88.5 | 84.6 |

A split value is graded whole, so a wrong join costs every field in it under "fields found". The key counts only
dates, phones and ID numbers as split values (Andrew, 2026-10-30). Names, addresses and signature lines are not.

**No Jev rerun is needed to start.** Each tuning page's whole light-path blueprint is saved in
`runs/benchmark/dev_predictions/light_bp/<page id>.json` (every box, its Jev is-field score, line splits).
`eval/benchmark_light.py`'s `to_prediction(bp, splits)` turns one into a prediction. Work from those files, write
predictions to a scratch directory, and score them:

    PYTHONPATH=. venv/bin/python eval/benchmark_score.py <prediction dir> --key runs/benchmark/dev_key

The flat page PDFs are in `runs/benchmark/dev_key/pages/`.

## Part A: printed type

**What the key calls printed:** signatures, initials, printed names. The date of signing and a signer's title stay
text. Andrew confirmed these by hand (`petey/validate/printed_fields.py`, tag `x_petey_printed`;
`benchmark_key._kind` writes `printed` into the key).

**Signals already known.** `eval/benchmark_printed.py` drafted candidates from three signals: caption words, the
validated field name, and the publisher's signature widget. Only the caption is page-only. Caption words alone were
P 59 / R 59 against field names on library pages (2026-10-31). FFDNet's signature class is no help: on CommonForms it
found 208 of 232 signature lines but labelled them text.

**Steps**

1. **Measure the caption signal on the light path's own boxes (read-only).** For each light box on the tuning set,
   take `benchmark_printed`'s caption reading (words beside, below, above or inside saying sign / signature /
   initials / print name). Score it as `printed` against the key. Break the misses and wrong calls down by cause:
   - the caption belongs to another box (beside vs below)
   - a date or title next to the signature took the cue
   - no caption at all
   - the key and the page disagree

   Show Andrew a handful of each with links.
2. **Caption pairing, if step 1 shows the beside-vs-below mix-up matters.** A caption often has a blank beside it
   and one under it. Pick one: rules first (an underline below with no caption of its own vs a wide space beside that
   ends at a rule), then for what is left one Jev question showing both boxes, "which of these two does this
   caption's answer go in?". The 2026-11-03 per-box yes/no Jev question on caption rows could not separate real from
   junk (`docs/STRUCTURE_ERRORS.md`, flat-structure notes), so ask it as a choice. First count how many captions on
   the tuning set have both candidates. That number has never been measured.
3. **A Jev check, only if captions plateau.** One picture question per candidate box: "is this where someone signs,
   initials or prints their name?" Measure it on the tuning set before proposing to wire it in. Record the cost per
   1000 fields.
4. **Wire in** (after Andrew's go): the light path marks the field printed on its blueprint (the `x_petey_printed`
   tag, source e.g. `light_caption`). `to_prediction` must emit kind `printed` for such fields. Today it emits text /
   choice only; `printed_fields.is_printed(spec)` is the reader. Add tests. Confirm once on the benchmark key.

**Done when:** printed F1 on the tuning set is a real number with its misses explained, and Andrew has chosen
whether to wire it in.

## Part B: split values

**What exists:** `compound_values.find(bp)` reads the page alone (geometry plus printed words). It finds dates,
times, names, phones, ID numbers, addresses, signature complexes and money. The benchmark's `light_splits` arm feeds
all of them in as groups. It is not in the main light path.

**Steps**

1. **Keep find to date / phone / id_number for the benchmark** (measured above: joins 856 to 243, P 41 to 51,
   fields found back to 84.6). Propose it to Andrew as the first change. It is a filter in the benchmark arm (or a
   `kinds=` argument to `find`), not a change to what the Groups tab suggests.
2. **Sort the remaining errors by cause (read-only).** Of the 243 joins, about half are wrong. Of the 210 key
   values, 94 are missed. Break each down:
   - **Wrong joins:** the parts belong to different questions, the line was split wrong upstream, the kind was
     misread, or the key lacks a value that is really there.
   - **Misses:** the boxes are there but not joined; the light path drew one box over the whole value (one box, no
     parts); boxes are missing; or no caption or cue marks the parts (MM / DD / YYYY under the line, parentheses
     around an area code).

   Picture sheets of a dozen each, with links.
3. **Fix the biggest cause first**, measured on the tuning set. (One box over a whole date is NOT a cause: Andrew,
   2026-11-04 evening, "text groups count as a single field, so if the light path finds one box instead of finding
   three and grouping them, that's still a correct result"; the scorer grades values whole already.) Likely:
   - **Parts joined across questions:** find's run logic (a ZIP next to a phone, FEIN next to SSN, account number
     next to sort code joined as one).
   - **Parts drawn but not joined:** slots marked by punctuation only ("( )", "- -", "____/____/____").
   - **Parts not drawn at all:** the light path's boxes on printed slots (the bigger half of the misses on the key,
     2026-11-04: 169 values with no box on any part, 113 with some parts; the finder's work, not find's).

   Each fix goes to Andrew as problem and fix before code.
4. **Into the main light path** only when joining stops costing "fields found": fields-found F1 with splits at or
   above the light path alone (84.8 today). Then `benchmark_light.py` writes one arm, not two. Confirm on the
   benchmark key once.

**Done when:** split P and R on the tuning set are well above 51 / 55, fields found is not hurt, and Andrew has
decided about wiring it in.

## Notes

- The two parts touch each other in one place: a signature and its date on one line (`signature_complex` in find) is
  not a split value in the key, but its signature part is printed.
- Caption pairing (Part A step 2) would also help Part B where the part labels (Month / Day / Year) are printed
  under the line. It is parked in Claude's memory as a back-burner idea; this plan is the reason to pick it up.
- Uncommitted work from other sessions sits on dev (ignored fields, snap sweep, tuning-set options, light-path line
  splits). Do not stage files you did not change.

## Findings 2026-11-04 (read-only, scratch scripts; no repo code changed)

**The tuning key is thin on both counts.** None of its 899 pages was confirmed on the printed sheet (its 348
printed tags come from the sweeps: signature_sweep, field_add, review), and its Split Fields were tagged on the key
pages only. Numbers on it are a floor; a wrong call there is as likely the key's as the light path's.

- `benchmark_printed.draft` on the tuning pages: 348 candidates typed text in the key, 166 of them with the
  publisher's signature widget behind them.
- `compound_values.from_names` would add 78 date / phone / id splits (key has 210) on 11 library forms, 63 of them
  on lib__va_21p_527ez, lib__va_21_686c and lib__vba21526ez.

**Part A step 1, caption cue on the light boxes (scorer):** printed P 44.8 / R 77.3 / F1 56.8. Hits 269 of 348.

| misses (79) | | wrong calls (331) | |
|---|---|---|---|
| caption has no cue word | 24 | date / title beside the signature took the cue | 108 |
| box not found by the light path | 22 | key says text, page says sign (key gap, mostly) | 78 |
| no caption at all | 19 | cue belongs to a neighbour (key printed field within 40 pt) | 67 |
| cue landed on a neighbour box | 14 | not a key field (junk box) | 58 |
| | | not a key field, near a key printed field | 20 |

Rule variants: dropping any caption with a date / title word gives P 51.9 / R 65.8 / F1 58.0 (loses 40 hits whose
caption also has a neighbour's "Date"); shorter left reach (80, 40 pt) or dropping the above / left readings only
lose. The cue-to-wrong-box mix-up (about 190 of 331 wrong calls, 14 misses) is the thing to fix, not the word list.

**Part A step 2 count:** 1,212 sign / signature / initials / print cue words on the tuning pages; 590 have no light
box next to them, 498 one, 124 two or more. Of the 124: 73 have a box over and one under the cue (key: over 26,
under 9, neither 32, both 6); 38 a box beside and one under (key: under 29, beside 3, neither 5). So a cue with a
box beside it and one under it almost always captions the one under: the caption sits under the signature line.

**Part B, find kept to date / phone / id_number (scorer):** splits P 51.0 / R 55.2, fields found 81.1 / 88.5 / 84.6.
243 joins: date 146, id_number 66, phone 31. By a stricter count (a join is right only when the scorer's whole-value
match lands on a key split): right 90, P 37 / R 43.

| wrong joins (153) | | misses (120) | |
|---|---|---|---|
| key has these as separate fields (VA forms' MM/DD/YYYY, SSN: the key gap above) | 112 | boxes there, not joined | 54 |
| a part is not a key field (junk box / wrong line split) | 36 | some boxes missing | 29 |
| a key split plus a part of another question | 3 | no boxes at all | 23 |
| right value, wrong parts | 2 | one light box over the whole value | 9 |
| | | boxes there, joined differently | 5 |

"Boxes there, not joined" (54) is the detector's own gap; the samples: a phone with "( )" and nothing else over
it, an SSN with "– –" between the boxes, two dates on one line ("FROM (MM/DD/YYYY) TO (MM/DD/YYYY)"), underscores
with dashes (`____-_____-_______`), and a few with no cue at all. "One box over the whole value" (9) is small: the
line_split fix in step 3 is not the biggest cause.

**Proposed order (waiting on Andrew):**

1. Fill the tuning key before tuning on it: Split Fields from the validated names (`from_names`) on library forms
   when the key is built, and the printed sheet over the 171 tuning pages with candidates (166 fields have a
   signature widget behind them). Otherwise every number above is capped by the key.
2. Part B step 1 as planned: the benchmark's splits arm keeps find to date / phone / id_number.
3. Part A: caption pairing by position (a cue with a box under it captions that box, not the one beside; a cue
   between two rows goes to the row above unless the box above has its own caption), measured on the filled key.
4. Part B: the detector's cue reading for "( )", "– –" and two dates on one line, measured the same way.

Scratch scripts (session 2026-11-04, scratchpad): a1_caption.py, a1_variants.py, a1_pairing.py, a1_keycheck.py,
b2_splits.py, b2_words.py, keygap_names.py, keygap_printed.py.

**Later on 2026-11-04 (Andrew's go): both sets rebuilt from the S forms.** The gold standard is STRUCTURE VALIDATED
("accept structure": fields, kinds incl. printed, groups incl. Split Fields, grids, blocks). The key builder's
S-only rule (the other session's change, same day) was applied: key 833 -> 847 forms / 1,379 -> 1,397 pages (122
non-S library forms out, 136 newly accepted forms in); tuning set 274 -> 291 forms / 899 -> 925 pages (25 out, 42
in). Page files not in the new indexes removed; the old indexes and page JSONs are in the session scratchpad
(key_before/, dev_key_before/). Light path run on the new pages (Jev under $1); FFDNet not rerun (Andrew: not
needed; the ffdnet_l arms are incomplete on both sets). The printed sheet and its candidate list are superseded by
the S: a printed field is whatever the S form's blueprint says (Add / remove kind dropdown, Review tab); the "thin
key" worry above is closed, the 2026-11-04 findings' numbers are on the old set, and the builder's "not confirmed on
the printed sheet" line is now noise.

Rebuilt tuning set, light path alone: fields found P 81.2 / R 88.7 / F1 84.8; printed 0 (372 in the key); splits 0
combined (227 in the key).
Rebuilt benchmark key, light path alone (1,397 pages, 0 missing): fields found P 83.9 / R 88.2 / F1 86.0 (was 85.5 on the 2026-11-03 key); printed 0 (938 in the key); splits 0 combined (732 in the key). Jev for the new pages: $0.70 both sets.

**Part B step 1 DONE (Andrew's go, 2026-11-04): the detector itself reports dates, phones and ID numbers only**
(`compound_values.find(bp, kinds=FOUND)`, `kinds=None` for everything; the other kinds are still read so their runs
stay claimed). Test: tests/test_compound_values_find.py. Uncommitted. The Groups tab does not call `find` (its
suggestions come from group_finder), so nothing changes on the review page. The tuning set's light_splits arm was
rewritten from light_bp with the new find (no Jev); the key's light_splits arm is still the all-kinds one (no
light_bp saved for the key: a Jev rerun, about $2.50, or run the key with --keep next time).

Rebuilt tuning set, light + splits: fields found P 81.9 / R 88.6 / F1 85.1 (light alone 84.8); splits P 74.7 /
R 53.7 (227 in the key, 162 combined). That clears the plan's bar for Part B step 4 (joining no longer costs fields
found), so wiring find into the main light path is the next decision for Andrew; the 54 "boxes there, not joined"
misses (step 3) are the recall work.

**Taxonomy + derived arms (Andrew's go, 2026-11-04 evening), uncommitted:**

- `petey/validate/split_types.py`: the split-value taxonomy, one list with each kind's parts and a `counts` flag
  (date, phone, id_number on). Read by the Groups tab (`group_review.ENTITY_TYPES`), the detector
  (`compound_values.TYPES / PARTS / FOUND`) and the key builder (a tagged value of an uncounted kind, or with no
  type picked, is not a split value in the key: 14 untyped tags on key pages, 1 time on the tuning set, now plain
  fields). Tests: tests/test_split_types.py.
- `benchmark_light.py --derive`: the light_splits arm rewritten from the light arm + the key's page PDFs, no Jev
  (`splits_for`, `derive_splits`); after any detector or taxonomy change, derive and rescore instead of rerunning.
  Test: tests/test_benchmark_light_derive.py. The light_bp copies are no longer needed for splits.
- Both sets rebuilt again (Andrew accepting forms live): key 1,420 pages, tuning set 955; light run on the 53 new
  pages ($0.10); every page has a prediction in both arms.

| | fields found P / R / F1 | splits P / R | in the key |
|---|---|---|---|
| key, light alone | 84.1 / 88.0 / 86.0 | | 730 splits, 942 printed |
| key, light + splits | 84.7 / 87.9 / 86.3 | 65.0 / 42.7 | |
| tuning set, light alone | 81.3 / 88.7 / 84.8 | | 233 splits, 386 printed |
| tuning set, light + splits | 82.0 / 88.6 / 85.2 | 75.1 / 53.2 | |

Splits help fields found on both sets. Split P / R are lower on the key than on the tuning set (the key takes each
form's fullest pages). Next decisions: wire the detector into the main light path (Part B step 4); the key
builder's "printed candidates not confirmed on the printed sheet" line is a leftover of the retired sheet.

Key split misses by cause (2026-11-04 evening, scorer's count: 312 of 730 found, one box over the whole counted as
found): no box on any part 169, some parts 113, all parts drawn but not joined 145. Wrong joins 257 of 434: a junk
box among the parts 139, neighbouring values joined 100.

**Detector: a run ends where a later box has its own caption (Andrew's go, 2026-11-04 night), uncommitted.**
`compound_values._cut_at_captions`: a label printed between two boxes on their line, or a caption phrase with a real
word (not a part word, separator or item number) starting above a later box, cuts the run there; a phrase that began
over an earlier box spans the run. Captions below are not read (instructions and the next question sit there;
cutting on them lost right joins on both sets). Tests in tests/test_compound_values_find.py (the old detector joined
the ZIP + phone fixture as one phone). Variants were scored on both sets (a bend of the tune-on-the-tuning-set rule;
the tuning set alone picks the same one). Andrew asked whether this overfits: the rule is general, the samples are
small (233 / 730 values).

| | fields found F1 | splits P | splits R | joins |
|---|---|---|---|---|
| key, before | 86.3 | 65.0 | 42.7 | 434 |
| key, after | 86.4 | 71.6 | 42.7 | 402 |
| tuning set, before | 85.2 | 75.1 | 53.2 | 169 |
| tuning set, after | 85.2 | 79.3 | 55.4 | 169 |

Left in the wrong joins: 139 with a junk box among the parts (the light path's boxes), and the joins the page gives
no cue for. Left in the misses: boxes drawn but not joined (slots marked by punctuation only), and the parts not
drawn (the finder).

**Part A BUILT (Andrew's go, 2026-11-04 night), uncommitted.** `petey/validate/printed_caption.py`: a text field is
printed when its OWN caption (the split detector's position reading: above / inside / label before / under, a word
between two rows to the nearer field) has a signing cue and no date / title word. Wired: `flat_light.build` tags
the fields (`x_petey_printed`, source light_caption); `benchmark_light.to_prediction` emits kind printed;
`--derive` also rewrites the light arm's kinds, so both arms carry printed with no Jev. Tests:
tests/test_printed_caption.py, test_benchmark_light_derive.py, test_benchmark_score.py. Full suite passes.

| | printed P | R | F1 | in the key |
|---|---|---|---|---|
| tuning set, caption words anywhere beside the box (morning) | 44.8 | 77.3 | 56.8 | 348 (old set) |
| tuning set, own caption | 60.5 | 77.5 | 68.0 | 386 |
| key, own caption (confirming run) | 56.0 | 67.9 | 61.4 | 942 |

**Open for Andrew: print names.** On the S forms, "print name" boxes are typed text almost everywhere: of the
tuning set's 386 printed fields, 296 have a signature caption, 3 a print-name caption; 82 of the rule's 188 wrong
calls are print-name boxes. With the print-name cue dropped (signature + initials only) the tuning set gives P 72.0 /
R 77.5 / F1 74.7. Either the definition changes (printed names are text) or the S forms need their print-name boxes
retagged; the cue list is `printed_caption.CUE`. Misses left (tuning set): box not found 36, own caption has no cue
31 ("signs here", "signed:", "x"), no caption 18, signature and date in one caption 14.

**Decided (Andrew, 2026-11-04 night): a printed name is NOT printed** ("'print' is the wrong field type, probably,
but I meant it like 'likely to be hand-written, not typed'"). `printed_caption.CUE` = signatures and initials.
Printed after the change: tuning set P 72.0 / R 77.5 / F1 74.7 (386 in the key); key P 66.0 / R 67.7 / F1 66.9 (942).

**Rebuilt again 2026-11-04 night (Andrew: "a couple dozen more validated forms"):** key 889 forms / 1,478 pages
(961 printed, 762 splits), tuning set 317 forms / 995 pages (403 printed, 245 splits); light run on the 98 new
pages ($0.22); arms derived. Light + splits: key fields found 86.5, printed P 66.3 / R 68.2, splits P 70.7 / R 43.3;
tuning set 85.3, printed P 71.2 / R 76.7, splits P 79.9 / R 55.1.

**DIRECTION (Andrew, 2026-11-04 night): "we are at the limit of what rules can do", train local models for printed
and splits**, on top of the finder's boxes (the finder stays the box source). Pattern: the same-box model
(eval/same_box_train.py: numpy logistic regression, folds by form, weights pasted into the module; the venv has
numpy only). Design proposed, awaiting go: see the chat of 2026-11-04 night / the next handoff.

**Printed MODEL trained (2026-11-04 night), uncommitted.** `petey/validate/printed_model.py` (features: box size and
place, own caption cue flags + 150 learned caption words, loose beside reading, X mark, neighbours on the line and
their captions) + `eval/printed_train.py` (numpy logistic regression, balanced classes, L2 1e-3, 400 steps; five
folds by form; cut for best F1; --paste writes the constants). Tuning set: 23,518 light boxes, 364 printed; folds
P 71.9 / R 84.3 / F1 77.6 at cut 0.85 (a longer, lighter fit overfits: 74.1). `printed_caption.find` uses the model
when its weights are set, else the caption rule. Scorer: tuning set printed P 75.1 / R 83.9 / F1 79.2 (in sample),
KEY P 68.0 / R 73.0 / F1 70.4 (was 67.2 with the rule). Fields found unchanged.

**Split MODEL trained (2026-11-04 night), uncommitted.** `petey/validate/split_model.py` (pair features: gap and
sizes, what is printed between, each box's own caption and a phrase spanning both, the run's cue words and part
labels, run length and place, 100 learned caption words; `chains` = maximal stretches of pairs >= CUT) +
`eval/split_train.py` (labels: both boxes matched to one key split value = 1, matched apart = 0, a box the key lacks
left out). Tuning set: 5,099 pairs, 272 positive; folds by form P 63.8 / R 68.8 / F1 66.2 at cut 0.85.
`compound_values.find` uses the model's chains per run when the weights are set (after the part-word captions), the
kind from the caption over the chain else the separators between the boxes (`_chain_kind`: slashes date, bracket
phone, dashes id_number, else "other" and not counted); else the caption-cut rules.

| light + splits, both models | fields found F1 | printed P / R / F1 | splits P / R |
|---|---|---|---|
| tuning set (in sample) | 85.5 | 74.9 / 83.9 / 79.2 | 90.5 / 64.1 |
| key (held out) | 86.6 | 68.0 / 73.0 / 70.4 | 76.2 / 44.0 |
| key, rules only (before) | 86.5 | 66.3 / 68.2 / 67.2 | 70.7 / 43.3 |

Split recall on the key barely moves because its misses are mostly parts the finder never drew. Retrain: run the
two trainers with --paste after any change to the tuning set, then --derive. CommonForms signature lines as extra
printed positives: parked until Andrew says.

**FINDER (Andrew, 2026-11-04 night: "if these are finder problems, we need to improve the finder").** Tuning set,
the key's split parts with no light text box (320) and printed fields with no light box (39), by what the finder did
(scratch missing_parts.py, squares.py, nocand.py):

| | split parts | printed |
|---|---|---|
| no finder candidate at all | 155 | 25 |
| kept, but typed as a choice box (character cells read as checkboxes) | 131 | |
| a candidate the Jev screen dropped (or lost in a line split) | 34 | 14 |

- Cells as checkboxes: 236 key text fields on the tuning set are light choice boxes (lib__nj1040 125,
  bm__pb_d985db100931 45, fin__pb_9dec7f6d42d5 20): rows of 8-14 same-size squares 13-20 pt wide, spaced, no word
  beside. "N same squares in a row" alone is weak (>= 7: P 57 / R 67; real checkbox rows exist); the tell is the
  captions (a checkbox row has a word beside each box).
- No candidate: under the parts the page draws a rect / fill 47, nothing (glyphs: "_ _ /_ _/_ _" with spaces,
  "......" leaders, "( ____ )____") 26, a line 23. nov3__pb_77eaaa8ca70f p5: the cell is a white-filled rect
  with no stroke inside a stroked outer box; the finder takes the outer box only.
- Screened out: lib__urla p1 SSN cells proposed exactly, Jev 0.49 / 0.48 / 0.39 vs KEEP 0.6.

Proposed order (awaiting go; a finder change re-keys the box cache): (1) typing of cell rows (131 parts + 236
fields), (2) candidates for white-fill cells, spaced underscores and dot leaders (155 + 25), (3) the screen's keep
line for cells that are parts of a run (34 + 14).

**Decisions 2026-11-04 night.** No FFDNet (Andrew: "we have 75 thousand labeled boxes and a fairly robust method for
finding fields"; the light path over-predicts more than it misses). The screen stays code + Jev (no is-a-field
model). A kind question on Jev would ride on the screen's request as a second question per box (Jev takes several
questions per request on one picture), but the batch of 20 was calibrated for one question and the answer side
doubles, so it is a re-calibration plus a slower screen: the local type model first, the Jev question the fallback.
Why not a VLM: exact geometry from the page, reproducible and inspectable structure, the house definitions learned
from the S forms; a VLM judges candidates (Jev's role), it does not replace the finder.

**TYPE MODEL trained + wired (uncommitted).** `petey/validate/type_model.py` (choice vs text over the kept boxes:
size and shape, the finder's own kind, same-size company in the row and the column, a word right beside / before /
over / under, separators and part labels, 100 learned beside-words) + `eval/type_train.py`. Tuning set: 27,651 matched
boxes, 8,838 choice; folds by form wrong 487 (the finder's shape call 669): choice called text 433 -> 287, text
called choice 236 -> 200; interaction features (row of squares with no word beside) did not help (501). Wired:
`flat_light._retype` after the screen (a radio the model keeps a choice stays radio; `retyped_from` kept),
`benchmark_light.retype` in --derive (a flipped box leaves its group). Tests: tests/test_type_model.py,
test_flat_light.py, test_benchmark_light_derive.py; full suite passes.

| light + splits, three models | fields found F1 | typed right | printed F1 | splits P / R | groups F1 |
|---|---|---|---|---|---|
| key (held out) | 86.7 (was 86.6) | 97.4 (was 96.5) | 70.5 | 74.8 / 46.3 (was 76.2 / 44.0) | 70.0 |
| tuning set (in sample) | 85.6 | 98.3 | 79.2 | 89.4 / 67.3 | 79.9 |

Retrain order after a tuning-set rebuild: type_train --paste, printed_train --paste, split_train --paste, then
--derive on both sets (the type model changes the boxes the other two see).
