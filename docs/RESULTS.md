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
