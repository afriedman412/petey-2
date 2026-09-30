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
