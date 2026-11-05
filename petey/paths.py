"""Repository layout, in one place.

Every module that needs a directory imports it from here instead of
computing it from its own ``__file__``. The dataset's directories (blueprints, runs, source_pdfs) come from
``petey_dataset``, so they follow ``PETEY_DATASET`` when the dataset lives outside the repo. ``PETEY_SENSIBLE_DIR`` overrides
the Sensible config library location (it is an external MIT repo, not
vendored).
"""
from __future__ import annotations

import os
from pathlib import Path

from petey_dataset import BLUEPRINTS, RUNS, SOURCE_PDFS  # noqa: F401  (the dataset: PETEY_DATASET, else the repo)
import petey_dataset

REPO = Path(__file__).resolve().parents[1]

MODELS = REPO / "models"                    # local models (MiniLM ONNX); gitignored
CANONICAL_LOOKUPS = petey_dataset.ROOT / "canonical_lookups"
SENSIBLE_DIR = Path(os.environ.get(
    "PETEY_SENSIBLE_DIR",
    str(REPO / "sensible-configuration-library")))
