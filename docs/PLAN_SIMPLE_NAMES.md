# Plan: benchmark a simpler naming scheme (2026-10-19)

Andrew: the "suffix" concept may be overcomplicating things and making labeling harder. The question to settle
with numbers: does a labeler that names only the SUBJECT, with the kind of value left to `type` and
`semantic_type`, produce better or worse blueprints than the one that also writes a suffix?

## The scheme under test ("simple")

- A field name is the subject in the form's own words: `first_name`, `vehicle_make`, `gross_rents`, `years_at_
  current_address`. No type suffix (`_txt`, `_nm`, `_nbr`, `_cd`, `_dt`, `_amt`, `_ind`, `_qty` ...), no semantic
  suffix (`_ssn`, `_ein`): the kind of value is the field's `type` and `semantic_type`, which the labeler still
  sets as today.
- Iterations and parts are unchanged: `parent_first_name_2`, `ssn_1`; option groups are named for the question as
  today, options by `<question>.<value>`.
- Where a consumer wants MeF-style names, the suffix is PRINTED from the type at output time, not labelled. The
  identifiers (`x_petey_identifiers`) already keep subject, suffix, iteration and part apart, so this is a print
  option, not a data change.
- The one case a suffix separated, two fields with the same subject and different kinds on one form (a phone text
  box beside a phone checkbox), falls to the dedup, which numbers the second; the benchmark counts how often it
  happens.

## What changes to run it

`--names simple` on `form_run` and `auto_label` (default `standard`, today's behaviour):

1. The labeler's system prompt loses its suffix rules (the MeF-style list, `_ind` for checkboxes, `_nm` / `_name`,
   `_business_name`) and says instead: name what the box holds in the form's own words; the kind of value is not
   part of the name. The dot-notation, radio, copy-prefix, tooltip and grounding rules stay.
2. Bulk structure printing (`petey/label/structure.py`) prints no suffix (it finds none to split off; nothing else
   to do). Guided mode is unchanged.
3. The page check is unchanged: it judges whether the name says what the box holds, which is the same question
   either way. (Its prompt does not ask for a suffix.)
4. The naming-standard pass (`eval/standardize_names.py`) is not part of a run and is not run.

## The benchmark

Same four forms as today's structure benchmark, bulk mode, everything else as the 17:06 timing run:

| form | why |
|---|---|
| ACORD 90 NY | the densest form; 13 tables; the suffix-heavy insurance vocabulary |
| Form 8825 | lettered columns, line-item rows, money everywhere (`_amt` on every cell today) |
| AO 40B | a 27-row ledger, dollar columns |
| IMM 5645 | block groups, names and dates, Yes / No pairs |

Two arms per form: `standard` (today's bulk runs, already recorded as `<form>_bulk5` / `_bulk3`) and `simple`
(new runs `<form>_simple`). Each arm's measures, all from the run record and the finished blueprint:

1. **Round-0 flags** (the page check's wrong_name / wrong_type / other on the labeler's output): the first-order
   quality measure. Split by problem.
2. **Type and semantic type right**: with no suffix in the name, the kind of value rests entirely on the type
   fields. Compared against the validated blueprint of the same form (`je__acord_90_ny`, `je__ao040b`,
   `je__f8825`, `je__ircc_imm_5645`), matched by widget rect: share of fields whose `type` agrees, whose
   `semantic_type` agrees.
3. **Subject agreement with the validated names**: the validated name's subject (its identifiers' `subject`, read by
   `eval/field_identifiers.read_form`) against the run's name's subject, matched by rect; exact, same words in
   another order, or different. The suffix is left out of this comparison for both arms, so it measures only what
   the labeler was asked to do in the simple arm.
4. **Tables on pattern** straight from the labeler, and cells printed from parts (bulk coverage).
5. **Labeler output tokens and time**; **loop rounds, fields reviewed, end-to-end time, flags left**.
6. **Collisions**: names the dedup had to number because two fields on a page got the same subject (the
   `x_petey_dedup_log` count), the cost of losing the suffix as a separator.

## Reading the result

- Simple wins if round-0 flags and subject agreement are level or better AND type / semantic-type agreement does
  not fall. Then the suffix was pure overhead and the standard becomes: subject names, kinds in the type fields,
  suffixes printed on request.
- Simple loses if type / semantic-type agreement falls (the suffix was making the labeler commit to a kind) or
  collisions rise sharply. Then keep a minimal suffix set, or print the suffix from the type at the end of
  labeling.
- Either way, the comparison is on four forms with a labeler whose output swings run to run (339 of 706 labels
  differed between two plain runs today), so a difference under ten percent on one form is noise; look for the
  same direction on all four.

## How to run it

The runs are launched the same way as today's: `scripts/run_form.sh <form>_simple <blank> --no-library
--structure bulk --names simple`, one per form, side by side; 3-20 min each. The comparison is
`eval/simple_names_bench.py`, which reads the records of both arms and prints the table above. Claude runs both
when asked; the plan is here so the next session can rerun or extend it.

## Handoff (2026-10-19, 17:50): what is built, how to run, what to watch

Built and committed on `field-identifiers-2026-10-19`:

- `--names simple` on `petey/validate/form_run.py` and `petey/label/auto_label.py`. The simple prompt is
  `auto_label._simple_system()`: the standard prompt with its suffix block replaced by "name what the box holds,
  no suffix" and a `kind` answer per label from the registry's vocabulary (`semantic_types.prompt_vocabulary()`
  plus text / checkbox / signature). The kind sets the type fields through `semantic_types.enrich_from_kind`; the
  standard scheme still infers them from the name. Bulk structure answers carry a kind per column / row / field.
- `eval/simple_names_bench.py`: the comparison table of the plan, standard arm = today's bulk records
  (`acord_90_ny_bulk5`, `f8825_bulk3`, `ao040b_bulk5`, `imm5645_bulk3`), simple arm = `<form>_simple`. Run it with
  `PYTHONPATH=. venv/bin/python eval/simple_names_bench.py` once the simple runs have records; it prints rows for
  whichever arms exist.
- The four simple runs were started once at 17:47 and stopped again a minute later (their partial outputs removed)
  so they can be run from the other chat without clashing names.

To run: one launch per form, `scripts/run_form.sh <form>_simple <blank> --no-library --structure bulk --names
simple`, blanks `acord/acord_90_ny.pdf`, `tax/f8825.pdf`, `us_courts/ao040b.pdf`, `ircc/imm5645e.pdf`.
Each takes 3-20 minutes (ACORD 90 NY the longest). Logs: `runs/judge_eval/<form>_simple.log`; completion lines
in `runs/judge_eval/old_library_progress.log`; the record `runs/judge_eval/form_runs/<form>_simple.json`.

Watch for: three small-form runs launched together at 17:27 (with seven runs in flight by 17:47) all died after
round 0 with `httpx ReadTimeout: The read operation timed out`, an API read timeout in the loop's first round. The
per-page judge and the page check now send a form's calls concurrently, so several forms at once multiply the
in-flight calls; run the four forms two at a time, or one after another, until a concurrency cap is added (the
judge's pool is `min(8, jobs)` per case, three cases a round). If a run dies the same way alone, that is a bug to
fix before reading any numbers: `grep -n Traceback runs/judge_eval/<form>_simple.log`.
