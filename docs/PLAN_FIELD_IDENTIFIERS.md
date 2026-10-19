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
   - subject and suffix from today's names (the naming standard's own reading: `eval/standardize_names.py`,
     `SUFFIXES`, `standard()`);
   - iteration from the kept grids and block groups (`petey/validate/grid_check.py` `listing()`,
     `eval/block_groups.py`);
   - part from compound values (`eval/associate.py` `compound_values()`).

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
{subject, suffix, iteration, grid | block_group + block, part}; `eval/field_identifiers.print_name` prints the name
in either order. `eval/field_identifiers.py` fills the parts in from today's names, the kept grids and block groups
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
counted and its attribute (the entity, `eval/associate.py`), which is parsing again. The decided order, the
iteration last (decision 7), has no such question; it renames 16,366 names (43.9%), every iterated one
(garaging_location_address_txt_1). Those renames are the migration (step 3's review); the fill is only as good as
the names it reads, so the naming pass goes first on the forms it has not touched.

## Where things stand (end of 2026-10-18 / 19 session)

On `validation-tools-2026-10-14` (pushed only up to the commits before this session's; Andrew opens the PR):

- `17e7641` Grids and Blocks as two tabs; kept list per form (ids `p1-T2` / `p2-BG1`, cancel with provenance
  finder / person / combined, draw an area, combine); block-group finder `eval/block_groups.py` (step voting, chains,
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
