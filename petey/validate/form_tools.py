"""The header's whole-form tools beside "run finders" (Andrew, 2026-11-04: "take the 'run finders' button and make it a
dropdown", then "split multiline blocks", "add signatures" and "add text groups"; "these can go through claude or
whatever"). Each proposes changes the person then checks; splits and signatures go through Add / remove (record ->
apply, `x_petey_added`), text groups through Groups' record (`group_review.ENTITY_KEY` tags), so all of it lands in
the working copy, shows in the save list and goes with discard.

- `split_proposals`: a text box over printed writing lines becomes one field per line, `<name>_line_N`, cut only at
  printed lines (2026-11-03: "take guidance from the printed lines"; no lines = one box). The lines are drawn rules,
  rows of printed dots ("......" text), or, on a page with an image and neither (a scan), dotted / solid rows in the
  page image. Boxes in a grid, and boxes with printed words under their first line (a table cell, not a writing area),
  are left alone.
- `signature_proposals`: a printed signature box or line that no field covers gets a field over it, marked printed
  (handwritten, as the 2026-11-01 signature sweep). A signature is a short caption with "sign" in it inside a box's
  top, to its left, or under a line, next to an empty printed box or a line.
- `text_group_proposals`: fields on one line that make one value ("sequential fields on a single line that can be
  combined logically", 2026-10-28: a date in parts, a phone, a name, an address line, a signature and its date)
  proposed by Claude from a picture of each page, typed with `group_review.ENTITY_TYPES`.
"""
from __future__ import annotations

import base64
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import numpy as np
import pymupdf

from petey.validate import field_add, group_review

SOURCE_SPLIT, SOURCE_SIG = "split_lines", "add_signatures"
MIN_TALL = 22.0                 # pt: a box shorter than this holds one line
SPAN, EDGE = 0.7, 4.0           # a rule crosses >= 70% of the box, >= 4 pt inside its top and bottom
MERGE, BAND = 6.0, 8.0          # rules closer than MERGE pt are one; every line >= BAND pt tall
DOTS = re.compile(r"[._…]{8,}")
PIX_DPI, PIX_DARK, PIX_COVER = 200, 140, 0.5

SIGN = re.compile(r"\bsign(ature|ed|s)?\b", re.I)
SIG_WORDS = 8                   # a caption line with more words is a sentence ("sign the form on page 3"), not a label
SIG_LINE_W, SIG_BOX_W = 80.0, 100.0
SIG_LINE_H = 18.0               # a field over a signature line reaches this far above it
SIG_ROOM = 15.0                 # pt of empty box under a signature caption inside it
TEXT_MODEL = "claude-opus-5"


# ------------------------------------------------------------------ shared

def _text_fields(bp: dict) -> dict[str, dict]:
    """{name: spec} of the one-box text fields (not groups, not checkboxes)."""
    out = {}
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        w = s.get("widget") or {}
        if w.get("rect") and w.get("page") and w.get("widget_type") in (None, "text"):
            out[n] = s
    return out


def _all_rects(bp: dict) -> dict[int, list[list[float]]]:
    out: dict[int, list[list[float]]] = {}
    for s in (bp.get("fields") or {}).values():
        if not isinstance(s, dict):
            continue
        for w in (list((s.get("widgets") or {}).values()) or [s.get("widget") or {}]):
            if w.get("rect") and w.get("page"):
                out.setdefault(int(w["page"]), []).append([float(c) for c in w["rect"]])
    return out


def rules(page) -> list[tuple[float, float, float]]:
    """Horizontal rules on the page: [(y, x0, x1)] from drawn lines and thin filled rectangles."""
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.8 and abs(a.x - b.x) > 8:
                    out.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
            elif it[0] == "re":
                r = it[1]
                if r.height < 1.6 and r.width > 8:
                    out.append(((r.y0 + r.y1) / 2, r.x0, r.x1))
    return out


def pixel_rows(page, rect, cover: float = PIX_COVER) -> list[float]:
    """y (pt) of dotted or solid rows across a box in the page image: a 2-px band where dark pixels sit in >= `cover`
    of the box's 8-px column bins; the bottom of each band."""
    x0, y0, x1, y1 = rect
    pix = page.get_pixmap(clip=pymupdf.Rect(x0 + 4, y0, x1 - 4, y1 + 3), dpi=PIX_DPI, colorspace=pymupdf.csGRAY)
    if pix.w < 16 or pix.h < 4:
        return []
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w) < PIX_DARK
    nb = a.shape[1] // 8
    bins = a[:, :nb * 8].reshape(a.shape[0], nb, 8).any(axis=2)
    cov = np.array([bins[max(0, i - 1):i + 2].any(axis=0).mean() for i in range(a.shape[0])])
    rows, run = [], []
    for i, c in enumerate(cov):
        if c >= cover:
            run.append(i)
        elif run:
            rows.append(run)
            run = []
    if run:
        rows.append(run)
    return [round(y0 + (max(r) + 1) * 72 / PIX_DPI, 1) for r in rows]


# ------------------------------------------------------------------ split multi-line boxes

def line_cuts(page, rect, words: Optional[list] = None, page_rules: Optional[list] = None) -> list[float]:
    """Where a box is cut into its printed writing lines (y in pt, top to bottom), or [] when it is one box. Drawn
    rules first, then rows of printed dots, then (a page with an image: a scan) rows in the image. A cut at a dot row is the row's
    bottom; the last row, on the box's bottom, ends the last line and is no cut."""
    x0, y0, x1, y1 = rect
    if y1 - y0 < MIN_TALL:
        return []
    wide = lambda a, b: min(b, x1) - max(a, x0) >= SPAN * (x1 - x0)
    words = page.get_text("words") if words is None else words
    ys = sorted(y for y, a, b in (rules(page) if page_rules is None else page_rules) if y0 + EDGE < y < y1 - EDGE and wide(a, b))
    if not ys:
        ys = sorted(w[3] for w in words if DOTS.fullmatch(w[4]) and y0 + BAND < w[3] < y1 - BAND and wide(w[0], w[2]))
        if not ys and page.get_images():            # a scan (or a page drawn as a picture): lines in the image
            ys = [y for y in pixel_rows(page, rect) if y0 + BAND < y < y1 - BAND]
    cuts: list[float] = []
    for y in ys:                                    # a double rule, or one drawn twice, is one
        if not cuts or y - cuts[-1] > MERGE:
            cuts.append(y)
    if not cuts:
        return []
    edges = [y0] + cuts + [y1]
    if min(b - a for a, b in zip(edges, edges[1:])) < BAND:
        return []
    # printed words below the first line: a table cell or a box over printed text, not a writing area
    if any(x0 - 1 <= (w[0] + w[2]) / 2 <= x1 + 1 and cuts[0] + 1 < (w[1] + w[3]) / 2 < y1 - 1
           and not DOTS.fullmatch(w[4]) for w in words):
        return []
    return [round(c, 2) for c in cuts]


def split_proposals(bp: dict, blank, now: Optional[str] = None) -> tuple[list[dict], list[dict], list[str]]:
    """(added, removed, notes) for Add / remove: each multi-line text box removed and replaced by its lines, full
    width, type and semantic type kept."""
    now = now or time.strftime("%Y-%m-%d %H:%M:%S")
    added, removed, notes = [], [], []
    doc = pymupdf.open(str(blank))
    try:
        cache: dict[int, tuple] = {}
        for n, s in _text_fields(bp).items():
            w = s["widget"]
            if (s.get("x_petey_identifiers") or {}).get("grid") or int(w["page"]) > len(doc):
                continue
            pg = int(w["page"])
            if pg not in cache:
                cache[pg] = (doc[pg - 1], doc[pg - 1].get_text("words"), rules(doc[pg - 1]))
            page, words, prules = cache[pg]
            cuts = line_cuts(page, w["rect"], words, prules)
            if not cuts:
                continue
            x0, y0, x1, y1 = [float(c) for c in w["rect"]]
            edges = [y0] + cuts + [y1]
            k = len(edges) - 1
            removed.append({"name": n, "page": pg, "rect": w["rect"]})
            copy = {c: s[c] for c in ("semantic_type", "pattern") if s.get(c)}
            for i, (a, b) in enumerate(zip(edges, edges[1:]), 1):
                r = [round(x0, 2), round(a, 2), round(x1, 2), round(b, 2)]
                added.append({"name": f"{n}_line_{i}", "kind": "text", "page": pg, "rect": r,
                              "type": s.get("type") or "string", **copy,
                              "widget": {"page": pg, "rect": r, "widget_type": "text", "path": None},
                              "description": f"{s['description']} (line {i} of {k})" if s.get("description") else None,
                              "name_source": "hand", "when": now,
                              "geometry": f"split multi-line box: line {i} of {k} of {n}"})
            notes.append(f"{n}: {k} lines")
    finally:
        doc.close()
    return added, removed, notes


# ------------------------------------------------------------------ add signatures

def _lines_of(words: list, gap: float = 15.0) -> list[dict]:
    """The page's printed phrases: {text, rect, n} from words grouped by block and line, split where words are more
    than `gap` pt apart ("Print Name ... Signature" under two boxes are two captions)."""
    by: dict[tuple, list] = {}
    for w in words:
        by.setdefault((w[5], w[6]), []).append(w)
    out = []
    for ws in by.values():
        ws.sort(key=lambda w: w[0])
        runs = [[ws[0]]]
        for w in ws[1:]:
            (runs[-1].append(w) if w[0] - runs[-1][-1][2] <= gap else runs.append([w]))
        for r in runs:
            out.append({"text": " ".join(w[4] for w in r), "n": len(r),
                        "rect": [min(w[0] for w in r), min(w[1] for w in r), max(w[2] for w in r), max(w[3] for w in r)]})
    return out


def _boxes_of(page) -> list[list[float]]:
    """Printed rectangles (plain or rounded) a signature could go in, de-duplicated."""
    out: list[list[float]] = []
    for d in page.get_drawings():
        r = d["rect"]
        if r.width >= SIG_BOX_W and 15 <= r.height <= 150 and (d.get("color") or d.get("fill")):
            box = [r.x0, r.y0, r.x1, r.y1]
            if not any(all(abs(a - b) < 2 for a, b in zip(box, o)) for o in out):
                out.append(box)
    return out


def sign_lines(page) -> list[tuple[float, float, float]]:
    """Lines one could sign on: stroked horizontal lines and thin bars, not the edges of a filled shape (a heading
    bar's or a shaded panel's outline is drawn with lines too)."""
    out = []
    for d in page.get_drawings():
        for it in d["items"]:
            if it[0] == "l" and d.get("fill") is None:
                a, b = it[1], it[2]
                if abs(a.y - b.y) < 0.8 and abs(a.x - b.x) > 8:
                    out.append(((a.y + b.y) / 2, min(a.x, b.x), max(a.x, b.x)))
            elif it[0] == "re" and it[1].height < 1.6 and it[1].width > 8:
                out.append(((it[1].y0 + it[1].y1) / 2, it[1].x0, it[1].x1))
    return out


def _covered(rect, rects: list[list[float]], frac: float = 0.3) -> bool:
    a = max(1.0, (rect[2] - rect[0]) * (rect[3] - rect[1]))
    for r in rects:
        ix = max(0.0, min(rect[2], r[2]) - max(rect[0], r[0]))
        iy = max(0.0, min(rect[3], r[3]) - max(rect[1], r[1]))
        if ix * iy >= frac * min(a, max(1.0, (r[2] - r[0]) * (r[3] - r[1]))):
            return True
    return False


def signature_spots(page, words: Optional[list] = None) -> list[tuple[list[float], str]]:
    """[(rect, caption)] of the page's printed signature places: a box whose top holds a signature caption or that has
    one just to its left; a line with one just under it or to its left on its baseline."""
    words = page.get_text("words") if words is None else words
    caps = [ln for ln in _lines_of(words) if SIGN.search(ln["text"]) and ln["n"] <= SIG_WORDS]
    if not caps:
        return []
    boxes = _boxes_of(page)
    lines = [(y, a, b) for y, a, b in sign_lines(page) if b - a >= SIG_LINE_W]
    out: list[tuple[list[float], str]] = []
    for c in caps:
        cx0, cy0, cx1, cy1 = c["rect"]
        cy = (cy0 + cy1) / 2
        best = None
        for b in boxes:
            # the caption in the box's top with room to sign under it (a heading bar holds its words and no more),
            # or just left of a box tall enough to sign in
            inside = (b[0] - 1 <= cx0 and cx1 <= b[2] + 1 and b[1] - 1 <= cy0 and cy1 <= b[1] + 0.45 * (b[3] - b[1])
                      and b[3] - cy1 >= SIG_ROOM)
            left = 0 <= b[0] - cx1 <= 40 and b[1] - 4 <= cy <= b[3] + 4 and b[3] - b[1] >= SIG_ROOM + 9
            if not (inside or left):
                continue
            # a container with other words in it is a section, not a signature box
            others = [w for w in words if b[0] < (w[0] + w[2]) / 2 < b[2] and b[1] < (w[1] + w[3]) / 2 < b[3]
                      and not (cx0 - 1 <= w[0] and w[2] <= cx1 + 1 and cy0 - 1 <= w[1] and w[3] <= cy1 + 1)]
            if others:
                continue
            area = (b[2] - b[0]) * (b[3] - b[1])
            if best is None or area < best[0]:
                best = (area, b)
        if best is not None:
            out.append(([round(v, 2) for v in best[1]], c["text"]))
            continue
        for y, a, b in sorted(lines, key=lambda t: abs(t[0] - cy0)):
            under = -3 <= cy0 - y <= 14 and min(b, cx1) - max(a, cx0) > 0.5 * (cx1 - cx0)
            beside = 0 <= a - cx1 <= 30 and abs(cy1 - y) <= 6
            # room to sign above the line: no printed words there (a panel's or heading bar's edge has its text)
            clear = not any(a < (w[0] + w[2]) / 2 < b and y - SIG_LINE_H < (w[1] + w[3]) / 2 < y - 1 for w in words)
            if (under or beside) and clear:
                out.append(([round(a, 2), round(y - SIG_LINE_H, 2), round(b, 2), round(y, 2)], c["text"]))
                break
    uniq: list[tuple[list[float], str]] = []
    for r, t in out:
        if not any(_covered(r, [u], 0.6) for u, _ in uniq):
            uniq.append((r, t))
    return uniq


def _sig_base(caption: str) -> str:
    """A signature's name from its caption ("Signature of parent" -> signature_of_parent)."""
    base = field_add._slug(re.sub(r"[:*#]+", " ", caption))[:48].strip("_") or "signature"
    return base if "sign" in base else f"{base}_signature"


def signature_proposals(bp: dict, blank, now: Optional[str] = None) -> tuple[list[dict], list[str]]:
    """(added, notes) for Add / remove: a printed field over each signature place no field covers, in reading order
    (columns read down); captions shared by several places numbered _1.._N, a name already taken numbered on."""
    now = now or time.strftime("%Y-%m-%d %H:%M:%S")
    have = _all_rects(bp)
    spots = []
    doc = pymupdf.open(str(blank))
    try:
        for i, page in enumerate(doc, 1):
            mid = page.rect.width / 2
            for rect, cap in sorted(signature_spots(page), key=lambda t: (t[0][0] >= mid, t[0][1], t[0][0])):
                if not _covered(rect, have.get(i, [])):
                    spots.append((i, rect, cap))
                    have.setdefault(i, []).append(rect)
    finally:
        doc.close()
    bases = [_sig_base(c) for _, _, c in spots]
    seen: dict[str, int] = {}
    taken = set((bp.get("fields") or {}).keys())
    added, notes = [], []
    for (i, rect, cap), base in zip(spots, bases):
        seen[base] = seen.get(base, 0) + 1
        name = f"{base}_{seen[base]}" if bases.count(base) > 1 else base
        k = seen[base]
        while name in taken:
            k += 1
            name = f"{base}_{k}"
        taken.add(name)
        added.append({"name": name, "kind": "text", "page": i, "rect": rect, "type": "string", "printed": True,
                      "widget": {"page": i, "rect": rect, "widget_type": "text", "path": None},
                      "name_source": "hand", "when": now, "caption": cap,
                      "geometry": f"printed signature place by '{cap}'"})
        notes.append(f"p{i} {name}")
    return added, notes


# ------------------------------------------------------------------ text groups (Claude)

TEXT_SYSTEM = """You look at one page of a blank form. Every one-line text field on it is outlined in red with its \
number in a small red tag at the box's top-left. Find the TEXT GROUPS: two or more fields that sit next to each other \
on one line (or one row) and together hold ONE value, so that a program reading the form back would join them.

Kinds (entity_type):
- date: a date split into parts (day / month / year, or mm / dd / yyyy boxes)
- time: a time split into parts (hours / minutes, am / pm)
- phone: a phone or fax number in parts (country code, area code, number, extension)
- id_number: one identifying number split into parts (SSN, EIN, account or licence number in segments)
- money: one amount split into parts (dollars / cents)
- name: one person's name in parts on one line (first / middle / last, title, suffix)
- address_line_1: the street part of an address in parts on one line (number, street, unit)
- address_line_2: the city part of an address in parts on one line (city, state, ZIP / postcode, country)
- full_address: a whole address in parts on ONE line (street through postcode)
- signature_complex: a signature with its date (and printed name or title) on the same line
- other: parts of one value that fit none of the above

Not text groups: fields that answer different questions, even on one line (a name and an unrelated date, the \
cells of a table row that hold different facts); one value written over several lines (a multi-line box split into \
lines); a field alone. Only propose clear cases; leave a field out when unsure. A field is in at most one group. \
Fields listed as already grouped are context only: do not propose them again.

Give each group a short snake_case name for the value it holds (date_of_birth, applicant_phone, spouse_name), its \
entity_type, and its field numbers in reading order."""

TEXT_SCHEMA = {
    "type": "object",
    "properties": {"groups": {"type": "array", "items": {
        "type": "object",
        "properties": {"name": {"type": "string"},
                       "entity_type": {"type": "string", "enum": list(group_review.ENTITY_TYPES)},
                       "fields": {"type": "array", "items": {"type": "integer"}}},
        "required": ["name", "entity_type", "fields"], "additionalProperties": False}}},
    "required": ["groups"], "additionalProperties": False}


def _page_rows(texts: dict[str, dict], page: int) -> list[dict]:
    """The page's text fields numbered in reading order, in `page_check.render`'s row shape."""
    on = sorted(((n, s) for n, s in texts.items() if int(s["widget"]["page"]) == page),
                key=lambda t: (round(t[1]["widget"]["rect"][1] / 6), t[1]["widget"]["rect"][0]))
    return [{"name": n, "id": str(i), "boxes": [{"page": page, "rect": s["widget"]["rect"], "label": str(i)}]}
            for i, (n, s) in enumerate(on, 1)]


def ask_page(client, blank, page: int, rows: list[dict], grouped: set[str], form: str,
             model: str = TEXT_MODEL) -> list[dict]:
    """One call for one page: [{name, entity_type, fields: [field names]}] as Claude proposes them."""
    from petey.synth.generate import final_message
    from petey.validate import page_check
    png, _, _ = page_check.render(blank, page, rows)
    listing = [{"id": int(r["id"]), **({"already_grouped": True} if r["name"] in grouped else {})} for r in rows]
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                            "data": base64.standard_b64encode(png).decode("ascii")}},
               {"type": "text", "text": f"Form {form}, page {page}. The outlined text fields: {json.dumps(listing)}\n\n"
                                        "Return the text groups as JSON."}]
    params = dict(model=model, max_tokens=32000, system=TEXT_SYSTEM, messages=[{"role": "user", "content": content}],
                  output_config={"format": {"type": "json_schema", "schema": TEXT_SCHEMA}})
    t0 = time.time()
    resp = final_message(lambda: client.messages.stream(**params), f"text groups p{page}")
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    try:
        from petey.label import call_log
        call_log.record(f"text_groups/{model}", raw=text, finish_reason=resp.stop_reason,
                        request={"model": model, "form": form, "page": page, "fields": len(rows)},
                        usage={"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens},
                        elapsed=round(time.time() - t0, 1))
    except Exception:  # noqa: BLE001  the log is a convenience
        pass
    if resp.stop_reason != "end_turn":
        raise RuntimeError(f"page {page}: the model stopped ({resp.stop_reason})")
    by_id = {int(r["id"]): r["name"] for r in rows}
    return [{"name": g["name"], "entity_type": g["entity_type"], "fields": [by_id[i] for i in g["fields"] if i in by_id]}
            for g in json.loads(text).get("groups") or []]


def clean_groups(proposed: list[dict], texts: dict[str, dict], grouped: set[str], taken: set[str]) -> list[dict]:
    """The proposals kept as Groups' text units: two or more one-box text fields on one page, none already in a group
    or in an earlier proposal, a free name and a known type."""
    out, used = [], set(grouped)
    for g in proposed:
        fs = [f for f in dict.fromkeys(g.get("fields") or []) if f in texts and f not in used]
        if len(fs) < 2 or len({int(texts[f]["widget"]["page"]) for f in fs}) != 1:
            continue
        fs.sort(key=lambda f: (round(texts[f]["widget"]["rect"][1] / 6), texts[f]["widget"]["rect"][0]))
        base = field_add._slug(g.get("name") or "") or "text_group"
        name, k = base, 2
        while name in taken:
            name, k = f"{base}_{k}", k + 1
        taken.add(name)
        used.update(fs)
        t = g.get("entity_type") if g.get("entity_type") in group_review.ENTITY_TYPES else "other"
        out.append({"kind": "text", "name": name, "type": "string", "items": fs, "origin": None, "entity_type": t,
                    "confirmed": False})
    return out


def text_group_proposals(bp: dict, blank, form: str, model: str = TEXT_MODEL, workers: int = 4) -> tuple[list[dict], list[str]]:
    """(text units for Groups, notes): Claude's text groups, one call per page with two or more free text fields,
    pages in parallel."""
    texts = {n: s for n, s in _text_fields(bp).items() if (s.get("widget") or {}).get("widget_type") == "text"}
    grouped = {n for n, s in texts.items() if isinstance(s.get(group_review.ENTITY_KEY), dict)}
    pages = sorted({int(s["widget"]["page"]) for n, s in texts.items() if n not in grouped})
    jobs = [(p, _page_rows(texts, p)) for p in pages]
    jobs = [(p, rows) for p, rows in jobs if sum(r["name"] not in grouped for r in rows) >= 2]
    if not jobs:
        return [], []
    from petey.synth.generate import make_client
    client = make_client(model)
    with ThreadPoolExecutor(max(1, min(workers, len(jobs)))) as ex:
        found = list(ex.map(lambda j: ask_page(client, blank, j[0], j[1], grouped, form, model), jobs))
    taken = set((bp.get("fields") or {}).keys()) | {(s.get(group_review.ENTITY_KEY) or {}).get("name")
                                                    for s in texts.values() if isinstance(s.get(group_review.ENTITY_KEY), dict)}
    units = clean_groups([g for page in found for g in page], texts, grouped, taken)
    return units, [f"{u['name']} ({u['entity_type']}): {', '.join(u['items'])}" for u in units]
