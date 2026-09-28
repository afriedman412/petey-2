"""Geometry for a flat form (no AcroForm layer) from step2flat.

Emits the same widget record `petey.locate.acroform.enumerate_widgets`
emits, so everything downstream — labeling, the emitter, extraction — is
indifferent to where the geometry came from. Per BPT spec §5.9.1 the
`path` is None: there is no form layer to bind to, and the rect is an
estimate, so the confidence and the rule that produced it ride along
under `x_petey_` keys.

Reading order (page, then top-to-bottom, left-to-right) gives stable ids.
"""
from __future__ import annotations

import sys
from pathlib import Path

from petey.paths import REPO

KIND_TO_WIDGET = {"text": "text", "checkbox": "checkbox", "radio": "checkbox", "comb": "text"}


def enumerate_fields(pdf_path: Path, keep_all: bool = False) -> tuple[list[dict], list[dict]]:
    """Return `(widgets, dropped)`; `dropped` holds sub-threshold candidates when `keep_all`."""
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    from step2flat import pipeline  # frozen reader + lattice + programmatic confidence

    kept, scored = pipeline.run(str(pdf_path))
    rows = sorted(kept, key=lambda r: (r["page"], round(r["rect"][1] / 4), r["rect"][0]))
    widgets = []
    for i, r in enumerate(rows):
        widgets.append({
            "id": i,
            "page": int(r["page"]) + 1,  # step2flat is 0-based; widget records are 1-based
            "rect": [float(x) for x in r["rect"]],
            "widget_type": KIND_TO_WIDGET.get(r["kind"], "text"),
            "path": None,
            "confidence": round(float(r["conf"]), 3),
            "geometry_source": r["src"],
            "geometry_why": r.get("why"),
        })
    dropped = []
    if keep_all:
        kid = {id(r) for r in kept}
        for r in scored:
            if id(r) in kid:
                continue
            dropped.append({"page": int(r["page"]) + 1, "rect": [float(x) for x in r["rect"]], "widget_type": KIND_TO_WIDGET.get(r["kind"], "text"),
                            "reason": "below_threshold", "confidence": round(float(r["conf"]), 3), "geometry_source": r["src"]})
    return widgets, dropped
