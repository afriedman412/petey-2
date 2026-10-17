"""Grids and blocks: the review page's view for tables (Andrew, 2026-10-16: "add a 'grids and blocks' view to the
reviewer and just route the skill through there ... a button to check and validate it in one click").

Every numbered table and repeated block the layout code finds (eval/grid_naming.grids) is listed with its cells, and
one click runs the lightest method that settles it, in order:

  1. the code check: already on pattern -> its cells accepted, nothing else;
  2. the resolver (grid_naming.resolve): each position's wording, settled by the name-check model against the
     position's shared caption, then the numbers (1..N, unless the series continues from another page or the
     numbers are printed line numbers) -> the renames applied as Claude's, the cells accepted;
  3. Jev: a position the model could not settle, chosen from its candidate wordings with the page image ->
     resolved again with that wording, applied and accepted;
  4. Opus (the chat with the grid-validation skill's rules, this page only): only what is still unclear; its
     proposals come back for the person to tick, nothing applied.

Nothing is stored about the tables in the blueprint (they may get names there later).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
import grid_naming as G  # noqa: E402

from petey.validate import hand_review as h, page_check as pc  # noqa: E402
from petey.validate.retype import resolve_blank  # noqa: E402

_LINES: dict[str, dict] = {}
JEV_MIN = 0.5            # Jev's probability for its chosen wording, below which the position stays unsure


def _lines(blank: Path) -> dict:
    from petey.validate.field_chain import _page_lines
    k = str(blank)
    if k not in _LINES:
        _LINES[k] = _page_lines(k)
    return _LINES[k]


NOT_GRIDS = h.OUT / "not_grids.json"      # {bid: [{page, cells, when}]}: what the person said is not a grid or block


def not_grids(bid: str) -> list[dict]:
    """The tables the person set aside as not a grid or block (Andrew, 2026-10-16: 'lets add a "not a grid or block"
    button'), by page and cell names, so the decision outlives renumbering of the listing; also a record of where the
    finder is wrong."""
    import json
    try:
        return (json.loads(NOT_GRIDS.read_text(encoding="utf-8")) if NOT_GRIDS.exists() else {}).get(bid) or []
    except (OSError, ValueError):
        return []


def set_not_grid(bid: str, page: int, cells: list[str], on: bool) -> list[dict]:
    import json
    import time
    rec = json.loads(NOT_GRIDS.read_text(encoding="utf-8")) if NOT_GRIDS.exists() else {}
    have = [e for e in rec.get(bid) or [] if not (e["page"] == page and _same(e["cells"], cells))]
    if on:
        have.append({"page": page, "cells": sorted(cells), "when": time.strftime("%Y-%m-%d %H:%M:%S")})
    rec[bid] = have
    if not have:
        rec.pop(bid)
    NOT_GRIDS.write_text(json.dumps(rec, indent=1, sort_keys=True), encoding="utf-8")
    return have


def _same(a, b) -> bool:
    """The same table, near enough: most of its cells (a rename or a cell joining moves a few)."""
    a, b = set(a), set(b)
    return bool(a and b) and len(a & b) >= 0.8 * max(len(a), len(b))


def dismissed(entries: list[dict], page: int, cells) -> bool:
    return any(e["page"] == page and _same(e["cells"], cells) for e in entries)


def _rect(bp: dict, name: str):
    """A field's box; an option group's (a column of a table or block since 2026-10-16) is the box around its boxes."""
    spec = (bp.get("fields") or {}).get(name) or {}
    w = spec.get("widget") or {}
    if w.get("rect") or not spec.get("widgets"):
        return w.get("rect")
    rs = [x["rect"] for x in spec["widgets"].values() if x.get("rect")]
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)] if rs else None


_HEADS: dict[str, dict] = {}


def _title(bbox, page_lines, heads=None, captions=()) -> Optional[str]:
    """The heading printed above a table: the nearest section heading (bold, capitals, larger type, Section / Part;
    `cheap_names.headings`) above it that overlaps it across, within 250 pt (ACORD 126: SCHEDULE OF HAZARDS, not
    its column header PREM/OPS); else the nearest line within 60 pt above."""
    from cheap_names import JUNK
    width = bbox[2] - bbox[0]

    caps = {" ".join(str(c).split()).lower() for c in captions if c}

    def titleish(bb, t):                 # a title starts at the table's left edge or spans much of it; not a column
        if " ".join(t.split()).lower() in caps:                                  # header (the table's own captions),
            return False                                                         # an instruction or a caption
        if __import__("re").match(r"^\(?\s*(rev\.?|revised|form\b|page\b|omb\b)", t.strip(), __import__("re").I):
            return False                                                         # a revision or form stamp
        return ((bb[0] <= bbox[0] + 12 or bb[2] - bb[0] >= 0.3 * width)
                and not JUNK.search(t) and not t.rstrip().endswith(":") and any(ch.isalpha() for ch in t))
    hs = [(bbox[1] - bb[3], " ".join(t.split())) for bb, t in heads or []
          if 0 <= bbox[1] - bb[3] <= 250 and min(bbox[2], bb[2]) - max(bbox[0], bb[0]) > 0 and titleish(bb, t)]
    if hs:
        return min(hs)[1]
    best = None
    for bb, t in page_lines or []:
        gap = bbox[1] - bb[3]
        if 0 <= gap <= 60 and min(bbox[2], bb[2]) - max(bbox[0], bb[0]) > 0 and len(t.split()) <= 12 and titleish(bb, t):
            if best is None or gap < best[0]:
                best = (gap, " ".join(t.split()))
    return best[1] if best else None


def tables(bp: dict) -> list[dict]:
    """[{id, page, kind, rows, cols, lines, positions, title, bbox, cells: [{name, rect, row, col}], on_pattern, why}]
    for every numbered table and block, in page order. `lines` is how many rows (or blocks) it numbers, `positions`
    each column (or a block's field) with its wording and the caption printed for it."""
    blank = resolve_blank(bp)
    page_text = _lines(blank) if blank and blank.exists() else {}
    if blank and blank.exists() and str(blank) not in _HEADS:
        from cheap_names import headings
        _HEADS[str(blank)] = headings(blank)
    heads = _HEADS.get(str(blank), {}) if blank else {}
    out, n = [], {}
    for g in G.grids(bp):
        if not G.iterated(g):
            continue
        page = g[0]["page"]
        n[page] = n.get(page, 0) + 1
        cells = [dict(c, rect=_rect(bp, c["name"])) for c in g]
        rs = [c["rect"] for c in cells if c["rect"]]
        if not rs:
            continue
        ok, why = G.on_pattern(g)
        reading = "columns" if G.keyed(g) else G.breaks(g)[0]      # lines named by role or kind are the rows
        pos_axis, num_axis = ("col", "row") if reading == "columns" else ("row", "col")
        how = "block" if g[0].get("block") else reading
        body = G.body(g)
        body_names = {c["name"] for c in body}             # a totals row is outside the check (and the validation)
        positions = []
        for k in sorted({c[pos_axis] for c in body}):
            pcs = [c for c in body if c[pos_axis] == k]
            wordings = sorted({(G._pattern(c["name"]) or c["name"]).replace("_N", "_#") for c in pcs})
            positions.append({"pos": k + 1, "wordings": wordings, "caption": G.position_caption(bp, pcs, how, page_text)})
        bbox = [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]
        out.append({"id": f"p{page}t{n[page]}", "page": page, "kind": "block" if g[0].get("block") else "grid",
                    "lines": len({c[num_axis] for c in body}), "positions": positions, "reading": reading,
                    "title": _title(bbox, page_text.get(page), heads.get(page), [p["caption"] for p in positions]),
                    "rows": max(c["row"] for c in g) + 1, "cols": max(c["col"] for c in g) + 1,
                    "bbox": bbox,
                    "cells": [dict({k: c[k] for k in ("name", "rect", "row", "col")}, total=c["name"] not in body_names)
                              for c in cells],
                    "on_pattern": ok, "why": why})
    out.sort(key=lambda t: (t["page"], t["bbox"][1], t["bbox"][0]))
    return out


def _grid(bp: dict, tid: str):
    """(the table listed under `tid`, its grid) or (None, None)."""
    want = next((t for t in tables(bp) if t["id"] == tid), None)
    if not want:
        return None, None
    names = {c["name"] for c in want["cells"]}
    g = next((g for g in G.grids(bp) if {c["name"] for c in g} == names), None)
    return want, g


def jev_choose(bp: dict, page: int, unsure: dict) -> Optional[str]:
    """Jev picks one position's wording from its candidates, looking at the page with the position's boxes tagged.
    The candidate pattern, or None when Jev is unsure too."""
    from petey.validate import jev_page
    import httpx
    key = jev_page._key()
    if not key or not unsure.get("candidates"):
        return None
    rows = pc.numbered(bp)
    png, _dpi, px = pc.render(resolve_blank(bp), page, rows, limits=jev_page.LIMITS)
    ref = jev_page.image_ref(png)
    ids = [r["id"] for r in rows if r["name"] in set(unsure["cells"])]
    cands = unsure["candidates"][:12]
    crit = {f"c{i}": G._desc(p).replace("_", " ") or p for i, p in enumerate(cands)}
    crit["none"] = "None of these wordings says what is written in these boxes."
    body = {"model": jev_page.MODEL,
            "state": {"page_number": page, "page": ref,
                      "boxes": [{"id": i, "pixel_box": [round(v) for v in px[i]]} for i in ids if i in px],
                      "printed_caption": unsure.get("caption")},
            "questions": {"w": {"type": "choice", "criteria": crit, "instructions": {
                "question": ("`page` is a page of a blank form with every box outlined and numbered. The boxes listed in "
                             "`boxes` are one column (or one repeated slot) of a table. Which wording says what a person "
                             "writes in them, judging by the headers and captions printed for them?")}}}}
    with httpx.Client() as client:
        res = jev_page.ask_split(client, key, body, {ref: png})
    a = (res.get("answers") or {}).get("w") or {}
    choice = a.get("choice")
    probs = a.get("probabilities") or {}
    p = probs.get(choice) if isinstance(probs, dict) else None
    if not choice or choice == "none" or (p is not None and p < JEV_MIN):
        return None
    return cands[int(choice[1:])] if choice[1:].isdigit() and int(choice[1:]) < len(cands) else None


def check(bid: str, tid: str, *, accept, apply, ask_opus) -> dict:
    """One click on a table: {status, steps, applied, accepted, proposals}. `accept(page, names)` accepts cells,
    `apply(edits)` writes renames (form_chat.apply's result), `ask_opus(page)` returns the chat's proposal."""
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid)
    if not g:
        return {"status": "gone", "steps": ["the table is no longer found on the page (renamed or moved?)"]}
    page, steps = t["page"], []
    if G.on_pattern(g)[0]:
        acc = accept(page, [c["name"] for c in G.body(g)])
        return {"status": "validated", "steps": [f"code check: on pattern; {len(acc)} cell(s) accepted"], "accepted": acc}
    blank = resolve_blank(bp)
    lines = _lines(blank) if blank else {}
    r = G.resolve(bp, g, lines, G.text_match_score())
    steps.append(f"resolver: {r['status']} ({r['why']})")
    forced = {}
    if r["status"] == "unsure" and all(u.get("pos") is not None for u in r["unsure"]):
        for u in r["unsure"]:
            pick = jev_choose(bp, page, u)
            steps.append(f"Jev, position {u['pos'] + 1}: " + (f"chose {pick}" if pick else "unsure"))
            if pick:
                forced[u["pos"]] = pick
        if len(forced) == len(r["unsure"]):
            r = G.resolve(bp, g, lines, G.text_match_score(), forced=forced)
            steps.append(f"resolver with Jev's wording: {r['status']} ({r['why']})")
    if r["status"] in ("fixed", "ok") and (r["renames"] or r["status"] == "ok"):
        out = apply([{"field": o, "edit": {"name": n}, "why": "grids and blocks: " + ("Jev's wording, " if forced else "")
                      + "each position one wording, each line one number"} for o, n in r["renames"].items()]) \
            if r["renames"] else {"changes": [], "errors": []}
        if out.get("errors"):
            steps.append("not all applied: " + "; ".join(out["errors"][:3]))
        names = [r["renames"].get(c["name"], c["name"]) for c in G.body(g)]
        acc = accept(page, names)
        steps.append(f"{len(out.get('changes') or [])} rename(s) applied; {len(acc)} cell(s) accepted")
        return {"status": "fixed" if r["renames"] else "validated", "steps": steps,
                "applied": out.get("changes") or [], "accepted": acc}
    prop = ask_opus(page)
    steps.append("Opus (this page only): " + (prop.get("reply") or "no proposal"))
    return {"status": "proposed", "steps": steps, "proposals": prop}
