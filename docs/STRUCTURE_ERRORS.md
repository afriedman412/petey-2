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

### Blocks that are not blocks

Repeats found where the page has none (2026-10-28, Andrew; not looked into yet). SIA keeps a pattern of 3 or more
fields a copy (`MIN_BOXES`).

- [bm__sd_4791959](http://localhost:5005/#review/bm__sd_4791959) page 1: "any three stacked fields become [blocks],
  apparently".

### Blocks that should be a grid

Repeated blocks found where the page has a grid (2026-10-28, Andrew; not looked into yet). The reverse of the next list.

- [bm__mu_0f47a5542e3d](http://localhost:5005/#review/bm__mu_0f47a5542e3d) page 7 ("blocks when should be a grid").
- [bm__sd_4393564 p2-G2](http://localhost:5005/#review/bm__sd_4393564/p2-G2): the finder made two blocks instead of
  this grid.
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
- [bm__sd_4887554 BT5](http://localhost:5005/#review/bm__sd_4887554/BT5): "combined horizontally", redone by hand
  (BT5 is Andrew's). Another side-by-side join, as sd_6512368.
- [bm__sd_5318548 BT1-1](http://localhost:5005/#review/bm__sd_5318548/BT1-1): one block, should be 2. The same across
  a few pages of [fl__sd_5318548](http://localhost:5005/#review/fl__sd_5318548) (the flat-forms copy of this form).

### Copies that are "close enough"

What Andrew wants more of (2026-10-28): blocks whose fields are mostly analogous, with a few differences, read as copies
of one type "a little more consistently. we aren't there yet." Not looked into yet.

- [bm__pb_43936af1594f BT2](http://localhost:5005/#review/bm__pb_43936af1594f/BT2): about 7 analogous fields across
  the two blocks, a few differences. The "country code" fields had to be added by hand (also under "Fields missing").

Today the finder grows a position when 75% of the other copies have it (`MOST`), and detect's box model takes a copy
with 75% of the positions; the caption check (80% of copies agree on a position, 60% of positions) is the strict part.

### Blocks found wrong

Blocks the finder made, but wrong (2026-10-29, Andrew; not looked into yet).

- [bm__pb_dd9943ab900b](http://localhost:5005/#review/bm__pb_dd9943ab900b) page 9: "block detection is incorrect".
- [bm__pb_d8ad9cc21d03](http://localhost:5005/#review/bm__pb_d8ad9cc21d03) page 9 (2026-10-30): "blocks aren't fully
  formed. not a problem for benchmarking (which doesn't care about blocks) but for the future".

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
- [bm__sd_4861991 BT1](http://localhost:5005/#review/bm__sd_4861991/BT1) ("wasn't found by finder").

### bm__sd_6148819 p2: should be 6 blocks

[bm__sd_6148819](http://localhost:5005/#review/bm__sd_6148819) page 2 (2026-10-27, Andrew: "should be 6 blocks"; not
looked into yet).

### bm__sd_5788289 p2-G1: two grids found as one

[p2-G1](http://localhost:5005/#review/bm__sd_5788289/p2-G1) (2026-10-27, Andrew: "should be 2 grids, not one"; not
looked into yet). Cf. his grid definition (2026-10-27): every row one data point, every column relates to it alone;
side-by-side tables are two grids.

### Overlapping blocks

The rule (Andrew, again 2026-10-28): "every field should only belong to a single grid or a single block". Already
decided (one block per field, the larger keeps it; a field in a grid is in no block, 7b93e5f), so an overlap is the
rule broken somewhere, not a call to make. Not looked into yet.

- [bm__sd_5773416 BT1-1](http://localhost:5005/#review/bm__sd_5773416/BT1-1): "wrongly shaped (overlaps with
  [BT2-1](http://localhost:5005/#review/bm__sd_5773416/BT2-1))" (2026-10-27).
- [bm__pb_457a4c6acc56](http://localhost:5005/#review/bm__pb_457a4c6acc56) page 2: overlapping blocks (2026-10-28).

### Grids the finder missed

Drawn by hand after run finders (2026-10-27, Andrew; not looked into yet). Also bm__sd_5428855's p3-G3 / p2-G6 below.

- [bm__sd_5680835 p2-G1](http://localhost:5005/#review/bm__sd_5680835/p2-G1) ("finder didn't find")
- [bm__sd_5763720 p8-G1](http://localhost:5005/#review/bm__sd_5763720/p8-G1) ("another missed grid")
- [bm__sd_646159 p2-G1](http://localhost:5005/#review/bm__sd_646159/p2-G1) ("finder didnt get")
- [bm__mu_02da0d39549a p4-G2](http://localhost:5005/#review/bm__mu_02da0d39549a/p4-G2) ("finder didn't find")
- [bm__sd_4763200 p2-G3](http://localhost:5005/#review/bm__sd_4763200/p2-G3) ("finder missed")

### bm__sd_5661166 BT1-3: a copy not detected

[BT1-3](http://localhost:5005/#review/bm__sd_5661166/BT1-3) (2026-10-27, Andrew: "didnt get detceted"; not looked into
yet).

### Things made fields that are not

Marks on the page taken as fields (2026-10-28, Andrew; not looked into yet). Checklists are ignored altogether
(Andrew, 2026-10-28: "we need to ignore checklists"; BENCHMARK_JUDGEMENT_QS "Decided").

- [bm__mu_01f0594c6419 field 1](http://localhost:5005/#review/bm__mu_01f0594c6419/1): "these are just bullet points
  (not fields)".
- [bm__mu_16908714b485](http://localhost:5005/#review/bm__mu_16908714b485) page 1: bullet points.
- [bm__pb_212919861076](http://localhost:5005/#review/bm__pb_212919861076) page 1 (2026-10-30): "bullet points
  marked as fields".
- [bm__pb_42efc4054792](http://localhost:5005/#review/bm__pb_42efc4054792) page 2: empty space taken as text fields
  (Andrew: "another recurring problem"). The same as his read of bm__mu_19df3dcf2619 (empty space beside each cell's
  label, "Blocks that should be a grid").

### Fields the wrong shape

Fields that exist but are drawn wrong (2026-10-28, Andrew; not looked into yet).

- [bm__pb_457a4c6acc56](http://localhost:5005/#review/bm__pb_457a4c6acc56) page 1, top right, the EIN (2026-10-29,
  Andrew: "how is this EIN getting parsed?"). A flat form (finder boxes, Jev's screen). Printed as two digit boxes, a
  dash, a seven-cell comb drawn as one rectangle with short ticks top and bottom. Read as: the two digit boxes as
  checkboxes ([p1_f4](http://localhost:5005/#review/bm__pb_457a4c6acc56/4),
  [p1_f5](http://localhost:5005/#review/bm__pb_457a4c6acc56/5): ~17 x 20 pt squares, under finder minor 3's 20 pt
  mark size); the comb as four overlapping text fields: the whole rectangle
  ([p1_f10](http://localhost:5005/#review/bm__pb_457a4c6acc56/10)), its end cells
  ([p1_f6](http://localhost:5005/#review/bm__pb_457a4c6acc56/6), [p1_f8](http://localhost:5005/#review/bm__pb_457a4c6acc56/8))
  and a strip between the ticks ([p1_f7](http://localhost:5005/#review/bm__pb_457a4c6acc56/7)). Jev scores each box
  alone (0.74-0.86) and nothing drops boxes nested in another. Cf. BENCHMARK_JUDGEMENT_QS 3 (combs).

- [bm__pb_d985db100931](http://localhost:5005/#review/bm__pb_d985db100931) page 1 (2026-10-29): "a lot of field
  location but also strange decisions", specifically things like
  [field 78](http://localhost:5005/#review/bm__pb_d985db100931/78). For later; Andrew: "kind of related" to the light
  path's place-name collisions (fields overwriting each other when built).
- [bm__pb_42d999b8507f](http://localhost:5005/#review/bm__pb_42d999b8507f) page 5: "fields created vertically".
- [fin__pb_9dec7f6d42d5](http://localhost:5005/#review/fin__pb_9dec7f6d42d5) page 2 (2026-10-29): "issues with text
  field identification, not a huge problem". Andrew keeps it as the test case if he takes up how precise field
  locations must be for the benchmark (BENCHMARK_JUDGEMENT_QS 15).

### Fields missing from the blueprint

Boxes on the page with no field (2026-10-27, Andrew; not looked into yet). One cause found and fixed 2026-10-29
(a55cacf): the light path names fields by place, two groups in one block copy or table row came to one name and the
second was written over the first (bm__mu_0d8e9867024f p3: 14 of 20 YES / NO boxes). 72 staged forms were short,
1,075 boxes; the 64 Andrew had not opened were re-staged (1,049 boxes back; old copies and finder records in
`runs/benchmark/before_restage_2026-10-29/`); the 8 with his work on them were left. The benchmark blueprints take their boxes
from the publisher's widgets, so a box the publisher made no widget for is missing (cf. BENCHMARK_JUDGEMENT_QS 2).

- [bm__sd_5661166](http://localhost:5005/#review/bm__sd_5661166): some Home / Bus / Cel buttons ("didn't show up");
  may tie to its BT1-3 above.
- [bm__sd_4234345](http://localhost:5005/#review/bm__sd_4234345): the "Living" / "Deceased" buttons ("needed to be
  added").
- [bm__mu_0b8b903f5fb7](http://localhost:5005/#review/bm__mu_0b8b903f5fb7) page 2: "lots of checkboxes not
  identified".
- [bm__pb_2c1e1c1cad37](http://localhost:5005/#review/bm__pb_2c1e1c1cad37) page 11: many Yes / No and Weekly / Monthly
  boxes added by hand.
- [bm__pb_43936af1594f BT2](http://localhost:5005/#review/bm__pb_43936af1594f/BT2): the "country code" fields, added by
  hand.
- [fin__pb_21b65d9f2580 field 44](http://localhost:5005/#review/fin__pb_21b65d9f2580/44) (2026-10-29): the finder
  missed the "Executive", "Union" and "Non-Union" boxes.
- [bm__sd_6457354](http://localhost:5005/#review/bm__sd_6457354): the F2 / M2 boxes ("didnt get identified"); added
  by hand as [3_2](http://localhost:5005/#review/bm__sd_6457354/3_2) and
  [3_4](http://localhost:5005/#review/bm__sd_6457354/3_4).

### Option groups: what the reported cases are (looked at 2026-10-28)

Andrew asked for a look at the overzealous / weird groupings. Read-only: each group's options, their places and
captions, and the publisher's field behind each box (the fillable original). Two causes:

- **The publisher's field reused across questions, kept whole by staging** (most of them). sd_537564 p1_o1: Group2,
  15 buttons over the whole page. sd_5514549 p1_o1: Group3, 13 buttons (sex, relationship, three Yes / No pairs on one
  line, another Yes / No). sd_5952614: Group30 over two Yes / No questions (already split by Andrew, 2026-10-27).
  sd_2801296 p3_o4 (field 50): one field, "Have you had this complaint before", over five Yes / No questions on pages
  3-5. mu_0bfb2573afdf p2_o1 / p2_o2: two checkbox fields, "Yes Checkbox" and "No Checkbox", four boxes each: the
  page's four Yes / No questions grouped by column (all the Yes boxes, all the No boxes), not by question.
  sd_480300 p1_o11: the publisher's field "2" on two unrelated boxes 279 pt apart ("Other" tint, "Traditional"
  edge), and our join added "Flash".
- **Our joins (code rules, Jev) where there is no publisher field.** mu_1c4c68a0803f p1 is flat (no widgets, every
  group ours), a building permit of small boxed sections: sections cut into pairs of neighbours (Project's Repair /
  Move, Addition / Other; HVAC as Furnace / Radiant plus the other four), one pair across a section border (Raze in
  Project with Underground in Electric, p1_o3), the rest of most sections loose; the energy source table's two rows are
  one group each (p1_b1_c1 / c2), which may be right. sd_480300 p1_o5: our join put two tint options ("19", "24") into
  the publisher's Lens Material group.

Fix ideas, not tried: a publisher field is a suggestion, split where the page shows separate questions (its options'
lines and captions); joins never cross a section edge (a ruled box or heading), the "section edges" thread below.

Both tested read-only (2026-10-28) against the validated library (`blueprints/`, 226 forms with a blank, 3,294 option
groups, 9,776 options; a group "breaks" when the idea cuts it into 2+ pieces), in a first, blunt form:

- **Idea 1, separate questions:** two options apart when a printed line lies between them that is no option's caption
  and starts left of both. Breaks 121 validated groups (3.7%), 580 options (5.9%), on 58 forms (uscourts_b_106c 14,
  b_106a_b 11, b_106j_2 7, f1040 5). Cause: the question's own wrapped lines sit left of its stacked options (f1040
  "with you more", faa8710 "speak, write, & understand the", gse_1076 "If Yes, for how long ...").
- **Idea 2, section edges:** two options apart when the line between them crosses a drawn rule >= 20 pt that is no
  field's own edge. Breaks 288 (8.7%), 1,115 options (11.4%), on 50 forms (f990 78, sf_3107 47, gse_1076 30). Cause:
  table cell walls between Yes and No (f990, sf_3107, gse_1076), a column rule down the page (f1040's special
  conditions).
- On the reported bad groups: idea 1 cuts 6 of 7 (sd_537564's 15 into 4 pieces, not the 7 questions; sd_480300
  p1_o5 not at all), idea 2 all 7, neither all the way. Splitting alone does not pair mu_0bfb2573afdf's Yes / No by
  question; the yes / no rules would have to join the pieces after.
- So neither as is. Sharper versions: idea 1's separator a line that starts a new item (its own number or letter, or
  a new question block), not the wrapped text of the one the options answer; idea 2's edge a closed box round a
  section (with its heading), not any cell wall. Script: session scratchpad `groups/survive.py`.

Distance and caption checks (2026-10-28, read-only, same two sets; script `groups/checks.py`):

- **A fixed distance** (single-linkage, edge gaps across / down, 30-250 pt by 8-45 pt) never separates them: at the
  loosest, 65 validated groups (454 options) still break and only 9 of the 44 publisher groups on the reported pages
  split. Page-relative is the same thing (the pages are all letter size). Andrew: "nothing on that form is that far
  apart".
- **Repeated captions** (two options of one group printing the same short caption, <= 3 words; Y / N read as Yes /
  No; each group's captions read from the side, left or right of the boxes, that gives the most distinct ones, stopping
  at the next box): flags 2 validated groups of 3,294 (8 options; acord_90_ny's "F G" columns). Catches sd_537564
  Group2, sd_5514549 Group3, sd_2801296 field 50, mu_0bfb2573afdf's No column, and on the unlabelled pages
  sd_4838056's No column and sd_4885390 Group1. Misses: sd_5952614 Group30 and mu_0bfb2573afdf's Yes column (captions
  read with the question's words), sd_480300 "2" (two different captions).
- **Nearest neighbour** (most of a group's boxes nearer a box outside it than half their nearest inside): flags 714
  validated groups (21.7%); unusable as is, though it catches mu_0bfb2573afdf's Yes column and sd_480300 "2".
- **A trained pair model** ("same question?", page-only features, 594 validated forms, folds by family): 74-75% of
  groups rebuilt exactly (logistic and a small network alike), lone boxes mostly over-joined; "err ungrouped" makes
  lone-box labels noisy. A keep-or-split model on Andrew's corrections: only 22 of 804 staged publisher groups split
  on the 215 validated benchmark forms, too few. Parked.
- **Built (2026-10-28, uncommitted, parked by Andrew until 10-29):** `eval/repeated_captions.py`, called from
  `flat_light.groups` on the publisher's groups before the joins and on every group after; tests
  `tests/test_repeated_captions.py`. Validated library: 2 of 3,294 groups changed. Open: commit; a suggestions pass
  for already-staged benchmark forms (unconfirmed groups only); the Groups counter counting a group confirmed when
  its field is accepted on Review (Andrew: "accepting means accepting groups too").

### Option groups split apart

The reverse of "take in too much": one question's options left as several groups (2026-10-29, Andrew; not looked into
yet). Andrew: "recurring problem is widely spread checkboxes that are all related."

- [mg__pb_e186aa37e4e4 field 54](http://localhost:5005/#review/mg__pb_e186aa37e4e4/54): three vertical sets of
  checkboxes, one question; Andrew grouped them into one by hand.

### Other odd option groups

Groupings wrong some other way, or not yet sorted (2026-10-28, Andrew; not looked into yet).

- [bm__mu_1c4c68a0803f](http://localhost:5005/#review/bm__mu_1c4c68a0803f) page 1: "weird check box grouping".
- [bm__sd_480300](http://localhost:5005/#review/bm__sd_480300) page 1: "more weird button grouping". The sd_537564
  survey listed its p1_o11 (3 options, a 279 pt gap between neighbours), likely a publisher radio field.
- [bm__pb_ba4c6e5ff63d](http://localhost:5005/#review/bm__pb_ba4c6e5ff63d) page 1 (2026-10-30): "not sure about the
  groupings here". Andrew unsure what the right groups are: a judgement call as much as an error.

### Option groups that take in too much

More of the kind of bm__sd_537564 p1_o1 below (2026-10-27, Andrew; not looked into yet).

- [bm__sd_5514549](http://localhost:5005/#review/bm__sd_5514549) ("more overzealous grouping"). The sd_537564 survey
  listed its p1_o1: 13 options on 4 lines, a 343 pt gap between neighbouring options; likely a publisher radio field.
- [bm__sd_5952614 field 59](http://localhost:5005/#review/bm__sd_5952614/59) ("slightly overzealous grouping").
- [bm__sd_2801296 field 50](http://localhost:5005/#review/bm__sd_2801296/50) ("overzealous grouping").
- [bm__mu_0bfb2573afdf](http://localhost:5005/#review/bm__mu_0bfb2573afdf) page 2 ("egregious grouping").
- [bm__sd_4838056](http://localhost:5005/#review/bm__sd_4838056) page 2 ("more aggressive grouping"; not looked into
  yet).
- [bm__sd_4848012](http://localhost:5005/#review/bm__sd_4848012) page 2 ("another aggressive grouping"; not looked into
  yet).
- [bm__sd_4885390 field 82](http://localhost:5005/#review/bm__sd_4885390/82) ("another aggressive grouping").
- [bm__pb_26d73752f551](http://localhost:5005/#review/bm__pb_26d73752f551) page 1 (2026-10-28).
- [fin__pb_0c0d6152cdae](http://localhost:5005/#review/fin__pb_0c0d6152cdae) page 1 (2026-10-29: "why did these yes
  and no buttons get grouped"; 2026-10-30: "the yeses and nos got grouped together (i fixed it)"). Six questions' Yes
  and No boxes in two columns. Looked at 2026-10-29 when Andrew asked: each caption is printed as "☐Yes", the box
  character run into the word, so the word starts inside the box and the caption reader skips it; the repeated-answer
  split (a55cacf) then sees too few repeated captions and cuts the columns 2 + 4 only. Proposed then, not made: take a
  word that starts inside the box and runs past its edge. Fixed by hand on the page.

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

- "Close enough" copies (Andrew, 2026-10-28): mostly analogous blocks with a few differences should read as one type more
  consistently; exact captions and fixed sizes are what hold them apart.
- Wrong fields upstream break structure downstream: a missing field can hide a block (sd_4234345), a false one can
  turn a grid into blocks (mu_19df3dcf2619, Andrew's read). Field finding may be the first thing to fix.
- Metadata trusted over the page: the publisher's radio fields kept whole (sd_537564).

- Fixed distances keep missing (3, 4, 10, 10.9, 30 pt): the box model already scores the pairs these rules refuse
  (BT2-2's address 0.91).
- Captions are both the best guard and a source of misses (a typo, a misread caption, rows of one table captioned by
  their own subject).
- Section edges (headings, borders) are never used; two cases cross one (sd_522176, and the grid on sd_3856391).
