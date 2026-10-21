# Claude pass: reviewing blueprints from what you know (brief for reviewer agents, 2026-10-13)

Petey turns fillable PDF forms into blueprints: one entry per field, with a snake_case name, a type, and the widget's position. Small models made these blueprints from limited evidence and many fields are obviously wrong to anyone who knows the form. Use everything you know about each form (the agency, its parts and line items, standard field conventions) together with the evidence in the dump, and propose corrections. Andrew (the founder) reviews every change on the review page before anything is saved, and every change needs a short rationale he can check.

## The dump: `runs/claude_pass/<id>.txt`, one line per field in reading order

- `p<page> <name>`: the field's current name.
- `type=`: type / semantic type / pattern.
- `tooltip=`: the publisher's own description of the widget. Strong evidence. On many government forms it names the part, item number and field exactly.
- `printed=`: text printed near the box on the page. This is noisy: it includes neighbouring lines.
- `desc=`: the description. It is often copied from the tooltip.
- `CHECK=`: an automatic name check saying the text fits another field better. That is a hint of a swap or a block shifted by one row; it is not proof.
- `ANDREW=`: Andrew's own verdict. `accept` means he checked that field: leave it alone unless it is clearly wrong, and then expect your change to become only a suggestion. A note after the verdict tells you what he thought was wrong. Use it.
- `options=[key='caption'...]`: the boxes of an option group. `(LOCKED: xfa)` and `(LOCKED: hand)` captions must not be changed. `<tooltip ...>` is that box's own tooltip.
- `UNCLAIMED sid=...` lines: boxes on the blank that no field covers.
  - A *widget* line (`checkbox widget ...`, `text widget ...`) is a real fill-in box the blueprint is missing. Usually add it.
  - A *finder* line (`finder text box ...`) is an image-detected box. Most are printed cells beside fields that already exist, or labels. Add one only when it is clearly a place to write that no field covers.
  - `would_be=` is the name the tool would give it. Improve on it.

Reading order and position matter. Neighbouring lines tell you which block of the form a field sits in, which helps you spot a block of names shifted by one, swapped pairs, line 1 vs line 2, and a field named after the label of the box next to it.

## What to look for

1. **Wrong names**: the name describes a different field from the one the box is.
   - Typical causes: shifted blocks (each field takes its neighbour's name), swaps, the wrong person (petitioner vs beneficiary, spouse vs applicant, employer 1 vs 2), the wrong part or section, and a date named as a signature.
   - Use the tooltip and your knowledge of the form to decide.
2. **Unclear or misleading names** that mean the right thing but would confuse a reader of the data, for example `field_23` or `text1`.
   - Leave names alone that are fine but merely not how you would write them. Do not rename for style.
3. **Types**:
   - Types are `string`, `number`, `integer`, `date`, `boolean` (a single checkbox), `category` (choose one of several boxes), and `multi_category` (any of several boxes).
   - Money is `number` with semantic type `money` (or `money_whole_dollar`).
   - Counts are `integer` with semantic type `count`.
   - Dates are `date`. A month/day/year split into separate boxes uses `date_month` / `date_day` / `date_year`.
   - An option group must be `category` or `multi_category`.
4. **Semantic types**: valid values are `account_number birth_date business_name city count country country_code date_day date_month date_year description ein email entity_name first_name id_part datetime indicator iso_date itin last_name money money_whole_dollar naics npi percent phone routing_number service_date ssn state_abbr street_address text tin year zip`, or `none` to clear one. Fix ones that are wrong (an SSN typed `phone`, a county typed `city`). Do not use `person_name`; it is being removed, and the apply step clears it everywhere.
5. **Option captions** that do not match the printed text at each box (not LOCKED ones). Give the caption as printed.
6. **Missing boxes**: UNCLAIMED widget lines, as above.
7. **Not fields**: a field on something nobody fills in, such as a heading or a printed instruction box. Remove only when you are sure; otherwise mark it not sure.

## Naming conventions (match what is there)

- snake_case, lower case, digits allowed.
- Suffixes in use:
  - `_nm` names
  - `_dt` dates
  - `_amt` any number, currency or not (hours, counts and measures are fine as `_amt`; fix the type instead of inventing `_hrs` / `_cnt`)
  - `_ind` a single checkbox
  - `_cd` codes and short coded values
  - `_txt` free text
  - `_num` / `_number` identifiers
  - `_ssn`, `_ein`
- Keep a form's existing pattern for repeated blocks (`employer1_...`, `employer2_...`; `line_1` / `line_2`).
- Option group names say what the group asks (`filing_status`, `marital_status`). Option keys are left alone.

## Output: one JSON file per form, `runs/claude_pass/proposals/<id>.json`

```json
{"changes": [
  {"field": "<current name>", "sure": true, "kind": "wrong", "name": "<new name>", "why": "Tooltip says Part 2 item 21 Employer 1 street; the name says city (block shifted by one)"},
  {"field": "<current name>", "sure": true, "kind": "type", "type": "number", "semantic_type": "money", "why": "..."},
  {"field": "<current name>", "sure": true, "kind": "caption", "options": {"<key>": {"caption": "<printed caption>"}}, "why": "..."},
  {"add": "<sid from an UNCLAIMED line>", "name": "<name>", "type": "string", "semantic_type": "...", "why": "..."},
  {"remove": "<current name>", "sure": false, "why": "..."}
]}
```

- One entry per field; it can carry several fixes at once (name + type + semantic_type). Only include keys you are changing.
- `kind`:
  - `wrong`: the name describes a different field.
  - `clarity`: same meaning, clearer.
  - `suffix`: only the suffix changes.
  - `type`: type or semantic type only.
  - `caption`: captions only.
- `sure`: true when the evidence (the tooltip, the printed text, your knowledge of the form) settles it. Use false when you think it is likely but not certain. Unsure changes become suggestions Andrew clicks "use" on; sure ones go straight into the working copy for him to check.
- `why`: required, one sentence, citing the evidence (tooltip, printed text, item number, the form's structure).
- Renames that swap two fields: list both. The apply step handles the swap.
- An empty `{"changes": []}` is a fine answer for a clean form.

Write only the proposal files. Do not edit blueprints or any other file. Check that each file is valid JSON when you are done (`python3 -m json.tool <file> > /dev/null`). At the end, report for each form: the number of changes by kind, the most important problems found (a few lines), and anything you could not decide.
