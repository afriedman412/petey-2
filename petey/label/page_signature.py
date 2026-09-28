"""Page-similarity matching for copy-page detection.

Multi-copy tax forms (1099-R, W-2G, 1098-*, etc.) render the same form
multiple times on separate pages. Sometimes those copies are pixel-
identical; sometimes they differ by one or two widgets (e.g., 1099-R
Copy A has a VOID checkbox that other copies omit).

We treat pages as "the same form" if their widget-geometry signatures
overlap above a threshold (default 0.85, Jaccard similarity). This is
looser than exact match but tighter than "any overlap."

Similarity rule:
  sig(page) = set of (rect_x, rect_y, width, height, widget_type) tuples
  jaccard(a, b) = |sig(a) ∩ sig(b)| / |sig(a) ∪ sig(b)|
  if jaccard(a, b) >= threshold → same canonical form

The earliest page in a similarity cluster is the canonical page; later
pages' widgets are dropped. Widgets on later pages that DIDN'T appear
on the canonical page (the "difference set") are also dropped, on the
assumption they're minor variations rather than distinct fields.

Only handles CROSS-PAGE copies. Same-page multi-copy layouts (W-2's
Copy A + D on page 1) need within-page geometric clustering.
"""
from __future__ import annotations

from collections import defaultdict

DEFAULT_THRESHOLD = 0.85


def _widget_sig(w: dict, precision: float = 1.0) -> tuple:
    """Return a geometry signature for one widget."""
    rect = w.get("rect", [0, 0, 0, 0])
    x0, y0, x1, y1 = rect
    return (
        round(x0 / precision) * precision,
        round(y0 / precision) * precision,
        round((x1 - x0) / precision) * precision,
        round((y1 - y0) / precision) * precision,
        w.get("widget_type") or w.get("type", "text"),
    )


def _page_sig_set(widgets_on_page: list[dict]) -> set[tuple]:
    return {_widget_sig(w) for w in widgets_on_page}


def _jaccard(a: set[tuple], b: set[tuple]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def canonical_page_map(
    widgets: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[int, int]:
    """Return `{page_num: canonical_page_num}`.

    Pages are grouped by fuzzy geometric similarity (Jaccard on
    widget-signature sets). The earliest page in a similarity cluster
    is the canonical page; matches use the FIRST canonical page whose
    similarity meets the threshold.
    """
    by_page_widgets: dict[int, list[dict]] = defaultdict(list)
    for w in widgets:
        by_page_widgets[w["page"]].append(w)
    by_page_sigs: dict[int, set[tuple]] = {
        p: _page_sig_set(ws) for p, ws in by_page_widgets.items()
    }

    canonical: dict[int, int] = {}
    canonical_pages: list[int] = []
    for page_num in sorted(by_page_sigs.keys()):
        this_sigs = by_page_sigs[page_num]
        matched = None
        best_sim = 0.0
        for cp in canonical_pages:
            sim = _jaccard(this_sigs, by_page_sigs[cp])
            if sim >= threshold and sim > best_sim:
                matched = cp
                best_sim = sim
        if matched is not None:
            canonical[page_num] = matched
        else:
            canonical[page_num] = page_num
            canonical_pages.append(page_num)
    return canonical


def collapse_copy_pages(
    widgets: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
) -> tuple[list[dict], dict]:
    """Filter widgets to canonical (first-copy) pages.

    Returns `(filtered_widgets, report)` where `report` documents
    which pages were collapsed to which canonical, along with the
    similarity scores.
    """
    page_map = canonical_page_map(widgets, threshold=threshold)
    canonical_pages = {p for p, cp in page_map.items() if p == cp}
    filtered = [w for w in widgets if w["page"] in canonical_pages]

    # Compute similarity scores for the report
    by_page_widgets: dict[int, list[dict]] = defaultdict(list)
    for w in widgets:
        by_page_widgets[w["page"]].append(w)
    by_page_sigs = {
        p: _page_sig_set(ws) for p, ws in by_page_widgets.items()
    }

    dropped_report = {}
    for page_num, cp in page_map.items():
        if page_num == cp:
            continue
        sim = _jaccard(by_page_sigs[page_num], by_page_sigs[cp])
        dropped_report[int(page_num)] = {
            "canonical": int(cp),
            "similarity": round(sim, 3),
        }

    return filtered, {
        "threshold": threshold,
        "canonical_pages": sorted(int(p) for p in canonical_pages),
        "dropped_as_copies": dropped_report,
    }
