"""Repository layout, in one place.

Every module that needs a directory imports it from here instead of
computing it from its own ``__file__``. ``PETEY_SENSIBLE_DIR`` overrides
the Sensible config library location (it is an external MIT repo, not
vendored).
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

BLUEPRINTS = REPO / "blueprints"            # v1.1 blueprints (geometry + semantic types)
SOURCE_PDFS = REPO / "source_pdfs"          # blank forms, gitignored
RUNS = REPO / "runs"                        # validation runs, caches, logs; gitignored
MODELS = REPO / "models"                    # local models (MiniLM ONNX); gitignored
CANONICAL_LOOKUPS = REPO / "canonical_lookups"
SENSIBLE_DIR = Path(os.environ.get(
    "PETEY_SENSIBLE_DIR",
    str(REPO / "sensible-configuration-library")))
