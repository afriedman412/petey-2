# Strategy v1 — building and validating blueprints across the three routes

Draft 2026-09-28. Task 3 of PLAN.md. Structure and integration only; optimization and the error taxonomy come later.
Everything here is built on what already runs (`docs/PORT_PLAN_v2.md`) plus identity (`petey/identify.py`, registry)
and geometry (`petey/locate/`).

## 1. Premise: the routes are stage sources, not pipelines

The three routes don't produce comparable objects, so "compare three blueprints" is the wrong integration. They
contribute to different **stages** of one construction:

| stage | programmatic | metadata (AcroForm / XFA) | VLM / LLM |
|---|---|---|---|
| identify | rules on the printed page (done) | /Info title, XFA root | — |
| locate (entry rects) | step2flat, with confidence | exact widget rects | measured unusable for rects |
| bind (anchor ↔ rect) | geometry | the path IS the binding | — |
| name | caption slug (floor) | XFA names, /TU tooltips, readable paths | normalize captions to canonical vocab (dev tool, later local) |
| type / pattern | widget shape | XFA `<validate>`, widget type | — |
| validate | anchored synthetic loop | anchored synthetic loop | auditor reading the filled image |

Agreement is therefore **per field, per stage**, between sources that don't share an input.

## 2. The object

A blueprint field is `(anchor, rect, name, type)` with evidence:

- **anchor** — the printed caption, with its own rect. Every field carries one, whatever named it. Canonical
  vocabularies bind to captions (MeF XSL carries the rendered form-box label; Sensible anchors are captions); a
  fillable and a print edition of the same form share captions but not paths; and a human or a VLM reading a
  filled page sees captions, not paths. It is the join key that survives every source.
- **rect** — from `petey.locate`: AcroForm (exact, `path` set) or step2flat (estimate, `path: null`,
  `x_petey_geometry.confidence`).
- **name** — from ranked evidence, most canonical first (§3.4). `label_source` records which.
- **type / pattern / semantic_type** — from `semantic_types` given the name, overridden by XFA `<validate>`
  where present.

This is BPT v1.1 plus `anchor` and evidence keys under `x_petey_`; no spec change needed to start.

## 3. Stages, sources, trust order

### 3.1 Identify — done
`petey.identify` → registry (`identities`, `aliases`, `external_refs`). Every later lookup goes through
`petey.registry_lookup`, never a filename.

### 3.2 Locate
`acroform → step2flat` (`sibling` opt-in). Open: raster pages (scans) need OCR before step2flat's vector lattice
applies; HISTORY.md's raster-lattice prototype covered 79% and isn't wired.

### 3.3 Bind — anchor to rect
- Fillable: the path binds value to widget; the anchor is found geometrically for the field's sake (§2), and
  `/TU` often *is* the anchor text.
- Flat: geometric rules (label left on the same row, label above with horizontal overlap, dropout caption
  inside) with a confidence. **Measured 2026-09-28** (`eval/caption_binding.py`, 26,216 widgets in 150
  committed blueprints): a caption is within reach for **57%** of widgets, and of those only **34%** share
  meaningful tokens with the committed name (21% at a strict bar) — **~19% of all widgets** get a plausible
  name from the nearest caption alone. Coverage is bimodal: the 1099 family 80–88%, dense tax forms and tables
  0–8% (`f1040sb` 0%, `f5500ez` 8%, `rrc_h_12` 7%). This agrees with the 2026-07 pinwheel result. **The
  nearest caption is not a name source.** What it can still do: be *searched for* — when a canonical label is
  known (MeF XSL carries the rendered form-box text for 173 forms; tooltips for 52% of widgets), finding that
  known string on the page and binding it to the nearest rect is a much easier problem than reading an unknown
  caption, and it is measured next (§5.1).

### 3.4 Name — ranked evidence, canonical first
1. XFA template field names / captions (102 hybrids; parser is new)
2. `/TU` tooltip (publisher-written)
3. Canonical vocabulary via the registry: MeF lookups (173 forms), Sensible ids (21 configs), ExtractBench schemas
   for evaluation only (never for generation, per the 2026-09-21 decision)
4. Publisher AcroForm path, when readable (`name_sources.is_readable`; positional names like `f1_01[0]` are not)
5. Caption slug — deterministic but weak (§3.3: ~19% of widgets); on flat forms it is the only model-free
   evidence, so a flat form without XFA or a canonical vocabulary needs 6.
6. LLM / VLM naming from the page — dev tool now, the local-model slot later; on flat forms this is where most
   names will come from until 5 improves. Every such name carries `label_source: llm` and `needs_review` unless a
   second source agrees.

Two sources agreeing (e.g. tooltip and caption, or XFA and MeF) → accept; one source → accept with
`needs_review`; conflict → review. "Independent" means different inputs: tooltip vs caption are independent,
LLM-from-tooltip vs tooltip are not.

### 3.5 Type
XFA `<validate>` / widget type → `semantic_types` from the name → widget shape (checkbox-sized square = boolean).

### 3.6 Validate — the loop, anchored
Existing: generate (multimodal LLM, keyed by AcroForm path) → fill (AcroForm) → extract (offline) → score by path.
It tests extraction mechanics, not blueprint correctness: generator and extractor share the key, so a wrong name
cancels (`EVAL_STATE.md`). On flat forms it is worse — the draft's own rect decides where the value is painted.

Change the key. Ground truth becomes `{anchor: value}` — "the box labeled *Employer identification number*
holds 12-3456789". Then:
- **fill** places the value by the blueprint's rect (AcroForm or painted onto the flat page — the flat renderer
  is new);
- **extract** returns `{name: value}` by geometry (exists);
- **score** joins on the anchor: does the field bound to this caption return this value? A misbinding now fails
  instead of cancelling, with no second arm and no model call — the 2026-09-23 note's "highest-value change",
  generalized.
- **referees** (independent of the geometry path): canonical names where they exist; XFA; the VLM/LLM reading
  the *filled image* and answering "what is in the box labeled X" (dev tool now, the local-VLM slot later); the
  23 flat/fillable twins for geometry (`eval/twins.py`).

Value generation itself needs no model: `semantic_types` already pairs every type with a pattern-compliant
generator; the multimodal generator stays as a referee, not the source.

### 3.7 Promote — registry lifecycle
`planned → located → named → validated → active`, one field-level `needs_review` list, two human gates (label
review; score-anomaly triage). The registry already tracks forms and artifacts; the states are new columns.

## 4. What exists, what is new

| piece | status |
|---|---|
| identify, registry, resolver | done |
| locate: acroform, step2flat, sibling (opt-in) | done |
| labeler, emitter, dedup, semantic types | ported |
| offline extractor, scorer, S1/S2 detectors, taxonomy | ported |
| canonical-label search on the page (known label text → nearest rect) | **new**; measured first (§5.1) |
| open caption → name (nearest caption) | measured: ~19% of widgets; not a name source, kept only as anchor evidence |
| XFA template parser (names, captions, validate) | **new** |
| name ranking wrapper over existing sources | **new**, small |
| anchored ground truth + scorer join on anchor | **new**, small change to `score.py` |
| flat-page fill (paint values into rects) | **new**, ~100 lines with pymupdf |
| lifecycle states + review list | **new**, registry columns |
| VLM per-stage evaluation (task 2) | **new**: score the frontier VLM per stage against AcroForm truth; each stage gets a number a local model must beat |

## 5. Build order (each a PR from dev, each with an API-free check)
1. Canonical-label search: for the 173 MeF forms and the 52% of widgets with tooltips, find the known label text
   on the page and bind it to the nearest rect; score against the committed widget. If this is high, flat forms
   with a canonical vocabulary can be named without a model; the 57% caption-reachability figure is the ceiling
   to beat. → number in RESULTS.md.
2. Name ranking wrapper (tooltip → canonical → path → caption); `label_source` on every field. Check: re-emit
   the 153 blueprints with `--no-llm` and report how many names are recoverable without a model.
3. XFA parser → fold into 2. Check: the 102 hybrids, names vs tooltips.
4. Anchored ground truth + scorer join; flat fill. Check: the f1040 run reproduces; one flat twin runs end to end.
5. Lifecycle states + review list in the registry. Check: lint.
6. VLM per-stage eval on 20 fillable forms (needs an API key; ~$1).

## 6. Open, in order of consequence
- Flat forms without XFA or a canonical vocabulary: no model-free naming path exists today (§3.3). Either the
  known-label search generalizes, or naming on those forms stays a model step — which makes the local-VLM naming
  question (Liquid experiment, untested branch) the one that matters.
- step2flat's own label features (`lab_left`, caption fields from the frozen reader) were not used in the
  measurement; they may bind better than the quick rule.
- Raster pages: OCR → step2flat.
- Retrieval measured with a real vocabulary (tooltips, XFA, canonical), now that the registry join works.
- The bottom six of the twin evaluation (`p-6p`, `form-p5`, `ps-79p`, `p_15`, `IA1`, `h-12p`).
