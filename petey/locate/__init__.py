"""WHERE a field is. Two sources, one record.

`enumerate_geometry(pdf)` returns `(widgets, dropped, method)`: the
document's own AcroForm widgets if it has a form layer, else step2flat's
estimate. Both emit `{id, page, rect, widget_type, path, ...}`;
programmatic records carry `path: None` plus a confidence.

`sibling` (borrow a registered fillable twin's rects) is opt-in only: the
dev corpus happens to hold print/fillable pairs, production sees one PDF.
"""
from __future__ import annotations

from pathlib import Path


def enumerate_geometry(pdf_path: Path, method: str = "auto") -> tuple[list[dict], list[dict], str]:
    from petey.locate import acroform, programmatic, sibling
    if method in ("auto", "acroform"):
        widgets, dropped = acroform.enumerate_widgets(pdf_path)
        if widgets or method == "acroform":
            return widgets, dropped, "acroform"
    if method == "sibling":
        widgets, dropped, twin = sibling.enumerate_fields(pdf_path)
        return widgets, dropped, f"sibling:{twin.name}" if twin else "sibling"
    widgets, dropped = programmatic.enumerate_fields(pdf_path)
    return widgets, dropped, "step2flat"
