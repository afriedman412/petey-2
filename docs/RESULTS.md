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
