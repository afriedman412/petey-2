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
