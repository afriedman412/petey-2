---
name: grid-validation
description: Validate and fix the field names of a table (grid) on a blueprint so every cell follows one pattern. Use when Andrew asks to check, validate, fix or rename a grid / table / schedule on a form (e.g. "can you check the grid on je__form10 p1"), or when eval/grid_naming.py flags cells.
---

# Grid validation

The rule (Andrew, 2026-10-15; docs/NAMING.md "Grids"): a table is named on one pattern. Either each column is one
kind of value with one wording and each row carries one iteration number (AO 40B's expense table:
`expense_private_5_amt`, row 5), or the transpose (Form 8825's income grid: `gross_rents_2_amt`, property column 2).
Names follow the naming standard `[description]_[iteration]_[suffix]_[part]` (docs/NAMING.md).

The code finds and fixes the mechanical cases; the judgment below is what the code cannot do.

## Steps

1. **Look at what the code sees.** Work on the review page's working copy (`hand_review.working_path(bid)`), never the
   saved file (it can be stale: the naming pass may already have fixed it).
   ```
   PYTHONPATH=. venv/bin/python eval/grid_naming.py <bid>          # cells off the pattern
   PYTHONPATH=. venv/bin/python eval/grid_naming.py <bid> --fix    # the renames it would make
   ```
   Print each grid as rows x columns (`grid_naming.grids(bp)`) to see the names in place. A table that passes the
   code check (`grid_naming.on_pattern`: each column one pattern varying only by its iteration, rows numbered by steps
   of 1) is done; the review page's "check grid" accepts it without a model call. Spend the judgment on the rest.

2. **Look at the page.** Render it with the boxes numbered and read the headers:
   `pc.render(resolve_blank(bp), page, pc.numbered(bp), dpi=100)` (petey/validate/page_check.py), then Read the PNG.
   Decide: what is a row (an iteration: a schedule number, a person, a property) and what is a column (a kind of value).

3. **Decide the names** (the judgment calls, with today's precedents):
   - **Which way it runs.** Rows numbered and columns worded is the usual reading; a grid of properties or periods across
     the top runs the other way (8825's income lines x property columns).
   - **Number by the table's own row, 1..N.** Not a continuation of another table's numbers (8949 page 2 had 12-22
     after page 1's 1-11; ACORD 81 page 3 amounts ran on from page 1).
   - **Labels that change page to page** (8825's properties A-D, schedule letters): number 1, 2, 3 instead.
     Fixed letters the form itself refers to keep their letters (the ADA claim's diagnosis codes A-D, which the
     procedure lines' "diag pointer" column points to): `diagnosis_code_a_txt`, not `_1_`.
   - **Preprinted rows and blank rows are one table.** ACORD 81's classes 1-13 (Jewelry, Furs, ...) and blank rows
     14-21 are all schedule numbers 1-21; fields only the blank rows have (class code, description) keep the row's number.
   - **Separate tables get separate names.** Two tables of the same columns (8949's Part I short-term, Part II
     long-term; AO 40B page 2's expense and property tables) are told apart by a prefix (`short_term_`, `long_term_`),
     each numbered from 1. Two stacked sections in one table keep one set of columns (C-148's recycling containments
     rows 1-5, storage tanks rows 1-6).
   - **Several of one kind in a row** (three coverage qualifiers per row): name the columns apart
     (`first_` / `second_` / `third_coverage_qualifier_N_cd`) so each name carries one number.
   - **A totals row** is named for the column without a number (`long_term_total_proceeds_amt`, `monthly_total_bbl`),
     the column's unit suffix kept.
   - **Y / N columns** printed as one text box per cell get the pattern `^[YN]$` (ACORD convention); when the page shows
     two tick boxes (YES / NO columns) over one widget, split into a yes / no group (eval/split_yes_no.py) instead:
     the page beats the widget metadata (memory: feedback-page-over-metadata).
   - **Misaligned boxes** (EP-2's RRC column a few points off): number each column from box positions, top to bottom,
     after checking every column has the same count.
   - Tax forms may keep line-number names (`line_4c`) where the caption is only an instruction.
   - A signature or address block that merely lines up is not a table: leave it.

4. **Apply** through the chat's apply path, which validates like a correction, refuses clashes, moves Andrew's verdicts
   with renames and records each change as Claude's (`x_petey_hand_edit` by claude):
   ```python
   from petey.validate import form_chat as fc
   fc.apply(bid, [{"field": old, "edit": {"name": new}, "why": "..."}, ...], groups=[])
   ```
   Patterns or types go in the same `edit` dict (`{"pattern": "^[YN]$"}`). For the mechanical cases,
   `eval/grid_naming.py <bid> --fix --apply` does the same.

5. **Re-check.** `eval/grid_naming.py <bid>` should list nothing for the table, then page-check only the changed fields:
   `PYTHONPATH=. venv/bin/python eval/page_check_working.py --changed <bid>` (keeps every verdict still valid).

6. **Report** by field code (`form_1_7`) and name, old -> new in a short table; say what was left and why. Do not touch
   forms Andrew is checking or has said he wants to look at first.
