# Results log

## Test set (9 US state tax forms, untouched, scored once with frozen pipeline v2)
| form | fields | frozen R/P | v2 R/P |
|---|---|---|---|
| ct-w4 | 19 | 0.84/0.34 | 0.74/0.22 |
| naa-01 | 64 | 0.92/0.74 | 0.88/0.72 |
| PIT-RES | 167 | 0.02/0.15 | 0.44/0.38 |
| m1x | 125 | 0.98/0.95 | 0.97/0.94 |
| EFO00305 | 50 | 0.98/0.55 | 0.98/0.51 |
| do41 | 136 | 0.71/0.74 | 0.61/0.72 |
| m19 | 190 | 0.74/0.47 | 0.95/0.54 |
| n344 | 108 | 0.47/0.58 | 0.67/0.59 |
| les022a | 77 | 1.00/0.90 | 0.99/0.89 |
| **micro** | | **0.66/0.63** | **0.77/0.60** |

Union ceiling on the test set: 0.81 recall. These forms are now development forms.

## Development and fresh sets
Dev (28 forms): frozen 0.55/0.56, lattice v1 0.67/0.41, lattice v2 0.64/0.61, pipeline v2 0.73/0.61.
Fresh (8 forms): frozen 0.79/0.79, pipeline v2 0.82/0.79 (optimistic: three fixes came from these forms).

## Structural measurements (27 forms, 9,299 fields)
- Box field = drawn box outer edge: 23/23 forms. Underline field bottom on the rule: 18/20 forms.
- ~84% of widgets fall inside a recovered lattice cell; closure takes 1065 from 51% to 95%.
- Few text styles per form (top 4 sizes cover 97% of text), but font size does not predict field size across forms.
- Field heights cluster within a form; underline heights match confident-field clusters on only 2/11 forms.

## v2.1 (three diagnosed fixes from the test set) — all 45 forms are now development forms
Fixes: right-end suffix text (".00", "%") -> field to its left; an underline is a cell border only if the cell is about
its height; small boxes penalised for text only when a word is centred inside.
| set | frozen | v2 | v2.1 |
|---|---|---|---|
| dev (28) | 0.55/0.56 | 0.73/0.61 | 0.75/0.60 |
| fresh (8) | 0.79/0.79 | 0.82/0.79 | 0.83/0.78 |
| former test (9; fixes came from these, so optimistic) | 0.66/0.63 | 0.77/0.60 | 0.88/0.62 |
| all 45 | 0.58/0.58 | 0.74/0.62 | 0.76/0.61 |
Biggest moves: PIT-RES 0.44/0.38 -> 1.00/0.54; IT-201 0.39/0.56 -> 0.79/0.73 (the old cents-box category, fixed by the
suffix rule without being used to design it). Small precision dips (0.03-0.05) on SS-4, GA-500, 1040, IL-1040, T1.

## True flat copies (23 twins, scored 2026-09-28 with pipeline v2.1)
The corpus holds both a print copy and a fillable copy of 23 forms (22 Texas RRC, 1 IAIABC); same page size, page-1 word
Jaccard >= 0.8. The fillable twin's widgets are exact ground truth for the flat copy — no self-flattening. `eval/twins.py`.

| form | flat copy | gt | pred | R50 | P50 |
|---|---|---:|---:|---:|---:|
| tx_rrc_w_1 (addendum) | form-w-1-field-addendum.pdf | 93 | 99 | 0.98 | 0.92 |
| w_3 | w-3p.pdf | 177 | 219 | 0.98 | 0.79 |
| tx_rrc_wh_2 | formwh2p.pdf | 191 | 218 | 0.97 | 0.85 |
| tx_rrc_w_3x | w-3x.pdf | 25 | 34 | 0.92 | 0.68 |
| tx_rrc_wh_3 | formwh3p.pdf | 75 | 98 | 0.88 | 0.67 |
| tx_rrc_ep_3 | ep-3-pdf.pdf | 43 | 46 | 0.86 | 0.80 |
| tx_rrc_p_5 (LC) | p-5-lc.pdf | 20 | 18 | 0.85 | 0.94 |
| tx_rrc_h_7 | h-7p.pdf | 50 | 48 | 0.84 | 0.88 |
| tx_rrc_w_1h | form-w-1h.pdf | 66 | 66 | 0.82 | 0.82 |
| tx_rrc_ep_4 | ep-4-pdf.pdf | 52 | 58 | 0.75 | 0.67 |
| tx_rrc_w_1d | form-w-1d.pdf | 49 | 50 | 0.73 | 0.72 |
| tx_rrc_wh_1 | wh-1p.pdf | 18 | 26 | 0.72 | 0.50 |
| tx_rrc_cf_1 | cf-1-06-09-14-final.pdf | 27 | 21 | 0.70 | 0.90 |
| tx_rrc_h_8 | h-8p.pdf | 33 | 31 | 0.58 | 0.61 |
| tx_rrc_p_12 | p-12p.pdf | 70 | 72 | 0.51 | 0.50 |
| tx_rrc_cf_2 | cf-2-final-04-2014.pdf | 31 | 23 | 0.48 | 0.65 |
| tx_rrc_w_15 | w-15-08-04-2014-final.pdf | 252 | 138 | 0.45 | 0.83 |
| tx_rrc_h_12 | h-12p.pdf | 74 | 67 | 0.42 | 0.46 |
| tx_rrc_ps_79 | ps-79p.pdf | 40 | 15 | 0.23 | 0.60 |
| p_15 | formp15p.pdf | 15 | 3 | 0.20 | 1.00 |
| tx_rrc_p_5 | form-p5.pdf | 95 | 55 | 0.16 | 0.27 |
| tx_rrc_p_6 | p-6p.pdf | 90 | 51 | 0.12 | 0.22 |
| iaiabc_ia_1 | IA1 First Report of Injury.pdf | 91 | 144 | 0.07 | 0.04 |
| **micro** | | **1677** | | **0.63** | **0.66** |

Against the same code's 0.76 / 0.61 on self-flattened development forms: recall is lower on real print copies, precision
slightly higher. The spread is the finding — six forms at or above 0.85 recall, six at or below 0.23. Diagnose the bottom
six per the protocol (they are now development forms); the `sibling` geometry source makes the number moot for these 23
in production, but the 104 flat forms with no fillable twin depend on it.

## Caption reachability and caption→name agreement (2026-09-28, `eval/caption_binding.py`)
26,216 widgets across 150 committed v1.1 blueprints. Nearest printed caption by rule: left on the same row (≤60pt),
above with horizontal overlap (≤24pt), or inside the rect.

| | share of widgets |
|---|---:|
| caption within reach | 57% (left 21%, above 34%, inside 2%) |
| /TU tooltip present | 52% |
| caption tokens overlap committed name ≥0.3 (suffix/section stripped) | 19% of all widgets (34% of captioned) |
| overlap ≥0.5 | 12% of all widgets |
| MiniLM cosine ≥0.60 (raw names) | 13% of all widgets (23% of captioned) |

Bimodal by form: f1099div 88%, f1099nec 83%, f1099k 80% of captioned widgets at ≥0.3; f1040sb 0%, uk_p60 3%,
f4506t 4%, rrc_h_12 7%, f5500ez 8%. Consistent with the 2026-07 pinwheel finding. The nearest caption is not a
name source; its remaining roles are anchor evidence and a search target for known canonical labels.

## Declared vs inferred validation on XFA hybrids (2026-09-28, `petey/label/xfa.py`, `eval/xfa_declared.py`)
STRATEGY_v1 §5 step 3. The parser reads the XFA template packet, joins template fields to AcroForm widgets by
path (exact join covers 95% of 17,749 widget paths across the 99 XFA PDFs in the corpus; index-stripped
fallback covers the rest), and `auto_label` overlays what the publisher declared on every joined field.
Re-emitted with `--no-llm` (no API):

| | 21-526EZ (345 fields) | 10-10EZ (122 fields) |
|---|---:|---:|
| joined to template | 345 | 122 |
| `pattern` from a text picture | 0 | 10 (4 SSN, 6 phone) |
| `type: date` declared | 35 | 17 |
| `type: number` declared | 0 | 12 |
| radio groups with declared captions | 23 | 22 |
| validate messages carried | 0 | 36 |
| `required` (nullTest=error) | 0 | 0 |

Corrections to §3.5 as written: the 70 pictures on 526EZ are the 35 date fields' `ui` + `format` clauses — the
form declares no text shapes at all, so its SSN parts and phone numbers have no publisher pattern. The
committed `vba21526ez.bpt` carries 130 inferred patterns; 35 of them sit on `type: date` fields, which the
spec forbids (§5.6), and the re-emit drops those. 95 inferred text patterns have no declared counterpart and
stay inferred. `nullTest="error"` occurs on 72 fields corpus-wide and on neither VA form: `required` is rarely
declared.

Hybrid detail: AcroForm radio appearance states are the exclGroup members' ordinals (0..n-1) in template order,
while XFA item values are what the data packet stores (BirthSex: states 0/1, items 1/2). `values` keeps the
appearance states because the extractor reads them; the captions pair by position under `x_petey_xfa.choices`.

**Step 3b measurement — mutex from scripts.** The strategy's example was wrong: the 19 "clear marital status"
scripts on 526EZ reference `married/divorced/separated/nevermarried`, fields that do not exist on that form
(copied from another form). Both VA forms have 0 reciprocal groups; their mutexes are exclGroups, already
`category` fields. Corpus-wide, 5,439 scripts, 532 with a clear-others assignment; requiring reciprocity
(A clears B and B clears A) leaves **68 groups of 2+ members on 7 forms**: i-130 39, i-485 9, DA 4187 8,
i-864 4, i-765 4, CBP 3299 3, VA DMV TPT-576 1. Two shapes: true mutexes (male/female, yes/no/unknown,
child/parent/sibling/spouse, approve/disapprove) and one-of address groups (state vs province vs postal code).
Committed blueprints exist for six of the seven.

**Step 3b build (2026-09-28).** `xfa.mutex_groups` keeps a reciprocal group only when its members share a kind:
a checkbox that clears a block of text fields which in turn clear it ("mailing same as physical",
"obtained certificate: No" clearing the certificate fields) is reciprocal but is a toggle — on a normal fill
most members hold a value at once — and the state/province/postal-code triples are US-vs-foreign toggles for the
same reason (state and zip coexist). With the filter: **30 groups on 5 forms, all checkbox groups** (i-130 15,
DA 4187 8, CBP 3299 3, TPT-576 3, i-864 1). The emitter writes them as `x_petey_rules: [{mutex: [...]}]` over
the emitted field names; on the committed `i130.bpt` 6 of the 15 survive the name mapping because the LLM
labeler had already folded the others into `category` fields with `widgets`, where the mutex is the type.
`score.check_rules` evaluates `rules:` / `x_petey_rules` on the extracted values and on the ground truth;
`rule_violation` is a new verdict count. Checks: a deliberately violating case (two relationship boxes held) is
caught, the compliant case is clean, and the saved f1040 case rescores with identical per-field verdicts and
`rule_violation: 0`.

## The loop, wired end to end in this repo (2026-09-28, late)
`validate` runs label -> generate -> fill -> extract -> score with everything in-repo: `--gen-model local`
draws values from the blueprint (no API; `petey/synth/local.py`), the default multimodal generator runs
**blind** (page image with numbered boxes + ids and control types only; `python -m petey.synth.generate <pdf>
--dry-run DIR` shows the payload), and the meaning-based arm `--methods native,petey:pymupdf|image` is
`petey/extract_llm.py` (field names/types/descriptions over the page text or images, never the widget layer).
Batch: `run_all --gen-model local` over the 132 blueprints whose source is survey-ready: **132/132 ran in 13 min**,
no API (runs/run_all_local.json, gitignored). Totals over 17,048 fields — intact: 16,929 agree / 27 differ / 92 miss
(99.3%); one flat case each: 16,074 / 603 / 371 (94.3%); 93 forms fully clean on intact. This is the extraction-mechanics
baseline; the blueprint-quality numbers below need VLM ground truth.

**How much the validation step is worth — measured on two forms with real (blind) VLM ground truth.**

| | W-9 (23 fields) | 21-526EZ (328 fields) |
|---|---:|---:|
| native, intact: agree | 23 | 326 |
| native, flat: agree / differ / miss | 23 / 0 / 0 | 216 / 49 / 63 |
| local-generator, flat: agree / differ / miss | 23 / 0 / 0 | 255 / 12 / 61 |
| VLM value contradicts the blueprint's declared type/pattern | 0 | **108** (79 date parts typed `date`, 28 pattern, 1 name) |
| meaning arm (`petey:pymupdf`), intact: agree / differ / miss | 23 / 0 / 0 | **133 / 129 / 66** |

Reading: the intact native score is the same whether the values come from the VLM or from the blueprint
itself (326 vs 325) — it validates fill and read-back by path, nothing about the blueprint. The blueprint
signal is in the VLM's label-grounded values (108 of 328 fields on 526EZ contradict what the blueprint
declares) and in the meaning arm's disagreement (195 of 328). Of the 195: fields bound to the wrong box
(`va_file_number_2` holds the last name; `current_mailing_address_line_1_txt` is the email box), part
fields named as wholes (`telephone_number` holds an area code), radio groups whose `values` are ordinals
(`0`/`1`) no name-based reader can resolve (the XFA captions under `x_petey_xfa.choices` would), and
repeated sections (veteran vs claimant SSN) where the name alone cannot pick the copy — the
"under-specified name" cause in `s2_meaning.py`. On the W-9 the meaning arm only loses flattened
checkboxes to the text-layer parser (3), which is what `petey:image` is for.

## Local VLM as the naming step (2026-09-28, `eval/local_vlm_naming.py`)
The untested branch of the Liquid experiment: geometry supplied (the committed widget rect drawn in red on a
page crop), the model asked only what the box is for, one snake_case name. 115 text widgets from fw9, f1040,
acord25, i130, 21-526EZ (cms1500 has no labelable text widgets). Yardstick as in the caption measurement:
MiniLM cosine against the committed name; baseline = nearest printed caption on the same widgets.

| namer | cos ≥ 0.60 | cos ≥ 0.85 | token overlap ≥ 0.3 | median s/widget |
|---|---:|---:|---:|---:|
| nearest caption (rule, no model) | **24%** | — | 19% | — |
| LFM2.5-VL-1.6B Q4 (llama-server) | 19% | 1% | 18% | 1.0 |
| LFM2.5-VL-3B Q4 (llama-server) | 17% | 1% | 24% | 1.4 |
| gemma3:4b (ollama) | 6% | 0% | 8% | 5.6 |

Caption or 3B ≥ 0.60: 29% (they mostly agree on the easy widgets; 1.6B and 3B both ≥ 0.60 on 12 of 115).
Per form the models track the caption (i-130 32%/36%, ACORD 25 8-12%/20%). Verdict: a local VLM reading a
crop is not a name source — it lands below the nearest-caption rule it would replace, and adds little to it.
Best/worst show why: it names the *section* (`employer_identification_number` for an SSN part, `claims_amount`
for a subrogation-waiver code) and never sees the form's naming convention. Mechanics: ollama 0.21 crashes its
runner on the Liquid GGUF (`llama runner process has terminated`); llama-server on ollama's own blobs
(`~/.ollama/models/blobs`, model + projector) works at ~1 s/widget on the M1.

## Declared shape vs label-grounded value, library-wide, before and after the retype pass (2026-09-28)
Ground truth: the 134 cached VLM cases imported from the old runs (`runs/_gen_cache/imported.json`; generated
with the full inventory, not blind). 121 of the 132 ready blueprints have one. `run_all --gen-model
claude-sonnet-4-6 --gen-cache-only`, one intact + one flat case each, no API.

| | before (`run_all_vlm.json`) | after `retype --apply` (`run_all_vlm_after.json`) |
|---|---:|---:|
| fields contradicting their blueprint (`gt_shape_mismatch`) | 903 of 17,048 (5.3%) | **544 (3.2%)** |
| by class: pattern / date / number / name | 553 / 185 / 162 / 2 | 295 / 84 / 162 / 2 |
| native intact agree | 98.5% | 98.5% |
| native flat agree | 92.8% | 92.7% |

The retype pass (`petey/validate/retype.py`, every change under `x_petey_retype`): 1,348 patterns removed
from non-string types (spec §5.6), 240 fields made parts by box max length, 118 comb boxes given the
separator-free pattern (SSN in 9 cells), 256 short shapes removed from wide boxes (`_state` in
`city_state_zip`), 107 parts by name (`_mm`/`_dd`/`_yyyy`/`_part1`), 49 dates on boxes too small for a date.
Extraction mechanics do not move: the pass changes declarations, and native reads by path.

What remains (544) is not one class. The old generator's formatting against the box (dashed SSNs where the
comb has 9 cells; the blind prompt now states `maxlen`), values that belong to another field (`it_dt` holding
"CERT-OF-ORIGIN" on CBP 7501; `duty_status_effective_dt` holding a duty description on DA 4187 — the swap
class for `method_delta` / `correct.py`), `percent` fields whose printed value is "Free" or "Various" (f720,
CBP 7501: a rate column that is not always numeric), and 526EZ's 35 approximate dates written as month/year
against a tooltip that asks for a full date. Registry change alongside: `phone` now accepts `(xxx) xxx-xxxx`
and dotted forms, which the scorer already canonicalised; committed blueprints keep the pattern they were
emitted with until re-emitted.

## Correction: the meaning arm on 526EZ, and the text layer of filled hybrids (2026-09-28)
The "133 / 129 / 66" meaning-arm row for 526EZ above is invalid. `petey:pymupdf` reads the page TEXT layer,
and on the filled 526EZ none of the widget values are in it (0 of 12 sampled), although every one renders
(appearance streams present; ink at the rects on both intact and flattened pages). The reader was asked for
values it could not see; its agreements were by absence. Library-wide (`runs/text_layer_check.json`): values
are in the text layer on 129 of 132 filled forms; the exceptions are 21-526EZ, MA Form 1 and VA 760, which need
`petey:image`. Text-mode results stand for the other 129.

526EZ measured properly, `petey:image`, intact case, same cached ground truth:

| blueprint | agree / differ / miss | candidate defects (swaps) | unlocatable |
|---|---:|---:|---:|
| committed before this session | 173 / 106 / 49 | 92 (44) | 51 |
| after `retype` + `--describe` | **190 / 99 / 39** | **71 (27)** | **39** |

Publisher tooltips and radio captions in `description` are what a name-based reader was missing; the
remaining 39 unlocatable are mostly the repeated veteran/claimant sections. The 71 candidates with 27 swaps
are `correct.py`'s input.

## Library-wide meaning arm and method_delta (2026-09-28, `eval/meaning_arm_all.py`, in-repo `petey:pymupdf`)
Over the runs with cached VLM ground truth (a mix of pre- and post-retype blueprint copies; the pass does not
change names). 54 forms scored on the first pass (6 failed: 4 without ground truth, 2 hit the since-removed
400-field skip); text mode is invalid on 526EZ, MA 1 and VA 760 (see the correction above) — 526EZ is included
in image mode. `method_delta`: **1,518 raw disagreements across 48 forms, 589 candidate defects (143 swaps),
399 unlocatable, 159 substring, 131 boolean**. Worst: CBP 7501 76, CRA T1 58, f1065 50, CA 540 29, AO 040A 28.
`correct.py` dry run over the same runs: 35 forms analysed, 3 closed cycles (the only
shape it will apply) and 123 open chains, most marked contradicted and escalated — on 526EZ every
chain is the repeated veteran/claimant section, where the by-name reader picks the first copy. So the swap
class that correct.py can fix losslessly is small in this library; the bulk of the 589 candidates are
under-specified names on repeated sections and table rows, which is a naming-convention question (row/copy
prefixes) rather than a rebind.

## The LLM reviewer, judged by the loop (2026-09-29, `petey/validate/review.py`, `iterate.py --review flagged`)
The reviewer sees only fields the detectors flagged, with an evidence bundle each (spec, box size and max length,
the publisher's field name and tooltip, the XFA declaration, printed words near the box, the section heading,
sibling copies, and what the detectors observed). It returns a verdict per field as strict JSON. The loop
re-validates and keeps each change only if that field's status improved; a rename that changes nothing is restored.

**Two measurement bugs found and fixed on the way.** (1) The name-based reader saw only the first 12 pages; on
526EZ that hid 116 fields on pages 13-15, and every earlier reader number for that form (133/129/66, 173/106/49,
190/99/39) was mostly that cap. The reader now gets every page that carries a field. (2) The reader sampled at the
default temperature, so a one-field change on I-765 moved its numbers by nine fields; it now samples at
temperature 0 (low effort on 5-generation models). Also: a 40-field review chunk on I-765 hit the 32k output cap
and lost all 40 decisions for $0.90 — now 64k, 25 fields per call, split-and-retry on truncation.

**526EZ with the corrected reader** (all 328 fields visible): reader agree **278 (85%)**, not found 0, real name
defects 11, format quibbles 39 (partial comb reads), shape contradictions 39 (35 approximate dates). One review
round (claude-opus-5, medium, **$0.36**): 50 flagged, 12 fixes proposed, **9 better, 0 worse, 3 no-op renames
restored**; agree 278 -> 282, name defects 11 -> 7, shape 39 -> 37.

**Reference forms** (text-layer reader, one round each): ACORD 25 — 6 fixes, all better, contradictions 8 -> 0,
clean, $0.04. W-9 — 1 fix, better, $0.04. I-765 — truncated (above); rerun pending.

Earlier rounds on the capped reader taught the rename policy: cosmetic renames (`_txt` suffixes, normalising)
made findable fields unfindable, and page-number qualifiers on repeated sections helped nothing; the prompt now
renames only when the name describes another box or cannot tell this box apart, with section context supplied.
Observation for the generator: repeated page-header copies of one identifier (the SSN on every 526EZ page) hold
the same value on a real filing; the blind generator's uniqueness rule gives each copy a different one.
