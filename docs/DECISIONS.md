# Decision log
- Froze the cold-build reader before any blind run; tuned variants run only as ablations afterward.
- Retired v7 (10 features tuned on 4 seen forms): no consistent blind gain across six batches, sometimes harmful.
- v8 box guard: single diagnosed cause (OCR word boxes erase fused checkboxes). Safe, modest; kept as a candidate.
- Chose grid-first: recover the lattice and infer fields from it; underlines are the outliers.
- Rejected parameterising everything: knobs only for genuine conventions (fill/colour, ink threshold).
- Rejected issuer as an input: too few forms per issuer; rules must hold per field, per form, computed from the page.
- Tried a learned (gradient-boosted) confidence model: learned dev-set quirks ("gray = blocked", "both readers agree")
  and under-trusted correct fields on unseen forms. Replaced with programmatic tiers + named adjustments.
- Harness: bake appearances when flattening; exclude push buttons; shaded-cell exclusion with a recorded threshold.
- 2026-10-17: Indra OCR is not a threat (no fields or types) and matching it is not a goal; stopped the page-reader
  prototype after OmniParseBench (`page-reader-prototype` branch, RESULTS "Indra OCR, and a code-only page reader").
  Possible later use: a broken-text-layer gate with Indra's OCR as the fallback.
