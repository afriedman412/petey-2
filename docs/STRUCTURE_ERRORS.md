# Structure errors

Option groups, grids and blocks the finders get wrong, collected while reviewing (Andrew, 2026-10-27: "lets start accumulating these errors and
fixes and see if we can't do something more cohesive when we have them all"). One entry per case: where, what is
wrong, which step did it and why, the fix tried or proposed with its numbers, and whether it is in. Edited in place.
New one-off fixes wait here; the aim is one design that covers them all. Terms: `docs/GLOSSARY.md`.

Option groups on the benchmark forms (`bm__sd_*`) come from staging (`acquisition/safedocs_stage.py` ->
`eval/flat_light.groups`): the publisher's radio fields (choice widgets sharing a field name) kept whole, never joined
to each other, plus code rules and Jev's joins for loose boxes.

The block steps, in the order they run (`petey/validate/block_discovery.py`, `block_types.py`):

- **SIA** (finder): every pair of alike boxes (same kind, size within 3 pt) votes for the shift between them, in 4 pt
  bins; the boxes of one shift, cut into pieces of boxes within `GAP` (30 pt) of each other, are a pattern; its copies
  found by layout (`copies_in`), grown box by box (`grow`, alike boxes within 30 pt), kept when each position's printed
  caption repeats (80% of copies, 60% of positions).
- **Labels pass** (finder and detect): more copies where the pattern's printed lines repeat (3 pt across, 10 pt down).
- **Lockstep** (finder, 2026-10-27): two patterns whose copies move together are one.
- **Growing by the box model** (`grow_more`, finder, 2026-10-27): a position most copies have that the size rule
  missed, chosen by the "same kind of box" model (`same_box`).
- **Detect** (rescan a page; run finders primes with it): a type's copies by layout (`copies_in`, within `tol`), then
  labels, then the box model (`model_copies`, 2026-10-27).
- **Fill** (`fill_blocks`): a block's empty position, by place then the box model.

Measures used below: **finder** = per field on the 151 je__/lib__ forms with saved types, a field in copy 2+ against
its copy-1 counterpart (right / wrong / unjudged = in no saved type); **replay** = each of 751 saved copies on 149 forms
held out and looked for by detect. Scripts were scratch (session 8b468f09 `copymatch/`); rebuild from these
definitions if needed.

## Open

### Blocks that should be a grid

Repeated blocks found where the page has a grid (2026-10-28, Andrew; not looked into yet). The reverse of the next list.

- [bm__mu_0f47a5542e3d](http://localhost:5005/#review/bm__mu_0f47a5542e3d) page 7 ("blocks when should be a grid").
- [bm__mu_19df3dcf2619](http://localhost:5005/#review/bm__mu_19df3dcf2619) page 2. Andrew's read: the finder takes the
  empty space beside each cell's label as a field, and those extra fields throw off the grid detector. If so, a
  false-field problem (above, "Things made fields that are not") showing up as a grid miss.

### Grids that should be blocks

A grid found where the page has repeated blocks (2026-10-27, Andrew; not looked into yet). Also bm__sd_3856391 p4
below (the references, grid p4-G1).

- [bm__sd_4623768 p2-G1](http://localhost:5005/#review/bm__sd_4623768/p2-G1) ("should be blocks, not a grid").

### Blocks holding two copies

One block found where there are two (2026-10-27, Andrew; not looked into yet). Suspect to check first: the lockstep
merge added today, which joins two patterns whose copies move together (copies 1 and 3 as one pattern, 2 and 4 as
another, would merge into 1+2 and 3+4).

- [bm__sd_6286157](http://localhost:5005/#review/bm__sd_6286157) page 3: 2 blocks, should be 4 ("each it found
  contained 2").
- [bm__sd_6512368](http://localhost:5005/#review/bm__sd_6512368) page 4: 3 blocks, should be 6 ("horizontal merge":
  side-by-side copies joined, which is what lockstep does to two patterns).
- [lib__n400](http://localhost:5005/#review/lib__n400) page 13: 2 blocks, should be 4. A library form, not a benchmark
  one.
- [bm__sd_7015625](http://localhost:5005/#review/bm__sd_7015625) page 4: "doubling up blocks".
- [bm__sd_5318548 BT1-1](http://localhost:5005/#review/bm__sd_5318548/BT1-1): one block, should be 2. The same across
  a few pages of [fl__sd_5318548](http://localhost:5005/#review/fl__sd_5318548) (the flat-forms copy of this form).

### Blocks the finder missed

Copies run finders did not make (2026-10-27, Andrew; not looked into yet). Also bm__sd_5661166 BT1-3 and
bm__sd_6148819 p2 below.

- [bm__sd_6282222](http://localhost:5005/#review/bm__sd_6282222) page 3: four blocks ("weren't found automatically").
- [bm__sd_6399018 BT1](http://localhost:5005/#review/bm__sd_6399018/BT1): run finders missed the type; once BT1-1 was
  drawn, detect found [BT1-2](http://localhost:5005/#review/bm__sd_6399018/BT1-2). So the copies match well enough for
  detect but the finder (SIA) never proposed the pattern.
- [bm__sd_4665989 BT2](http://localhost:5005/#review/bm__sd_4665989/BT2) ("finder didn't find").
- [bm__sd_4234345 BT1](http://localhost:5005/#review/bm__sd_4234345/BT1) ("finder missed"); the same form's Living /
  Deceased buttons were missing too (below), which may be why.

### bm__sd_6148819 p2: should be 6 blocks

[bm__sd_6148819](http://localhost:5005/#review/bm__sd_6148819) page 2 (2026-10-27, Andrew: "should be 6 blocks"; not
looked into yet).

### bm__sd_5788289 p2-G1: two grids found as one

[p2-G1](http://localhost:5005/#review/bm__sd_5788289/p2-G1) (2026-10-27, Andrew: "should be 2 grids, not one"; not
looked into yet). Cf. his grid definition (2026-10-27): every row one data point, every column relates to it alone;
side-by-side tables are two grids.

### bm__sd_5773416 BT1-1: wrongly shaped, overlaps BT2-1

[BT1-1](http://localhost:5005/#review/bm__sd_5773416/BT1-1), [BT2-1](http://localhost:5005/#review/bm__sd_5773416/BT2-1)
(2026-10-27, Andrew: "wrongly shaped (overlaps with sd_5773416_BT2-1)"; not looked into yet).

### Grids the finder missed

Drawn by hand after run finders (2026-10-27, Andrew; not looked into yet). Also bm__sd_5428855's p3-G3 / p2-G6 below.

- [bm__sd_5680835 p2-G1](http://localhost:5005/#review/bm__sd_5680835/p2-G1) ("finder didn't find")
- [bm__sd_5763720 p8-G1](http://localhost:5005/#review/bm__sd_5763720/p8-G1) ("another missed grid")
- [bm__sd_646159 p2-G1](http://localhost:5005/#review/bm__sd_646159/p2-G1) ("finder didnt get")
- [bm__mu_02da0d39549a p4-G2](http://localhost:5005/#review/bm__mu_02da0d39549a/p4-G2) ("finder didn't find")

### bm__sd_5661166 BT1-3: a copy not detected

[BT1-3](http://localhost:5005/#review/bm__sd_5661166/BT1-3) (2026-10-27, Andrew: "didnt get detceted"; not looked into
yet).

### Things made fields that are not

Marks on the page taken as fields (2026-10-28, Andrew; not looked into yet). Checklists are ignored altogether
(Andrew, 2026-10-28: "we need to ignore checklists"; BENCHMARK_JUDGEMENT_QS "Decided").

- [bm__mu_01f0594c6419 field 1](http://localhost:5005/#review/bm__mu_01f0594c6419/1): "these are just bullet points
  (not fields)".
- [bm__mu_16908714b485](http://localhost:5005/#review/bm__mu_16908714b485) page 1: bullet points.

### Fields missing from the blueprint

Boxes on the page with no field (2026-10-27, Andrew; not looked into yet). The benchmark blueprints take their boxes
from the publisher's widgets, so a box the publisher made no widget for is missing (cf. BENCHMARK_JUDGEMENT_QS 2).

- [bm__sd_5661166](http://localhost:5005/#review/bm__sd_5661166): some Home / Bus / Cel buttons ("didn't show up");
  may tie to its BT1-3 above.
- [bm__sd_4234345](http://localhost:5005/#review/bm__sd_4234345): the "Living" / "Deceased" buttons ("needed to be
  added").
- [bm__sd_6457354](http://localhost:5005/#review/bm__sd_6457354): the F2 / M2 boxes ("didnt get identified"); added
  by hand as [3_2](http://localhost:5005/#review/bm__sd_6457354/3_2) and
  [3_4](http://localhost:5005/#review/bm__sd_6457354/3_4).

### Other odd option groups

Groupings wrong some other way, or not yet sorted (2026-10-28, Andrew; not looked into yet).

- [bm__mu_1c4c68a0803f](http://localhost:5005/#review/bm__mu_1c4c68a0803f) page 1: "weird check box grouping".

### Option groups that take in too much

More of the kind of bm__sd_537564 p1_o1 below (2026-10-27, Andrew; not looked into yet).

- [bm__sd_5514549](http://localhost:5005/#review/bm__sd_5514549) ("more overzealous grouping"). The sd_537564 survey
  listed its p1_o1: 13 options on 4 lines, a 343 pt gap between neighbouring options; likely a publisher radio field.
- [bm__sd_5952614 field 59](http://localhost:5005/#review/bm__sd_5952614/59) ("slightly overzealous grouping").
- [bm__sd_2801296 field 50](http://localhost:5005/#review/bm__sd_2801296/50) ("overzealous grouping").
- [bm__mu_0bfb2573afdf](http://localhost:5005/#review/bm__mu_0bfb2573afdf) page 2 ("egregious grouping").

### bm__sd_5428855: grids missed, or found as blocks

(2026-10-27, Andrew; not looked into yet.) Grids the finder did not make, all four drawn by hand at 19:02 after run
finders at 19:01:

- [p3-G3](http://localhost:5005/#review/bm__sd_5428855/p3-G3) (21 cells) and
  [p2-G6](http://localhost:5005/#review/bm__sd_5428855/p2-G6) (30 cells): not detected.
- [p1-G5](http://localhost:5005/#review/bm__sd_5428855/p1-G5) and
  [p1-G6](http://localhost:5005/#review/bm__sd_5428855/p1-G6) (10 cells each): Andrew thinks they were found as blocks
  (the record has BT3 only, next id BT4, so BT1 / BT2 were made and are gone).

### bm__sd_537564 p1_o1: one publisher radio field across the whole page

[p1_o1](http://localhost:5005/#review/bm__sd_537564/3) (2026-10-27, Andrew: "overzealous group inclusion"). 15 options
in one group: Gender M / F, question 2's normal / abnormal / borderline, question 3's three normal / abnormal pairs,
questions 7 and 8's Yes / No. Should be seven groups.

- Cause: the publisher. The fillable original (`runs/acquisition/safedocs/pdf/insurance/5613694.pdf`) has one radio
  field, Group2, Choice1-15, for every round button on the page (in their PDF, ticking M clears question 2). Staging
  keeps a publisher radio field as one group and never splits it.
- How common (benchmark blueprints, 4,352 groups on 367 forms): 76 groups span more than one page; 38 more, on 33
  forms, have a gap over 60 pt between neighbouring options (sd_5026196 p2_o3 509 pt, sd_3010933 p2_o1, sd_5514549
  p1_o1 13 options, sd_887924, sd_2642779, sd_6893117 p3_o1 17 options ...). Not each checked: a long list can have
  a wide gap and be right.
- Fix idea (not tried): treat a publisher group as a suggestion, split where the page shows separate questions (the
  code rules / Jev joins inside it, or its options' lines and captions), as "page over metadata" says. Re-staging
  would need Jev calls for the groups split.

### bm__sd_522176 BT3: the applicant columns grow into the agency section

[BT3-1](http://localhost:5005/#review/bm__sd_522176/BT3-1), [BT3-2](http://localhost:5005/#review/bm__sd_522176/BT3-2)
(2026-10-27). Each column also holds two agency fields from above the "Applicant / Co-Applicant" headings: BT3-1 has
p1_f8 (agency City/State/Zip, left part) and p1_f11 (agency Phone), BT3-2 p1_f10 and p1_f12 (agency Email).

- Step: growing by the box model. SIA found only the four bottom rows (Daytime Phone, Email, Occupation, Employer);
  the model grew upward one row at a time (all right up to Name / M F), then took agency Phone <-> agency Email,
  same shift as the columns, captions sharing no word (the model asks for shared words only when a box is far off),
  which brought the City/State/Zip pieces within reach.
- Fix tried (not in): growing refuses a position when both boxes are captioned and share no word. Finder: right
  4,068 -> 4,065, wrong 1,087 -> 1,087, unjudged 3,384 -> 3,368. Lost: fl_142 jewelry vs checking-accounts rows,
  gse_1003 "unit" vs "income" (a misread caption), acord_90_ny additional-interest type. Removed unjudged: mostly
  overreach (cra_t2125 gross profit <-> parking fees; i_693 different vaccines' dates). Same rule as detect's guard.
- Not tried: a printed heading or a ruled border between two rows as a block's edge.

### bm__sd_3856391 p4: the references are a grid, not a block

[BT2](http://localhost:5005/#review/bm__sd_3856391/BT2) (2026-10-27). Three references (Name, Email, "(", Phone, and
Address on the line below); the finder made grid p4-G1 of the top rows and no block, so BT2 was drawn by hand.

- Three causes, any one enough. (1) Grid first: a block lying mostly inside an active grid is not made (4 of 5 fields
  in p4-G1). (2) SIA's 4 pt bins split copy 1 -> copy 2's votes over four bins; only copy 1 -> 3 reached 3 boxes.
  (3) Caption check: copy 2 prints "Phone #r", so the Phone position agrees in 2 of 3 copies (needs 80%).
  Also: Name and Address differ in width by more than SIA's 3 pt across copies (217 / 214 / 210 pt).
- Proposed (not tried): a grid whose every row has another field under it gives way to a block; shifts grouped by
  nearness rather than fixed bins.

### fl__sd_6863766 BT9: option groups 18-23 pt along their line

(2026-10-27, earlier session.) 32 / 33 and 42 / 43 stay out of BT9-2 / BT9-3: past the labels pass's 14.4 pt reach.
Proposed then, not built: fill empty positions in order along the line, option groups only (6 positions on this form,
0 elsewhere).

### Fields of one block found as two types when the columns are the same width

From the lockstep test (2026-10-27): when a block's two columns have boxes of one size, SIA finds the right column as
more copies of the left (Name <-> Company) and the caption check then drops both. Seen only in a synthetic page so far;
sd_3867602's columns differ in width (258 / 175 pt).

## Fixed

### bm__sd_3856391 BT2-2: a copy set tighter missed by detect

[BT2-2](http://localhost:5005/#review/bm__sd_3856391/BT2-2) (2026-10-27). Drawing BT2 and detecting found BT2-1 and
BT2-3, not BT2-2: its address line (field and label) sits 12 pt higher; layout allows 10.9 pt, labels 10 pt.

- Fix (in): detect's last pass, the box model picks each position (`block_types.model_copies`), with a
  guard: two or more captioned positions sharing no word is no copy. Replay: exact 694 -> 726, missed 45 -> 9, wrong
  fields 8 -> 13, ~24 more copies among fields in no saved block, about half real (fl_142 debts, cms_10269 dates),
  half junk (cms_10269 phone digits, acord_35 / acord_80).
- Tried and dropped: the same search inside SIA (+14 right / +111 wrong; on its own pages with SIA's caption check
  +5 / +17); SIA's caption check on detect's search (lost 20 real copies: fl_142, schedule A, va_21_686c).

### bm__sd_3867602 p2: one party's two columns found as two types

BT1 / BT2 (2026-10-27): each party's Name / Address / Email / Signature and Company / Phone / Invoices sent to / Date,
38.7 pt apart, past SIA's 30 pt `GAP` and the growing reach.

- Fix (in): lockstep (`block_discovery.lockstep`): two patterns, as many copies, copy i at the same shift
  in both (12 pt), each copy nearer its partner than its own nearest copy. Finder: right 4,056 -> 4,068, wrong 1,087
  -> 1,087 (gsa_sf_1199a, cra_t4a_nr). Existing records change only when finders run again.
- Related, measured by another session the same day, not in: growing reach 30 -> 75 pt, +169 right / -99 wrong on the
  same 151 forms, 5 forms worse (va_21_8940, acord_80, n_600, b_106e_f, hud_92800_5b).

## Threads so far

- Wrong fields upstream break structure downstream: a missing field can hide a block (sd_4234345), a false one can
  turn a grid into blocks (mu_19df3dcf2619, Andrew's read). Field finding may be the first thing to fix.
- Metadata trusted over the page: the publisher's radio fields kept whole (sd_537564).

- Fixed distances keep missing (3, 4, 10, 10.9, 30 pt): the box model already scores the pairs these rules refuse
  (BT2-2's address 0.91).
- Captions are both the best guard and a source of misses (a typo, a misread caption, rows of one table captioned by
  their own subject).
- Section edges (headings, borders) are never used; two cases cross one (sd_522176, and the grid on sd_3856391).
