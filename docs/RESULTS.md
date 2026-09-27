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
