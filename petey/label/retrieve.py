"""Local retrieval-based label-to-widget matching.

Torch-free. Uses onnxruntime + tokenizers to embed text via
all-MiniLM-L6-v2, then cosine-similarity + Hungarian assignment to pair
each expected label with a detected widget.

Usage as a library:
    from petey.label.retrieve import Embedder, match_labels_to_widgets

    emb = Embedder()  # loads MiniLM once (~200ms)
    result = match_labels_to_widgets(
        page,                 # pymupdf.Page
        widgets,              # list[Detection] from detect.py
        expected_labels,      # list[(canonical_id, display_text)]
        embedder=emb,
    )
    # result: {canonical_id -> Detection or None}
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import pymupdf
from tokenizers import Tokenizer

# --- Embedder ---------------------------------------------------------------

from petey.paths import MODELS
MODEL_DIR = MODELS / "minilm"
# MiniLM's positional embedding is 512, but 128 is plenty for
# form-label snippets and keeps embedding fast.
MAX_LEN = 128


class Embedder:
    """all-MiniLM-L6-v2 via ONNX. Torch-free.

    Loads the model + tokenizer once (~200ms). `encode()` accepts a string
    or list of strings; returns (N, 384) L2-normalized embeddings.
    """

    def __init__(self, model_dir: Path | str = MODEL_DIR):
        d = Path(model_dir)
        # imported here, not at module level: onnxruntime's telemetry thread
        # can abort the interpreter at exit (recursive_mutex throw during
        # __cxa_finalize, seen 2026-09-30 on a --no-retrieval labeling run
        # that never used it). Only a run that embeds pays for the import.
        import onnxruntime as ort
        providers = ort.get_available_providers()
        preferred = [p for p in ("CoreMLExecutionProvider",
                                 "CPUExecutionProvider") if p in providers]
        self.session = ort.InferenceSession(
            str(d / "onnx" / "model.onnx"), providers=preferred,
        )
        self.tokenizer = Tokenizer.from_file(str(d / "tokenizer.json"))
        # MiniLM's tokenizer already handles special tokens; we just
        # need to pad/truncate to a fixed length for batching.
        self.tokenizer.enable_truncation(max_length=MAX_LEN)
        # Pad to the longest string in the BATCH, not to MAX_LEN. What this
        # embeds is field labels and single text lines: the longest observed
        # across a real vocab plus a full ACORD-25 page is 30 tokens, so a
        # fixed 128 padded every row four-fold and spent the compute on
        # nothing. Measured at 99 -> 438 texts/s, and the embeddings are
        # bit-identical (min cosine 1.000000 over 256 real strings), because
        # attention_mask already excludes the padding from the mean pool.
        #
        # Truncation stays at MAX_LEN. A fixed pad of ~10 would be faster
        # still and would silently cut the real 30-token lines.
        self.tokenizer.enable_padding()
        self.input_names = {i.name for i in self.session.get_inputs()}

    def encode(self, texts: str | Sequence[str]) -> np.ndarray:
        if isinstance(texts, str):
            texts = [texts]
        texts = [t if t else "." for t in texts]  # tokenizer chokes on ""
        enc = self.tokenizer.encode_batch(list(texts))
        input_ids = np.array([e.ids for e in enc], dtype=np.int64)
        attention_mask = np.array([e.attention_mask for e in enc],
                                  dtype=np.int64)
        feed = {"input_ids": input_ids, "attention_mask": attention_mask}
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.zeros_like(input_ids)
        out = self.session.run(None, feed)[0]   # (N, seq_len, hidden)

        # Mean-pool over tokens with attention mask.
        mask = attention_mask[..., None].astype(np.float32)
        summed = (out * mask).sum(axis=1)
        counts = np.clip(mask.sum(axis=1), 1e-9, None)
        pooled = summed / counts

        # L2-normalize.
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return pooled / np.clip(norms, 1e-12, None)


# --- Nearby-text extraction --------------------------------------------------

# Widget-type -> ordered list of (direction, extent_pt, tolerance_pt).
# LEFT / RIGHT are rect-based (with neighbor-bounding) — good for
# widgets in a horizontal row where the label sits inline.
# ABOVE is handled specially via line-aware extraction (see
# _lines_above_widget) — rect-based ABOVE sweeps through intro
# paragraphs and adjacent form sections.
NEARBY_SEARCH_BOXES = {
    "text":         [("left", 260, 8), ("above", 45, 25)],
    "checkbox":     [("right", 260, 4)],
    "radiobutton":  [("right", 260, 4)],
    "signature":    [("left", 200, 8), ("above", 45, 25)],
    "combobox":     [("left", 260, 8), ("above", 45, 25)],
}


def _search_rect(rect: pymupdf.Rect, direction: str,
                 extent: float, tolerance: float) -> pymupdf.Rect:
    """Compute a search rect in the given direction from `rect`.

    - left: extend `extent` pt leftward, tolerance-tall band across widget y
    - above: extend `extent` pt upward, tolerance-wide band across widget x
    - right: extend `extent` pt rightward
    """
    x0, y0, x1, y1 = rect.x0, rect.y0, rect.x1, rect.y1
    if direction == "left":
        return pymupdf.Rect(max(0, x0 - extent), y0 - tolerance,
                            x0, y1 + tolerance)
    if direction == "right":
        return pymupdf.Rect(x1, y0 - tolerance,
                            x1 + extent, y1 + tolerance)
    if direction == "above":
        return pymupdf.Rect(x0 - tolerance, max(0, y0 - extent),
                            x1 + tolerance, y0)
    raise ValueError(f"unknown direction: {direction}")


_STUB_RE = re.compile(r"^\s*[\d]+[a-z]?\.?\s+")   # "1a.", "5 " etc.


def _distance_in_direction(a: pymupdf.Rect, b: pymupdf.Rect,
                           direction: str) -> float | None:
    """Return the gap between rect a and rect b in `direction`, only if
    b is genuinely in that direction from a (with some overlap on the
    perpendicular axis). Returns None if not in direction."""
    # Perpendicular overlap tolerance for treating two widgets as
    # sharing a row/column. Kept tight (2pt) so widgets in adjacent
    # but distinct rows don't get treated as neighbors and clip each
    # other's label search. Same-row widgets (aligned to grid) are
    # almost always within 1pt.
    perp_tol = 2.0
    if direction == "left":
        if b.x1 > a.x0:
            return None
        if b.y1 < a.y0 - perp_tol or b.y0 > a.y1 + perp_tol:
            return None
        return a.x0 - b.x1
    if direction == "right":
        if b.x0 < a.x1:
            return None
        if b.y1 < a.y0 - perp_tol or b.y0 > a.y1 + perp_tol:
            return None
        return b.x0 - a.x1
    if direction == "above":
        if b.y1 > a.y0:
            return None
        if b.x1 < a.x0 - perp_tol or b.x0 > a.x1 + perp_tol:
            return None
        return a.y0 - b.y1
    return None


_LINES_CACHE: dict[int, list[tuple[pymupdf.Rect, str]]] = {}


def _text_lines(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """Enumerate every text line on the page as (bbox, text) pairs.
    Cached per page id (safe: pymupdf.Page identity is stable for the
    duration of a doc handle)."""
    key = id(page)
    cached = _LINES_CACHE.get(key)
    if cached is not None:
        return cached
    out: list[tuple[pymupdf.Rect, str]] = []
    try:
        td = page.get_text("dict")
    except Exception:
        _LINES_CACHE[key] = out
        return out
    for block in td.get("blocks", []) or []:
        if block.get("type") != 0:      # 0 = text block
            continue
        for line in block.get("lines", []) or []:
            spans = line.get("spans", []) or []
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            bbox = line.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            out.append((pymupdf.Rect(*bbox), text))
    _LINES_CACHE[key] = out
    return out


def _lines_above_widget(
    page: pymupdf.Page,
    widget_rect: pymupdf.Rect,
    max_dist_pt: float,
    h_tol: float,
    y_bound_above: float | None = None,
    max_lines: int = 2,
) -> list[str]:
    """Return the text line(s) closest above the widget with horizontal
    overlap. Optionally returns up to `max_lines` contiguous lines
    (for multi-line labels like 'Business name/disregarded entity
    name, if different from above.').

    `y_bound_above` — if set (from neighbor-bounding), skip any line
    whose top edge is above that y (i.e. inside a nearer widget's row).
    """
    candidates: list[tuple[float, pymupdf.Rect, str]] = []
    wx0, wy0, wx1 = widget_rect.x0, widget_rect.y0, widget_rect.x1
    for lrect, ltext in _text_lines(page):
        # Line must be fully above the widget (bottom edge above or
        # touching widget's top).
        if lrect.y1 > wy0 + 1:
            continue
        # Must have horizontal overlap with widget (with tolerance).
        if lrect.x1 < wx0 - h_tol or lrect.x0 > wx1 + h_tol:
            continue
        # Distance = vertical gap between line's bottom and widget's top.
        d = wy0 - lrect.y1
        if d > max_dist_pt:
            continue
        if y_bound_above is not None and lrect.y0 < y_bound_above:
            continue
        candidates.append((d, lrect, ltext))
    if not candidates:
        return []
    candidates.sort(key=lambda c: c[0])
    # Take the closest line; then walk upward and include additional
    # lines that are contiguous (small vertical gap, similar height).
    _, first_rect, first_text = candidates[0]
    result_lines: list[tuple[pymupdf.Rect, str]] = [(first_rect, first_text)]
    line_h = first_rect.y1 - first_rect.y0
    top_rect = first_rect
    for _, r, t in candidates[1:]:
        if len(result_lines) >= max_lines:
            break
        # Contiguity: this line's bottom is close to previous line's top
        # (typical inter-line gap is < 1.2 × line height).
        gap = top_rect.y0 - r.y1
        if gap < 0 or gap > line_h * 1.2:
            continue
        result_lines.insert(0, (r, t))
        top_rect = r
    return [_STUB_RE.sub("", t).strip() for _, t in result_lines]


def nearby_text_candidates(
    page: pymupdf.Page,
    widget_rect: pymupdf.Rect,
    widget_type: str,
    all_widget_rects: list[pymupdf.Rect] | None = None,
) -> list[str]:
    """Return candidate label texts for a widget from all search
    directions. Empty texts are dropped.

    If `all_widget_rects` is provided, each search extent is bounded
    by the nearest widget in that direction (minus a small buffer),
    which prevents grabbing neighboring widgets' labels on tightly
    packed rows.
    """
    boxes = NEARBY_SEARCH_BOXES.get(widget_type, NEARBY_SEARCH_BOXES["text"])
    out: list[str] = []
    for direction, extent, tol in boxes:
        eff_extent = extent
        y_bound_above: float | None = None
        if all_widget_rects is not None:
            for other in all_widget_rects:
                if other is widget_rect:
                    continue
                d = _distance_in_direction(widget_rect, other, direction)
                if d is None:
                    continue
                capped = max(0.0, d - 4.0)
                if capped < eff_extent:
                    eff_extent = capped
                # For the ABOVE search we also want to know the y
                # coordinate below which the nearest above-neighbor
                # sits — used to clip line-aware search so we don't
                # cross a widget that sits between us and the label.
                if direction == "above":
                    other_bottom = other.y1
                    if (y_bound_above is None
                            or other_bottom > y_bound_above):
                        y_bound_above = other_bottom
        if eff_extent <= 0:
            continue
        if direction == "above":
            # Line-aware — get the nearest text line above (plus
            # optional wrapped continuation).
            lines = _lines_above_widget(
                page, widget_rect, eff_extent, tol,
                y_bound_above=y_bound_above,
            )
            if lines:
                out.append(" ".join(lines))
            continue
        # LEFT / RIGHT — rect-based with neighbor bounding.
        sr = _search_rect(widget_rect, direction, eff_extent, tol)
        txt = page.get_textbox(sr) or ""
        txt = " ".join(txt.split()).strip()
        if txt:
            out.append(_STUB_RE.sub("", txt).strip())
    return out


def nearby_text(page: pymupdf.Page, widget_rect: pymupdf.Rect,
                widget_type: str) -> str:
    """Backwards-compatible single-string variant. Prefer the
    _candidates version in the matcher path so we can pick the
    best-matching direction per label."""
    cands = nearby_text_candidates(page, widget_rect, widget_type)
    return cands[0] if cands else ""


# --- Matching ---------------------------------------------------------------

@dataclass
class Match:
    canonical_id: str
    widget: dict | None       # a Detection dict, or None if unmatched
    display_text: str
    nearby_text: str
    similarity: float


def match_labels_to_widgets(
    page: pymupdf.Page,
    widgets: list[dict],
    expected_labels: list[tuple[str, str | list[str]]],
    *,
    embedder: Embedder,
    min_similarity: float = 0.55,
) -> dict[str, Match]:
    """For each `(canonical_id, display_text)` in expected_labels, return
    the best-matching widget on the page (or None if no match clears
    the threshold).

    `display_text` can be a string OR a list of alias strings — if a
    list, the label's similarity to a widget is the MAX across aliases
    (so acronym + expansion + colloquial form can all be tried).

    Widgets are dicts with at least `cls_name` and `bbox_xyxy` keys —
    matching the Detection TypedDict from detect.py.

    Uses Hungarian assignment for global 1-to-1 pairing so no two
    labels can claim the same widget.
    """
    from scipy.optimize import linear_sum_assignment

    # Normalize labels: each entry becomes (canonical_id, primary_display,
    # list_of_alias_texts).
    normalized = []
    for cid, dtxt in expected_labels:
        if isinstance(dtxt, str):
            aliases = [dtxt]
            primary = dtxt
        else:
            aliases = list(dtxt)
            primary = aliases[0] if aliases else cid
        normalized.append((cid, primary, aliases))

    if not normalized or not widgets:
        return {cid: Match(cid, None, primary, "", 0.0)
                for cid, primary, _ in normalized}

    # For each widget, gather all directional candidates. Embed all,
    # take max similarity per (widget, label) — different labels can
    # prefer different directions (e.g. label above vs left).
    # Bound each widget's search rects by nearest same-direction
    # neighbor so tightly packed rows don't cross-contaminate.
    all_widget_rects = [pymupdf.Rect(*w["bbox_xyxy"]) for w in widgets]
    all_candidates: list[str] = []
    candidate_owner: list[int] = []          # widget index per candidate
    for wi, w in enumerate(widgets):
        rect = all_widget_rects[wi]
        cands = nearby_text_candidates(page, rect, w["cls_name"],
                                       all_widget_rects=all_widget_rects)
        for c in cands:
            all_candidates.append(c)
            candidate_owner.append(wi)

    # Flatten aliases: keep track of which canonical_id each alias
    # belongs to so we can reduce back with max.
    flat_alias_texts: list[str] = []
    flat_alias_owner: list[int] = []                # canonical_id index
    for li, (_, _, aliases) in enumerate(normalized):
        for alias in aliases:
            flat_alias_texts.append(alias)
            flat_alias_owner.append(li)

    label_embs = embedder.encode(flat_alias_texts)               # (A, 384)
    if not all_candidates:
        # No text nearby any widget → nothing to match.
        return {cid: Match(cid, None, primary, "", 0.0)
                for cid, primary, _ in normalized}
    cand_embs = embedder.encode(all_candidates)                  # (C, 384)
    cand_alias_sim = cand_embs @ label_embs.T                    # (C, A)

    # Reduce aliases → canonical labels via max over aliases.
    L = len(normalized)
    cand_sim = np.full((cand_alias_sim.shape[0], L),
                       -np.inf, dtype=np.float32)
    for ai, li in enumerate(flat_alias_owner):
        cand_sim[:, li] = np.maximum(cand_sim[:, li],
                                     cand_alias_sim[:, ai])

    # Reduce to (widget, label): for each widget, pick the direction
    # that best matches each label.
    W = len(widgets)
    sim = np.full((W, L), -np.inf, dtype=np.float32)
    best_ctx_per_pair: dict[tuple[int, int], str] = {}
    for ci, wi in enumerate(candidate_owner):
        row = cand_sim[ci]
        for li in range(L):
            if row[li] > sim[wi, li]:
                sim[wi, li] = row[li]
                best_ctx_per_pair[(wi, li)] = all_candidates[ci]
    # Widgets with zero candidates keep -inf (below threshold).
    sim = np.where(np.isfinite(sim), sim, -1.0)

    # Hungarian assignment: maximize total similarity. scipy minimizes,
    # so negate. Non-square matrices are handled: rows > cols leaves
    # extra widgets unmatched, and vice versa.
    row_ind, col_ind = linear_sum_assignment(-sim)

    # Build result.
    label_by_col = {i: (cid, primary) for i, (cid, primary, _)
                    in enumerate(normalized)}
    result: dict[str, Match] = {}
    matched_labels: set[int] = set()
    for r, c in zip(row_ind, col_ind):
        cid, dtxt = label_by_col[c]
        score = float(sim[r, c])
        if score >= min_similarity:
            result[cid] = Match(
                canonical_id=cid, widget=widgets[r], display_text=dtxt,
                nearby_text=best_ctx_per_pair.get((r, c), ""),
                similarity=score,
            )
            matched_labels.add(c)
    # Un-matched labels get None entries.
    for c, (cid, dtxt) in label_by_col.items():
        if c not in matched_labels:
            result[cid] = Match(
                canonical_id=cid, widget=None, display_text=dtxt,
                nearby_text="", similarity=0.0,
            )
    return result


if __name__ == "__main__":
    # Sanity check: two embeddings should be highly similar for
    # paraphrases and low for unrelated text.
    e = Embedder()
    print(f"providers: {e.session.get_providers()}")
    texts = [
        "Social Security Number",
        "SS #",
        "SSN",
        "Employer Identification Number",
        "EIN",
        "The taxpayer's date of birth",
        "Date of birth",
        "Name of the entity or individual",
        "Business address",
    ]
    embs = e.encode(texts)
    sim = embs @ embs.T
    print("\ncosine similarity matrix:")
    print("     " + "  ".join(f"{i:>4}" for i in range(len(texts))))
    for i, row in enumerate(sim):
        print(f"{i:>3}: " + "  ".join(f"{v:.2f}" for v in row))
    for i, t in enumerate(texts):
        print(f"  {i}: {t!r}")
