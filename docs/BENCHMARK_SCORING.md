# How the flat-structure benchmark is scored

A summary of the scoring rules as of 2026-11-01: what is built, what is agreed but not built yet, and what is still
open. The decisions behind each rule, with Andrew's words and dates, are in `docs/BENCHMARK_JUDGEMENT_QS.md`. The code
is `eval/benchmark_key.py` (the answer key) and `eval/benchmark_score.py` (the scorer).

## The task

A system gets one page of a form as a flat PDF: a text layer, no widgets, no metadata. It hands back the page's fields
(a box and a type for each) and which fields belong together. Nothing else is scored: not names, not what a field
means, not what kind of group a group is, not grids or blocks.

## The answer key

- **Pages.** Forms validated on the review page (in full, or "structure validated"), from the benchmark's sets. At
  most two pages a form, the two with the most fields. Pages marked "ignore page" are left out.

- **Fields.** Every field in the validated blueprint, with its box. A field is anywhere information goes on the page.

- **Three types.**

  - **Text:** anything written in.
  - **Choice:** a box to tick, checkbox or radio alike.
  - **Printed:** anything expected to be handwritten: signatures, initials, printed names.

- **Types follow the page, not the publisher's widgets.** Anything that looks like a checkbox is choice:

  - a small square box (5 to 16 pt a side), including Y / N boxes the publisher made text boxes;
  - every box of a checkbox group, however it was drawn.

  Exceptions: the cells of a comb (three or more alike boxes side by side) and the boxes of a text group stay text.
  Printed fields stay printed.

- **Groups.** Fields that belong together.

  - **Choice groups:** boxes that answer the same question.
  - **Text groups:** text fields that together make one value of a specific type (a date, a phone number, an ID
    number), like a date written across three boxes.

- **The key is kept as the publisher cut it.** A comb drawn as one box stays one field, and a date in three boxes
  stays three fields in one text group.

## How a system's answer is matched to the key

- **The unit is the answer, not the box.** A choice box counts on its own. A text answer is a text group taken whole
  (the box around all its fields) or a single text field.

- **So these are all the same answer:** a date drawn as one box, the same date in three boxes grouped together, and a
  comb found as one box or as its cells grouped.

- **A match needs overlap, or the same place.** A found answer matches a key answer when their boxes overlap by at
  least half of the area the two cover together. Short of that, two single fields still match when one box sits
  mostly inside the other (80% of the smaller inside, the smaller at least a fifth of the larger), or when they share a
  line (half their joint width in common, each box's middle inside the other's height). A text group (a date in three
  boxes) matches by overlap alone, so one part of a date, or two answers joined, is not the value. Each key answer
  matches at most one found answer, best overlaps first. Type is ignored for matching; it is scored separately. Why
  (2026-11-02, question 15): a text field's height is arbitrary on a flat page, and a caption inside a box can be
  dodged by the band below it or the band beside it; Claude Opus 5 on 40 pages found 72.6% of fields by overlap alone
  against 88.2% with this rule, the extra matches checked by eye. The plain overlap score is reported alongside.

## The scores

1. **Fields found:** precision, recall and F1 over answers.

   - Every key answer nobody found costs recall.
   - Every found answer that matches nothing costs precision: junk boxes, a second box on an answer already found, a
     box badly off in size or place.

2. **Typed right:** of the answers found, the share with the right type, and precision and recall for each of the
   three types. A text group counts as printed only when all its fields are printed.

3. **Choice groups:**

   - **Pairs.** Over the key's checkboxes that were found as checkboxes: two boxes grouped together by both the key
     and the system count as right. Grouped by the system only, it counts against precision. Grouped by the key only,
     it counts against recall.
   - **Rebuilt exactly.** A key group counts when every one of its boxes was found, all in one found group that holds
     nothing else.

4. **Text groups combined:**

   - **Recall:** the share of the key's text groups found whole, either combined from their parts or as one box over
     the whole.
   - **Precision:** the share of the system's text groups that match a key answer.

   A wrong combination (two separate answers joined) matches nothing, so it costs in fields found as well.

## Agreed, not built yet

From question 18 (2026-10-30 and 10-31). Andrew still wanted to look at the first point more carefully.

- **Text groups all or nothing, choice groups with partial credit.** A text group is found whole or it is not, as
  scored now. A choice group gets partial credit: its pair score averaged per group, so one 126-box group counts as
  one group rather than as 7,875 pairs. Today 87 groups of ten boxes or more hold 64% of all pairs.
- **"Rebuilt exactly" becomes the headline grouping score, with precision as well as recall.** A found group that
  matches no key group is a false positive, a group made only of junk boxes included.
- **Choice and text groups reported as one "grouped" score** with a choice and text breakdown, since both are groups.

## Open

- **How a found text group is matched to a key one.** By area for now: one wide part (a long street line) can stand in
  for the whole value. The other option is to count the key fields it takes in.
- **Text group coverage.** Text groups are in the key only where they were tagged on the Groups tab, so the key's
  text-group count depends on how far tagging has gone. Where a form is untagged, a system's correct text groups count
  as wrong.

## First baseline (2026-10-30, before the latest key changes)

The light path, on the 1,077 pages the key had then: fields found F1 75.3% (precision 73.3%, recall 77.5%), typed
right 98.8%, choice group pairs precision 92.0% and recall 42.3%, 61% of choice groups rebuilt exactly. With the
page-only text group detector added: 40.4% of the key's text groups found whole, 33.5% of its combinations right
(undercounted by the coverage problem above). The key has changed since (types follow the page, printed fields, Andrew's
re-validation), so these numbers need a rerun.
