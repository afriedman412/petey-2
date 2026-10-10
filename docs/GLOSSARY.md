# Glossary

The words the loop is described in, one meaning each (Andrew, 2026-10-01: codify the terms). Where a term names a
module, the module is given. Older documents use some of these loosely; this page is the reference.

## The document

- **Blank**: the publisher's PDF as downloaded, under `source_pdfs/`. The only input generation is allowed to read.
- **Flat copy**: the blank with its widget appearances baked into the page and the widgets stripped
  (`step2flat.pipeline.flatten`). What the finder reads; what a printed form looks like.
- **Widget**: an AcroForm annotation on the blank: a text box, checkbox, radio button, combo or list. The widget
  layer is read at fill time and at scoring time, never by generation.
- **Path**: a widget's fully qualified AcroForm field name (`topmostSubform[0].Page1[0].f1_1[0]`). A publisher
  fact about the file, not about the page.
- **XFA node**: the template declaration of a widget on a LiveCycle hybrid, kept separate from the path.
- **Caption**: the text printed on the page for a box, what a person filling in the form reads ("C corporation"
  beside a W-9 checkbox). A fact about the page. Not "label": in this project *label* is only the verb of the
  labeler (below), never a word for printed text (2026-10-07).
- **Tooltip**: the publisher's hover text for a widget (`TU`), if any. Often the caption repeated, sometimes junk
  ("undefined", "30. Description_1"). A publisher fact, like the path.
- **Option value** (on-state): the value the PDF stores when a checkbox or radio option is ticked, set by the
  publisher (`2`, `Off` / `On`, or a word like `Married`). What the filler writes; not necessarily the caption:
  publishers copy widgets between questions and keep the old values (N-565's error-type boxes still carry
  Married / Single / Divorced / Widowed).

## The blueprint

- **Blueprint** (`.bpt`, YAML; `BPT SPEC v1.1.md`): the schema that says, for every fillable box on a blank, what
  it holds. The thing under test.
- **Field**: one blueprint entry. **Field name**: its slug (`taxpayer_phone_number`). A field has one `widget`
  (text) or a `widgets` map (an option group: one entry per option, keyed by on-state).
- **Field id** (`x_petey_id`, `petey/validate/field_ids.py`, since 2026-10-07): a fixed identifier, `<page>_<n>`,
  the n-th field on the page in reading order when it was given (`1_25`). It never changes: a rename keeps it, a
  removed field's id is not reused, a field added later takes the next free number on its page. Use it to say which
  field you mean; the review page shows it. Given by the labeler and by every tool that adds fields; not meant to
  agree between blueprints.
- **Verdict** (review page, `runs/hand_review/`; Andrew, 2026-10-07): **accept** = the field is good to go,
  including a correction the person saved (apply writes it into the blueprint); **flag** = "I can't or don't want to
  fix this myself", with a note saying what is wrong, which "review edits" sends to the agent. A removed field is an
  accept with the note `removed`. Measurements count a field as wrong when it is flagged or carries a correction.
- **Field reference**: `<blueprint file stem>_<page>_<n>`, the file name and the field id together
  (`ca_courts_dv_130_1_10`): the way to name one field across forms. Read from the right: the last two parts are
  the id. Clicking "Selected field" on the review page copies it. A stem can exist in more than one place (a library
  blueprint and its side copy under `runs/`); the review page's picker says which one is open.
- **Option group**: one field for a radio group or a set of checkbox kids; each option carries its box, on-state
  and caption.
- **Description**: the blueprint's one-line explanation of a field ("Federal tax classification of the entity"),
  most often copied from the tooltip (`x_petey_description_source: tooltip`), else written by the labeler.
- **Labeler** (`petey/label/auto_label.py`): the model that reads a blank and writes its blueprint: field names,
  types, option groups and their captions. Gemini 3.8 Flash since 2026-10-06.
- **Side copy**: a blueprint kept outside `blueprints/` (under `runs/`) so an experiment never touches the library.
- **Flat blueprint** (`petey/label/flat_label.py`, 2026-10-05): a blueprint for a blank with no form layer. Its
  structure is the class map (finder boxes, the classifier's class, caption and grouping), its names come from a
  second model reading the page's words (the labeler, `claude-opus-5` by default), its types from the names. Every
  widget has `path: null`; `x_petey_geometry` records the finder; `x_petey_page_class` / `x_petey_caption` carry
  the classifier's reading. Side copies under `runs/flat/blueprints/`.
- **Widget key** (`boxes.widget_key`): the key a widget's ground truth is stored under: its AcroForm path, or on a
  flat blueprint `rect:p<page>:<rect>`. The scorer, the rect join and the witness identity all go through it.
- **Build stamp** (`x_petey_build`, `petey/validate/provenance.py`): the finder version, classifier model and
  prompt, generator, case set and run of the blueprint's latest validation. Written by the loop after every run.

## The page side

- **Finder** (`step2flat/`, entry `pipeline.run`; wrapped by `petey/synth/boxes.find_boxes`): the deterministic
  reader that proposes fillable boxes on the flat copy from printed cues alone: lattice cells from drawn rules,
  raster cells, underlines, combs, enclosed small boxes. Output: boxes `{page, rect, kind, conf}`.
- **Finder version** (`boxes.FINDER_VERSION`): `FINDER_LABEL`, bumped by hand when the finder's behaviour is meant
  to change, plus `+code<sha>` when `step2flat/*.py` differs from the sha the label describes and `+env<sha>` when
  pymupdf or tesseract differ from the environment it was read under. Every cache keys on it. Changing it is a
  versioned event: re-run the forms being addressed, not the library. A label bump is its own commit, and the
  commit message is the label's documentation: what changed in the finder and the yardstick before and after.
  From a manifest or a build stamp, `git log -S 'FINDER_LABEL = "<label>"'` finds it.
- **Box** (finder box, case box): one of the finder's rectangles. **Rect key**: `p<page>:<x0>,<y0>,<x1>,<y1>`, the
  identity of a box everywhere downstream.
- **Classifier** (`petey/synth/classify.py`): a vision model that sees the page with the boxes numbered and gives
  each a caption, a class from a closed vocabulary, an entity and, for options, a group. Output: the **class
  map**, cached per blank, finder version, model and prompt version.
- **Bank** (`petey/synth/bank.py`, `bank.yaml`): a store of names, addresses, numbers and shaped values. Given a
  class map and a seed it writes one value per box, one persona per entity. Deterministic; no API.
- **Case**: one set of values for a blank, keyed by rect key, plus the filled PDF they produce. A **bank case** is
  drawn by the bank; a **blind case** by the generator.
- **Case set** (`runs/_gen_cache/sets/<form>_set<N>.json`): a numbered, frozen group of cases for a form, with the
  **case basis** it was drawn on. Set 1 is the standing set.
- **Case basis** (`provenance.case_basis`): `<finder version>|<classifier model>|<classifier prompt>`, everything
  a case's values depend on besides the blank and the case key. Bank cases are cached under it; a set on another
  basis refuses to load unless rebuilt (`validate --rebuild-set`).
- **Generator** (`petey/synth/generate.py`): the frontier vision model that writes case values from the page
  (blind: box numbers only). Dev-time, one cached case per form; the bank is the default.
- **Filler** (`petey/synth/render.py`, `render_case`): puts a case's values into the blank's widgets by rect match.
  The only generation-side step that touches the widget layer. What it actually wrote is the **ground truth**.

## Reading back

- **Run** (`runs/<form>_<timestamp>/`): one validation: the blueprint copy, each case's directory, scores, the
  summary with its build record.
- **Native reader**: extraction through the AcroForm paths the blueprint names, then the text layer clipped to
  the rect, then (a path-less option box, flat blueprints) ink against the blank, then OCR. Cannot see a misnamed
  field.
- **Judge** (`judge:<parser>`, `petey/extract_llm.py`): the reader that looks for each field BY NAME in the page
  text or image, so a wrong name produces a wrong value. A dev-time instrument, metered; not product extraction.
- **Reviewer** (`petey/validate/review.py`): the model that receives flagged fields with their evidence and
  returns `ok` or a fix (rename, type, pattern, description). Its edits are applied and then judged by the next
  validation (`iterate.judge_review`).
- **Adjudicator** (`petey/validate/adjudicate.py`): the vision model that decides a contested rename from a crop
  of the blank with the widget outlined: `current` / `proposed` / `unclear`. Independent of the classifier.
- **The loop** (`petey/validate/iterate.py`): validate, detect, fix (rules, then reviewer), validate again; keeps
  a reviewed change only if the next run says it helped.

## Checks and measures

- **Chain** (`petey/validate/field_chain.py`): box -> class -> value, the order a case is built in; a field's
  signals count only from the first link that holds. **Stage**: where a field's chain breaks (`box`, `class`) or
  `value` when it holds.
- **Inventory check** (`petey/validate/inventory_check.py`): the case's boxes against the blueprint's rects, both
  directions: `box_unreached`, `merged_box`, `split_box`, `uncovered_widget`, `unbacked_box`,
  `option_group_mismatch`, `tie`.
- **Class check** (`petey/validate/class_check.py`): the class map's class for a box against the blueprint's type
  for the field on it; tiers 1 (captioned, disagree) to 3 (uncaptioned).
- **Yardstick** (`eval/finder_vs_widgets.py`): the finder against the blank's widget layer, size-aware: `hit`
  (a box within 3x the widget's area), `in_region`, `part`, `miss`; region boxes reported on their own. The
  finder's regression check, one reading per finder version, local and free.
- **Taxonomy** (`petey/validate/defect_taxonomy.py`): the named defect classes a residue is sorted into.
- **Test forms** (`petey/validate/test_forms.py`): the five documents every comparison runs on (tiers `smoke`,
  `core`, `full`). **Development forms**: anything diagnosed on.
- **Hand review** (`petey/validate/hand_review.py`, a local web page): a person judges a blueprint's fields against
  the rendered blank, accept / flag / a note per field; verdicts in `runs/hand_review/<id>.json` with the
  blueprint's sha and build stamp. The check outside the loop that a promotion rests on.
- **Page check** (`petey/validate/page_check.py`, 2026-10-05): a vision model does the first pass of hand review,
  one call per page of the blank, with every field's box outlined and numbered and a list of each number's name,
  type and publisher path. Accepted fields come back as bare numbers; a flag carries a problem (`wrong_name`,
  `wrong_type`, `not_a_field`, `should_group`, `options`, `other`), a proposed name or type and a reason. Records
  in `runs/page_check/`, keyed by a hash of the fields; `x_petey_page_check` on the blueprint is the only change
  it makes. Feeds the `page_check` witness and, through it, the reviewer and adjudicator; never touches hand-review
  verdicts. Scored against hand review by `eval/page_check_fixture.py`.
- **Witness** (`petey/validate/witness.py`): one independent source's verdict on a field, `for` / `against` /
  silent: publisher (tooltip, XFA caption), page (printed text at the widget), classifier (class and caption),
  judge (read back by name), structure (option grouping), adjudicator, page check (accepted / flagged). **Tier**: `contested` (any against),
  `settled` (two or more for, none against), `single`, `unknown`; the hand-review page sorts by it and can accept
  the settled fields in bulk. No API calls.
- **Rival** (`witness.Names.rivals`, 2026-10-09): a field a swap or a one-row slip could involve: same page,
  within an inch of the box, same XFA subform, no heavier-than-usual rule line between. "Belongs to another
  field" only ever names a rival.

- **Belongs to / does not describe**: the two ways a text witness turns against a name. *Belongs to*: the text
  fits a rival clearly better than this field (and better than the rival's own text). *Does not describe*: the
  text-match model gives P < 0.01 that the text describes the name. A text several fields carry word for word
  is never used to flag (it cannot tell them apart).

- **Printed-text gate** (`witness.printed_agrees`, Andrew 2026-10-09): a publisher flag counts (contests the
  field) only when the tooltip shares two thirds of its words with a line printed at the box; otherwise it is
  *unconfirmed*, a hint, and the loop's reviewer never gets it.

- **Text-match model** (`petey/label/text_match.py`): a local cross-encoder (MiniLM-L6, fine-tuned, ONNX) that
  scores whether a text describes a field, 0 to 1. Weights in `models/text_match/` (gitignored);
  `PETEY_TEXT_MATCH=0` turns it off and the witness falls back to word overlap.

- **Caption chooser** (`petey/label/caption_choice.py`): picks an option's printed caption from the text around
  its box with the text-match model; its proposals are review-page suggestions. Never replaces an XFA or hand
  caption.

- **Jev** (TypeSafe System One, API): a calibrated yes/no model used as an independent second opinion
  (`eval/jev_hand_check.py`, `eval/text_match_eval.py`).

- **Flat calibration** (`eval/flat_calibration.py`): the whole flat path run on a form whose truth is known (a
  test form baked flat, or a true flat copy with a fillable twin) and compared with the widget layer (structure)
  and the committed blueprint (meaning): the error rate to attach to real flat forms, where neither exists.

- **Fixture**: a small frozen list of hand-checked facts that does not depend on the cases, rerun when the
  component it tests changes: the widget layer for the finder (the yardstick), hand-verified fields for the
  adjudicator (`eval/adjudicator_test.py`), and the same pattern for the judge and reviewer. The reference that
  survives a code change. There is no held-out set of forms (Andrew, 2026-10-01): the cases are a function of the
  finder and classifier, so a cached reading of such a set is stale the moment either changes, and re-reading it
  on every change is a sweep. A working blueprint is a working blueprint; the loop tests that per form.
