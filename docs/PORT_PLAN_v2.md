# Port plan v2 — changes from v1 after review (2026-09-28)

Supersedes [PORT_PLAN_v1.md](PORT_PLAN_v1.md); only the deltas are here. The layout, slice order and "left behind"
list stand unless amended below.

## Decisions taken
- **`petey/` is the successor of the `petey` package (0.5.1), not a new package.** Same import name, next major.
  PyPI and every other deployment concern are deferred; nothing in the port is shaped by packaging.
- **`tesserocr` is not installed until a flat-scan case needs tier 3.** `extract.py` already degrades cleanly
  (`_TESSEROCR_OK = False`). The tesseract binary is on the machine (5.5.3) when the time comes.
- **v1.0 blueprints are vestigial and are not ported.** They stay at `petey-master/blueprints/` and are referenced in
  place if a description or field list is ever wanted. Consequences:
  - Slice 2 is now: `registry/` + the **v1.1** blueprints (`widget-mapper/blueprints`, 148, plus `blueprints_rrc`, 5)
    + `canonical_lookups/`. The registry's `lint` is re-pointed at the v1.1 directory, and its `source_pdfs` rows are
    re-pointed **by sha256** to the new corpus (all 481 old files are in it by content; 161 are net-new).
  - The "prose merger" is dropped from the plan. Prose only matters to the dev-tool LLM arm, which can read a v1.0 file
    in place when it wants one.

## Added scope: XFA on the metadata route
Measured on the corpus: **102 of 646 PDFs carry XFA** — 101 hybrids that also have AcroForm widgets, 1 pure XFA.
Of the remaining 544: 391 plain AcroForm with widgets, 32 with an AcroForm dictionary but no widgets, 119 with no form
layer, 1 unreadable, 1 erroring on catalog read.

- **Geometry** for the 101 hybrids is already free from the AcroForm widgets; nothing changes in `locate/`.
- **Naming**: new `name/xfa.py` parses the XFA template packet (`/AcroForm/XFA`) for field names, captions, data
  types and `<validate>` rules. This is model-free and, where it exists, likely stronger than `/TU` tooltips. The old
  repo has no template parser; it has only path heuristics in `name_sources.py` (strip `[n]` indices; spelled-out
  numbers are positions, not meanings), which come over with it. Lands with slice 4.
- **Values**: on a filled hybrid, the value may live in the XFA datasets packet rather than `/V`. Slice 5's
  verification adds one XFA-hybrid case to check that tier 1 of `extract.py` doesn't read an empty `/V` as absent.
- The single pure-XFA form (no widgets) is out of scope until there is more than one.

## The two local models (what they are, so this doesn't get re-asked)
Both live at `petey-master/widget-mapper/models/` (105M), gitignored there and here (`models/`, `*.onnx`), tracked out
of band. Both are torch-free and run under `onnxruntime` with CoreML on M-series.
- **`widget_v1.onnx`** (12M): YOLOv8n field detector, 6 classes (text / checkbox / radio / label / signature /
  combobox), trained 2026-07-14 on ~14K tiles. A local **geometry** source for flat forms — slice 3. Must be run
  tiled (`detect_pdf_page_tiled`, dpi 250, tile 512, overlap 128); whole-page inference shrinks checkboxes to ~10px
  and looks broken. Recall 50–80% on filled-rect forms, ~0 on stroked-outline forms. It is the fourth geometry source
  next to AcroForm, step2flat and the VLM, and the only learned one.
- **`minilm/`** (91M): `all-MiniLM-L6-v2` sentence embedder exported to ONNX, with its tokenizer. Used by `retrieve.py`
  to embed nearby printed text and the vocab (Sensible configs + existing slugs), then cosine + Hungarian assignment
  to pair labels with widgets. A local **naming** source — the retrieval prepass in `auto_label.py` that names a widget
  without a model call when cosine ≥ 0.85. Slice 4. Same embedder backs the eval scorer's similarity comparisons.
