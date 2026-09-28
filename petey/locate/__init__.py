"""WHERE a field is. Two sources, one record.

`enumerate_geometry(pdf)` returns `(widgets, dropped, method)`: AcroForm
widgets when the document has a form layer, otherwise step2flat's fields
for a flat form. Both emit `{id, page, rect, widget_type, path, ...}`;
programmatic records carry `path: None` plus a confidence.
"""
from __future__ import annotations

from pathlib import Path


def enumerate_geometry(pdf_path: Path, method: str = "auto") -> tuple[list[dict], list[dict], str]:
    from petey.locate import acroform, programmatic
    if method in ("auto", "acroform"):
        widgets, dropped = acroform.enumerate_widgets(pdf_path)
        if widgets or method == "acroform":
            return widgets, dropped, "acroform"
    widgets, dropped = programmatic.enumerate_fields(pdf_path)
    return widgets, dropped, "step2flat"
