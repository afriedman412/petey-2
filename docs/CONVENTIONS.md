# Harness and scoring conventions

- **Flattening bakes appearances.** Anything visible on a real printed form is fair input, not leakage.
- **GT exclusions** (sealed but never scored): barcode widgets, hidden/NoView widgets, push buttons
  (print/reset/navigation). Read-only widgets are kept: signatures, computed totals and auto-filled fields are extractable.
- **Shaded cells**: text fields on neutral gray at least `--shade-delta` (default 25) levels darker than the page's paper
  are excluded, because gray means "don't enter anything here" (an IRS-derived, moving-target convention). Checkboxes are
  never excluded (some forms draw them as solid gray squares). Coloured tints are entry areas, never shading.
  Sensitivity matters: HUD-1 puts 144 fillable fields on a light tint that delta 15 would wrongly exclude; UB-04's zebra
  rows survive delta 25 by one level.
- **Metrics**: 1:1 greedy IoU matching per page. R50/P50 are headline; R30, centre-in, mIoU, and many-to-one credit
  (R_m2o/P_m2o: merges and splits) are diagnostics.
- **Scope**: fields with no printed cue (e.g. most of GA-500) are out of scope for a visual reader. Punt per field, not per form.

## Test forms (2026-09-30)

Every comparison runs on the same five documents, defined once in `petey/validate/test_forms.py` and used by the
harnesses (`eval/generator_models.py`, `eval/labeler_models.py`, `eval/relabel_compare.py`; `--tier smoke|core|full`):

| tier | form | blank | pages / fields | reader | note |
|---|---|---|---|---|---|
| smoke | W-9 `fw9` | `tax/fw9.pdf` | 1 / 23 | text | cheapest; the smoke check |
| core | ACORD 25 `acord25` | `acord25_blank.pdf` | 1 / 128 | text | dense coverage grid; five automobile boxes named one row off |
| core | I-765 `i765` | `immigration/i-765.pdf` | 7 / 140 | text | XFA hybrid; repeated sections; the hard reference form |
| full | VA 21-526EZ `vba21526ez` | `vba-21-526ez-are.pdf` | 15 / 328 | image | 35 date parts, 23 radio groups; values missing from the text layer |
| full | VA 10-10EZ `va_form_10_10ez` | `VA Form 10-10EZ.pdf` | 6 / 122 | text | 22 radio groups; not in the library; side copy `runs/relabel/blueprints/va_form_10_10ez_relabel2.bpt` |

`core` is the everyday set for model sweeps (a dollar or two per sweep); `full` adds the two radio-heavy XFA forms
for questions about option groups or the whole gamut. Ground truth is keyed by the stem (`--gen-key <stem>`), so
every version of a form's blueprint is scored against the same cached values.
