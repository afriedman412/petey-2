# Benchmark judgement questions

The calls still to make about how the flat-structure benchmark counts things: what a field is, which fields belong
together, and what the answer key says when the page and the publisher's widgets disagree. Edited in place; a question
moves to "Decided" with Andrew's words and the date once he settles it. Terms: `docs/GLOSSARY.md`.

The benchmark (2026-10-26): on single flat pages, find each field and its visible kind (text, signatures included, or
choice), then the fields it belongs with. Tier 1 is fields and kind, tier 2 option groups, tier 3 grids (same row,
same column) and blocks (same copy, same slot). Scored pairwise plus groups, grids and blocks rebuilt exactly.

## Decided

- Single pages, not documents. Purely structural: compound values (date parts, SSN, name parts, address) are out; they
  need meaning (2026-10-26).
- Kinds are the visible ones only: text (signatures count as text) and choice (checkbox and radio together). Comb is
  not a kind (2026-10-26).
- About 1,000 pages, diverse across pages: caps per form (~2 pages) and per publisher; the VA / IRS / USCIS families are
  "variations on a theme" (2026-10-26).
- Input is digital PDFs. FFDNet is a comparison only, never a dependency; mini-CommonForms (images only) a secondary line
  at most (2026-10-26).
- Validated blueprints are the answer key for all three tiers; grid and block membership in them is hand-validated
  (2026-10-26).
- The business-like set: a form is in when Jev's business screen scores >= 0.85 and it has >= 40 widgets; government is
  fine (2026-10-27). 427 forms in `runs/benchmark/blueprints/` (review ids `bm__sd_*`).
- Checklists are ignored (2026-10-28, Andrew: "we need to ignore checklists"): the filer's own tick lists (documents to
  attach, steps done) are not fields for the benchmark. What counts as a checklist, and whether to drop them from the
  key or the pages, still to set down.

## Before the full run

Fix the tiers and these calls before scoring the full set: choosing after seeing scores reads as cherry-picking
(raised 2026-10-26).

## 1. One ruled line holding several fields: one field or several? (2026-10-27, waiting)

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

## 3. Combs (2026-10-27, needs a word)

The 2026-10-26 note says a comb is "one text field, or per-cell partners". The scoring needs one of the two, or a rule
for when each applies (the line split keeps a comb whole: 3+ equal cells <= 25 pt). Cases: bm__sd_531654's date and
number combs (one widget over 7-9 cells), bm__sd_7180896's driver number, bm__sd_8219299's ID number.

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

## 8. Is this new? (2026-10-26, open)

A novelty check against prior work (form understanding datasets, CommonForms / FFDNet, VAREX) before writing it up.
Not started.

## 9. The 237 forms that failed the business cut (2026-10-27, needs a word)

The first SafeDocs harvest's 374 forms were staged before the business screen; 237 fail Andrew's rule and are still in
`runs/flat/blueprints/` as `fl__sd_*` (fl__sd_1443547 and fl__sd_7919716 among them). Keep them as a separate
homemade set (useful: one-line-many-fields rows are common there), or move them aside.

## 10. Text boxes answered "Y" or "N" (2026-10-27, open)

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
could be a grid of per-row groups) and strike-out choices ("delete whichever is inapplicable"). Cases: none logged yet.

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
(2026-10-28, Andrew: "a messy example").
