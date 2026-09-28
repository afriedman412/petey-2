"""WHERE a field is. Two sources, one record.

`enumerate_geometry(pdf)` returns `(widgets, dropped, method)`, trying in
order: the document's own AcroForm widgets; a registered fillable twin of
the same form with a matching layout (`sibling`, exact rects for free);
step2flat's estimate for a flat form. All emit `{id, page, rect,
widget_type, path, ...}`; programmatic records carry `path: None` plus a
confidence.
"""
from __future__ import annotations

from pathlib import Path


def enumerate_geometry(pdf_path: Path, method: str = "auto") -> tuple[list[dict], list[dict], str]:
    from petey.locate import acroform, programmatic, sibling
    if method in ("auto", "acroform"):
        widgets, dropped = acroform.enumerate_widgets(pdf_path)
        if widgets or method == "acroform":
            return widgets, dropped, "acroform"
    if method in ("auto", "sibling"):
        widgets, dropped, twin = sibling.enumerate_fields(pdf_path)
        if widgets or method == "sibling":
            return widgets, dropped, f"sibling:{twin.name}" if twin else "sibling"
    widgets, dropped = programmatic.enumerate_fields(pdf_path)
    return widgets, dropped, "step2flat"
