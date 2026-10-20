# Simple names, day 2: held-out forms and extraction on a fixed harness (2026-10-20)

Follows `docs/RESULTS_SIMPLE_NAMES.md` (2026-10-19). Three forms from families none of the prompt changes looked at,
run standard and simple (simple6) twice each, interleaved: SBA 413 (personal financial statement, 139 fields),
CBP 7512 (customs, 147), HMRC 64-8 (UK, 76). The bench is `eval/simple_names_bench.py`; it now leads with
extraction, the measure that counts (Andrew: a disagreement matters only if it changes what extraction reads back).

## Extraction is level

Yesterday's extraction numbers were partly the test harness's: frozen test cases held doubled values, and values
drawn for the page finder's box overflowed the narrower form field inside it (`docs/HARNESS_DOUBLED_VALUES_2026-10-20.md`).
With that fixed, every final run's blueprint refilled on its own frozen set (wrong read-backs of values read):

| form | standard | simple |
|---|---|---|
| ACORD 90 NY | 3 of 1,613 | 14 of 1,605, 2 of 1,578 |
| Form 8825 | 0 of 576 | 0, 0 of 576 |
| AO 40B | 35 of 702 | 31, 28 of 702 |
| IMM 5645 | 0 of 354 | 0, 0 of 354 |
| SBA 413 | 3, 2 of 384 | 2, 1 of 384 |
| CBP 7512 | 18 of 362, 16 of 363 | 14, 15 of 362 |
| HMRC 64-8 | 0, 0 of 207 | 0, 0 of 207 |

Level on all seven forms. What is left on both sides is mostly the page classifier and the blueprint disagreeing on
what a box holds (AO 40B's shaded cells, "life or rate"; CBP 7512's date fields; ACORD 90 NY's horsepower, which the
simple arm types an integer, correctly, while the classifier drew a state code there).

## Round-0 flags on the held-out forms

| form | standard | simple |
|---|---|---|
| SBA 413 | 0, 0 | 1, 3 |
| CBP 7512 | 5, 8 | 4, 2 |
| HMRC 64-8 | 9, 7 | 2, 2 |

The held-out forms confirm the type finding: HMRC 64-8's standard runs typed `company_registration_number` and
`company_unique_tax_reference` business names from the word "company", the same name-word inference behind all of
yesterday's standard wrong-type flags. They also showed the simple scheme's own failure mode, a wrong kind:

- **SBA 413's full-name box** (sba413_2_1) typed `first_name` in one simple run: the kind list offered first and last
  name and no whole name.
- **HMRC 64-8's postcode and phone** given the kinds `zip` and `phone`, whose patterns are American (a five-digit ZIP,
  (555) 555-5555); the loop's page check flagged them on a UK form. The standard scheme puts the same US pattern on
  `phone` from the name.

## Decided today (Andrew)

- **One name kind**: `name` for any name, a person's or an organization's, whole or part ("more specific than that is
  just noise"); first / last / entity / business name are no longer offered (they stay valid in the registry). City,
  country, street address, name and address, description stay ("fine and common"); `text` is the fallback.
- **Split lines are fine**: a multi-line answer kept as numbered fields (`entered_or_withdrawn_by_line_1` .. `_5`) is
  not an error; the page check no longer flags them as continuing each other.
- Folded by Claude, not yet confirmed: `birth_date` and `service_date` are no longer offered; they are `iso_date` to
  the letter (type, pattern, charset), and IMM 5645's dates of birth came back as either.

## Decided later the same day (Andrew)

- **Simple names are the default** for new blueprints (`--names standard` gives the suffixed scheme).
- **Non-US patterns**: new kinds `ca_postal_code` (A1A 1A1), `uk_postcode` (SW1A 1AA), `uk_phone`, `intl_phone`
  (Canada's phones fit `phone`). 19 fields in 11 library blueprints corrected in their working copies as Claude's
  edits (CRA T2 and T1 postal codes; HMRC 64-8, IHT400 and six Companies House phones; Hong Kong IRD phone and fax),
  for Andrew to save or discard on the review page; IRCC IMM 5476's representative postal code left as a suggestion
  (the country varies).
- **Dates**: what a date is for belongs in the name; the type is `iso_date`.

## Open

- The suffix printed on request (MeF-style names from the type at output): not built.
