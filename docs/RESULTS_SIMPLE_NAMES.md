# Results: the simple naming scheme against the standard one (2026-10-19 evening)

The benchmark of `docs/PLAN_SIMPLE_NAMES.md`, run on its four forms (ACORD 90 NY, Form 8825, AO 40B, IMM 5645), bulk
structure labeling, Gemini 3.8 Flash as labeler and round-0 page check, Opus 5 for the loop's page checks and review,
the same page-check prompt (`bbf7099d`) in every run. Commits `001bd62` .. `6101afb` on `field-identifiers-2026-10-19`.
The comparison is `eval/simple_names_bench.py` (it prints every run and the summary below).

## The answer

The simple scheme is level with the standard one on what the plan measured, and it removes one class of error
outright: types read off the name. It is not a win on the names themselves: subjects agree with the validated
blueprints a point or two less often on two forms. On the final version (simple5 on all four forms, simple6 on ACORD
90 NY, two runs each), against three runs of the standard scheme (two on ACORD):

- **Round-0 flags**: ACORD 90 NY standard 13 and 25, simple 4, 12, 8, 10; AO 40B standard 8, 10, 8, simple 4, 8;
  IMM 5645 0 in every run; Form 8825 standard 0, 0, 0, simple 4, 4 (one column, below).

- **Wrong type at round 0**: 20 in the standard runs, 0 in the simple ones. Every standard one is a type read off a
  word in the name: `rate_class_cd` typed as a percent ("rate"), `stated_amount_veh_1_num` as money ("amount"),
  AO 40B's telephone-expense cells as phone numbers ("telephone"), ACORD 90 NY's Y / N box
  `any_other_insurance_with_company_ind` as a business name ("company"). The same reading cost AO 40B's `_final` run
  77 money types, not flagged: its column labels came without `_amt`. The simple scheme never reads a type from the
  name.

- **Wrong name at round 0**: level per form (ACORD 90 NY standard 6, 9; simple 2, 10, 6, 4). The families are the
  same in both arms: ACORD 90 NY's driver-6 column, a table's captions read one row off, option captions taken from
  a neighbouring header.

- **Type agreement with the validated blueprints**: 100% on Form 8825, AO 40B and IMM 5645 in every run; ACORD 90 NY
  standard 94.9 and 98.2%, simple6 95.5 and 96.6% (simple5 91.1-96.0, before the `#` / "number" fix below).

- **Subject agreement**: a little lower on ACORD 90 NY (84-85% same or nested over four simple runs, 86-87% over two
  standard) and AO 40B (96-98 against 98-100); level on Form 8825 and IMM 5645. The differences are vague or
  renamed subjects (`official_id` for the AO 40B number, a bare `date`), no one pattern.

- **Tables on pattern, cells printed from parts, collisions**: level within each arm's own swing (table below). No
  collision in any final simple run was a pair a suffix would have kept apart.

- **Cost**: the labeler writes about a quarter more output tokens a page (one kind per label); time is level within
  its swing.

The one place the suffix did work the subject did not: Form 8825 column (c), captioned "Type (Enter code A-I; see
below for list.)". Every run in both arms, and the validated blueprint, names it `other_information`; the page check
accepts `other_information_cd` and flags `other_information`, because "code" is what the caption asks for. Either the
subject was vague all along and the suffix papered over it, or the code list is headed "other information" and the
page check is too strict; worth a look at the page.

What it took to get there: every gap in the list of kinds the labeler chooses from turns straight into type errors,
where the suffix used to carry the distinction. The first simple version lost a fifth of ACORD 90 NY's types for
want of an identifier kind; simple5 still put 45 location-number cells in as counts until the prompt said a caption
with "#" or "number" names an identifier. The kind list is now the thing to keep complete, as the suffix list was.

Standard against the final simple versions, each measure as the range over the runs (`eval/simple_names_bench.py
--md`). Standard runs: `_bulk5` / `_bulk3` (15:38-16:42), `_final` (17:27, round 0 only), `_std` (18:21-18:59, today's
code); the standard minutes' upper ends are the 15:38-16:42 runs on older code, before the validate pass was cut. End
to end on today's code: ACORD 90 NY standard 21.1 min, simple 17.8-25.3; Form 8825 6.1, 6.2-9.1; AO 40B 5.9, 5.8-8.9;
IMM 5645 4.3, 3.5-4.2.

| form | arm | runs | flags / 100 fields | type % | semantic dropped + conflict % | subject same or nested % | tables on pattern | printed from parts % | labeler tokens / page | minutes / page |
|---|---|---|---|---|---|---|---|---|---|---|
| acord_90_ny | standard | 2 | 1.9-3.6 | 94.9-98.2 | 1.5-4.0 | 86.3-87.2 | 10/13, 13/14 | 63-67 | 2301-2442 | 5.3-13.4 |
| acord_90_ny | simple5 | 2 | 0.6-1.8 | 91.1-96.0 | 3.6-4.0 | 84.1-85.1 | 11/14, 12/14 | 67-68 | 2800-2900 | 4.5-6.3 |
| acord_90_ny | simple6 | 2 | 1.2-1.5 | 95.5-96.6 | 3.6-4.6 | 84.4-85.4 | 13/14, 12/14 | 68-71 | 2678-2779 | 4.8-5.3 |
| f8825 | standard | 3 | 0.0 | 100.0 | 4.4-5.4 | 68.8-96.1 | 7/7, 7/7, 7/7 | 94-97 | 693-754 | 3.0-4.2 |
| f8825 | simple5 | 2 | 2.0 | 100.0 | 0.0-2.4 | 88.8-95.6 | 7/7, 7/7 | 94 | 887-890 | 3.1-4.5 |
| ao040b | standard | 3 | 3.4-4.2 | 100.0 | 0.0-33.8 | 98.3-99.6 | 3/3, 3/3, 3/3 | 91-93 | 582-734 | 3.0-8.1 |
| ao040b | simple5 | 2 | 1.7-3.4 | 100.0 | 1.7 | 95.8-98.3 | 3/3, 3/3 | 91 | 930-964 | 2.9-4.5 |
| imm5645 | standard | 3 | 0.0 | 100.0 | 0.0 | 92.9 | 3/3, 3/3, 3/3 | 62 | 886-932 | 2.1-3.0 |
| imm5645 | simple5 | 2 | 0.0 | 100.0 | 0.0-3.5 | 92.9 | 3/3, 3/3 | 62 | 1196-1198 | 1.8-2.1 |

## How the versions differ

The simple arm went through six versions tonight, each fixing what the one before showed. The records are kept
under their own names (`<form>_simple`, `_simple2`, `_simple2b`, `_simple3` .. `_simple6b`); the bench reads them all.

- **simple v1** (the plan as committed): ACORD 90 NY type agreement 507 of 671 against the standard 645 of 680. The
  kind list had no identifier, so 100 number cells (location, vehicle, driver numbers) became integer counts; an
  indicator on a Y / N text box was typed boolean (49), where `_ind` gives a string; the text and description kinds
  dropped their semantic types.

- **simple2**: an `identifier` kind (a plain string), `count` described as how many of something, indicator on a
  text box a string. ACORD 90 NY type agreement back to 94%. Left: the prompts still showed suffixed examples (the
  bulk rules' first suffix-free twin never matched, the radio rule showed `is_amended_return_ind`), so ACORD 90 NY
  still got 23-46 names with `_ind`; and on IMM 5645 every simple run named the 7th sibling's marital-status box,
  which the block finder leaves outside the block, plain `marital_status` (the standard runs: `sibling_marital_status_7`).

- **simple3 / simple4** (IMM 5645 only, probes): a box of a repeated person or thing says whose. As first worded the
  labeler read it as "number every block's cells" and dropped both pages' bulk answers (0 of 128 cells printed from
  parts); then a middle number (`sibling_7_marital_status`) broke the column the block printer writes with the number
  last.

- **simple5**: no suffixed example left in either prompt; a table or block answered by its parts takes no number
  (printing adds it); a lone box of a numbered person or thing says whose, number last (`sibling_marital_status_7`).

- **simple6** (ACORD 90 NY only): a caption with "#" or "number" in it is an identifier; count only for a box that
  asks how many. simple5b had typed 45 location-number cells as integer counts.

## Reading the measures

- **Round-0 flags** are the page check's verdicts on the labeler's output, the first-order quality measure. Most
  flags in both arms are table-pattern breaks on the same cells (ACORD 90 NY's driver-6 column, an option group's
  captions) and swing run to run.

- **Type / semantic agreement** is against the validated blueprint of the same form, matched by widget rect. The
  validated blueprints leave many semantic types unset, so a run that sets one where the validated blueprint does not
  (added) is not counted against it; dropped (the run lost one) and conflict (both set, different) are. The simple
  runs' conflicts are mostly dates of birth typed `iso_date` where the validated blueprint says `birth_date`: both
  dates, the same extraction.

- **Subject agreement** compares the names' subject words with the kind of value left out of both sides
  (abbreviations spelled out, abbreviations and acronyms matched, word forms stemmed, copy and iteration numbers and
  column letters dropped): same, nested (one a more detailed form of the other, usually a table prefix like
  `property_`), overlap, different. It swings within an arm as much as between arms (Form 8825's three standard runs:
  96, 75 and 69% same or nested), so only a difference on all four forms would mean anything; there is none.

- **Collisions** are names the dedup numbered because two fields got the same name. They swing with the labeler in
  both arms (Form 8825: standard 24-72, simple 75-88; ACORD 90 NY: standard 33-43, simple 44-116). They are almost all
  a table repeated on another page or a row labeled without its number. Between kinds (the case the plan worried
  about, a phone text box beside a phone checkbox): 0 in every standard run, 0-15 in the simple runs, and those were
  the labeler giving one column two kinds on two pages (identifier, count), which a suffix would not have separated
  either (both `_nbr`).

- **Noise**: the standard arm's own runs disagree as much as the arms do (ACORD 90 NY round-0 flags 13 and 25;
  AO 40B's `_final` dropped 77 money semantic types the other two standard runs kept, because its column labels came
  without `_amt`). Read a direction only where all four forms agree.

## What else came out of tonight

- **Stalled streams retried** (`001bd62`): the three `_final` timing runs of 17:27 died in loop round 1 of an httpx
  ReadTimeout mid-stream, which the SDK does not retry. `generate.final_message` now retries a dropped or stalled
  stream twice (labeler, page check, per-page judge, reviewer). No run tonight needed it (two runs at a time), so the
  fix is in place but has not yet met a live stall.

- **The `_final` timing runs' replacements**: `<form>_std` are the same configuration (bulk, everything in) on
  today's code: Form 8825 6.1 min, AO 40B 5.9, IMM 5645 4.3, ACORD 90 NY 21.1 (two runs at a time).

- **Bench measures** that did not survive their first look: the identifiers' subject (kept iteration digits written
  after a suffix and column letters as differences) and raw semantic agreement (counted a run more specific than the
  validated blueprint as wrong).

## Open, for Andrew

- Make simple the default? It changes every new blueprint's names (no suffix) and makes the kind list part of the
  labeler's contract. The plan's "suffix printed on request" (MeF-style names from the type at output) is not built.

- Validated blueprints carry suffixed names; a simple-scheme blueprint compared against them differs in every name.
  The identifiers keep subject and suffix apart, so the comparison can ignore the suffix, but the review page shows
  whole names.

- The `#` / "number" line (simple6) ran on ACORD 90 NY only; the other three forms ran on simple5, which differs from
  it by that line alone.

- The kind list: `identifier` is a prompt-level kind (a plain string), not a registry semantic type. If it should
  be one, it goes in the registry (spec §5.8.1).
