# Doubled test values in the validation loop (found and fixed 2026-10-20)

## What happened

The loop tests a blueprint by filling made-up values into the blank through its form fields (the usual way a
filer enters data), reading the page back at the blueprint's boxes, and comparing. On 27 forms the expected values
themselves were corrupt: Form 8825's property address expected "Omar Fischer, 1120Omar Fischer, 1120" in round 1
and four copies in round 2, a code box "5C5C". When the value no longer fit its box, the read-back was cut off and
scored as the blueprint's miss (Form 8825: 0 wrong in round 1, 21 from round 2 on, in both naming schemes).

## Why

The test values are drawn per box the page finder sees. Where the finder sees several boxes inside one form field
(a two-line address box seen as two lines, a comb seen as cells), the filler writes one string into that field: the
cells' values joined. That part is right; it is what the field holds.

The bug was in what got saved. A case is drawn once and frozen so every round fills the same values. The frozen copy
was taken after filling, so it held the joined string on every cell, and the next round's fill joined the joined
strings again. Both pieces went in on 2026-09-30 (`f7d3468` freezing, `dce27d5` joining).

How far it reached: 106 of 1,684 runs, 27 of 287 forms, about 4,500 of 485,000 expected values (under 1%). Worst:
Form 8825 (28 of 33 runs), DO-10, CMS-855A / B / I, CRA T1 and T1-ON. Every other field's score stands. Standard
against simple names is unaffected (both arms met the same corrupt values on the same forms); the absolute
extraction numbers on those 27 forms were off.

## Why it was not caught

1. The check compares what was read with what was written. A doubled value is both written and expected, so it
   scores as right whenever it fits its box; only overflow exposed it.
2. When it did show, the loop filed it as "extraction mechanics" and "value overflows box": true about the symptom,
   pointing away from the test data.
3. Nothing checked the generated values themselves.
4. The repo had no test suite: `make test` pointed at a `tests/` that never existed.

## What changed

- **The draw is frozen, not the fill** (`validate._bank_case`). A reused case fills from the same values every round.
- **The filler joins a field's cells by line** (`render._join_cells`): cells side by side run together ("1" "2" "3"
  -> "123"), lines of one answer get a space, and a line repeating the line above is written once.
- **The expected-value builder claims every cell that landed in a field** (`rect_join.case_to_paths`); the second
  line of a two-line box was counted as a box no field claims.
- **The loop checks the harness every round** (`harness_check.expected_drift`): the same cases must expect the same
  value at every field, round to round. A change logs `HARNESS` and is recorded as `harness_drift` on the round. On
  the old Form 8825 runs it finds 84 drifted values between rounds 1 and 2; on IMM 5645, none.
- **Frozen cases repaired** (`eval/repair_frozen_cases.py --apply`): 272 replaced by their original draw (the seed
  reproduces it); 56 whose inputs changed since had each stored join kept once; backups in
  `runs/_gen_cache/_backup_frozen_2026-10-20/`. A second pass finds none left.
- **A test suite** (`tests/`, `make test`, about 2 seconds, offline), run by the pre-push hook. It covers this bug
  (fill, freeze, reuse: the same expected values three times running) and this week's other changes.

## Verified

VERIFICATION

## The "two boxes become one" question

Andrew asked whether this is intractable: two boxes on the page become one field in the blueprint (or the reverse),
but one value has to go into both. It is not, because every side keys on the form field:

- the filler writes each field once, with whatever its page cells drew (joined when the finder split it, split by
  parts when one page box covers several fields: a date into month / day / year);
- the expected value of a blueprint field is what its form field holds after the fill;
- extraction reads the page at the blueprint field's box.

So the finder's view and the form layer can disagree without breaking the test; only the frozen copy of the joined
string did.
