# Field naming (draft, 2026-10-14)

Settled with Andrew on 2026-10-14, being workshopped on copies before it touches any blueprint. Once settled it goes
into the blueprint spec (`BPT SPEC v1.1.md` §5.2 Field Names, which today only says names SHOULD be snake_case). The
associations it serves (entities, compound values; `eval/associate.py`) would be new spec too: §5.5's `parent` composition
covers repeating rows of an `array`, not entities, compound values, or rows bound to their own widgets. Goal: names whose
shape is predictable, so associated fields (entities, compound values) can be read from them.

## Shape

    [description]_[iteration, when there is more than one]_[suffix]

- The **suffix** says what kind of value the box holds. It is always last, and there is exactly one.
- The **description** uses the form's own words: `given_nm` on a form that prints "Given Name", `first_nm` where it
  prints "First Name". Consistency is in the suffix, not the vocabulary.
- An **iteration** number follows the word it counts and comes before the suffix: `parent_1_first_nm`,
  `premises_2_city_nm`, `line_other_6_txt`. When a thing occurs more than once, every occurrence is numbered, the first
  one too: `parent_1_nm` and `parent_2_nm`, never `parent_nm` and `parent_2_nm`. Numbers are separate words
  (`parent_1`, not `parent1`) and never come after the suffix (`agency_customer_2_nbr`, not `agency_customer_id_2`).
- **Option groups** (one question answered by several boxes) are named for the question, with no suffix, as before.

## Suffixes

| suffix | the box holds |
|---|---|
| `_nm` | the name of anything: a person, business, agency, plan, city. Person vs business is the semantic type's job |
| `_nbr` | an identifier written out, not a quantity: phone, policy, account, unit, license, case, claim |
| `_ssn`, `_ein`, `_tin`, `_npi` | those identifiers (they say more than `_nbr`) |
| `_cd` | a code from a fixed list: state, country, ZIP, SIC, NAICS, class codes |
| `_dt` | a full date |
| `_month`, `_day`, `_yr` | one part of a date written in separate boxes (a compound value) |
| `_time` | a clock time, in whatever format (the pattern carries "12:00" vs "1430") |
| `_amt` | money only |
| `_cnt`, `_qty` | a count or quantity; equivalent, whichever reads better |
| `_pct` | a percentage of something (a rate in percent, a share); not `_qty` (2026-10-15) |
| measure units | `_ft`, `_sq_ft`, `_miles`, `_hours`, `_days`, `_months`, `_years`, `_bbl`, `_mcf`: a quantity named for its unit (a term in months: `loan_term_months`; `_month` stays the month part of a date) |
| `_ind` | a single checkbox |
| `_txt` | free text, including address lines and email addresses (`_address_line_1_txt`, `_email_address_txt`) |
| `_signature` | a signature box |

Apartment, suite and unit boxes are `unit_nbr`. A state is `state_cd` (not `state_abbreviation_cd`, `state_abbr`,
`state`): the suffix already says it is a code.

## Grids

A table is named on one pattern (2026-10-15): each column (or row) is one kind of value with one wording, and each row
(or column) carries one iteration number, the same in every cell of it. AO 40B's expense table runs by row:

- `expense_type_5_txt`, `expense_official_5_amt`, `expense_private_5_amt`, `expense_total_5_amt` (row 5)

Form 8825's income grid runs by column, the property: `gross_rents_2_amt`, `advertising_2_amt`, ... (property 2).
When a table's own labels are letters that change from page to page (8825's properties A-D), number the iterations
1, 2, 3 instead. `eval/grid_naming.py` finds tables by layout and lists the cells that break the pattern (in the
mechanical pass); the page check flags them too. Rows outside the pattern are set aside and said on the Grids card
(2026-10-19): a last row of totals, and a first or last row of its own kind whose cells are not named like their
columns while the other rows agree (ACORD 90 NY's driver-number boxes over the vehicle rows). The card lists the
columns (each wording, the printed caption, cells numbered off their row) with a "standardize" button on a column
that needs one and "standardize all" at the top, and the rows (numerical 1 to N, lettered, or labelled) with
"standardize" on a row whose cells carry more than one number; the table's id copies its reference
(`acord_90_ny_p1-T13`) like a field's.

`eval/standardize_names.py` applies the rules that are mechanical and lists the names it cannot place.

## Identifiers (draft, 2026-10-19; docs/PLAN_FIELD_IDENTIFIERS.md)

A field name is printed from stored parts, never edited as a string (Andrew, 2026-10-19: "encode the field name
parts instead of inferring the name from structure"). Each field carries them under `x_petey_identifiers`:

    first_name_txt_3:
      x_petey_identifiers:
        subject: first_name     # what the box is about, in the form's own words (Andrew, 2026-10-19: "subject")
        suffix: txt             # what kind of value it holds (the table above); an option group has none
        iteration: '3'          # the Nth field holding this information: 3, 12, 4a, b; absent when it occurs once
        grid: p1-T2             # the kept grid it is a cell of (ids from the review page's Grids tab)
        part: month             # which box of a compound value: month / day / yr, area / prefix / line,
                                #   dollars / cents, 1 / 2 / 3 (SSN, EIN, ZIP, numbered lines); absent otherwise

- `subject` and `suffix` are the name's words; `iteration` is the field's own number, the Nth field holding this
  information (Andrew, 2026-10-19), and needs no grid: `grid` says which kept grid it belongs to when it does (the
  kept record, `runs/hand_review/grids/<id>.json`, holds the cells' rows and columns), which is how the grid checks
  verify the numbers; `part` says which box of one value it is. (`block_group` / `block` went with block groups,
  2026-10-22; a block's prefix and iteration come from its block type, `petey/validate/block_types.py`.)
  A compound value is the boxes whose subject, suffix and iteration agree and whose parts differ, as
  `eval/associate.py` reads it today.
- A number that is not an iteration stays in the subject (`line_6`, `item_5a`, `w2`): the subject is words, and a
  number in it is one of the words.
- Keyed tables (rows named by role or kind: `applicant_nm`, `spouse_nm`) have a grid but no iteration: the row's
  key is part of the subject.
- **Printing** (`eval/field_identifiers.print_name`): `[subject]_[suffix]_[iteration]_[part]`, absent parts
  skipped, joined by `_` (decided 2026-10-19: the iteration last, the one part that never repeats across a form;
  `parent_first_nm_1`, not `parent_1_first_nm` as the shape above had it). This supersedes "an iteration number
  follows the word it counts" above once the identifiers are applied. A table letter for a second table sharing a
  subject (`first_name_txt_a1` / `_b1`) would go inside the iteration at print time; not decided.
- Nothing reads the parts back out of the string. The grid checks, the resolver and the clash handling compare
  identifiers (plan step 5); until then they parse the printed name as before.

On the review page the field name is read-only and its parts sit under a "parts" button beside it (2026-10-19):
edit a part and the name is reprinted; saving stores the parts on the field. `eval/field_identifiers.py` fills the identifiers in from today's names, the kept grids and block groups and the
compound values, on copies under `runs/identifiers/`, and reports what it could not read (plan step 2), then prints
every name back and lists the differences (step 3).
