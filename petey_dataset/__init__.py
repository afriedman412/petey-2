"""The dataset: where the blueprints, the blanks and the review records are, and how to read them.

The one piece of code shared by everything that reads the dataset: the petey package (its pipeline writes blueprints
into sections and reads working copies and verdicts), the review page, and the benchmark runner (the key builder and
the scorer, which must run without the petey package: they judge any method's predictions, not only petey's). It
imports nothing from petey.

The root is the directory holding `blueprints/`, `runs/` and `source_pdfs/`: `PETEY_DATASET` in the environment,
else the directory this package sits in (the repo). The layout under it is unchanged from the single repo:

    blueprints/                     the library (lib__ on the review page)
    runs/<section>/blueprints/      the other sections (judge_eval, flat, benchmark, manual_grabs, finance, ...)
    runs/drafts/<id>/               a form's working copy while the review page has it open
    runs/hand_review/<id>.json      a form's verdicts and its structure stamp
    runs/hand_review/ignored_forms.json, runs/benchmark/ignored_pages.json, ignored_fields.json
    runs/benchmark/{key, dev_key, picks.json, domains.json, field_types.json, printed/candidates.json}
    source_pdfs/                    the blanks (mirrored to S3, not in git)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(os.environ.get("PETEY_DATASET") or Path(__file__).resolve().parents[1])

BLUEPRINTS = ROOT / "blueprints"
RUNS = ROOT / "runs"
SOURCE_PDFS = ROOT / "source_pdfs"
HAND_REVIEW = RUNS / "hand_review"
DRAFTS = RUNS / "drafts"
BENCHMARK = RUNS / "benchmark"
KEY = BENCHMARK / "key"
DEV_KEY = BENCHMARK / "dev_key"
PICKS = BENCHMARK / "picks.json"

from petey_dataset import split_types  # noqa: E402,F401
from petey_dataset.blueprints import (  # noqa: E402,F401
    FIELD_TYPES, PRINTED_CANDIDATES, PRINTED_TAG, SOURCES, blueprint_paths, is_printed, is_text, launch_tiers, load, page_sizes, printed_record, resolve_blank,
    reviewable, sha, split_values, stale, warm_parsed, widgets, working, working_path)
from petey_dataset.verdicts import (  # noqa: E402,F401
    FORM_NOTES, LOCK, checked, form_notes, load_verdicts, set_form_note, new_to_check, reset_verdicts, stamp_structure, structure, structure_ok,
    unstamp_structure, verdict_path, write_verdicts)
