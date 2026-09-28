# HISTORY: how step2flat got here (handoff for the next session)

## Context
Petey builds `.bpt` blueprints for PDF forms; extraction runs off the `.bpt`. There are three ways to generate one:
AcroForm widgets + tooltips, a VLM, and this repo: a **deterministic, non-VLM flat-form reader**. The goal is
agreement between two of the three, with disagreements (and low-confidence fields) routed to the synthetic-fill
validation loop. This code proposes fields; it is not the scraping engine.

## Working principles (set by the user; keep them)
- **Score first, diagnose after.** New forms are an untouched test set, scored once with frozen code. Anything
  diagnosed from them moves them into development, and the next batch becomes the test set.
- **Structure over parameters.** Every rule needs a structural reason, not just a score gain. Knobs only for genuine
  conventions (fill/colour, ink threshold). Parameterising everything makes it impossible to tell what's true.
- **Grid-first.** Recover the lattice and infer fields from it; underline fields are the outliers.
- **No issuer as an input.** Too few forms per issuer; rules must hold per field, per form, computed from the page.
  Count near-duplicate templates (e.g. the three CMS-855s) once.
- **Read like a person.** "No visual cue" means the detector missed a cue, except for genuinely cue-less fields,
  which are out of scope and punted per field (GA-500).
- **Harness guideline:** anything visible on a real printed form is fair input (bake widget appearances when
  flattening). Gray shading means "don't enter here" (IRS-derived, moving-target convention).

## Chronology
1. **Frozen blind run.** Froze the cold-build raster reader (`frozen_reader.py`, hash-checked) after tuning on 4
   seen forms (VA 760, ACORD 125, Utah 122, DD 1155). Built a harness that seals widget GT, flattens, runs cold, scores.
2. **Blind batches 1–5** (~30 forms). Frozen reader: strong on boxed government forms (I-765 0.96), weak on underline,
   open-cell, dropout-colour and character-box forms. The tuned candidate v7 failed six times (sometimes badly),
   so the seen-set tuning was overfitting; retired. v8 (box guard) fixed a diagnosed cause: OCR word boxes erasing
   checkboxes fused to their labels. Safe, modest; kept as a candidate.
3. **Harness fixes.** Many-to-one credit (R_m2o); exclude barcodes, hidden widgets, push buttons; bake appearances
   (MCS-150 draws checkboxes only in widget appearances); shaded-cell exclusion with a sensitivity-swept threshold
   (HUD-1's light tint would be wrongly excluded at delta 15; UB-04's zebra rows survive delta 25 by one level).
4. **Measuring structure from widgets** (27 forms, 9,299 fields): a box field = the drawn box's outer edge (23/23 forms);
   an underline field's bottom sits on the rule (18/20); few text styles per form, but font size doesn't predict field
   size; field heights cluster within a form but don't transfer to underlines on most forms.
5. **Lattice.** Grid recovery from vector rules plus virtual closure of open edges: ~84% of widgets fall inside a
   recovered cell (1065: 51% to 95% with closure). Cell to field via label position.
6. **Confidence.** A learned model (gradient-boosted trees on hand features) worked on development forms but absorbed
   dev-set quirks ("gray = blocked", "both readers agree") and dropped correct fields on unseen forms (UB-04,
   later fresh forms). **Replaced with programmatic tiers plus named adjustments.** Zebra-vs-blocked gray became a
   structural rule (alternating bands = decoration).
7. **Lattice v2** from fresh-form diagnosis: contrast cells (white boxes cut from tinted panels), closure only from
   long rules and never through text, character-box grouping, writable-size limits. Also: typed underscores and dot
   leaders are line cues, not text; an underline outside the lattice is the genuine outlier field.
8. **Test set** (9 untouched US state tax forms, scored once): frozen 0.66/0.63 vs pipeline v2 **0.77/0.60**.
9. **v2.1** from test-set diagnosis: right-end suffix text (".00", "%") gives a field to its left (PIT-RES 0.44 to
   1.00 recall; also fixed IT-201's cents boxes, which weren't used to design it); an underline is a cell border only
   if the cell is about its height; small boxes are text-filled only if a word is centred inside.
   All 45 forms: frozen 0.58/0.58, v2 0.74/0.62, **v2.1 0.76/0.61** (R50/P50).

## Form inventory (all 45 scorable forms are now development forms)
- **Seen (original tuning):** VA 760, ACORD 125, Utah 122, DD 1155.
- **Blind batches:** I-765, URLA 1003, RRC P-5, 1040, CMS-1500, SS-4, CMS-855I, RRC P-4, IT-201, PA-40, HUD-1, 8949,
  CRA T1, VA 10-10EZ, IL-1040, CA 540, DS-11, 1065, K-1 (1065), MCS-150, 1120-S, NJ-1040, I-130, VA 21-526EZ, GA-500,
  CMS-855A, CMS-855B, UB-04 (fillable copy).
- **Fresh (used for diagnosis):** Form 12S, LIC100, GR claim form, KS2, nurse1, CA24, DL7, IR957E.
- **Former test set:** CT-W4, NAA-01, PIT-RES, M1X, EFO00305, DO-41, M-19, N-344, LES022A.
- **Unscorable (no usable field layer):** SA100 (4 widgets), UB-04 flat copy, ACORD 25, flat P-5, Vasek claim form,
  RNLPN, form12, Florida F-1120. Useful for visual checks only.
- **Parked outliers:** GA-500 (mostly cue-less fields), 8949 (row-extent convention).

## Open threads (see docs/ERROR_TAXONOMY.md)
- **Next step:** run the next untouched batch against v2.1 frozen. The SafeDocs random PDF corpus, filtered for real
  field layers, would be the least biased test set.
- DO-41 gained less than expected from the underline fix; worth a look.
- Precision is flat versus the frozen reader. Likely rule: when the frozen reader finds a closed box or cell, overlapping
  lattice cells add nothing.
- Raster pages aren't wired into the lattice (CMS-1500; a raster-lattice prototype covered 79%).
- Box extent (interior vs outer edge); faint strokes (PA-40, ink threshold knob); zebra runs shorter than 3 bands;
  instruction pages and lines hidden under white shapes (SA100 p1).
- Colour roles still need discernment: text inside = label/header; light colour with no text = dropout-ink entry
  structure; checkbox-sized gray = control; field-sized gray in a partial column = blocked; zebra = decoration;
  large fill = background whose white openings are entry areas. More colour forms are wanted to settle the rules.

## How to resume
```
python -m step2flat.pipeline form.pdf -o fields.json --keep-all
python eval/evaluate.py path/to/fillable_pdfs --tag NAME
```
Verify `step2flat/FROZEN_SHA256` before any blind run. Change one named rule at a time, justify it structurally,
and re-run all development forms before calling it an improvement.
