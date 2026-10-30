# Benchmark judgement questions

The calls still to make about how the flat-structure benchmark counts things: what a field is, which fields belong
together, and what the answer key says when the page and the publisher's widgets disagree. Edited in place; a question
moves to "Decided" with Andrew's words and the date once he settles it. Terms: `docs/GLOSSARY.md`.

The benchmark (2026-10-26): on single flat pages, find each field and its visible kind (text, signatures included, or
choice), then the fields it belongs with. Tier 1 is fields and kind, tier 2 option groups, tier 3 grids (same row,
same column) and blocks (same copy, same slot). Scored pairwise plus groups, grids and blocks rebuilt exactly.

## Decided

- Single pages, not documents. Purely structural: compound values (date parts, SSN, name parts, address) are out; they
  need meaning (2026-10-26). Superseded 2026-10-28: Split Fields are in (below), feasibility pending.
- Kinds are the visible ones only: text (signatures count as text) and choice (checkbox and radio together). Comb is
  not a kind (2026-10-26). Still holds: the draft below lists Signature separately for how it is drawn, not as a
  different kind of answer.
- Andrew's draft of the benchmark's definitions is in `PETEY BENCHMARK HEURISTICS AND GLOSSARY` (repo root, 2026-10-28):
  Fields of three Types (Text, Choice, Signature) and four kinds of Collection (Groups, Entities, Grids, Blocks); Entity
  renamed Split Field (below). Signatures (Andrew, 2026-10-28): "text fields for all intents and purposes, but they are
  rendered and located in specific and challenging ways, and often are not strongly denoted on the page. I don't think
  the difference is all that meaningful on paper"; "annoying but an unavoidable part of forms." Which Collections go
  into the benchmark depends on whether finding them is feasible ("still figuring out").
- Membership (2026-10-28): a field is in at most one Group or Split Field, and in at most one Grid or Block. A Group or
  Split Field sits in a Grid or Block as one field (Andrew: "a field can be part of an entity within a block", entity =
  Split Field).
- Group: reopened. "The answers to one question" (2026-10-28, Andrew: "a much better way to put it") was taken back the
  same day: "we are limited by what's written on the page, and we are pretty frequently just using structure and
  context." Proposed instead, not decided: Choice Fields the layout presents as options under one prompt (one shared
  caption above or left; together in one line, column or cell with no other field or prompt between; each with a short
  label of its own or none); boxes that each carry a full sentence stay ungrouped; unclear layouts stay ungrouped. He
  will add encodings for recurring arrangements of choice fields, taken from his examples (see 13).
- Split Field (2026-10-28, Andrew; first drafted as "Entity", then "Compound Value") = Text Fields in sequence on one
  line making one value (dates, phones, addresses, ID codes). Full addresses are in "because they often span a single
  line" (2026-10-28). Graded as one value, however it is cut (2026-10-29, below).
- Values are graded whole, not by how they are cut into fields (2026-10-29, Andrew: "better off adjusting the grading
  than adjusting our process. the goal is to connect pieces of one thing that are potentially split between fields,
  but the output is the one thing. so maybe the idea for the benchmark is 'find this date' or 'find this entire SSN'";
  the aggressive split detection was "a downstream concern for easier naming and better block grouping"; "a little
  bit on the edge of structure and meaning, but that's less of an issue than reconsidering the entire way the light
  path works"). The key's unit is the value: a Split Field (all its fields together) or a field holding a whole value
  on its own (a comb drawn as one widget). A comb, a date in three boxes and one box over the whole date are the same
  answer. The key stays as the publisher cut it; no comb splitting. How a found value is matched to the key's (the
  area its fields cover, or the key fields it takes in) stays open until the set is assembled and labeled (Andrew,
  2026-10-29). Difficulty is handled then too: by which pages are chosen, or a difficulty measure for each grouping
  ("we can wait to figure that out until the labeling is done").
- What a grouping is, is not graded, only that its fields are grouped (2026-10-30, Andrew: "we don't need to identify
  the type of grouping, just that they are grouped. want to keep text interpretation to a minimum"). A Split Field's
  type (date, phone, ID number: the Groups tab's entity type) is not in the key's grading; the Groups tab can still
  record it for the product's naming.
- Input and aim (2026-10-30, Andrew): "the input is a PDF with text layer and no widgets, and the specific goal is to
  do this without VLM." What sets the set apart from the prior work in 8, all of which scores page images. The line:
  "no general-language models"; small local models are fine. Priorities "size and (to a lesser extent) locality.
  price too, but that is downstream of both of those." Jev is "ok for now" (a stopgap). Why: "the goal is extracting
  data form structure with a few minor bells and whistles, because once you have that, you can do programmatic
  extraction forever, fast, cheap and local."
- Grid (2026-10-28, Andrew): "every row is a single data point and every column is a feature (axes can be swapped)".
  A row number counts as a row's identifier.
- Every hard case is a located field of one of the three Types (2026-10-28): a comb is a collection of fields (one per
  cell; graded as one value since 2026-10-29, above); a line holding several answers is several fields (settles 1 for
  the key); a Y / N text box is a Text field (settles 10 for the benchmark); leaving out checklists is a note on how
  the set is built.
- Grids and blocks stay, marked conservatively (2026-10-28). Andrew weighed dropping them ("they are mostly tools for
  naming consistently, and they are arbitrary"), then: "proceed as normal but stop being so aggressive with making
  [blocks] and grids." Only clear cases go in the key; judgment calls stay unmarked, as with groups (err ungrouped).
- Blocks across pages vs single pages (4): open, Andrew 2026-10-28: "how to split the difference between these
  definitions in a Petey context and in the context of the benchmark."
- About 1,000 pages, diverse across pages: caps per form (~2 pages) and per publisher; the VA / IRS / USCIS families are
  "variations on a theme" (2026-10-26).
- Input is digital PDFs. FFDNet is a comparison only, never a dependency; mini-CommonForms (images only) a secondary
  line at most (2026-10-26).
- Validated blueprints are the answer key for all three tiers; grid and block membership in them is hand-validated
  (2026-10-26).
- The business-like set: a form is in when Jev's business screen scores >= 0.85 and it has >= 40 widgets; government is
  fine (2026-10-27). 427 forms in `runs/benchmark/blueprints/` (review ids `bm__sd_*`).
- Checklists are ignored (2026-10-28, Andrew: "we need to ignore checklists"): the filer's own tick lists (documents to
  attach, steps done) are not fields for the benchmark. What counts as a checklist, and whether to drop them from the
  key or the pages, still to set down. Defined 2026-10-28 (Andrew): "not just a list of checkmarks, it's specifically
  a list of requirements or documents provided for the user of the form. They aren't rendering data that is useful
  downstream, probably." A call on purpose, not layout, and on what is useful in the set, not a scoring mechanic
  (Andrew: "this isn't a functional issue, it's a question of what is useful as a part of this benchmark"): made when
  the set is built.

## Before the full run

Fix the tiers and these calls before scoring the full set: choosing after seeing scores reads as cherry-picking
(raised 2026-10-26).

## 1. One ruled line holding several fields: one field or several? (2026-10-27; key settled 2026-10-28: several)

Publishers often draw one widget along a line that takes several answers: fl__sd_1443547's pick-up table (one widget
per row under Name / Address / Phone / Relationship to child), bm__sd_402696's dependent rows (six captions under each
line). The benchmark's starting key comes from the original widgets, so it counts these rows as one field each.

Options: keep the publisher's one field; split by the printed columns (captions or column rules); accept either.

Andrew (2026-10-27): "that's the fundamental question, and I think we are going to have to wait to see if it's viable."
Where splitting stands: the light path now cuts these lines (`eval/line_split.py`, commit e6349d5). On 152 lines judged
by eye, 64 of them holding several fields, column rules or Jev >= 0.6 split 60 of the 64; the wrong splits are mostly
junk boxes the is-field screen kept. Not reached: lines with no rule or caption to cut at, and a few Jev scores just
under the cutoff (fl__light3_sd_7919716 p1_f2, p2_f7). Andrew's hint, confirmed: these lines are longer than the form's
usual field (>= 4x the median width: 11% hold several fields, against <= 3% for shorter lines).

## 2. Fields the publisher left without a widget (2026-10-27, open)

Same root as 1: the key starts from the original widgets, and publishers skip fields. The finder's new underline rule
(commit 9429ea6) found signature and date lines with no widget behind them, and lines like bm__sd_402696's
"LAST NAME / FIRST NAME / STUDENT ID #" row with none at all. Against the widgets these count as false finds.

Options: add them to the key by hand during validation; leave the key as the publisher drew it and report finds with
no widget separately; count only fields some widget backs.

## 3. Combs (2026-10-27; settled 2026-10-29: graded as one value, the key not split)

The 2026-10-26 note says a comb is "one text field, or per-cell partners". The scoring needs one of the two, or a rule
for when each applies (the line split keeps a comb whole: 3+ equal cells <= 25 pt). Cases: bm__sd_531654's date and
number combs (one widget over 7-9 cells), bm__sd_7180896's driver number, bm__sd_8219299's ID number.

2026-10-28, Andrew (on [bm__sd_2560846 p2-G2](http://localhost:5005/#review/bm__sd_2560846/p2-G2), four 20-cell account
number combs, one widget each): keep the cells as fields and make each comb a Split Field? Asked to do it across the
set; he decides how on 2026-10-29. Read-only scan (`runs/benchmark/comb_scan_2026-10-28/`: script, `combs.json`, sample
sheets): 2,307 widgets cut into exact combs by printed rules (2,208 full-height rules, 99 tick marks), 25,618 cells, 151
of 2,664 forms; a third on three forms (pb_43936af1594f 261, pb_474afba05c55 84, pb_8b6d026df458 44). 294 more
"near" combs (only some cells comb-width) are mostly junk (checkboxes, lone boxes, a comb drawn with a wider field):
left out. Plan offered: each cell a text field (p2_f7 -> p2_f7_1..20), tagged one Split Field (`x_petey_entity`),
blueprints and records snapshotted first (`runs/` is not in git), forms with an open draft skipped. Reach: Grids-tab
records on 90 of the 151 forms name the comb as a cell, so Grids and Blocks must first treat a Split Field as one
position, or each comb grid falls apart into one column a cell; verdicts on 17, Groups records 19, Add / remove 6, open
drafts 7. His calls: (a) a `comb` Split Field type (combs hold cities, dates, money, account numbers) vs id_number /
other; (b) a date or SSN comb drawn as three widgets: one Split Field of all its cells (a field is in one Split Field
only) vs three; (c) Grids / Blocks change first, then the split; (d) combs the publisher already drew one widget a
cell: tag them too, or only split the joined ones.

2026-10-29, Andrew: grade values whole instead (Decided, "Values are graded whole"). The split is not done; the four
calls fall away. The scan stays as a count of combs in the set.

## 4. What a block is (2026-10-27, open)

Raised on fl__sd_2420367 (IPMA-HR award nomination): page 1's nominated agency and page 2's person submitting share an
eight-row layout (Address, City, State / Zip, Phone / Fax, Email under three rows whose labels differ: Agency, Contact
Name, Title vs Name, Title, Employed by). BT1 as found holds rows 4-8 only, and misses Zip on both pages (page 2's Zip
line starts 4 pt further left). Andrew is undecided on how the benchmark should set this. Proposal, not decided:

- **Single pages:** a block counts only when two or more of its copies are on the same page (this form adds no block
  pairs: one copy a page).
- **Same copy** (fields describing one thing) from structure: the repeated section under one heading, all of it, the
  top three rows included.
- **Same slot** (one question asked of each copy) only where the printed label repeats (Address, City, State, Zip,
  Phone, Fax, Email); fields whose labels differ (Agency / Name, Contact Name / Title) are members of their copy with
  no slot partner.
- **Second case, size not label (bm__sd_1242044, Axeon credit application):** billing and shipping address are BT2 (City,
  State, Zip, Country, two copies); the Address line above each is left out because shipping's is 178 pt wide against
  billing's 264 (shortened for its "Same as above" checkbox) and the finder matches boxes within 3 pt. Andrew: the blocks
  should probably include the top field. Possible fix: when growing a block, take a box at the offset whose printed
  label matches copy 1's even when its size differs.
- **Grid or block? (bm__sd_5985401 p5-G3):** [p5-G3](http://localhost:5005/#review/bm__sd_5985401/p5-G3), 2026-10-27,
  Andrew: "can't decide if [it] should be a grid or a block". Not looked into yet. A case for where the line between
  the two sits (section 5: every row one data point, every column about it alone). Second case:
  [bm__sd_2801296](http://localhost:5005/#review/bm__sd_2801296) page 4 (2026-10-27, "grid v. blocks").

## 5. What a grid is: grids by geometry (2026-10-27, parked: more validated data first)

Andrew: grids are defined partly by geometry: each column's boxes share a width and each row's a height (columns and
rows may differ from each other), reasonably uniform spacing, a field in most slots (not every one), and labels
consistent down each column (one header, or the same caption repeated under every row, as bm__sd_1115475's unruled
sections A-C; labels changing row to row are separate questions). The name test (`grid_naming.iterated`) stays a
second way in.

Measured read-only on validated lib / je forms against the Grids-tab records (scratchpad `geo_grids.py`): of 731 grids
kept the geometric draft accepts 351 (48%), the name test 709 (97%); of 140 cancelled, 60 and 129, so the cancelled set is
mostly grids redrawn or not wanted, not a clean negative set. The draft rejects mostly on its label reader (514: row labels
of ledgers read as changing captions), then size (322), spacing and row heights (~180 each, ledgers' taller rows). It
would add 62 candidates nobody has judged (ao040b p1 27 x 3, boat application 4 x 6, some doubtful 2 x 3s). Next, when
Andrew has validated more: tune it on the kept grids, look at the 62, then decide whether library forms use it.

## 6. Starting groups come from the system being benchmarked (2026-10-26, open)

The staged `bm__` blueprints start with groups from the light path's own rules (publisher radio groups kept, plus code
and Jev joins), and grids / blocks from `structure.find`. Validating them by eye anchors the key toward what the system
already does. Options: validate from a blank start on a sample to measure the anchoring; strip the starting groups on
part of the set; accept it and say so.

## 7. Near-duplicate layouts and caps (2026-10-26, open)

The caps are per form and per publisher, but different publishers reuse one layout (the same vendor template, a
rehosted government form). Open: a page fingerprint to catch near-duplicates across publishers, and what the cap is for
a fingerprint.

## 8. Is this new? (2026-10-26; first survey 2026-10-30)

A novelty check against prior work (form understanding datasets, CommonForms / FFDNet, VAREX) before writing it up.

Survey 2026-10-30 (two web searches, claims checked against papers / dataset pages; a few marked not verified):

- **Finding fields alone is not new.** CommonForms (2025, WACV 2026; ~59k Common Crawl PDFs, labels taken from
  AcroForm widgets, text / choice / signature, COCO mAP, no grouping; FFDNet-L 81.0 mAP), mini-CommonForms (DAS 2026,
  a cleaned subset, calls itself a benchmark), Nutrient's form-field-v1-benchmark (Aug 2026, vendor, public
  leaderboard, 2,334 blank pages; best mAP on blank pages 0.526; label origin not stated), AutoFormBench (2026, 407
  hand-labeled PDFs, checkbox / line / box, coarse F1). All score images by object detection; none takes the vector PDF;
  none has combs or split values; the widget-labeled ones miss what was never made fillable (CommonForms says so).
- **Closest prior on grouping: Adobe's Forms Dataset (2020: Aggarwal WACV, Sarkar ECCV, Form2Seq EMNLP).** Blank,
  mostly government forms; hand-labeled widgets, Fields (caption + 1..n widgets), ChoiceFields, ChoiceGroups, tables
  and lists (ECCV); an exact-member group metric, the same idea as ours. But only 400 images released (the rest held
  back "due to legal issues"), CC BY-NC-ND, no harness; Form2Seq is handed the widgets, so it scores grouping only;
  split values are folded into Field, not a relation of their own; no repeated blocks. Must be cited.
- **Others:** FormStruct-Bench (Aug 2026, synthetic filled images from 70 templates; WG-F1 scores option membership:
  read the full paper before claiming "first to score option groups"); NAF (2019, historical filled scans, field-field
  and row / column links); FUNSD / XFUND / Form-NLU / DocILE / VRDU / CORD (filled forms, key-value links, not fields);
  form-filling benchmarks (FormGym, PDF Bench) score filling, not structure. BaFCo (ECCV 2026) not inspected.
- **What is open:** finding fields and grouping them in one task, from a page with no widgets; vector PDF input;
  split values (date boxes, SSN parts, combs) as a relation, graded whole; option groups + split values + grids +
  blocks in one hand-validated key; ~1,000 pages from many publishers; an open licence.
- **Contamination:** CommonForms was built from the same 2021 Common Crawl PDF crawl as the SafeDocs harvest
  (`bm__sd_*`), so FFDNet may have trained on some benchmark pages. Check the overlap before using FFDNet as a baseline.

## 9. The 237 forms that failed the business cut (2026-10-27, needs a word)

The first SafeDocs harvest's 374 forms were staged before the business screen; 237 fail Andrew's rule and are still in
`runs/flat/blueprints/` as `fl__sd_*` (fl__sd_1443547 and fl__sd_7919716 among them). Keep them as a separate
homemade set (useful: one-line-many-fields rows are common there), or move them aside.

## 10. Text boxes answered "Y" or "N" (2026-10-27; benchmark settled 2026-10-28: Text)

[bm__sd_5952614](http://localhost:5005/#review/bm__sd_5952614) has an array of text boxes the page says to fill with Y or
N (Andrew: "need to decide how to deal with an array of 'put Y or N' text boxes"). Two earlier calls pull different
ways: the benchmark's kinds are the visible ones only, and this box looks like text; but where the page shows a yes / no
choice the blueprint models what the page shows (2026-10-15, the boat application's YES / NO columns built as text
widgets became yes / no pairs). There the page printed two boxes; here it prints one box and asks for a letter. Options:
text (what is drawn); a choice field of one box with values Y / N (what it means, and meaning is out of the benchmark);
text in the benchmark, a Y / N value in the product blueprint.

Second case: [bm__sd_6490706](http://localhost:5005/#review/bm__sd_6490706), 2026-10-27, Andrew: "another array of
text boxes that should be bools" (his lean: booleans).

## 11. "Circle one: YES NO" (2026-10-27, open)

Printed choices with no box, answered by circling a word (Andrew: "figure out what to do with 'circle one: YES NO'").
Nothing to detect as a field on the page, yet the answer is a choice. Options: a choice field per word, its box the
printed word (the page shows the choices, "page over metadata"); out of the benchmark as having no field; a text field
over the line. Related, parked 2026-10-15: circle-response grids (je__student_athlete_forms_157 p3, levels 0-3 per row,
could be a grid of per-row groups) and strike-out choices ("delete whichever is inapplicable"). Cases:
[bm__pb_996e62b8f783](http://localhost:5005/#review/bm__pb_996e62b8f783) page 2 (2026-10-28, Andrew: "circle fields
('circle the value that applies' or similar) -- need to figure these out").

## 12. "Official use only" / "office use only" sections (2026-10-28, open)

Andrew: "I need to decide what we are going to do about 'official use only'/'office use only' stuff." Fields the filer
never fills, left for the receiving office. Options: fields like any other (they are on the page and someone fills
them, and a filed form read back may carry them); out of the benchmark, as checklists are (decided 2026-10-28: the
filer's own tick lists are not fields); in the key but marked, so they can be scored with or without. Whatever is
chosen for the benchmark, the product blueprint may still want them (an office reading its own stamped forms).
Cases: none logged yet.

## 13. Stacked questions answered with checkboxes (2026-10-28, open)

Andrew: "I need more consistency on how vertically stacked questions that have checkbox answers or associations are
handled." A column of questions, each answered by its own boxes (Yes / No, or a few options), laid out alike down the
page. What the rules say today, from different decisions:

- **Groups:** each question's boxes are one option group (Yes / No pairs are the clear case; err ungrouped otherwise,
  2026-10-15).
- **Blocks:** a list of different Yes / No questions laid out alike is no block (I-360, 2026-10-22: SIA drops patterns
  made only of tick boxes).
- **Grids:** labels that change row to row are separate questions, not a grid (section 5); yet every row is one data
  point and the Yes / No columns relate to it alone (2026-10-27 definition), so the same stack can read as a grid.

So one stack can come out as loose groups, a grid, or (with a text box per row) blocks, depending on which finder
reaches it first. To set: which of the three such a stack is, and whether an "association" (the follow-up text box,
"if yes, explain") changes it. Cases: [bm__mu_204c0491798c](http://localhost:5005/#review/bm__mu_204c0491798c) page 1
(2026-10-28, Andrew: "a messy example"); [bm__sd_4808835](http://localhost:5005/#review/bm__sd_4808835) page 2
(2026-10-28: "another big checkbox array I need to consider (this is not aggressive grouping)"); [bm__sd_4821735](http://localhost:5005/#review/bm__sd_4821735)
page 1 (2026-10-28: "another checkbox array"); [bm__sd_4828646](http://localhost:5005/#review/bm__sd_4828646) page 2
(2026-10-28: "another array"); [bm__sd_4883926](http://localhost:5005/#review/bm__sd_4883926) page 1 (2026-10-28:
"another checkbox situation for me").

## 14. Noise and skew (2026-10-28, open)

Andrew: "do we want to include noise in the data set? skew? something to consider." The set is clean digital PDFs, as
the product is (decided earlier: scans and handwriting out of scope; "Input is digital PDFs" above). Options: clean only,
matching the product; a separate robustness split, the same pages degraded (noise, skew, blur, rasterised) so the clean
scores stay comparable; real scans as their own set later. A degraded copy keeps its answer key (the boxes move with a
known transform), so it costs little to make; whether to report it is the call.

## 15. How precise a field's location must be (2026-10-29, open)

Andrew: "I'm thinking about how precise we want to be with field ID's for the benchmark". To set: when a found text
field counts as the answer key's field (how far its box may differ in place and size), and whether a field drawn a
little off is graded wrong or right. Test case, if he comes back to it:
[fin__pb_9dec7f6d42d5](http://localhost:5005/#review/fin__pb_9dec7f6d42d5) page 2 ("issues with text field
identification, not a huge problem"; logged in STRUCTURE_ERRORS, fields the wrong shape).

## 16. Checkbox hierarchies (2026-10-30, open)

Andrew: "difficult checkbox hierarchy question". Boxes nested under other boxes (an option whose choice opens options of
its own). To set: whether the sub-options are a group of their own, part of the parent's group, or tied to the parent
box some other way, and how the benchmark grades that. Case:
[fin__pb_bdbbcb1e5299](http://localhost:5005/#review/fin__pb_bdbbcb1e5299) page 1;
[fin__pb_5b1f96bd91b6](http://localhost:5005/#review/fin__pb_5b1f96bd91b6) page 2 (2026-10-30: "another group hierachy
question"). Related: 13 (stacked questions).

Guidance from the second case (Andrew, 2026-10-30): "text groups shouldn't cross grid lines -- but that's heuristic
guidance, not something we should hard code for now." A text group (an entity, a split field) stays inside one cell of
a grid. For the benchmark's guidance, not a rule in the finders.
