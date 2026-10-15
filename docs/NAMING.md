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
mechanical pass); the page check flags them too.

`eval/standardize_names.py` applies the rules that are mechanical and lists the names it cannot place.
