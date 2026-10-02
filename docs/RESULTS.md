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

## Model comparison with the loop as judge (2026-09-29, `eval/reader_models.py`, `iterate.py --review-model`)
**Readers** (same run, same filled PDF, same ground truth, same fields; text layer except 526EZ in image mode).
`defect` = the reader returned another box's value where the by-path read was right; those become flags.

| form (fields) | Sonnet 4.6, temp 0 | Sonnet 5, low effort | Haiku 4.5, temp 0 |
|---|---|---|---|
| W-9 (23) | 16 agree, 0 defect, 1.7¢ | 18, 0, 1.4¢ | 17, 0, 0.4¢ |
| ACORD 25 (128) | 119, 0, 6.7¢ | 119, 0, 6.0¢ | 108, **5**, 2.4¢ |
| I-765 (140) | 111, 18, 11.5¢ | 101, 18, 25.9¢ (194 s) | 80, **37**, 3.5¢ |
| 21-526EZ (328, image) | 282, 7 | 282, 6, 29¢ | 265, **21**, 8.5¢ |

Sonnet 4.6 and Sonnet 5 read alike; Sonnet 5 costs more here because its thinking is billed as output even at low
effort. Haiku is 3-5x cheaper and two to three times more likely to flag a correct field as a defect, and every false
flag is a paid reviewer call — not a judge. Reader noise floor: on I-765 the same blueprint gave 40 and 45 detections
on different runs at temperature 0, so differences of a few fields per round are not signal.

**Reviewers** (same flagged fields; the Sonnet 4.6 reader judges; each model starts from the committed blueprint).

| form | Opus 5 | Sonnet 5 | Haiku 4.5 |
|---|---|---|---|
| ACORD 25 (6 flagged) | 6 fixes, 6 better, clean, 4.0¢ | same 6, clean, 1.9¢ | same 6, clean, 0.7¢ |
| W-9 (4 flagged) | 1 fix, better, 3.6¢ | 4 fixes, 1 better, 3 kept, 1.5¢ | 1 fix, better, 0.5¢ |
| I-765 (32-37 flagged) | 13 fixes: 3 better, **1 worse**, 5 no-op renames restored, 29¢ | 3 fixes: 1 better, 20¢ | 27 fixes: 2 better, 9 kept, 0 worse, 4.5¢ |

On the two easy forms all three models make the same fixes and Haiku costs a sixth of Opus. On the hard form no model
produced a clear win within the judge's noise floor, and Opus was the only one to make a field worse (restored by the
loop). Nothing measured here justifies Opus for the reviewer; the loop's per-field judgment is what protects the
blueprint, not the model tier. I-765 rerun with the truncation fix: 32 fields reviewed, nothing lost.

**Local models as the reader** (ollama on the M1, text mode, temperature 0; same runs as above):

| form | Sonnet 4.6 | qwen3:4b-instruct | llama3.1:8b |
|---|---|---|---|
| W-9 (23) | 16 agree, 0 defect, 10 s | 17, 2, 21 s | 16, 1, 35 s |
| ACORD 25 (128) | 119, 0, 26 s | 66, **28**, 180 s | 70, **20**, 218 s |
| I-765 (140) | 111, 18, 50 s | 68, **47**, 278 s | 61, **39**, 302 s |

Fine on a one-page form, then a cliff: on 128-140 fields they find about half and flag 20-47 correct fields as
defects, at 5-6x the wall-clock. Not a judge. The local-model slot that remains plausible is a narrow naming model
trained on loop-judged pairs (`runs/review_pairs.jsonl` now accumulates evidence, decision and loop outcome per
reviewed field), not a general reader.

## Relabel test: the current emitter against the committed blueprints (2026-09-29, `docs/RELABEL_PLAN_v1.md`, `eval/relabel_compare.py`)

Five blanks relabeled from scratch into side copies (`--no-register --no-retrieval`, labeler `claude-sonnet-4-6`), each
scored by the loop against the same cached ground truth as its committed counterpart, then one Haiku review round on the
relabel. The committed blueprints carry every retype pass and, for 526EZ, the accepted Opus review; the relabels carry
only what the emitter does today (XFA declarations, tooltips as descriptions, box-geometry rules at emit).

| form | version | fields | emit fixes | shape contradictions | name-based reader | name defects | Haiku review (relabel) | labeling (Sonnet 4.6) | names vs committed |
|---|---|---|---|---|---|---|---|---|---|
| fw9 | committed | 23 |  | 1 {'pattern_vs_value': 1} | 16/23 agree, 4 differ, 3 miss | 0 |  |  |  |
| fw9 | relabel | 17 | wide_widget_short_pattern 1 | 0 | 10/17 agree, 4 differ, 3 miss | 0 | 3 flagged, 0 fixes, $0.00 | 24,673 in / 758 out, $0.09, 9c/page | 13/23 identical, token jaccard 0.70 |
| acord25 | committed | 128 |  | 6 {'pattern_vs_value': 6} | 115/128 agree, 8 differ, 5 miss | 0 |  |  |  |
| acord25 | relabel | 128 | none | 0 | 121/128 agree, 2 differ, 5 miss | 0 | no flags | 21,636 in / 2,824 out, $0.11, 11c/page | 24/128 identical, token jaccard 0.58 |
| i765 | committed | 140 |  | 8 {'pattern_vs_value': 8} | 104/140 agree, 31 differ, 5 miss | 25 |  |  |  |
| i765 | relabel | 154 | wide_widget_short_pattern 15, separators_dropped_by_maxlen 6 | 12 {'pattern_vs_value': 12} | 119/154 agree, 26 differ, 9 miss | 21 | 27 flagged, 27 fixes: 3 better / 0 worse / 0 restored, $0.03 | 72,775 in / 3,490 out, $0.27, 4c/page | 39/154 identical, token jaccard 0.65 |
| vba21526ez | committed (after review) | 328 |  | 37 {'pattern_vs_value': 2, 'date_type_vs_value': 35} | 282/328 agree, 46 differ, 0 miss | 7 |  |  |  |
| vba21526ez | relabel | 345 | date_narrow_widget->string 57, part_by_maxlen 7 | 37 {'pattern_vs_value': 2, 'date_type_vs_value': 35} | 300/345 agree, 45 differ, 0 miss | 6 | 43 flagged, 39 fixes: 19 better / 0 worse / 1 restored, $0.06 | 129,877 in / 8,034 out, $0.51, 7c/page | 33/343 identical, token jaccard 0.46 |
| va_form_10_10ez | committed | (not run) |  |  |  |  |  |  |  |
| va_form_10_10ez | relabel | 122 | wide_widget_short_pattern 1, separators_dropped_by_maxlen 1 | 8 {'date_type_vs_value': 6, 'pattern_vs_value': 2} | 95/122 agree, 6 differ, 21 miss | 6 | 27 flagged, 20 fixes: 8 better / 0 worse / 2 restored, $0.03 | 58,471 in / 2,583 out, $0.21, 7c/page |  |

Reader = the name-based reader (`petey:pymupdf`; `petey:image` on 526EZ), Sonnet 4.6 at temperature 0; `agree` counts
fields, so a relabel that collapses a checkbox cluster into one category field has fewer fields to agree on (W-9: the
seven tax-classification boxes became one field; every one of the 23 widgets is still covered).

**Per form.**
- **W-9**: identical reader outcomes on all 23 widgets (same 4 differ, same 3 comb misses); the relabel's one
  contradiction fewer is the retyped `account_number` pattern. Names agree on 13 of 23 widgets; the rest are
  synonyms (`city_state_zip_cd` vs `_txt`). SSN/EIN parts came out `^\d{1,5}$` (the `id_part` default in
  `semantic_types.py`); the committed parts were narrowed by box length in the retype pass, which the emitter's
  `part_by_maxlen` rule only does when the widget carries MaxLen.
- **ACORD 25**: the relabel is clean on the first pass, no flags. The committed blueprint's six phone contradictions are
  six **misnamed fields**: `producer_phone_area_cd` / `_phone_nbr` and their insured / certificate-holder twins sit on
  the state-abbreviation and ZIP boxes; the relabel names them `producer_state_abbreviation_cd` / `producer_zip_cd`.
  Reader agree 121 vs 115. The one place where a fresh labeling beats every pass the old blueprint has been through.
- **I-765**: 154 fields (the committed grouped 14 checkboxes into categories; both cover the same 154 widgets).
  Reader agree 119 vs 104 and name defects 21 vs 25, both in the relabel's favour; shape contradictions 12 vs 8
  against it — all twelve are inferred patterns that the generator's formatting contradicts (SSN with dashes against
  `^\d{9}$`, `(617) 555-0234` against `^\d{10}$`, receipt numbers `MSC…` against `^\d{13}$`, eligibility-category
  letters against the `id_part` default). The committed blueprint lost these to the retype pass; the emitter cannot,
  because it has no values at emit time. That is what the loop is for, and it is the Haiku round's job below.
- **21-526EZ**: 345 fields (the committed has 328 after review), shape contradictions 37 = 37 (the same 35 approximate
  month/year dates typed `date`, on both), reader agree 300/345 vs 282/328 (87% both ways), name defects 6 vs 7 (the
  committed had 11 before its Opus round). The fresh emitter reproduces the reviewed blueprint's quality in one pass
  and $0.51 of labeling; `date_narrow_widget->string` fired 57 times on real names. Names agree on 33 of 343
  widgets — the labeler does not produce the committed names, it produces names that work as well.
- **10-10EZ** (no committed version; first fully new-emitter form): 122 fields, 8 contradictions (6 approximate
  dates, 2 patterns), 6 name defects, 19 reader misses. The misses are radio groups whose values are the XFA export
  codes (`0`/`1`), which the text-layer reader cannot locate — the `yn_column` class, not a text-layer problem (the
  filled PDF's text layer carries 74 of 75 string values).

**The Haiku review round** (`--review flagged --review-model claude-haiku-4-5`, per-field judgment by the loop):
- W-9: 3 flagged, all `ok`, $0.004. ACORD 25: nothing flagged.
- **I-765: 27 flagged, 27 "fixes": 25 of them removed the tooltip description**, 2 loosened patterns (better).
  The per-field judge scored the 25 as `same_kept` because each reviewed field read the same afterwards — but the
  whole form went from 37 detections to 51: sixteen **other** fields, the Part 6 additional-information rows, lost
  their disambiguation and collided. The emitter's `description_from_tooltip` rule put the descriptions back on the
  next iteration and the form returned to 37/21. Two lessons: (1) the judge is per field and blind to collateral
  damage — it needs a whole-form guard (restore the round when `detected_after` exceeds `detected_before` by more
  than the noise floor); (2) a reviewer must not be allowed to delete publisher-sourced descriptions, and Haiku
  deletes them eagerly. $0.03.
- 526EZ: 43 flagged, 39 fixes, the 35 approximate month/year dates retyped `date` -> `string` with a pattern:
  **19 better, 1 restored**, detections 43 -> 24, contradictions 37 -> 18, $0.06. The 18 left are the patterns Haiku
  put on those retyped dates, which the generator's values contradict in 16 cases — the fix traded one class for a
  smaller one, and a second round would remove them. Compare the committed blueprint after its Opus round: 37
  contradictions, 7 name defects, $0.36.
- 10-10EZ: 27 flagged, 20 fixes — 6 approximate dates retyped, 6 patterns, 2 names: **8 better, 2 restored**,
  contradictions 8 -> 0, name defects 6 -> 0, detections 33 -> 19, $0.03. The 19 left are the radio groups keyed by
  export code, which no reviewer fix reaches (a generator/reader convention, not a blueprint defect). Here too Haiku
  deleted 10 descriptions and the emitter's `description_from_xfa_choices` rule restored them a round later.

**Labeling cost, measured** (Sonnet 4.6, one call per page, `runs/_calls/auto_label/<form>/`): 4–11¢ per page, 
$1.19 for the five forms (49 pages, ~307k input / 18k output tokens); the plan's 9¢ estimate holds. Whole test with
validations and reviews about $2.50, under the $6 budget.

**Answers to the plan's questions.** The relabel matches or beats the retyped originals on every form on reader
agreement and name defects; it is behind only on inferred patterns that the generator's formatting contradicts (I-765),
which the loop removes in one round. The emit-time rules fire on real names (57 + 7 on 526EZ, 15 + 6 on I-765). No new
regression class; the `yn_column` and `approximate_date_month_year` classes account for the residue. New forms can be
generated with the current labeler as is; the 10-10EZ blueprint is fit to enter the library after one loop round. The
reviewer's default stays a per-field judge with a whole-form guard to add before the next wider run; Haiku is fine on
declarations and unsafe on descriptions.

## Option groups: one field per group, one entry per option (2026-09-29, `eval/radio_survey.py`, `petey/validate/expand_options.py`)

Prompted by the 10-10EZ residue: 19 radio groups the text reader could not place. The emitter wrote a radio group as
one widget (the union box) with `values` = on-states, so neither a person nor a geometry-aware reader could see the
options. The corpus survey found the encodings that exist: 1,172 button fields with more than one widget in 147 PDFs —
692 flagged radio (306 word states, 225 yes/no, 159 ordinal `0..n-1`), 480 flagged **checkbox** (423 with distinct
states, which behave exactly like radios; 45 with one state drawn in several places), 21 radio fields with a single
widget, groups of 2 to 12 options with two outliers at 64 and 93. The checkbox-flagged groups had been deduped to
their first kid: CMS-1500's seven-way insurance type was one boolean named `amended_return_ind`; 81 such groups in 11
library forms.

**Encoding now.** Any button field with several kids is one field. Distinct on-states are options: `type: category`,
`values` = the on-states (what the field stores; generator, filler, scorer unchanged), `widgets` keyed by on-state, each
entry with the option's own box, `on_state`, and `caption` (XFA member caption, else the on-state when it is a word;
ordinal states without a declaration stay uncaptioned — nothing guessed). Kids repeating one state are a boolean with
`x_petey_appearances`. Selection everywhere is "the field holds this option's on-state" (`extract.py`, `score.py`,
`synth/local.py`); the filler sets only the matching kid of a checkbox-flagged group on (`synth/render.py` — before,
every kid went on and GT "F" read back as `[M, F]`). XFA captions prefer the member's word value over its template
name (10-10EZ section 2 read "YES4" / "NO4"; the members' values are YES / NO).

**Checks** (native arm, cached ground truth, no reruns beyond these): 10-10EZ 122/122 with 22 groups; 526EZ 328/328
with 23 groups; CMS-1500 and DS-11, the checkbox-flagged cases, every migrated group agrees (their remaining misses are
date fields bound to name paths, pre-existing). 10-10EZ relabeled with the new emitter and run through the loop with a
Haiku round: 0 contradictions, 0 name defects; the text reader still cannot see radio states (19 unlocatable), as
expected — that is a reader-mode question, not a blueprint one.

**Library migration** (`expand_options --apply`, deterministic, from each blank's AcroForm kids and XFA captions):
43 forms, 376 groups rebuilt (286 single-widget radios, 90 booleans-on-first-kid), 965 options, 882 captioned. Names
untouched — the CMS-1500 group still answers to `amended_return_ind`; renaming is the reviewer's job.

**Captions, second pass (2026-09-30).** Three sources, in order, none guessed: the XFA member caption from an exact or
page-instance join whose member count matches the state count (a shape-fallback join lands on a same-named sibling —
526EZ page 13's branch-of-service and checking/savings groups had worn the neighbouring yes/no captions, now refused);
the on-state itself when the publisher wrote it as text ("0-5 years", "1 . Single.", "Medicare"); and the printed text
beside the box (`petey/label/captions.py`: right of the box, else left, else the short column header above, as in
yes/no grids; item labels, URLs, dot leaders and a sentence-length run are rejected; a caption repeated across options
of one group is dropped). Measured against XFA-declared captions: 526EZ 48 of 54 exact or prefix, 1 wrong, 5 empty;
10-10EZ 47 of 51 exact, 2 wrong (a paragraph-long declared caption), 2 empty. Library after the pass: 953 of 965 options captioned,
12 uncaptioned (two branch-of-service boxes whose text sits off the box's line, and boxes with no printed text near
them). Flat PDFs: the geometry finder tells ovals from squares but the adapter drops the distinction and nothing
groups them; radio groups on flat forms are the next gap.

## Frontier models as the blind generator (2026-09-30, `eval/generator_models.py`, `petey/synth/generate.py` OpenAI-compatible backends)

Same three forms, same loop, only the generator changes: one blind generation per form (page image with numbered boxes,
no names), fill, by-path readback, Sonnet 4.6 name-based reader. A generator is judged on whether its values survive
filling (`fill agree`), contradict declared shapes (`shape`), and can be found by a reader beside the right caption
(`reader agree`, with the reader's defect count) — the last is the realism proxy. `filled` is how many fields it chose
to fill; a real filing leaves fields empty, so more is not better by itself. Tokens are in/out for the whole form;
dollars are not tabulated for non-Anthropic vendors (no price table in the repo).

| form (fields) | generator | filled | fill agree / miss / differ | shape contradictions | reader agree (defects) | tokens in/out | gen s |
|---|---|---|---|---|---|---|---|
| W-9 (23) | claude-sonnet-4-6 | 8 | 23 / 0 / 0 | 0 | **23** (0) | 2.8k/0.2k | 4 |
| | gpt-5.5 | 8 | 23 / 0 / 0 | 1 | **23** (0) | 3.6k/0.6k | 11 |
| | gpt-4.1 | 15 | 23 / 0 / 0 | 1 | 19 (0) | 1.9k/0.2k | 3 |
| | gemini-3.8-flash | 10 | 23 / 0 / 0 | 1 | 16 (2) | 2.4k/0.2k | 4 |
| | gemini-3.1-pro-preview | 12 | 23 / 0 / 0 | 1 | 19 (2) | 2.4k/0.3k | 15 |
| | deepseek-flash | 10 | 23 / 0 / 0 | 1 | 13 (0) | 2.1k/4.6k | 22 |
| | deepseek-v4-pro | 12 | 23 / 0 / 0 | 1 | 20 (1) | 1.2k/20.0k | 257 |
| ACORD 25 (128) | claude-sonnet-4-6 | 78 | 127 / 0 / 1 | 7 | 111 (5) | 5.0k/1.1k | 18 |
| | gpt-5.5 | 97 | 127 / 0 / 1 | 9 | 111 (8) | 5.4k/5.2k | 68 |
| | gpt-4.1 | 111 | 110 / **16** / 2 | **27** | 51 (19) | 3.7k/1.1k | 8 |
| | gemini-3.8-flash | 78 | 128 / 0 / 0 | 8 | **118** (0) | 4.7k/1.2k | 20 |
| | gemini-3.1-pro-preview | 71 | 128 / 0 / 0 | **2** | **119** (1) | 4.7k/1.5k | 45 |
| | deepseek-flash | — | reasoning exhausted the 32k output cap, no JSON | | | | |
| | deepseek-v4-pro | 114 | 113 / **9** / 6 | **39** | 24 (36) | 3.0k/26.1k | 286 |
| I-765 (140) | claude-sonnet-4-6 | 123 | 136 / 4 / 0 | 2 | 104 (20) | 23.8k/1.5k | 36 |
| | gpt-5.5 | 117 | 136 / 4 / 0 | 1 | 110 (17) | 28.4k/15.7k | 251 |
| | gpt-4.1 | 133 | 139 / 1 / 0 | 4 | 98 (26) | 16.3k/1.3k | 21 |
| | gemini-3.8-flash | 95 | 137 / 3 / 0 | 1 | 108 (22) | 20.8k/1.6k | 89 |
| | gemini-3.1-pro-preview | 108 | 136 / 4 / 0 | 1 | **114** (11) | 20.8k/1.9k | 168 |
| | deepseek-flash | 118 | 138 / 2 / 0 | 1 | 108 (24) | 18.1k/89.8k | 414 |
| | deepseek-v4-pro | — | reasoning exhausted the 32k output cap, no JSON | | | | |

**Reading.** Every model's values survive filling except two: gpt-4.1 and deepseek-v4-pro fill almost every box on
ACORD 25 (111 and 114 of 128) with values that contradict the declared shapes (27 and 39) and that the reader cannot
place (51 and 24 agree, 19 and 36 defects) — over-filling makes an unrealistic document. On realism, **Gemini 3.1 Pro
is the best generator** here: fewest reader defects on both larger forms (1 on ACORD 25, 11 on I-765, against
Sonnet 4.6's 5 and 20; the I-765 reader noise floor is about 5 fields, so the ACORD gap is within noise and the I-765
gap is not), the fewest shape contradictions, and no fill misses. Gemini 3.8 Flash matches it on ACORD 25 (118, 0
defects) at a quarter of the wall-clock, and is a step behind on I-765. gpt-5.5 reads like Sonnet 4.6 on quality and
costs 7x the wall-clock and 10x the output tokens (its reasoning is billed as output). The DeepSeek models are
reasoning models too: deepseek-flash spent 90k output tokens on I-765's seven pages and both hit the 32k cap with
no JSON on one form each — not usable as configured (their thinking would need to be turned off or capped).

**Caveats.** One generation per form per model, so the generator's own variance is unmeasured; the judge is a Claude
reader, and Gemini won anyway; the six non-Anthropic backends go through the OpenAI-compatible endpoints, keys from
`petey-master/.env`. Decision this feeds: the default blind generator (Sonnet 4.6 today) has a better-realism
alternative in Gemini 3.1 Pro and a cheaper near-equal in Gemini 3.8 Flash; price per form for those two is the
number still missing.

**Prices** (vendor list prices fetched 2026-09-30, $/1M in/out: Sonnet 4.6 3/15, gpt-5.5 5/30, gpt-4.1 2/8, Gemini
3.1 Pro 2/12, Gemini 3.8 Flash 0.75/3.75 through 2026, DeepSeek flash 0.3/1.2 and v4-pro 1.32/3.96 at peak). Per form,
generation only: I-765 — Sonnet 4.6 9.4¢, Gemini 3.1 Pro 6.4¢, Gemini 3.8 Flash 2.2¢, gpt-4.1 4.3¢, gpt-5.5 61¢,
DeepSeek flash 11¢ (its 90k reasoning tokens); ACORD 25 — 3.1¢ / 2.8¢ / 0.8¢ / 1.6¢ / 18¢ / 11¢ (v4-pro). So the
better-realism generator (Gemini 3.1 Pro) is also a third cheaper than the default, and Gemini 3.8 Flash is a quarter
of the default's price. The harness now tabulates dollars (`PRICES` in `eval/generator_models.py`).

**Correction to the generator comparison (2026-09-30).** The `reader agree` column above counts every field the
reader and the ground truth agree on, including fields empty in both. A generator that leaves fields blank collects
that agreement for free, and the fill rates differ by 2x, so the column flattered the sparse fillers. Counted on the
fields each generator actually filled (the harness now prints this):

| form | generator | filled | reader agree on filled | $ | agreed fields per cent |
|---|---|---|---|---|---|
| ACORD 25 | claude-sonnet-4-6 | 78 | 63 (81%) | 3.1¢ | 20 |
| | gpt-5.5 | 97 | 86 (89%) | 18¢ | 5 |
| | gemini-3.8-flash | 78 | 73 (94%) | 0.8¢ | 91 |
| | gemini-3.1-pro-preview | 71 | 67 (94%) | 2.8¢ | 24 |
| | gpt-4.1 / deepseek-v4-pro | 111 / 114 | 36 (32%) / 13 (11%) | | |
| I-765 | claude-sonnet-4-6 | 122 | 89 (73%) | 9.4¢ | 9 |
| | gpt-5.5 | 116 | 91 (78%) | 61¢ | 1.5 |
| | gemini-3.8-flash | 95 | 67 (71%) | 2.2¢ | 30 |
| | gemini-3.1-pro-preview | 108 | 84 (78%) | 6.4¢ | 13 |
| | deepseek-flash | 118 | 90 (76%) | 11¢ | 8 |
| 21-526EZ (image) | claude-sonnet-4-6 | 312 | 262 (84%) | 13¢ | 20 |
| | gemini-3.8-flash | 219 | 211 (96%) | 3.1¢ | 68 |
| | gemini-3.1-pro-preview | 156 | 147 (94%) | 9.0¢ | 16 |
| 10-10EZ (image, side copy) | all three | 99-103 | 99-102 (99-100%) | 1.2-4.6¢ | |

Reading, corrected: the Gemini pair has the highest **precision** (share of filled values a reader can find: 94% on
ACORD 25, 94-96% on 526EZ) and Sonnet 4.6 the highest **yield** (it fills 312 of 526EZ's 328 fields against Gemini
3.1 Pro's 156, and so produces the most reader-confirmed fields on that form, 262 to 211 to 147). gpt-5.5 ties Gemini
3.1 Pro on I-765 precision at ten times the price. As training data per dollar, **Gemini 3.8 Flash** is ahead on every
form by 3-4x (68-91 confirmed fields per cent on the two large forms against Sonnet's 20); its weakness is I-765, where
it fills fewer fields at the lowest precision of the four usable models. Gemini 3.1 Pro's earlier "best on realism"
verdict was the by-absence artifact: it is precise because it is sparse. On 10-10EZ every generator is at 99-100%
and the form does not separate them. 526EZ note: Sonnet's 36 shape contradictions there are the 35 approximate
month/year dates it fills that the blueprint types `date`; Gemini leaves most of those blank.

## Frontier models as the labeler (2026-09-30, `eval/labeler_models.py`, `auto_label --model`)

Same three forms relabeled from the blank by each model (side copies, `--no-register --no-retrieval`), scored through
the loop against the same cached Sonnet 4.6 ground truth, so only the names, types and declarations differ. Field
counts differ where a labeler grouped checkbox clusters into categories (the committed I-765 has 140).

| form | labeler | fields | shape contradictions | reader agree on filled / miss | name defects | $ | s |
|---|---|---|---|---|---|---|---|
| W-9 (23 widgets) | all six | 17 | 0 | 8/11 / 3 | 0 | 1.4¢ (DeepSeek) to 15¢ (gpt-5.5) | 4-34 |
| ACORD 25 | claude-sonnet-4-6 | 128 | 0 | 77/82 / 5 | 0 | 11¢ | 32 |
| | gpt-5.5 | 116 | 0 | 78/79 / 1 | 0 | 22¢ | 43 |
| | gpt-4.1 | 128 | 0 | 77/82 / 5 | 0 | 6¢ | 21 |
| | gemini-3.8-flash | 125 | 0 | 78/82 / 4 | 0 | 3¢ | 38 |
| | gemini-3.1-pro-preview | 128 | 0 | 77/82 / 5 | 0 | 8¢ | 76 |
| | deepseek-flash | 115 | 0 | 78/79 / 1 | 0 | 3¢ | 87 |
| I-765 | claude-sonnet-4-6 | 154 | 10 | 84/117 / 12 | 20 | 27¢ | 54 |
| | gpt-5.5 | 133 | 10 | 85/117 / 1 | 28 | 57¢ | 114 |
| | gpt-4.1 | 152 | 10 | 69/117 / 11 | **35** | 16¢ | 30 |
| | gemini-3.8-flash | 135 | 12 | 89/117 / 4 | 22 | 8¢ | 170 |
| | gemini-3.1-pro-preview | 133 | 10 | **92/117** / 2 | 21 | 21¢ | 189 |
| | deepseek-flash | 139 | 10 | 86/117 / 4 | 25 | 4¢ | 65 |

Reading: on W-9 and ACORD 25 every labeler produces a blueprint the loop cannot tell apart (no contradictions, no name
defects, the same reader outcomes). I-765 separates them a little: Gemini 3.1 Pro, Gemini 3.8 Flash, Sonnet 4.6 and
DeepSeek flash sit within the reader's noise floor of each other (20-25 name defects, 84-92 of 117 filled fields
found); gpt-5.5 is a step behind (28) and gpt-4.1 clearly worse (35 defects, 69 found). The ten pattern contradictions
are the same on every labeler — inferred patterns the generator's formatting contradicts, the loop's job to remove. So
the labeler slot is not where model choice matters; cost is. Gemini 3.8 Flash labels I-765 for 8¢ against Sonnet's
27¢ with the same quality, and DeepSeek flash for 4¢ (its reasoning tokens stayed under the labeler's 32k cap here;
they did not in the generator). gpt-5.5 costs the most for no gain.

**Decisions this feeds.** Generator: Gemini 3.8 Flash for volume (best confirmed fields per dollar), Sonnet 4.6 or
Gemini 3.1 Pro when yield per form matters more than price; gpt-4.1 and the DeepSeek models are out for this slot.
Labeler: Gemini 3.8 Flash is the value default; nothing measured favours a dearer model. Both are one generation per
form per model; the variance of the generators themselves is unmeasured.

**Framing (user, 2026-09-30).** The product use case is a handful of forms at a time; library-wide runs are a
development concern. So the per-dollar and seconds columns above are dev numbers, not decision criteria: at a few
forms, price differences are cents and latency is minutes. On quality alone the generator choice is yield (Sonnet 4.6,
most confirmed fields per form) against precision (the Gemini pair, fewer fields, nearly all findable); the labeler
choice is a wash among the top four.

**Yield is a knob (user, 2026-09-30).** How many boxes a generator fills is a property of the case it invented, not
of the model, and the prompt can set it for any model. The model's own signal is precision on the boxes it filled:
Gemini 3.1 Pro and 3.8 Flash lead on ACORD 25 and 526EZ, gpt-5.5 ties 3.1 Pro on I-765, Sonnet 4.6 trails by 7-13
points on the two large forms (and 35 of its 36 contradictions on 526EZ are approximate dates it chose to fill). On
that reading the Gemini pair is at least as good as the default for this slot. The next comparison, if wanted, is
precision at controlled density: two prompt variants per form (typical filing, complete filing) for every model.

**Where the generator sits (2026-09-30).** The synthetic case is generated once per form and cached (blank bytes +
model + case key); every later loop run reuses it, and most library cases were imported from petey-master. It runs on
the product path only when a new form enters, once, and never during extraction. So its cost and latency are paid once
per form; its quality is baked into every judgment on that form until someone regenerates — which argues for choosing
the generator on precision and for more than one case per form.

## Synthetic-case coverage audit and three fill-path bugs (2026-09-30)

Andrew's question: how much of each target form do the cached synthetic cases cover? Distinct cases across
petey-master's runs (non-blind, by path) and this week's blind generations, a group counted as filled when any option
is selected:

| form | cases | fields | filled per case | filled in at least one case | never filled |
|---|---|---|---|---|---|
| W-9 | 14 | 23 | 8-15 | 19 (83%) | C-corp / trust boxes, "other" classification |
| ACORD 25 | 18 | 128 | 71-114 | 120 (94%) | 8 coverage flags (claims-made, hired autos, ...) |
| I-765 | 21 | 140 | 95-126 | 136 (97%) | arrested/convicted, replacement EAD, 2 preparer-scope boxes |
| 21-526EZ | 23 | 328 | 156-313 | 316 (96%) | signatures, "no date" flags, "other, specify" text |

The never-filled fields are the legitimately rare ones; a single case covers 60-80% of a form and a handful of cases
cover 94-97%. What the audit turned up on the way, all fixed:
- **Blind inventory ignored checkbox-flagged option groups** (one field, several kids: CMS-1500 insurance type). The
  kids were shown as independent true/false boxes and their answers overwrote one another on the shared path;
  `blind_inventory` now groups them exactly as the emitter does (CMS-1500: 11 groups where there were none).
- **Escaped on-states never filled.** I-765's unit-type boxes have on-states like `#20APT#20` (" APT "); the
  filler passed the raw name and pymupdf left the box Off in every case since July. On-states are now decoded in the
  filler and the local generator; I-765 by-path readback is 140 of 140 (was 136 with 4 misses on every run).
- **Cluster options scored against the wrong value type.** A labeler cluster's options are separate checkbox fields
  whose ground truth is a bool; the scorer compared it to the on-state string and reduced the group to nothing.
- Labeler clusters now carry each option's on-state and a caption (the on-state word — Widowed / Divorced / Single /
  Married — else page text): 1,231 on-states and 1,146 captions across 52 library forms.

Andrew's directions from the same discussion: keep several cases per form as a versioned set (fixed within any
comparison, refreshed when the generator changes) rather than regenerating every round; stockpile examples of
recurring value types (SSN, address, phone) drawn from cases we trust; keep "extract a correct value" and "fix a
malformed value" as separate problems.

## Ink-mark detection, robustness experiment (2026-09-30, `petey/validate/ink.py`, `eval/ink_marks.py`)

Andrew's condition before ink detection becomes the reader's eyes for radio and checkbox states: verify it against
different shapes, sizes, colours and densities of marks. Twelve pages he picked (AcroForm forms, so every option
box's rectangle and truth are known; 314 boxes): each page is flattened (widget appearances baked into the content,
since a hand mark sits on top of the printed box), 60% of boxes get a synthetic mark with a random variant — shape
(check, X, dot, filled square, tick, scribble), size 0.45-1.25 of the box, colour (black, blue, red, grey, faint
pencil), stroke 0.5-3 pt, offset 0-0.45 of the box — and 40% stay empty; a second pass marks boxes the PDF's own way
(appearance glyphs). Detector: render the box from the marked and the blank page at 200 dpi, grey, mean darkening
over the box (borders and printed glyphs cancel).

| threshold (mean darkening) | precision | recall |
|---|---|---|
| 0.005 | 0.985 | 0.982 |
| **0.010 (chosen)** | 0.984 | 0.952 |
| 0.020 | 0.987 | 0.900 |

Appearance-glyph marks: recall 0.985 (the two misses are DA 4187 kids whose appearance does not bake). Drawn
marks by variant at 0.01: every colour including faint pencil above 85%; every shape above 85% except the small
thin tick; marks shifted 0.45 of a box out are the main loss (52 of 77) and would confuse a person too. The four
false positives are empty boxes next to an oversized or shifted neighbour's mark spilling in. A first, binary
"dark pixel" version missed all 38 pencil marks; mean darkening fixed that. Caveat: these are rendered pages; scans
add speckle and need their own calibration before the threshold is trusted there. For a group, `selected_option`
takes the option with the most added ink, which sidesteps the threshold for the chosen one.

**Design restated by Andrew (2026-09-30):** generate synthetic cases from both outputs — the blueprint's typing and
the publisher metadata (AcroForm / XFA, or the page itself) — and compare what each puts in every box; a box the two
disagree on is a labeler flag. That sits alongside the extraction comparison the loop already runs.

## Radio and checkbox states in the text reader (2026-09-30, `extract_llm.page_texts_with_marks`)

The text-mode reader gets a `[x]` / `[ ]` token at every option box, placed by the blueprint's rectangles, decided by
the widget's own value when the document still has its form layer (exact; the product's inputs are clean digital)
and by ink in the box against the blank otherwise (`petey/validate/ink.py`, for flattened cases and later flat
forms). The widget's own glyph is dropped from the text; when nothing is printed beside a box (yes/no grids under
column headers) the token carries the blueprint's caption: `[ ] YES [x] NO`. The reader still gets no coordinates,
no paths and no widget names.

| form | before (text reader) | after | option fields found |
|---|---|---|---|
| 10-10EZ (side copy, 122) | 95-102 agree, 19 radio groups unlocatable | **122 / 122**, no detections at all | 42 / 42 |
| I-765 (140) | 104-119 agree, 20-25 name defects | **137 / 140**, 0 name defects | 24 / 24 |
| ACORD 25 (128) | 115-121 agree, 7-8 boolean deltas | 112 / 128 | 19 / 24 |

ACORD 25 goes *down* because the reader can now see what it could not before: five automobile-coverage boxes in the
committed blueprint are named one row off (the box beside ANY AUTO is `auto_liability_ind`, beside OWNED is
`auto_any_auto_ind`, beside HIRED is `auto_owned_autos_only_ind`, the blank fourth-row box is
`auto_hired_autos_only_ind`; `name_slide`). The reader answers what the page shows and disagrees with the ground
truth's names — the correct outcome. The PDF's own field names (`Vehicle_AnyAutoIndicator_A` on the box beside ANY
AUTO) were right; the old labeler slid. Along the way: I-765's unit-type boxes export ` FLR ` / ` APT ` / ` STE `
one place over from the printed Apt. / Ste. / Flr. (new taxonomy class `export_caption_mismatch`); tokens defer to
the printed word beside the box, so it does not matter to the reader. Ink detection stays as the fallback only; the
library recaption from page text was tried and reverted (right where the export is a code, wrong where the text
beside a box is a question or a watermark) — parked with the flat-form work.

## Page-grounded classification, value bank and case sets (2026-09-30, `petey/synth/classify.py`, `petey/synth/bank.py`, `petey/validate/class_check.py`)

The TODO's synthetic-data plan, steps 1-4, built and run on the five test forms. The classifier sees what the blind
generator sees (page image with numbered red boxes, an inventory of ids and control types, no names, no export
values) and returns per box the caption it read, a class from a closed 40-name vocabulary, whose value it is
(`entity`), and for checkboxes the question a set of boxes answers (`group`). Cached once per blank, model and
prompt version. The bank (`bank.yaml`: 24 personas with aligned state / ZIP / area code, 12 businesses) then
builds any number of cases for nothing: one persona per entity, so every applicant SSN box on a form holds the
same string; split boxes (SSN 3-2-4, EIN 2-7, phone 3-3-4, date parts) filled from one whole; one box per checkbox
group. Sets of three cases per form are frozen on disk (`validate --case-set 1`, manifest in
`runs/_gen_cache/sets/`).

**Classification, Sonnet 4.6, prompt v3** (three prompt versions over the day; 60 page calls, $1.80 in total).

| form | boxes | uncaptioned (label null) | checkbox groups | off-vocabulary | unknown ids |
|---|---|---|---|---|---|
| W-9 | 23 | 0 | 1 (the 7 tax-classification boxes) | 0 | 0 |
| ACORD 25 | 128 | 40 | 7 | 0 | 0 |
| I-765 | 161 | 17 | 13 | 0 | 0 |
| 21-526EZ | 342 | 0 | 5 | 0 | 0 |
| 10-10EZ | 122 | 0 | 3 | 0 | 0 |

Prompt v1 had no `label`; on ACORD 25 the producer / insured / certificate-holder blocks (four lines under one
heading, no per-line caption) came back slid by one or two rows, in a different direction from the committed
blueprint's own slide (its six "phone" fields are the state and ZIP boxes). v2 asks for the caption and returns null
where a box has none, with the conventional order (name, street, street, city; short boxes ending a line are state
then ZIP) as the fallback; the insured block then read in that order and the 40 uncaptioned boxes are marked as
guesses. v3 added `group` after the bank ticked two or three boxes of I-765's marital status and unit-type sets
(distinct paths per kid, so neither the inventory nor the filler sees a group).

**Bank set 1, three cases, by-path readback (`native`).** W-9 23/23, ACORD 25 128/128, I-765 140/140, 21-526EZ
328/328 on every case; zero ground-truth defects after the group fix (before it: 2-4 mutex violations per case on
I-765 and 526EZ). Two fill-path bugs found on the way: YAML reads an unquoted `1978-03-14` as a date object, and
pymupdf returns (export, display) pairs for I-765's state comboboxes; both normalised.

**Class check: page class vs blueprint type, per field, family level** (a scoring step, run for any generator
once the form has a cached classification; generation itself reads nothing from the blueprint). Tier 1: captioned box, typed field,
families differ (a detection; reaches the reviewer as `page_class` with the caption read). Tier 2: captioned box,
blueprint field untyped; the page offers a type (a suggestion, reported not counted). Tier 3: uncaptioned; a guess
on both sides.

| form | fields | tier 1 | tier 2 | tier 3 | what tier 1 is |
|---|---|---|---|---|---|
| W-9 | 23 | 1 | 4 | 0 | requester name-and-address typed person_name |
| ACORD 25 | 128 | 13 | 21 | 17 | six insurer names typed person_name; seven policy / certificate numbers typed free text |
| I-765 | 140 | 13 | 10 | 6 | `attorney_state_bar_num` typed state_abbr (`_state` slug); E-Verify company id typed business_name; eight document numbers typed free text; eligibility-category parts |
| 21-526EZ | 328 | 47 | 52 | 0 | 35 `disability_N_nm` typed person_name (the `_nm` slug rule); name-and-address boxes typed person_name; financial institution typed person_name |
| 10-10EZ (side copy) | 122 | 8 | 11 | 0 | next-of-kin address / relationship, designee, facility, three numbers typed free text |

The 526EZ box named `va_file_number_2` is captioned VETERAN/SERVICEMEMBER'S NAME (a tier-2 row: the field is
untyped). The `_nm` and `_state` slug rules in `semantic_types.py` account for most tier-1 rows across the forms.

**Class flags against the reader's flags** (text reader, set 1, `iterate --max-iter 1`; fields flagged in any of
the three cases):

| form | reader flagged (defect / unlocatable) | class tier 1 | both | reader hit a tier-2 field |
|---|---|---|---|---|
| W-9 | 2 | 1 | 0 | 0 |
| ACORD 25 | 32 | 13 | 0 | 4 (INSR LTR codes, the WC yes/no) |
| I-765 | 3 | 13 | 1 (`attorney_state_bar_num`) | 0 |

The two detectors see different faults. The reader answers placement and naming (ACORD 25's slid producer /
insured / holder blocks, the automobile row shift, the OTHER coverage rows); the class check answers typing (a
business named as a person, a number typed as prose). Neither reaches the six misnamed ACORD 25 phone fields by
name, but the bank does by value: it fills them as state and ZIP per the page class, the blueprint's phone pattern
rejects that, and `pattern_vs_value` fires on all six in all three cases; on I-765 the same detector fires on the
bar number typed as a state code. That is the two-generator disagreement of the design showing up through the
existing shape detector rather than a new one. (A first pass had the reader flagging one more field on each form;
that was before the combobox fix, when I-765's state boxes held pairs.)

Not run: 526EZ and 10-10EZ with the reader arm (image mode on 526EZ; 10-10EZ's blueprint is a side copy and
`validate` has no `--bpt` override). The blind-generator default (step 5) and the library-wide set (step 6, 134
forms, a classification per form at about 2 cents a page) wait on Andrew.

## Synthetic cases from the page alone: finder boxes, rect-keyed cases, widgets only at fill time (2026-09-30, late; `petey/synth/boxes.py`, `render.render_case`, `validate/rect_join.py`)

Andrew's correction to the section above: case generation may take nothing from the AcroForm layer, not names,
not export values, not control types or MaxLen or choice lists, and not where the boxes are. Walking the widgets
to fill the form is plumbing and is fine; an inventory of them going to the model is leakage, and it also leaves
flat forms with no path. So the synthetic path was rebuilt on page geometry:

1. **Boxes come from the page.** step2flat's finder runs on the rendered blank (widget appearances baked in, widgets
   stripped), so an AcroForm blank and a flat blank go through the same code. Each box is a page and a rect.
2. **The model sees ids and the image, nothing else.** Classifier and blind generator alike: a numbered red
   rectangle per finder box and the list of numbers. The classifier decides for itself which boxes take a mark
   (`option`), which are not boxes at all (`none`, the finder over-proposes), and which marks form one question
   (`group`). The bank builds a case keyed by rect: strings for text, True / False for marks, no on-states anywhere.
3. **Widgets at fill time only.** `render_case` matches each rect to the widget that best overlaps it (not the
   first hit: neighbouring widgets share strips) and writes through it; on a blank with no widgets it draws the
   text or an X at the rect. It reports where each value landed, and that report is the ground truth.
4. **Scoring joins on the landing rects.** Every blueprint widget and option carries a rect, so a field is credited
   with what its own widget holds. The blind generator was moved to the same footing (ids only, bools for marks,
   cases by rect). Set 1 (path-keyed) is retired; set 2 is the rect-keyed set.

**The finder against the widget layer** (`eval/finder_vs_widgets.py`, a debugging yardstick, feeds nothing):

| form | widgets | finder boxes | text recall | option recall | extras |
|---|---|---|---|---|---|
| W-9 | 23 | 70 | 13 / 15 | 8 / 8 | 49 (instruction pages) |
| ACORD 25 | 128 | 121 | 100 / 104 | 24 / 24 | 16 |
| I-765 | 161 | 241 | 116 / 123 | 38 / 38 | 87 |
| 21-526EZ | 385 | 623 | 291 / 292 | 93 / 93 | 253 |
| 10-10EZ | 151 | 173 | 73 / 80 | 71 / 71 | 37 |

Every option box on all five forms; the text misses are the I-765's seven barcode widgets, 10-10EZ's six date
boxes on page 5 and a handful of small cells. The extras are what the `none` class absorbs. Recall is counted
widget by widget, so the finder's different granularity (below) does not show here.

**Classification v4 (ids only, Sonnet 4.6):** W-9 70 boxes, 44 none, 8 options in one group; ACORD 25 121 /
23 / 20 options in 10 groups (8 "options" on wide text lines turned back to none by a geometry guard, its small
typed-X cells kept); I-765 241 / 27 / 38 in 15 groups; 526EZ 623 / 171 / 85 in 29 groups; 10-10EZ 173 / 30 / 70
in 25 groups. No off-vocabulary answer, no unknown id, on 1,228 boxes.

**Where the page's boxes and the widget layer disagree in granularity**, and the one rule that covers it (the
filler reports where a value landed; the scorer joins on that):

- several page cells over one comb widget (the W-9's SSN came back as a 3-cell box, two single cells and a 4-cell
  box): the filler writes their concatenation in reading order, the bank splits the SSN by cell boundaries;
- one page box over several stacked line widgets (ACORD 25's PRODUCER / INSURED / CERTIFICATE HOLDER blocks: one
  bordered cell, four lines): the filler splits the value on commas across the lines, as a filer would;
- two page boxes over one checkbox (a finder duplicate): the widget holds the OR of the marks and both report it;
- a small text cell the model calls an option (ACORD 25's ADDL INSD / SUBR WVD): the filler types an X.

**Set 2, three bank cases per form, by-path readback** (`validate --gen-model bank --case-set 2`):

| form | agree | residue |
|---|---|---|
| W-9 | 23 / 23 on all three | none; the signature and date lines are page boxes with no widget (correct) |
| ACORD 25 | 128 / 128 on all three | none |
| I-765 | 140 / 140 on all three | none |
| 21-526EZ | 328, 326, 327 of 328 | the dollars / cents pair of 27D (two cells, one more granularity case); one option group the page groups differently from the blueprint (`living_situation_14b`, two marks) |
| 10-10EZ (side copy, `validate --bpt`) | 122 / 122 on all three | none |

The blind generator on the same footing, one W-9 case: 23 / 23 by path, but it filled 14 of the 26 fillable
boxes (names and codes came back null), where the bank fills them all. Fill count was already known to be a
prompt knob; on the rect prompt it needs turning before the blind generator is generator (b) in a per-box
comparison.

**Class check under v4** (page class vs blueprint type, scoring step, tier 1 / 2 / 3): W-9 0 / 4 / 0, ACORD 25
21 / 15 / 0, I-765 8 / 24 / 8, 526EZ 45 / 53 / 3, 10-10EZ 9 / 5 / 0. The join is by rect now, so a field whose
rect the finder merged with a neighbour's compares against the merged box's class; the ACORD rise from 13 to 21
is mostly the address blocks (one `address_block` box against four line fields typed street / city / phone).

Cost of the day's classification: 60 page calls under v1-v3 ($1.80), then v4 on finder boxes over 35 pages
(the W-9's five instruction pages included; about $1.30). The finder takes 5-50 s a form and is cached.

## Inventory cross-reference: what set 2's clean numbers were hiding (2026-09-30, late; `petey/validate/inventory_check.py`, `score` verdict `not_generated`)

Andrew's condition before trusting set 2: score the case inventory against the blueprint inventory, by rect, both
directions and many-to-one, with a taxonomy class per mismatch. The reason: a field no page box reached was left
out of the ground truth and scored as agree-on-empty, so a form could read 100% while the finder had missed a
tenth of it. Two things changed. The scorer gained a verdict, `not_generated`, for a field whose rect no value
landed on (derived from the filler's landing report; stored per case; rescore derives it for older rect runs).
And a scoring step writes `inventory_check.json` per case with the classes `box_unreached`, `merged_box`,
`split_box`, `uncovered_widget`, `unbacked_box`, `option_group_mismatch`, plus `tie` where two case boxes overlap a
field rect equally (recorded, not resolved). The widget layer is read here, after the case exists, only to say
whether the finder or the labeler is the one off.

**Set 2 rescored** (three bank cases each; by path):

| form | fields | agree | not_generated | differ / defect | why not generated |
|---|---|---|---|---|---|
| W-9 | 23 | 21 | 2 | 0 | "Other" classification text and the requester box: no finder box |
| ACORD 25 | 128 | 93 | 35 | 0 | finder merges the INSR LTR / ADDL INSD / SUBR WVD cells into tall column boxes (the classifier then rightly refuses them as options) and each address block into one box, so lines two to five never receive a value; the OTHER coverage rows merge likewise |
| I-765 | 140 | 138 | 2 | 0 | two small boxes |
| 21-526EZ | 328 | 320 | 8 | 1 / 1 | three "no date" checkboxes, two yes/no options, one explanation box; the 27D dollars / cents pair |
| 10-10EZ (side copy) | 122 | 114 | 8 | 0 | the six page-5 date boxes the finder misses, plus two |

So the honest coverage of set 2 is 93 / 128 on ACORD 25, not 128 / 128. The same verdict puts a number on the
blind generator's under-fill: its one W-9 case, 23 / 23 before, reads 13 agree and 10 not generated. Everything the cases DO fill still reads
back by path; what they do not fill is now a number.

**Inventory classes per form** (from the class map, before filling):

| form | case boxes | box_unreached | merged | split | uncovered widget | unbacked | option-group mismatch | ties |
|---|---|---|---|---|---|---|---|---|
| W-9 | 26 | 2 | 0 | 2 | 0 | 3 | 0 | 2 |
| ACORD 25 | 99 | 16 | 5 | 0 | 1 | 5 | 0 | 0 |
| I-765 | 214 | 2 | 0 | 13 | 0 | 12 | 0 | 13 |
| 21-526EZ | 452 | 10 | 4 | 59 | 4 | 8 | 14 | 65 |
| 10-10EZ | 143 | 8 | 0 | 0 | 0 | 0 | 0 | 0 |

Two counts of "unreached" and both are right: `box_unreached` (16 on ACORD 25) is a field rect no case box
covers; `not_generated` (35) is a field no value landed on, which adds the lines inside a merged box the split
could not feed. The merged boxes are the finder list's items seen from the other side: ACORD's three address
blocks and two OTHER-coverage columns, 526EZ's three split dates and the dollars / cents pair. `unbacked_box`
rows are page boxes with neither a field nor a widget under them: the W-9's signature and date lines, I-765's
twelve, legitimate boxes the publisher never made fillable. `uncovered_widget` (ACORD 25 one, 526EZ four) is a
widget with no blueprint field, a labeler miss.

**Option groups, three-way.** 526EZ has 14 `option_group_mismatch` rows and the other four forms none. Most are
one blueprint field spanning two printed questions: `currently_homeless_ind` over 14A and 14B,
`currently_serving_reserves_or_national_guard_ind` over 21A and 21B, `receiving_military_retired_pay_ind` over
24A and 24B, `retired_status_cd` over 24C and 25, `branch_of_service_19a` over 19A and 19B. The page reads each
question as its own group; the blueprint's `widgets` map pools them, which is the labeler merge the three-way
rule attributes when the metadata shows several radio paths. These are the rows the reviewer should see next.

## Finder list re-read, and set 3 (2026-09-30, late; `step2flat/confidence.py` comb tier, classifier guard, `render._parts_for`)

The inventory cross-reference's "finder list" was re-read against the finder's raw candidates before anything was
changed. Of the four faults, one was the finder's:

| fault | what the candidates showed | where the fix went |
|---|---|---|
| W-9 SSN / EIN combs uneven | the raster pass had the right 3-2-4 and 2-7 groups; the lattice's single cells won the overlap at equal confidence | finder: `fz:comb` 0.60 -> 0.65, version `step2flat-2` |
| ACORD 25 INSR LTR / ADDL INSD / SUBR WVD cells "merged into columns" | found at the printed granularity, one tall cell per coverage section; the classifier said `none` or `option`, and the geometry guard then rejected the tall narrow ones | classifier guard: any cell up to 30 pt wide keeps `option`, whatever its height |
| ACORD 25 address blocks, 526EZ three-part dates and dollars / cents as one box | one box on the page; the lines and parts exist only in the widget layer | filler: a value over several widgets under one box splits by its natural parts (date -> month / day / year, money -> dollars / cents, phone 3-3-4, SSN 3-2-4, else commas), driven by the box's class |
| 10-10EZ page-5 dates missed | nothing drawn: "FROM:" and "TO:" with white space; the widget is invisible once baked | a new finder class, caption-anchored white space; recorded, not built |

Two more filler rules fell out of the rerun, both the same principle (what landed on the page is the truth): a text
widget is written once, and any later page box over it reports the value already there; the comb-cell join only
gathers cells smaller than the widget, so it no longer collides with the split rule when a big box and a small
box overlap one widget.

**Set 3 (finder v2, classifier v4, three bank cases) against set 2, by path:**

| form | fields | set 2 agree + not generated | set 3 agree + not generated | differ |
|---|---|---|---|---|
| W-9 | 23 | 21 + 2 | 21 + 2 | 0 |
| ACORD 25 | 128 | 93 + 35 | 98 + 30 | 0 |
| I-765 | 140 | 138 + 2 | 138 + 2 | 0 |
| 21-526EZ | 328 | 320 + 8 (1 differ) | 324 + 4 | 0 |
| 10-10EZ | 122 | 114 + 8 | 114 + 8 | 0 |

ACORD 25's remaining 30 are the address-block lines the four-part split cannot feed (six line widgets per
block, four parts), the OTHER-coverage columns and the cells the classifier still reads as `none` (the
AUTOMOBILE LIABILITY insurer-letter cell among them). 526EZ's remaining four: three "no date" checkboxes and the
explanation box, all `box_unreached`. Its unbacked count rose from 8 to 41 under the comb tier: the additional
periods of service table on page 12 is rows of cells with no widgets behind them, now found as combs; real page
boxes the publisher never made fillable, counted honestly.

A labeler finding on the way: 526EZ's `separation_pay_amount_dollars` carries the rect of the right-hand (cents)
box and `_cents` the left-hand (dollars) one. The class check cannot see it (both are `money`); the inventory
check cannot either (each rect is reached). It shows only when a filler writes dollars left and cents right and
the by-path readback disagrees, which is what the two "differ" rows were before the write-once rule masked them.
Worth a taxonomy class of its own: two fields of one family with swapped rects.

## Reader stability (2026-09-30, `eval/reader_stability.py`, I-765 set 3)

The loop's name-based reader (the dev-time judge of the blueprint's names; product extraction is the native path)
once gave 40 and 45 detections on the same I-765 blueprint and document. Andrew: no noise floor, measure it. Three
cases of the frozen bank set 3, each read five times with the reader cache bypassed (a salt per read), text mode,
Sonnet 4.6 at temperature 0; every read scored as validate scores. 30 calls, 329k in / 38k out tokens, $1.55.

| case | detections per read (differ + miss) |
|---|---|
| case 1 | 4, 4, 4, 6, 5 |
| case 2 | 4, 4, 4, 4, 4 |
| case 3 | 7, 7, 7, 8, 8 |

| per field, across the three cases | fields |
|---|---|
| stable and right | 125 |
| stable and wrong | 9 |
| flips on some case | 4 |
| flips on every case | 0 |

The reader is mostly stable, and its instability is not scattered. Three of the four flipping fields are
stable-wrong on the other cases, and the fourth (`item_6c_item_number`) is the neighbour of a slid cell: a flip is
the borderline case of a systematic fault, not noise on a sound field. The faults:

- **Empty cells in a table row (8 of the 13 fields that are not stable and right).** I-765 Part 6's page / part / item number
  rows: when the bank leaves the page number empty, the text layer shows `475 206` under the three headers with no
  sign of which cell is empty, and the reader shifts the values one column left (`item_5a_page_number` reads 475,
  `item_5b_part_number` reads 206, `item_5c_item_number` reads nothing). Stable when the shift is unambiguous,
  flipping when it is not (`item_6b_part_number` read 64 once in five). A text-mode representation gap, not a
  naming defect: the names are right.
- **Unit type** (`mailing_` / `physical_address_unit_type`): the reader answers the printed caption beside the
  `[x]` (ste), the ground truth carries the export word (flr). The known `export_caption_mismatch` class; stable.
  One read of an empty group answered `ste_ind` (a flip on case 1).
- **`attorney_state_bar_num`**: missed on cases 1 and 2 (bank values `A968179675`, `ACCT450740399`), found three
  times in five on case 3 (`VA524200606`). The field is typed `state_abbr` (a class-check tier-1 row) and the
  bank's identifier shapes are not bar numbers; both make it borderline.
- **Filling an empty field from context**: `place_of_last_arrival_txt` empty in the ground truth, read as
  'Richmond' (the applicant's city) in every read.

The ambiguity proxies (numbered sibling, shared description) flag 2 of 32 fields flipping against 2 of 106
without: too crude to test the hypothesis that flips sit on fields the blueprint leaves ambiguous; "wrong on
another case" predicts the flips better than either proxy.

Consequence for the loop: a judge this stable is consistent with the 40 / 45 swing coming from the batch cache
(one edit re-reads every field of a 120-field batch) landing on the few borderline fields; that was not measured
here.
Next: empty-box tokens in text mode (as the `[x]` / `[ ]` option tokens), then rerun; the whole-form check
compares only fields whose verdict held and confirms changed verdicts with two extra reads; the same measurement
on ACORD 25 and 526EZ before generalising.

### Three forms, two judges (2026-09-30, same script, set 3)

ACORD 25 and 10-10EZ added, and Haiku 4.5 (also temperature 0) beside Sonnet 4.6 on all three. Three cases x five
fresh reads each, text mode. Six runs, 180 calls, $5.04.

| form | judge | stable right | stable wrong | flipping | detections per read, case 1 / 2 / 3 | $ |
|---|---|---|---|---|---|---|
| I-765 (138 judged) | Sonnet 4.6 | 125 | 9 | 4 | 4-6 / 4 / 7-8 | 1.55 |
| I-765 | Haiku 4.5 | 114 | 23 | 1 | 14 / 11 / 18-19 | 0.53 |
| ACORD 25 (98 judged; 30 not_generated) | Sonnet 4.6 | 66 | 24 | 8 | 14-16 / 13-15 / 14-15 | 1.03 |
| ACORD 25 | Haiku 4.5 | 57 | 37 | 4 | 32 / 23-24 / 28-31 | 0.34 |
| 10-10EZ (115 judged) | Sonnet 4.6 | 99 | 15 | 1 | 6 / 6 / 8-9 | 1.18 |
| 10-10EZ | Haiku 4.5 | 97 | 16 | 2 | 7-9 / 4 / 10 | 0.41 |

**Randomness is small and sits on hard fields.** No field flips on every case, on any form, for either judge;
detections move by at most three between reads of one case. Sonnet's flips are fields Haiku is stuck wrong on (I-765
4 of 4, ACORD 25 6 of 8, 10-10EZ 1 of 1): a flip on the better judge marks a field that is hard, not a coin toss.
Haiku's flips are mostly fields Sonnet gets right (5 of 7): Haiku's own weakness.

**Stable is not right.** Haiku flips about as little as Sonnet but is stably wrong far more often (I-765 23 against
9; ACORD 25 37 against 24). Stability alone cannot choose the judge; Sonnet 4.6 is the more accurate on all three
forms. Most of Sonnet's wrong fields are wrong for Haiku too (I-765 12 of 13, ACORD 25 29 of 32, 10-10EZ 10 of 16):
field-level causes, not model noise.

**Few of the wrong verdicts are about names.** Sonnet's not-right fields on the three forms, by cause:

- **Empty cells in rows and columns** (the largest group on every form). The text layer keeps the filled values of
  a row in order but drops the empty boxes, so the judge shifts values into the empty slot: I-765 Part 6 page /
  part / item; ACORD 25 policy effective / expiration dates (effective empty, expiration read into it) and the
  umbrella and general-liability limit columns; 10-10EZ discharge dates and the spouse / child income columns.
- **Ground-truth defects from case generation**, where the judge is right: ACORD 25's insured address line holding
  an insurer's name and insurer C holding the insured's business (the uncaptioned blocks classified by position);
  10-10EZ's home address slid one box (city 'Columbus', state 'ma', ZIP 'OH', county '43215'; the judge reads
  Columbus / OH / 43215); free text in an ADDL INSD cell; a name inside a next-of-kin address.
- **Mark cells and checkbox grids.** ACORD 25's ADDL INSD / SUBR WVD / INSR LTR cells take a typed X that sits in
  the text with nothing tying it to its row; the automobile and umbrella checkboxes and 10-10EZ's race boxes
  (Black vs Native Hawaiian) read against the wrong caption in a grid.
- **Known classes**: I-765 unit type (`export_caption_mismatch`), `attorney_state_bar_num` (typed state_abbr).
- **Left over**: a handful (ACORD `revision_number_txt` missed; 10-10EZ next of kin read without the middle
  initial).

So in text mode the judge mostly reports how the page is presented to it, and in a few places the case itself,
not the blueprint's names; a reviewer handed these as name defects would rename correct fields. The empty-cell and
mark-cell groups are the target of the next change (tokens for empty boxes and typed marks in text mode, or
image mode for grid pages); the ground-truth group goes to the case generator (ACORD's uncaptioned blocks,
10-10EZ's address run).

## How informative is the judge? Four new forms through the whole pipeline (2026-09-30)

Andrew: before changing the judge, see how often it disagrees and whether the disagreements are useful. Four AcroForm
forms new to the loop (I-9; WC Form 5020; Alabama AL8379, almost no tooltips; Form 5500-EZ) went through the whole
pipeline as side copies (`runs/judge_eval/`): fresh label (Sonnet 4.6, `--no-register --no-retrieval`), blind
classification, a bank case set of three, then `iterate --review flagged --apply-correct` with the judge
(`judge:pymupdf`, Sonnet 4.6) and the default reviewer (Opus 5). OCC 1003 was dropped after a text-mode bug (TODO:
pages with no option boxes read in stored order). The blueprints before the loop are kept as `<form>_v0.bpt`.
Evidence per disagreement: the caption the classifier read for the box, ground truth, native, the judge's answer.

| form | fields | judge disagreements | judge flags to the reviewer | edits on judge flags | edits on other flags (source) |
|---|---|---|---|---|---|
| I-9 | 125 | 9 | 5 | 0 | 1 (class check) |
| WC 5020 | 77 | 22 | 14 | 2, neither improved the judge's own count | 9 (7 class check, 1 shape, 1 option group) |
| AL8379 | 58 | 16 | 1 | 0 | 0 |
| 5500-EZ | 88 | 6 | 4 | 0 | 1 (class check) |
| total | 348 | 53 | 24 | 2 | 11 |

The 53 fields the judge disagreed on, by cause:

| cause | fields | examples |
|---|---|---|
| empty cells / column layout in the text layer | 27 | AL8379 injured-spouse / other-spouse / joint columns (15); 5500-EZ participant counts 5a / 5b x (1) / (2); 5020 date pairs |
| case values implausible for the box | 8 | I-9 "Issuing Authority" = 'Services maintenance'; 5020 county = 'Invoice renewal' |
| single-letter code cells | 7 | 5020 EVENT / SOURCE / PART OF BODY codes 'E', 'P', 'C' with nothing tying them to their column |
| typed-X mark cells | 3 | 5020 AM / PM |
| judge answers an unmarked option group | 3 | 5020 on-premises 'No', type of employer 'City' |
| scorer / format | 3 | address blocks with the name prepended |
| occasional misses (1 of 3 cases) | 2 | I-9 List B document number, expiration date |
| a wrong name | 0 | |

Two fields look misnamed on inspection, and the judge disagreed on neither for that reason: WC 5020
`mail_to_address_txt` sits on a box captioned FIRM NAME (the judge returned the firm name with extra text, a
`substring` row), and `industry_txt` on one captioned OCCUPATION (the judge could not find the one-character
code value). Every kept edit that the loop scored better came from another check, mostly the class check
(passport number typed as a country; prior plan name typed as a person; hours and days typed as text). Their "better"
is partly by construction, since a type fix clears the class-check flag that counted against the field, but each
reads right on inspection.

**Reading.** On these forms, with this case generator and in text mode, the judge raised 53 disagreements and none
was a naming error; the 24 that reached the reviewer produced two description edits with no measured gain. Its
disagreements measure the presentation of the page (empty cells, code and mark cells) and the plausibility of
the generated values far more than the names. The class check carried the loop's useful edits. Not shown here:
whether the judge would catch a misname on a page it reads cleanly (the stability runs' I-765 and ACORD 25
blueprints are older and partly tuned on); planted misnamings would answer that directly.

### Twenty more forms (2026-09-30, `eval/judge_informativeness.py`)

The same pipeline on 20 more new AcroForm forms (13 verticals, random pick with at most two per vertical, each with
at least one option box so the text-mode ordering bug does not apply; list in `runs/judge_eval/batch20.txt`), three
workers, about 30 minutes; reviewer cost $2.20 over the batch. With the first four, 24 forms and 1,740 fields.

| | count |
|---|---|
| judge disagreements | 308 |
| sorted by rule: layout shift / implausible value / format / code cell / mark cell / unexplained | 193 / 46 / 34 / 6 / 2 / 27 |
| flags to the reviewer: judge / class check / shape / option group | 183 / 132 / 45 / 23 |
| kept edits | 102: 81 on flags the judge did not raise (mostly the class check), 21 on judge flags (10 judge only) |

**The judge does find naming defects; they are about one disagreement in twelve.** Read by hand from the
disagreements and from a name-vs-caption screen (60 candidates, most of them noise: abbreviations, caption
fragments, captions read one box off):

- **TX DMV 1756**: 15 fields named `control` ... `control_15` in a Year / Make table (the labeler kept an opaque
  path name). The judge disagreed on all 15.
- **KS DO-10**: five widgets the publisher placed one row off: `ein_ssn_ptin` sits in the box captioned Area Code &
  Phone Number, `representative1_phone_number` in the EIN/SSN/PTIN box, `representative1_ein_ssn_ptin` in the Fax
  Number box (confirmed on the rendered page; captions print at the top of their own box). A filer types by
  position, so the blueprint's names, copied from the publisher, are wrong. The judge disagreed on all five. The
  ACORD 25 phone / ZIP pattern again.
- **ND 1TP**: `process_types` and `primary_waste_streams` swapped. The judge disagreed on both.
- **SS-4** (`ein` on the legal-name box), **ID STC-06** (phone-number name on a name-and-phone box), **TX DWC-001**
  (a months / years pair crossed, one of the two): judge disagreements, the first two also flagged by other checks.
- Missed: AL 2848A `taxpayer_signature` on the `SignatureDate` box (the judge agreed); the other DWC-001 field.

About 25 of the 308 disagreements are naming defects; the rest are the presentation and value families above.

**The loop under-repairs what the judge finds.** SS-4 and STC-06 were renamed correctly. 1TP got descriptions that
describe each box correctly beside the swapped names, so each field now contradicts itself; the repair is a
rebind (`correct.py`), which did not fire. DO-10: the reviewer kept the publisher's names, citing the rule that
publisher metadata outranks nearby text, which is exactly backwards when the publisher placed the widget wrong.
DMV 1756: the reviewer passed all 15 `control` fields as "ok".

**Noise from the batch cache, seen in passing.** DMV 1756: one description edit, and the next round's detections
rose from 63 to 71: the edit re-keyed the 120-field batch and every field was read again.

**Reading.** The judge is informative but low-precision: its naming signal (opaque names, publisher misplacement,
swaps) is real and sits under a much larger layer of presentation and value disagreements, which the presentation
fixes and plausible case values should remove. The larger loss is downstream: the reviewer defers to publisher
metadata and does not rename opaque names, so the judge's best catches are not repaired.

### Batch 2: twenty more forms with the fixes in (2026-09-30)

Same pipeline after commit 21dff12 (the page wins on position, opaque names renamed, swaps not described, judge
flags gated by caption, unique bank free text). 20 new forms (`runs/judge_eval/batch20b.txt`), 1,751 fields,
about 25 minutes on three workers.

| | batch 1 (24 forms) | batch 2 (20 forms) |
|---|---|---|
| fields | 1,740 | 1,751 |
| judge disagreements | 308 | 428 |
| by rule: layout / implausible / format / unexplained / code+mark | 193 / 46 / 34 / 27 / 8 | 239 / 89 / 61 / 36 / 3 |
| renames kept by the loop | 2 | 11 |

**The fixes repaired publisher misplacement.** VA DMV RDT-120: the widgets whose tooltips say DOING BUSINESS AS
NAME and CORPORATION STATE sit in the boxes captioned STATE BUSINESS FORMED IN and TOTAL NUMBER OF QUALIFIED
VEHICLES; the reviewer renamed both, and `individual_account_nm` to `legal_business_nm`, all three right on the
rendered page. Utah WC-122: `claim_number` on the PHONE # box (its path is "Employer Tel #"), the labor-commission
date on LOCATION #, the employer address on EMPLOYERS LOCATION ADDRESS: renamed, all right.

**And it made two wrong renames, from a misread caption.** WC-122 `time_of_occurrence` sits under the printed
TIME OF OCCURRENCE and was renamed `date_of_injury_illness` (the neighbouring cell's caption). MA LIC100
`out_of_state_state_abbreviation_cd` sits under C5. State and was renamed `applicant_nm`: the classifier gave
that box the caption "B16. Name", two rows up. The finder box and the widget align; the classifier misattributes
captions on dense forms (on LIC100 a run of them: `ssn` against "B4. Suffix", the mailing address one box off),
and both the review gate and the reviewer's `caption_printed_for_this_box` take its word. The reviewer left
LIC100's other offset fields alone.

**The labeler would not have made the WC-122 errors with the path.** Its paths are readable ("Employer Tel #",
"Location", "Time of Occ") and the labeler never sees them (the path-to-labeler change, decided 2026-09-30, not
yet built).

**Louisiana 7006's 52 edits are mostly defensible.** 50 came from shape flags that bank filler set off ("Quarterly
renewal" in a box typed year); the reviewer loosened the type citing the printed column caption "Year(s) or
Period(s)", which does take ranges. Filler as the trigger, a right decision on the caption.

**Irish MED2**: 83 of its 84 disagreements are layout shifts (a table of expenses with empty cells).

Implausible case values over all 44 forms: 135 (`runs/judge_eval/implausible_case_values.csv`); commonest caption
words excise, location, district, qtr, county, township, range.

### The case chain: box -> class -> value (2026-10-01, `petey/validate/field_chain.py`)

Andrew: the case is built box -> class -> value, so a fault early in the chain makes every later signal wrong; check
in that order. Each field gets the stage where its case breaks: `box` (the inventory check says the case box does
not line up, or no value reached it), `class` (the classifier's caption for the box is none of the text lines lined
up with the widget within 36 pt above, below, inside, left or right, nor the nearest lined-up line above it (a
column header) or to its left (a row label)), else `value`. A box- or class-stage field sends no class, regex or
judge flag to the reviewer and adds nothing to the loop's per-field status; class and regex disagreement on a bank
case count as one signal.

Tuned on the hand-checked fields, in four steps: nearest-line only marked 94 of 527 fields on six forms wrong, mostly
where the classifier was right (captions printed below the box, section headings nearer than the real caption);
any lined-up line within reach; alignment over the shorter extent (a short caption over a wide box); column headers
and row labels for table cells, and letter-spaced small caps compared without spaces (KS DO-41 'Y EAR/ P ERIOD').

| over 44 forms, 3,491 fields | |
|---|---|
| box stage | 1,012 |
| class stage | 197 (TX DMV 1756's county checkbox grid, 38 of them, read one column off by the classifier) |
| value stage | 2,282 |
| hand-checked fields reaching the reviewer as they should | 16 of 17 |

The one miss is SS-4 `ein`: the classifier read its caption right ('Legal name of entity'), but an 'EIN' label sits
close enough that the geometry calls it uncertain, so the field no longer reaches the reviewer and the batch-1
rename (to `entity_legal_nm`) would not happen. The cost of the rule: a right rename deferred, against wrong renames
stopped (LIC100, Utah WC-122 `time_of_occurrence`). Batch 2's reviewer flags: 228 at the time, 168 with the chain.

## The rename adjudicator, and the box stage measured (2026-10-01, `petey/validate/adjudicate.py`, `eval/finder_vs_widgets.py`)

Andrew: lean on the agentic side of the loop rather than on more hard-wired rules, and do not fix one form's problem
in a way that moves another's. Both items of the 2026-10-01 handoff were taken that way: the contested renames go to
a model that reads the page, and the finder is measured over all 44 forms before anything in it changes.

### Adjudicator for contested renames (`adjudicate.py`, `eval/adjudicator_test.py`)

One vision call per contested rename, between the reviewer's decisions and `apply_decisions`: a crop of the rendered
blank, full page width, the widget's own rect (from the blueprint) outlined in red, reaching up to the nearest
lined-up line above the box so a table's column header is in view (TX DMV 1756, fifteen rows down); the current
name, the proposed name, the reviewer's reason, the tooltip / path, the description. The question is what a filer
writes in the outlined box and which name describes it: `current` / `proposed` / `unclear`. A rename is contested
when the chain's caption is unverified (`verified` False or None) or the publisher's tooltip / path and the caption
share no word; `unclear` keeps the name and sets `x_petey_adjudication.needs_person`.

Tested on the nineteen fields checked by eye on 2026-09-30 / 10-01, forced on every case:

| model | agree with the hand check | cost |
|---|---|---|
| Sonnet 4.6 | 18 / 19 | $0.12 |
| Opus 5 | 18 / 19 | $0.22 |

**The one disagreement was the hand check's error, not the model's.** Both models answered `current` for SS-4 `ein`
-> `entity_legal_nm`, and the crop shows why: the widget sits in the header's EIN box (under the printed "EIN",
beside the OMB number), not on line 1. The classifier had read line 1's caption for the header box, the batch-1
reviewer followed it, the loop scored the rename 'better', and the 2026-09-30 note called it right. The fixture's
expectation was corrected; both models then agree with all nineteen. Everything else came out as expected: KS
DO-10's five publisher misplacements upheld to the captions of their cells; RDT-120, WC-122 and 1TP's right renames
upheld; DMV 1756's `control` cells to a Year / Make name (both models noticed that `control_2` is row 15 and
`control_15` row 2 and judged the kind of value, as asked); the two wrong renames from misattributed captions
(WC-122 `time_of_occurrence`, LIC100 `out_of_state_state_abbreviation_cd`) rejected. Sonnet 4.6 is the default.

Of the nineteen, the loop would have contested eleven (DO-10's five and DMV 1756's three by tooltip-vs-caption
disagreement; SS-4, WC-122 `time_of_occurrence` and LIC100 by the chain) and landed eight without a call (the
RDT-120 and WC-122 renames whose tooltip shares a word with the caption, 1TP's swap).

**Wiring.** `review.review()` adjudicates by default (`--no-adjudicate`, `--adjudicator-model` on `review` and
`iterate`); a rename not upheld is dropped from the decision and the rest of it (type, pattern, description)
stands; every adjudicated field carries `x_petey_adjudication`. Two loop changes go with it, both in the direction
of letting the model decide instead of a rule: a class-stage field (box lined up, caption unverified) now reaches
the reviewer again on a judge flag, with the caption withheld, and any rename on it is contested, so SS-4's field
is no longer silently held (and is now kept, for the right reason); and `judge_review` keeps an adjudicated rename
it would otherwise restore as 'same', since a class-stage field's before and after are both zero by construction.
Shape and class flags on class-stage fields stay held: they rest on the misread caption. End to end on KS DO-10's
existing run (`review` without `--apply`): the reviewer (Opus 5) proposed the five renames, all five were contested
and upheld.

### The box stage, measured with a size-aware yardstick (`eval/finder_vs_widgets.py --list runs/judge_eval/forms44.txt`)

`match_rect` scores intersection over the smaller area, so a widget inside a region box counted as found. The
yardstick now calls a widget `hit` only when its best box is within 3x of its area either way, `in_region` when
the box is more than 3x larger, `part` when more than 3x smaller, and reports the region boxes with the widgets
they hold. Over the 44 forms (`runs/judge_eval/finder_vs_widgets_before.json`):

| 44 forms, 3,795 widgets, 3,644 finder boxes | old yardstick | size-aware |
|---|---|---|
| text widgets found | 86% | 2,212 / 2,853 = 78% |
| option widgets found | 55% | 488 / 942 = 52% |
| widgets inside region boxes | counted as found | 250, in 45 boxes |
| widgets under part boxes | | 13 |
| missed | | 832 |

Not concentrated: the six worst forms carry 44% of the misses, 22 of the 44 forms find at least 90% of their text
widgets, 11 miss five or fewer. Read from the finder's raw candidates (`pipeline.run`'s scored list) under the
missed widgets, the misses fall into four families:

1. **Region boxes whose rows exist only in the widget layer** (ND 10RR 102 widgets in 4 boxes, SFN 18668 86 in 4;
   together 75% of all in-region widgets). The 10RR region is one tall printed cell under "Transporter" with no
   rule between its 25 rows: zero drawings inside it on the page, and the baked widget appearances draw nothing.
   SFN 18668's region has one dashed column divider (Volume | Bbls or MCF) and no row rules. The handoff's fix,
   split a region at the rules printed inside it, has nothing to split on here; the rows are not on the page, and
   a page-only finder cannot know there are 25 of them. What would recover them is fill-time, where the widget
   layer is allowed: a region value written as lines, one per widget stacked inside the region. Not built; a
   design decision for Andrew.

2. **Typed line cues with a currency sign** (B106I 44 of its 61 misses, B410 12). The text layer carries the word
   `$___________`; `features.LINE_CUE` excludes words made purely of line characters, so this one counts as printed
   text (coverage 0.58) and `text_filled` sinks the underline candidate from 0.70 to 0.40. Patch: let one leading
   non-word character precede the run. Measured with `eval/finder_experiment.py --patch linecue` (the change
   monkeypatched, boxes into a scratch cache, nothing in `runs/_gen_cache/` touched):

   | | before | after |
   |---|---|---|
   | text widgets found | 2,212 | 2,273 |
   | forms that changed | | B106I 23 -> 72 of 81, B410 31 -> 43 of 55 |
   | any other form, option recall, extras | | unchanged (930 extras before and after) |

3. **Checkbox squares that are text glyphs**: ZapfDingbats '■' on LA 7006 (68 option widgets, 0 found),
   Wingdings2 0xF0A3 on TX RRC R-32 (78, 12 found), Wingdings on B410 (33) and KS DO-41 (19). The frozen raster
   reader erases text before it looks for boxes, so the square leaves no candidate; where the lattice has one
   (7006), the glyph makes it `text_filled` and, being bold, `header`, and it sinks to 0.45. Patch: drop such
   glyphs from the words the features count and add each as a `lat:glyph` candidate at 0.75, a square of the
   character's advance width centred on its bbox (the bbox is the font's line height; with the full bbox KS
   DO-41's 7 pt radios sat inside boxes over 3x their area). Both patches together, over the 44 forms
   (`eval/finder_experiment.py --patch both`, `runs/judge_eval/finder_vs_widgets_after_both.json`):

   | | before | linecue + glyph |
   |---|---|---|
   | text widgets found | 2,212 / 2,853 (78%) | 2,275 (80%) |
   | option widgets found | 488 / 942 (52%) | 800 (85%) |
   | missed | 832 | 477 |
   | widgets inside region boxes | 250 | 233 |
   | extras (finder boxes with no widget) | 930 | 962 |
   | forms that changed | | 13 |
   | forms worse on text or option recall | | none |

   Thirteen forms change, none for the worse: LA 7006 0 -> 68 of 68 options, TX RRC R-32 12 -> 78 of 78, B410
   0 -> 33 of 33, LA 16019 0 -> 33 of 33, LA 1048 0 -> 14 of 14, KS DO-41 0 -> 19 of 19, KS DO-10 0 -> 8 of 8,
   LIC100 20 -> 66 of 68, HK IRD 26 -> 33 of 33, OCC 1014cs / 1022a 4 -> 9 and 3 -> 9. The 32 new extras are 23
   on LIC100 (printed squares in its A1 to A4, C2 and D rows that no widget backs: real boxes on the page, the
   inventory check's `unbacked_box`), 5 on DO-41, 2 on Form 5500, 1 each on B106I and LA 1048.

4. **Form 5500**: 51 of its page-2 misses have no candidate from either reader: the 8a / 8b feature-code combs
   (32 cells), the administrator address block, the header checkbox. Their borders are drawn as sub-point filled
   slivers; the lattice drops segments narrower than 3 pt and the frozen reader (sha-pinned) sees nothing. Nine
   more are small enclosed boxes with an 'X' in the text layer (`text_filled` + `header`). Not reduced to a fix.

**What a `FINDER_VERSION` bump entails (checked in the code, 2026-10-01, after Andrew asked).** Nothing codifies
it; it is one constant in `petey/synth/boxes.py` and the caches that hash it. The one bump so far (`step2flat-1`
-> `-2`, the comb tier, 2026-09-30) is a line in the TODO. Keyed on it: the box cache (`runs/_gen_cache/boxes/`,
local, 15-20 s a page), the classifier cache (`runs/_gen_cache/classify/`, one call per page per form), and the
blind generator's cache (`generate.py`, only when that generator is used). NOT keyed on it: the bank cases
(`validate._bank_cache_path`: blank bytes + `bank` + case key) and the case-set manifests
(`runs/_gen_cache/sets/<form>_set1.json`, 59 forms), whose values are stored by the OLD finder's rect keys
(`p1:464.6,108.5,570.7,118.1`). After a bump, set 1 stays on disk and silently misaligns: the new boxes have no
values, the dropped boxes keep orphan values, and the inventory check reads it as the finder's fault. So a bump
is three things: re-run the finder, re-classify every form, and regenerate (or version) the frozen case sets,
which Andrew froze deliberately. The patches stay in the experiment harness until he decides; the sets' cache key
should carry the finder version before any bump, so a stale set refuses to load rather than scoring.

### Versioning the finder, and what was already stale (2026-10-01, late; `petey/synth/boxes.py`, `petey/validate/provenance.py`)

Andrew: do not regenerate the library when the finder changes; re-run the forms being addressed, record on every
blueprint which finder built it, and make "rebuild it with the current finder" the first step when a form
misbehaves. Codified as follows.

- **Finder version** is derived, not typed: `FINDER_LABEL` (bumped by hand when behaviour is meant to change) plus
  `+code<sha>` when `step2flat/*.py` differs from the sha the label describes, plus `+env<sha>` when pymupdf or
  tesseract differ from the environment it was read under (the raster reader erases OCR'd text before it looks
  for boxes, so tesseract is part of the function). Code edited without a bump re-keys the caches and prints
  why, instead of serving boxes the code no longer produces. The finder is deterministic (DO-10 twice: identical).
- **Case basis** `<finder>|<classifier model>|<prompt version>`: everything a bank case depends on besides the
  blank and the case key. Bank cases are now cached under it; set manifests record it; a set on another basis
  refuses to load (`validate --rebuild-set` draws it again under the current basis, same id, old build kept in
  the manifest's history and its files on disk).
- **Build stamp**: the run's `summary.json` carries the basis spelled out plus generator, set and run;
  `iterate` writes the same onto the blueprint as `x_petey_build` after every validate.
- **Frozen files stay frozen.** Stored case values are the filler's effective values (merged and truncated), so a
  fresh draw is not the same file (DO-10 set 1 case 1: 19 of 57 differ, RDT-120: 9 of 127). A set whose manifest
  basis equals the current one adopts its pre-basis files by copy; nothing is redrawn.

**What the check found on the 59 manifests:** 50 are on the current basis (all 44 judge-eval sets, the five
forms' set 3). Nine are not: fw9, acord25, i765, 526EZ and 10-10EZ sets 1 and 2 were drawn under `step2flat-1`
(two of them before the manifest recorded enough to tell) and have been readable against `step2flat-2` class maps
ever since the comb-tier bump. They are the retired sets (set 3 replaced them), so nothing scored since depends
on them, but it is the exact failure the basis check exists for, and it had already happened once.

Terms are now defined in one place, `docs/GLOSSARY.md`.

### step2flat-3 landed, rebuilt on the forms it was diagnosed on (2026-10-01, late)

Andrew: re-run only the forms being addressed; the others stay on the finder they were built with. The line-cue and
glyph patches moved from the experiment harness into `step2flat/` (`features.LINE_CUE`, `features.glyph_rects`,
`lattice.lattice_fields`, `confidence.TIER['lat:glyph']`), `FINDER_LABEL` became `step2flat-3` (code sha
`93d5efe257db`; the sha is now over the parsed AST with docstrings dropped, so a comment edit is not drift), and set
1 was rebuilt with `validate --rebuild-set` (native reader only; the classifier call per page was the only API use)
on the six forms the patches were diagnosed on. The rebuild moves the old build into the manifest's history only
once the new set is recorded, so a failed rebuild leaves the manifest as it was (learned on Form 5500, below).

The landed code gives exactly the experiment's boxes on all six:

| form | text found, before -> landed | options found, before -> landed | extras |
|---|---|---|---|
| B410 | 31 / 55 -> 43 / 55 | 0 / 33 -> 33 / 33 | 12 -> 12 |
| B106I | 23 / 81 -> 72 / 81 | 0 / 8 -> 7 / 8 | 17 -> 18 |
| LA 7006 | 92 / 92 | 0 / 68 -> 68 / 68 | 35 -> 35 |
| TX RRC R-32 | 78 / 78 | 12 / 78 -> 78 / 78 | 30 -> 30 |
| KS DO-41 | 97 / 117 | 0 / 19 -> 19 / 19 | 17 -> 22 |
| KS DO-10 | 56 / 56 | 0 / 8 -> 8 / 8 | 4 -> 4 |

What that did to the case chain on the same six forms (set 1 rebuilt, side-copy blueprints as they stand):

| form | fields | box stage, before -> after | class stage | value stage |
|---|---|---|---|---|
| B410 | 75 | 45 -> 14 | 1 -> 2 | 29 -> 59 |
| B106I | 81 | 60 -> 8 | 4 -> 44 | 17 -> 29 |
| LA 7006 | 160 | 68 -> 2 | 0 -> 78 | 92 -> 80 |
| TX RRC R-32 | 156 | 66 -> 2 | 24 -> 24 | 66 -> 130 |
| KS DO-41 | 136 | 44 -> 30 | 16 -> 22 | 76 -> 84 |
| KS DO-10 | 62 | 6 -> 0 | 0 -> 1 | 56 -> 61 |
| six forms | 670 | 289 -> 56 | 45 -> 171 | 336 -> 443 |

**The box stage is no longer the bottleneck on these forms; the classifier is, on two of them.** 233 fields left
the box stage; 107 reached the value stage and 126 stopped at the class stage, almost all on LA 7006 (78) and B106I
(40). On 7006 the newly found checkboxes sit in dense lists and the classifier captions them one row off (the box
beside "Audit - Natural Gas Franchise" gets "Audit - Motor Vehicle Sales"), which the chain catches: those fields
now send no class, regex or judge flag, and a rename on one would be contested. The agentic repair is the one
already built for renames (a crop with the box outlined, a model that reads it); whether the classifier gets a
caption pass of that kind, or a prompt version, is the next decision. R-32 and B410 converted cleanly.

**Not done, by design or by accident.** The other eight forms whose boxes change under `step2flat-3` (OCC 1014cs
and 1022a, Form 5500, LIC100, LA 16019 and 1048, HK IRD) stay on `step2flat-2` until someone addresses them; a
first loop over the thirteen was stopped after the point was made, by which time OCC 1014cs had been rebuilt (its
old build is in its manifest's history) and Form 5500's rebuild had failed on a classifier parse error (Sonnet 4.6
returned a stray brace on page 3; `classify_form` does not retry); its manifest was restored. The 31 forms whose
boxes do not change are not touched at all: if one is validated later, `_check_set` compares that one blank's boxes
with the old cached list, migrates the set and its class map when identical, and otherwise refuses. That migration
path is written and its cache-key mirror checked, but it has not yet run on a real form.

### The class stage tests the class, not the caption (2026-10-01, late; `field_chain.py`)

Andrew: a naming problem should not become a class problem; a checkbox is a checkbox. Of LA 7006's 78 class-stage
fields after the rebuild, 54 were checkboxes the classifier classed `option` and 24 text; B106I's 44 were 43 amount
cells classed `money`. The chain had been holding a field whenever the classifier's caption was not the text at the
widget, on the theory that a wrong caption means a wrong class and a wrong value. For a checkbox the caption plays
no part in the case (the class comes from the shape, the value is a mark), and row 5a's caption on row 5b's amount
cell still gives `money`. The rule is now: a misattributed caption holds the field only when the class it produced
disagrees with the blueprint's type (the run's `class_disagreements.json`), because then nothing downstream can
tell whether the blueprint or the caption is wrong. When the classes agree the signals flow; the caption stays
unverified for the reviewer, which withholds it, and a rename on the field is still contested.

The three cases the chain was built on are still held: LIC100's state box captioned "B16. Name" (classed as a
name against a code), SS-4's header box captioned with line 1 (a business name against an EIN), WC-122's time box
captioned DATE OF INJURY (a date against a string). On the six rebuilt forms:

| six forms, 670 fields | box stage | class stage | value stage |
|---|---|---|---|
| before step2flat-3 | 289 | 45 | 336 |
| after the rebuild | 56 | 171 | 443 |
| with the class-stage rule | 56 | 32 | 582 |

LA 7006 keeps 27 at the class stage and B106I 1; those are the fields where the misattributed caption did change
the class, and the caption pass (TODO) is for them.

### Batch 3: twenty new forms through the whole pipeline, and LA 7006 re-run (2026-10-01, evening; `eval/loop_compare.py`, `eval/judge_informativeness.py --forms`)

Twenty forms new to the loop (`runs/judge_eval/batch20c.txt`: unused AcroForm blanks with at least fifteen text
widgets, one option box and at most eight pages, at most two per vertical, eighteen verticals), through label
(Sonnet 4.6), validate (bank set 1 under `step2flat-3`), and `iterate --review flagged --apply-correct` with the
judge, the reviewer (Opus 5) and the adjudicator (Sonnet 4.6). Plus LA 7006 re-run from its pre-loop blueprint.
Andrew's scope was these plus SS-4; 31 further re-runs of the earlier batches went through before the scope was
narrowed (their loop-2 results are in `<form>_loop2.json`; summarised at the end).

| 20 new forms | |
|---|---|
| fields | 2,034 |
| judge disagreements: layout / format / implausible / unexplained | 654: 413 / 143 / 62 / 36 |
| name-vs-caption screen candidates (judged) | 36 (20) |
| edits kept: on judge flags / on other flags | 31 / 106 |
| renames proposed | 12; adjudicated: proposed 7, current 3, unclear 2, settled 5 |
| reviewer + adjudicator cost | $1.87 (labeler, classifier and judge calls not logged here) |
| chain: box / class / value stage | 511 / 100 / 1,423 (box stage 25%; 11% without A-1 and EP-5, below) |

**The adjudicator in the wild.** Twelve renames on forms it had never seen. It upheld seven that read right on the
crop (two checkbox fields named for their option, a lodging-or-tips description, a tax-years box, a lease-and-field
column). It stopped three as `current`: the identity-theft affidavit's `taxpayer_current_mailing_address` proposed
as `taxpayer_first_nm` (the box holds the mailing address), and two P-17 renames from `rrc_identifier_row_42` to
`rrc_identifier_row42`, style-only changes the reviewer's own prompt forbids; the adjudicator does not police
style, it asked what the box holds and found the current name already said so. It answered `unclear` on two P-17
`well_no` renames that turned on a row index, which keeps the name and flags the field. One upheld rename is a
suffix-only change (`ou_manager` -> `ou_manager_nm`): the adjudicator judges the kind of value, as asked, so a
cosmetic rename that does not change the kind passes it; that remains the reviewer's rule to keep.

**Box stage on the new forms is two forms.** 320 of the 511 box-stage fields are Alabama A-1 (247 of 247) and TX
RRC EP-5 (73 of 74). A-1 is a dynamic XFA form: its page content is the "open this in Adobe Reader" notice, the
form exists only in the XFA template, and the finder correctly finds nothing to fill (26 boxes, all `none`). It
should never have been in the pick; the corpus probe needs an exclusion for XFA-only pages. EP-5 is an underline
form whose text widgets sit off the printed underscore runs: 106 finder boxes, 79 widgets, 41 case boxes with no
widget under them, 77 fields no box reached. A yardstick family (widget above the line it belongs to), not
diagnosed to a fix. The other eighteen forms: 191 box-stage fields of 1,713. P-17 (418 fields, a two-page table)
carries 68 of the 100 class-stage fields.

**LA 7006, re-run from v0 under step2flat-3:** detected 150 -> 80 over the loop (loop 1 was 114 -> 33 with 68
option widgets never reached), 36 reviewed fields kept, 3 restored, no renames.

**The 31 incidental re-runs** (not asked for; the forms from batches 1 and 2 other than 7006 and SS-4, from their
v0 blueprints): 24 renames against 26 in loop 1, but now adjudicated: 23 upheld, 2 stopped; restores 6 against 15.
TX DMV 1756's fifteen `control` fields became the Year/Make column (loop 1 had passed all fifteen as ok) and KS
DO-10's five publisher misplacements were renamed to their cells' captions and upheld. $2.28 reviewer + adjudicator.
