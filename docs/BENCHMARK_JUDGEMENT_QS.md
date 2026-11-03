# Benchmark judgement questions

The calls about how the flat-structure benchmark counts things: what is decided, and what is still open. Edited in
place; a question moves to "Decided" once Andrew settles it. How the scorer works today: `docs/BENCHMARK_SCORING.md`.
Terms: `docs/GLOSSARY.md`. Streamlined 2026-11-02 (the earlier history: git, and
`runs/benchmark/BENCHMARK_JUDGEMENT_QS_before_streamline_2026-11-02.md`). Open questions keep their old numbers, so
references elsewhere still point to them.

## Decided

### The task

- One flat page at a time: a PDF with a text layer and no widgets. Find each field and its type, then which fields
  belong together (2026-10-26).

- Without VLMs or general-language models; small local models are fine. Priorities: size, then locality, then price
  (2026-10-30, Andrew: "once you have that, you can do programmatic extraction forever, fast, cheap and local").

- Scored: fields found, typed right, grouped, and text groups combined. Not scored: names, what a field means, what
  kind of group a group is, grids, blocks (2026-10-30).

- FFDNet is a comparison only, never a dependency; mini-CommonForms (images only) a secondary line at most (2026-10-26).

### The set

- About 1,000 pages, at most two a form, a generally diverse mix rather than a picture of the library (2026-11-02). No
  source folder over 10% of pages; government at most 60-65%. Measured 2026-11-02 (1,088 pages, 643 forms): about 78%
  government. To close the gap: private-sector forms first (a "private" section on the review page, set "private" in
  the key), government forms held back except to fill a missing publisher type.

- The business-like set: Jev's business screen >= 0.85 and >= 40 widgets (2026-10-27). 427 forms, `bm__sd_*`.

- Pages need not be blank (2026-10-31): a filled page is fine when its key can be drawn. Still digital PDFs.

- Validated blueprints are the answer key (2026-10-26).

- Near-duplicate layouts: every library page fingerprinted (`eval/page_inventory.py`, `eval/page_dups.py`); copies of
  one form archived; different forms on one layout stay two forms; a key page that repeats another is ignored (was 7,
  2026-10-31).

- Any key page can be ignored, with a reason, on the review page ("ignore page") or the /sweep sheet; the key and the
  scorer leave it out (2026-10-31). This is how checklist pages (the filer's own lists of documents or steps) and
  pages with few fields are dropped.

### Fields and types

- Anything on the page that could hold information is a field, office-use sections included (was 12, 2026-10-31).
  Fields the publisher drew no widget for are added during validation (sweeps, finder suggestions).

- Three types (2026-10-31): text; choice (checkbox and radio alike); printed (anything expected to be handwritten:
  signatures, initials, printed names). The date of signing and the signer's title are text. Printed is stored on the
  blueprint (`x_petey_printed`).

- Types follow the page, not the publisher's widgets (was 10, 2026-11-01: "let's just make everything that looks like
  a checkbox a checkbox"). In the key, a small square text box (5-16 pt a side) is choice, and so is every box of an
  option group; comb cells and text-group boxes stay text. The blueprints are unchanged.

- A line holding several answers is several fields in the key (was 1, 2026-10-28).

- "Sign and date" drawn as one line is one printed field, not split (2026-10-31).

- Combs are not split in the key: values are graded whole, so a comb, a date in three boxes and one box over the whole
  date are the same answer (was 3, 2026-10-29).

- "Circle one: YES NO" (printed choices with no box): deferred, no fields for now (was 11, 2026-11-01).

### Groups and collections

- A field is in at most one group, and in at most one grid or block. A group sits in a grid or block as one field
  (2026-10-28).

- Text groups (formerly Split Fields, entities, compound values) are text fields that make one value: dates, phone
  numbers and ID numbers only (2026-10-30; addresses dropped). Associated text fields are groups just as associated
  choice fields are.

- What kind of group a group is goes ungraded, only that its fields are grouped (2026-10-30).

- A found group that matches no key group is a false positive, a group of junk boxes included (2026-10-30).

- Grid: "every row is a single data point and every column is a feature" (2026-10-28). Grids and blocks are marked
  conservatively (clear cases only, as with groups) and are not scored. Text groups stay inside one grid cell (guidance,
  not a rule, 2026-10-30).

### Scoring

- How a field must be placed (was 15, 2026-11-02): overlap at least half, or, for single fields, one box mostly inside
  the other or the two on the same line. Text field heights are arbitrary on a flat page and a caption inside a box
  can be dodged two ways, both right (Andrew: "it seems fair to account for a blind spot"). The same rule for every
  method; the plain overlap score reported alongside. Details: `docs/BENCHMARK_SCORING.md`.

- Comparability with other benchmarks is not a goal of the match rule (2026-11-02): their inputs, labels and metrics
  differ anyway; comparison comes from running their methods (FFDNet) on our pages.

- The VLM baseline uses one fixed prompt for every model (2026-11-02), telling it what a field's box is (from the
  line up to the top of its caption; a drawn box filled). Prompt and runner: to move from the scratch run into
  `eval/` when the baseline is run for real.

## Before the full run

Fix these calls before scoring the full set: choosing after seeing scores reads as cherry-picking (2026-10-26).

## Open

### 1. One line, several answers: how it is graded (2026-11-02, watch)

The key splits a line into its answers (Decided). A system that finds one field where the key has three (last / first
/ initial) is scored as missing two; whether that is fair is the open part. Andrew: "something to keep an eye on.
nothing to fix rn". Cases: [bm__mu_0a5e3e21554b](http://localhost:5005/#review/bm__mu_0a5e3e21554b) page 1,
[bm__pb_0142dc15c3c0](http://localhost:5005/#review/bm__pb_0142dc15c3c0) page 1.

### 6. Starting groups come from the system being benchmarked (2026-10-26)

Staged `bm__` blueprints start with the light path's own groups, so validating them by eye anchors the key toward what
it already does. Options: validate a sample from a blank start to measure it; strip starting groups on part of the
set; accept it and say so.

### 7. Cap per layout (2026-10-26)

Duplicates of one layout are caught (Decided); still open is whether a layout shared across publishers gets a cap of
its own.

### 8. Is this new? (survey 2026-10-30)

- **Finding fields alone is not new.** CommonForms (WACV 2026; ~59k PDFs, labels from widgets, text / choice /
  signature, mAP, no grouping; FFDNet-L 81.0 mAP), mini-CommonForms (DAS 2026), Nutrient's form-field-v1-benchmark
  (Aug 2026, 2,334 blank pages), AutoFormBench (2026, 407 hand-labeled PDFs). All score images; none takes the vector
  PDF, has combs or split values; the widget-labeled ones miss what was never made fillable.

- **Closest on grouping: Adobe's Forms Dataset (2020: Aggarwal WACV, Sarkar ECCV, Form2Seq EMNLP).** Hand-labeled
  widgets, fields, choice groups, tables; an exact-member group metric like ours. Only 400 images released, CC
  BY-NC-ND, no harness; split values folded into fields; no repeated blocks. Must be cited.

- **Others:** FormStruct-Bench (Aug 2026, synthetic; scores option membership: read it before claiming "first to score
  option groups"); NAF (2019); FUNSD / XFUND / Form-NLU / DocILE / VRDU / CORD (filled forms, key-value links);
  FormGym, PDF Bench (filling, not structure). BaFCo (ECCV 2026) not inspected.

- **What is open:** finding and grouping fields in one task from a page with no widgets; vector PDF input; split values
  graded whole; option groups + text groups in one hand-validated key; ~1,000 pages, many publishers; an open licence.

- **Contamination:** CommonForms comes from the same 2021 Common Crawl PDFs as the SafeDocs harvest (`bm__sd_*`).
  Check the overlap before using FFDNet as a baseline.

### 9. The 237 forms that failed the business cut (2026-10-27)

Still in `runs/flat/blueprints/` as `fl__sd_*`. Keep them as a separate set (rich in one-line-many-answers rows), or
move them aside.

### 13. Stacked questions answered with checkboxes (2026-10-28)

A column of questions, each with its own boxes (Yes / No or a few options), laid out alike. Each question's boxes are
an option group; the open part is anything wider: whether the follow-up text box ("if yes, explain") belongs with
them, and how far "err ungrouped" goes on big arrays. Cases:
[bm__mu_204c0491798c](http://localhost:5005/#review/bm__mu_204c0491798c) p1,
[bm__sd_4808835](http://localhost:5005/#review/bm__sd_4808835) p2,
[bm__sd_4821735](http://localhost:5005/#review/bm__sd_4821735) p1,
[bm__sd_4828646](http://localhost:5005/#review/bm__sd_4828646) p2,
[bm__sd_4883926](http://localhost:5005/#review/bm__sd_4883926) p1.

### 14. Noise and skew (2026-10-28)

Clean digital PDFs only, as the product is; or a separate robustness split (the same pages degraded, the key moved by
a known transform) so clean scores stay comparable. Cheap to make; whether to report it is the call.

### 16. Checkbox hierarchies (2026-10-30)

Options nested under an option. Are the sub-options a group of their own, part of the parent's group, or tied to the
parent another way, and how is that graded? Cases:
[fin__pb_bdbbcb1e5299](http://localhost:5005/#review/fin__pb_bdbbcb1e5299) p1,
[fin__pb_5b1f96bd91b6](http://localhost:5005/#review/fin__pb_5b1f96bd91b6) p2.

### 17. Notary stamp fields (2026-10-30)

Is the space left for a seal a field (and of what type)? Are the notary's own entries in the benchmark? No case logged.

### 18. How groups are scored (2026-10-30, Andrew's lean recorded)

Lean, to look at more carefully: "we only give partial credit for choice groupings. you either get the whole text
grouping or you don't." Not built; what it would mean is in `docs/BENCHMARK_SCORING.md` ("Agreed, not built yet").

### Filled pages (2026-10-31)

Whether filled pages are mixed in or kept as a split of their own, and whether the values written on them stay out of
the key.

### Choice group definition (2026-10-28)

Proposed, not decided: choice fields presented as options under one prompt (one shared caption; together in one line,
column or cell with nothing between; each with a short label or none). Boxes that each carry a full sentence stay
ungrouped; unclear layouts stay ungrouped.

## Parked

- **2. Fields with no widget** (2026-10-27): settled in practice by adding them during validation (Decided).

- **4. What a block is, 5. grids by geometry** (2026-10-27): blocks and grids are not scored (2026-10-30). Cases kept:
  [bm__sd_5985401 p5-G3](http://localhost:5005/#review/bm__sd_5985401/p5-G3) and
  [bm__sd_2801296](http://localhost:5005/#review/bm__sd_2801296) p4 (grid or block?), fl__sd_2420367 and
  bm__sd_1242044 (block edges). Geometry draft measured on 731 kept grids: 48% accepted vs 97% by the name test.
