# Error taxonomy (what fails, why, and which rule addresses it)

| category | example forms | mechanism | status |
|---|---|---|---|
| open table edges | 1065, 1120-S, P-5, T1 | last column has no closing rule | lattice closure (fixed) |
| closure through labels | 1040, SA100 | virtual lines split label cells | long rules only, never through text (fixed) |
| character boxes | KS2, SA100, PA-40, MA, VA 760, IT-201 | each box returned separately | grouping (fixed) |
| white boxes on tint | KS2, DS-11, SA100 | white fill ignored as paper | contrast cells (fixed) |
| slivers | many | non-writable cells | size limits (fixed) |
| typed underscores / dot leaders | CA24, P-4 | counted as text | treated as line cues (fixed) |
| underline outliers | CA24, fresh forms | underline tier too low | outside-lattice bonus (fixed) |
| checkbox erased with its label | URLA, MCS-150, IL-1040 | OCR word box engulfs box | v8 box guard (candidate, not in pipeline) |
| box extent | 855A/B | interior reported, widget = outer edge | open |
| faint strokes | PA-40 | edges straddle ink threshold | open (ink knob) |
| dropout ink | MA Form 1, VA 760, GA-500 | light colour above ink threshold | partly (contrast cells, vector path) |
| zebra vs blocked gray | UB-04 vs 1065 | same gray, different role | zebra detector (runs >= 3 bands) |
| raster pages | CMS-1500 | lattice is vector-only | open (raster lattice prototype exists) |
| cents boxes | IT-201 | ".00" box read as checkbox | open, looks form-specific |
| row extent | 8949 | full cell vs lower band | convention question |
| no printed cue | GA-500 | nothing to see | out of scope |
| non-form pages / covered lines | SA100 p1 | illustration geometry, lines under white shapes | open |
