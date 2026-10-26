# Plan: field identifiers (names built from stored parts)

Branch `field-identifiers-2026-10-19`, cut from `validation-tools-2026-10-14` at `13961fb` (2026-10-19). Written at the
end of a long session so the next one can start here.

## Why

Field names carry meaning that the code then has to read back out of the string, and the string is ambiguous:

- `veteran_ssn_1`: part 1 of one SSN, or veteran 1's SSN?
- `property_a_…`: a lettered row (an iteration) or a label?
- `first_nm` in two different tables: a clash, or the same series continued across a page?
- `taxpayer_city_nm` / `firm_city_nm`: a disagreement in a column, or row labels in a consistent grid?

Grids, blocks, the naming standard and the clash handling all stumble on this parsing. Andrew (2026-10-19): "maybe we
should just encode the field name parts instead of inferring the name from structure."

## The idea

Each field stores its identifiers. The field name (the slug) is printed from them by one function, and is never
edited directly.

| Identifier | Example | Comes from |
|---|---|---|
| (the field's subject: name to be decided, see below) | `first_name` | the labeler; the person |
| suffix | `txt` | the type (suffix discipline is a later, separate cleanup) |
| iteration | grid / block group id + row (block) | membership in a kept grid or block group |
| part | compound value id + box index | membership in a compound value |
| grid, block, block group | `p2-T1`, `p2-BG1` | the kept list |

The print order is a rendering choice. Andrew's proposed order, [subject]_[suffix]_[iteration], makes the iteration the
unique last part ([subject]_[suffix] can repeat across a form; the iteration never does). A table letter for
different tables sharing a subject (children's `first_name` and contacts' `first_name`) goes inside the iteration:
`first_name_txt_a1`, `first_name_txt_b1`. Changing the order later reprints names; nothing is re-parsed.

## Decisions made (2026-10-19)

1. **Store the parts; print the name.** The information is already there (types, kept grids and block groups,
   compound values); the problem is parsing it back out of the name.
2. **Review page:** the field name and the type become expandable: click the field name to reveal its identifiers
   (subject, suffix, iteration, grid, block, block group, part). The field name cannot be edited directly, only its
   identifiers.
3. **Rename "description" for this part.** `description` is already the field's metadata (the blueprint's one-liner,
   usually from the tooltip). The identifier needs another word. Candidates: `subject` (what the field is about),
   `stem`, `term`, `concept`. Not `label` (reserved for the labeler, docs/GLOSSARY.md) and not `caption` (the printed
   text). Andrew to choose.
4. **The generator folds in later.** It already builds names from parts; making it emit identifiers instead should
   be a small change.
5. **New branch** (this one).

6. **"subject"** is the word (Andrew, 2026-10-19, later: "subject works as a replacement for description").
7. **Print order: the iteration last**, [subject]_[suffix]_[iteration]_[part] (Andrew: "I trust your judgement";
   chosen because it dissolves the one round-trip difference, below).
8. **An iteration needs no table.** It is "the Nth field that contains this information" (Andrew, 2026-10-19); a kept
   grid or block group is how the checks verify the numbers, not what makes a number an iteration. The fill's
   "series outside any kept grid" flag was dropped.

## Open decisions (for Andrew)

- The table letter: on every table whose subject repeats elsewhere in the form, or only the later ones? (Raised
  2026-10-19, not answered.)
- Where iteration membership lives: grids and block groups are kept outside the blueprint today
  (`runs/hand_review/grids/<id>.json`). For a blueprint to stand alone, the grids and block groups it refers to
  probably need to move into it (a blueprint-level list), or the identifiers carry enough to print the name without
  them. Recommend: into the blueprint, as an `x_petey_` extension.
- Suffix discipline (`first_nm` vs `first_name_txt`: is a suffix a data type or something semantic like nm?). Andrew:
  "we've kind of strayed from the suffix discipline, we will probably have to go back and sort that out later." With
  suffix as its own identifier this becomes a pass over one field. Keep it out of this branch's first steps.

## Steps

1. **The record format.** Write it into docs/NAMING.md and the BPT spec draft (`BPT SPEC v1.1.md` §5.2): the
   identifiers, the extension key on each field, the print function, the print order (once decided).
2. **Fill in the identifiers for existing fields** (about 78,000 across the 608 review-page blueprints), automatically:
   - subject and suffix from today's names (the naming standard's own reading: `petey/validate/standardize_names.py`,
     `SUFFIXES`, `standard()`);
   - iteration from the kept grids and block groups (`petey/validate/grid_check.py` `listing()`,
     `petey/validate/block_groups.py`);
   - part from compound values (`petey/validate/associate.py` `compound_values()`).

   Run on working copies, never the saved blueprints, and report: how many fields read cleanly, how many are flagged
   (ambiguous parse, conflicting memberships), by form and per page. Flag rather than guess.
3. **The print function** and a round-trip check: print every field's name from its identifiers and compare with
   today's name. The differences are the renames the migration would make; review them before applying (recorded as
   Claude's corrections, the person's verdicts moving with the names, as the naming-standard pass did).
4. **The review page.** Field name and type expandable; the identifiers editable; the name read-only and reprinted
   on every edit. (`petey/validate/blueprint_review.html` Review mode field panel; edits go through
   `hand_review.clean_edit` and `edit_fields`.)
5. **Point the checks at identifiers.** The grid code check (`grid_naming.on_pattern`), the resolver
   (`grid_naming.resolve`, `same_words`, `resolve_labelled`, `keyed_split`), the block checks and the clash handling
   compare identifiers instead of parsing names. Most of today's parsing (iteration tokens, lettered rows,
   [row label]_[column label] splits) should drop away.
6. **The generator.** Find where it builds names today (the labeler prompts in `petey/label/`, the type-to-suffix
   rules in `petey/semantic_types.py`, the naming standard pass) and have it emit identifiers.

Steps 1-3 first: step 2's numbers show whether the automatic fill is good enough to build the rest on.

## Steps 1-3 done (2026-10-19, later the same day)

Record format in docs/NAMING.md "Identifiers" and `BPT SPEC v1.1.md` §5.2.1 (draft): `x_petey_identifiers`
{subject, suffix, iteration, grid | block_group + block, part}; `field_identifiers.print_name` prints the name
in either order. `petey/validate/field_identifiers.py` fills the parts in from today's names, the kept grids and block groups
(`grid_check.listing`, so every form now has lasting ids under runs/hand_review/grids/) and the compound values, on
copies under runs/identifiers/<id>/, with a report (runs/identifiers/report.json) per form and per page. Run on the
289 launch T1 / T2 forms (Andrew: use those; 89 T1 + 200 T2), 1127 pages, 37,321 fields:

| | fields | share |
|---|---|---|
| read cleanly | 34,405 | 92.2% |
| flagged | 2,916 | 7.8%, 2.6 per page; 403 of 1127 pages have one, 147 have five or more; 107 forms have none |
| in a kept grid or block group | 16,053 | |
| with an iteration | 16,808 | 12,762 of them in a kept grid or block group; 4,046 in series no kept grid covers (case_N_nbr, debtor_N_nm, line_N_amt), which is fine (decision 8) |
| parts of compound values | 1,333 | |

Why flagged (fields / forms): a cell's number is not its row's or column's 1,237 / 74 (ACORD 126's
premises_operations_premium_amt_3: unstandardized names with the number after the suffix, and tables whose axis the
finder reads the other way; the worst pages are GSA SF 330 p12 151 of 250, IRS 941 Sch B p1 121 of 209, ACORD 126 p1
112 of 148); no standard suffix 1,034 / 112 (forms the naming pass has not touched; the fill should run after
`standardize_names`, not before); an unnumbered cell in a numbered table 204 / 39 (location_number, the un-numbered
first row); a row with no number at all 149 / 26 (ACORD 131's underlying coverages: rows named by kind the keyed
test does not take); two numbers and no way to tell which iterates 116 / 16 (ACORD 90 NY's vehicle_1_driver_6_use_pct:
a vehicle x driver grid); in two kept entries at once 111 / 10 (a finder table inside a block group both active);
a name that is only a suffix 69 / 59 (dt, signature, initial).

Round trip: printed back in the old order ([subject]_[iteration]_[suffix]_[part]), 29,568 of 37,321 names come back
the same and 7,753 (20.8%) differ, every one for the same reason: the old standard put the iteration after the word
it counts (garaging_location_1_address_txt, parent_1_first_nm), and one subject printed with the number next to the
suffix gives garaging_location_address_1_txt. Printing that shape would need the subject split into the thing
counted and its attribute (the entity, `petey/validate/associate.py`), which is parsing again. The decided order, the
iteration last (decision 7), has no such question; it renames 16,366 names (43.9%), every iterated one
(garaging_location_address_txt_1). Those renames are the migration (step 3's review); the fill is only as good as
the names it reads, so the naming pass goes first on the forms it has not touched.

## Step 4 done (2026-10-19, evening)

The review page's field card prints the name from its parts. The field name box is read-only; a "parts" button
beside it opens subject / suffix / iteration / part (editable), the kept grid or block group the field is a cell of
(read-only, from the kept list) and whether the parts are stored on the field or read from its name (plus what the
reading could not settle, in red). Typing in a part reprints the name in the box as you type; "save correction"
sends the parts, the server prints the name from them (`hand_review.clean_edit`, `identifiers` in the edit), the
rename goes through as every rename does (verdicts follow, the working copy takes it) and the parts are stored on
the field as `x_petey_identifiers` (membership kept from the kept list; `edit_fields`). The page's payload carries
each field's parts (`hand_review.identifiers` -> `field_identifiers.read_form`: stored ones with the membership
refreshed, else read from the name, about 0.3 s per form on open). Headless check on lib__fw9: edit, save, reload,
the rename in the list and the parts stored; no page errors.

Not changed: "improve name" and the page check's fixes still fill the name box directly (the next save sends the
name alone, and the parts are read from it again); the Groups tab and the chat's renames do not store parts; the
old-order names on the 289 forms are not migrated (step 3's renames wait for a pass, after the naming standard
on the forms it has not touched). The panel's open / closed state is remembered in the browser.

## Step 6 in progress: structure before labeling (2026-10-19, evening)

Andrew: "identify the grids and blocks first, then use that as guidance for labeling"; then "keep working on
integrating grid and block structure into the generation process". Built (`petey/label/structure.py`; `auto_label
--structure guide | bulk`, `form_run --structure`):

- **The finders run on the raw widgets** (box positions; the page's captions for block groups), before any name,
  in half a second. A table or block group is never split across two labeler batches (the batches are cut at its
  edges), and each batch's prompt lists its structures row by row, with evidence of which axis repeats read from
  the publisher's own field names (Vehicle_SeatBeltCode_A / _B down a column: the rows; PIP_PremiumAmount_A .. _D
  along a row: the columns; generated ids f1_01 / f1_02 say nothing).
- **guide**: still one label per widget, with the structure as context.
- **bulk**: the labeler names a table's columns once (or its rows, when the columns repeat; or both, when rows are
  things and columns kinds) and a block's fields once with the entity that repeats; the cells are printed from the
  parts, `[subject]_[suffix]_[iteration]`, and keep them as `x_petey_identifiers` (the review page shows "parts
  stored on the field"). A Yes / No pair inside a structure is labelled `<question>.<value>` and becomes one choice
  field per row or block. A line no filer writes in is labelled "" and its cells dropped. A table the labeler calls
  unlike, a column it leaves out, or two boxes the finder stacked at one position are labeled one by one.
- Also today, on the way: labeler batches and page-check pages run concurrently (a call's time is its output, so a
  dense page costs its slowest batch and a form its slowest page); the grid finder no longer lumps boxes whose x
  matches no column centre into one bogus column.

Measured on four forms (round 0 = straight out of the labeler and its first page check; "on pattern" = tables
the code check passes on the round-0 blueprint; "printed" = names printed from parts, kept as identifiers; label
cost = the labeler's calls' output tokens). The bulk column is its last version (v3-v5: evidence hints, the
settled axis told, ledger suffix, aside rows, duplicate labels); the run records are under
runs/judge_eval/form_runs/ as <form>_guide / _bulkN:

| form | plain | guided | bulk |
|---|---|---|---|
| ACORD 90 NY (687 fields, 13 tables) | 107 flags (a batch split the vehicle table); 2 on pattern; 16k tokens; 214 reviewed; 40 min, 89 flags left | 13 flags; 8 on pattern; 17k tokens; 150 reviewed; 34 min, 7 flags left | 13 flags; 10 on pattern; 437 of 690 printed; 9.8k tokens |
| Form 8825 (205, 7 tables) | 0 flags; 3 on pattern; 4.9k tokens; 143 reviewed | 8 flags (reserved lines kept); 6 on pattern; 124 reviewed | 0 flags; 7 on pattern; 198 printed; 1.4k tokens; 121 reviewed |
| AO 40B (238, 3 tables, a 27-row ledger) | 8 flags (hatched cells); 0 on pattern; 5.1k tokens | 8 flags; 1 on pattern; 5.5k tokens | 8 flags; 3 on pattern; 222 printed; 1.2k tokens |
| IMM 5645 (113, 3 block groups) | 0 flags; 1 on pattern; 2.7k tokens; 2 review rounds | 0 flags; 3 on pattern; 1 review round | 0 flags; 3 on pattern; 76 printed (the Yes / No pairs are choice fields); 1.9k tokens |

What it took to get the labeler to name tables in bulk (each a prompt or printing change, each measured):
without evidence it called 6 of ACORD 90 NY's 9 tables and all of AO 40B's "unlike"; told which axis the
publisher's field names settle, and that such a table is not unlike, it named them all; a ledger cell takes its
suffix from the row label when the column has none; a header line over a table (ACORD's driver numbers) is set
aside by the labeler; two panes side by side read as one table (vehicles 1-2 left, 3-4 right) give one label to two
columns and those cells are labeled one by one instead of colliding. Small and odd tables (under 3 x 3 without
evidence) are left out altogether (Andrew: the big ones are the low-hanging fruit).

What this says: cutting the batches at table edges removes the split-table failure outright; the structure in the
prompt doubles or triples the tables on pattern straight from the labeler and shortens the loop; bulk reaches the
same round-0 flags as guided at a third of the labeler's output tokens (8825: 4.9k -> 1.4k; AO 40B: 5.1k -> 1.2k;
ACORD 90 NY: 16k -> 9.8k) and leaves every printed cell with its parts stored. Open: a block's choice field carries
no parts yet; the kept-list ids for structures found before labeling (today `listing` refinds them on the finished
blueprint); whether bulk goes on by default (it is a flag on form_run today).

## The validate pass, measured and cut (2026-10-19, late)

A loop round on ACORD 90 NY cost about seven minutes whether it changed 24 fields or none, because the pass
regenerated, re-extracted and re-judged the whole form every round. Measured step by step (round 1, 14:29-14:40):
classify the boxes for the generator 4 min (once per blank, cached), make and fill 3 cases 1 min, native
extraction and scoring 3 min, the judge 2 min (a Sonnet call per 120 fields with the whole document in each, cached
on the whole document and field list, so any rename missed every call), then detection and the reviewer. Fixed:

- **Native extraction** walked `page.widgets()` for every field: 213,000 widget loads, 182 s a case. The page's
  widgets are indexed once: 0.7 s, the same 687 values.
- **The judge** reads one page per call, a page's fields against that page's text, cached on the page and its
  fields, the pages together. A page nothing changed on is free in the next round.
- **The classifier's pages** go out together (64 + 34 + 11 + 11 s -> the slowest).
- Also: the labeler's batches and the page check's pages together (the morning's change).

A full pass on the guided ACORD 90 NY blueprint now takes 1 min 38 s (three cases: fill 55 s, native 2 s, judge
and scoring 40 s), from about six with the classification cached and ten without. A second pass with nothing
changed took the same, because one page's filled text differed between two renders of the same frozen case (a
money box drawn "424 / 87" then "424 87 / 00"), which re-asked that page: the fill is not byte-deterministic, and
that is the next thing to look at if the warm pass should be free. The 40-minute ACORD 90 NY run would be about
20 with these in: the labeling, the reviewer's Opus calls and the first page check are what is left.

## Extraction reads the page only (2026-10-19, late)

Andrew: "the loop should be evaluating the ability to extract data from the form based on the blueprint alone.
presume the form is flattened and no metadata is available. metadata is only for generating (and correcting,
editing etc) the blueprint." Until today `petey/extract.py` (the product extractor, and the loop's native arm) read
the AcroForm stored value by path first and fell back to the rect only without a form layer, so the loop measured
the form layer. Now: the input is flattened in memory; a text field is the words mostly inside its rect less what
the blank prints there; a mark is added ink against the blank; a dropdown is the text it shows mapped to its
option; the form layer is never read. On ACORD 90 NY case 1, 652 of 687 values are as before and the rest are what
the box shows of a value that overflows it (4821 as 482): the loop's differ count rises from 6 to 33 on that case,
and those are real findings about boxes too narrow for the generator's values. Paths and tooltips stay in the
blueprint as metadata for the labeler, the page check, the witnesses and the review page.

## The whole loop, timed (2026-10-19, 17:06-17:26)

ACORD 90 NY end to end with everything in (guided structure, the concurrent labeler / page check / classifier,
the page-only extractor, the per-page judge), from the run records' stamps:

| run | round 0 | loop rounds | end |
|---|---|---|---|
| plain, morning | 7.8 min (107 flags) | 18, 7, 7 min | 40.2 min |
| guided, old pass | 4.6 min (13 flags) | 14, 7, 8 min | 33.9 min |
| guided, new pass | 7.5 min (14 flags; a 172 s Gemini strip) | 6.8, 1.6, 2.2, 1.7 min | 19.8 min |

A loop round after the first costs about two minutes instead of seven; the first costs the reviewer's Opus
calls (124 fields) plus a fill. What is left: labeling (4.6 min, Gemini's time on a batch swings from one to three
minutes), the first page check (3 min, output-bound), the reviewer in round 1 (about 4 min), and a fill a round.

## Where things stand (end of 2026-10-18 / 19 session)

On `validation-tools-2026-10-14` (pushed only up to the commits before this session's; Andrew opens the PR):

- `17e7641` Grids and Blocks as two tabs; kept list per form (ids `p1-T2` / `p2-BG1`, cancel with provenance
  finder / person / combined, draw an area, combine); block-group finder `petey/validate/block_groups.py` (step voting, chains,
  caption check). Spot check 100: 89 right, 3 doubtful, 2 wrong; 304 groups on 164 forms.
- `6ebf7b7`, `13961fb` Grid resolver standardizes equivalent spellings in code (both rows and columns; labelled
  rows read as the code check reads them). `eval/grid_equiv_eval.py`: equivalent plants settle 83-100%, different
  plants stay unsettled 217/218 and 88/89. On the library only 5 more tables settle in code; most tables that go to
  Opus hold genuinely different wordings or are read the wrong way round (4797's properties, 5498's boxes).

Not done, waiting on this plan:

- **Name clashes** (54 tables stop because the name they want is held outside the table): mostly a series continued
  across a page or past the finder's table boundary (B 106E/F creditors 1-3 on p2, 4+ on p4; FW-001's first income
  rows), sometimes a different table sharing a subject. Agreed direction: continue numbering for a split table; a
  table letter for a different table. With identifiers, both become a question of which grid a field belongs to.
- Block groups with two entries per block (N-336 additional information, PLD-PI-001 defendants A/B) should be split
  in half, not rejected; FEC 3X page 6's block edges are off by a line.
