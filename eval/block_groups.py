"""Block groups: a discrete set of fields that repeats (Andrew, 2026-10-18: "blocks ... involve a higher order detection
of a repeated pattern ... we need a new concept: 'block group', which is a set of 'blocks' -- a discrete set of fields
that repeat"). Grids are found apart (grid_naming); this finds what is not a grid: a set of fields over two or more
lines, laid out again one step further down (or across) the page, again and again.

A block group: blocks (one per repeat, in order), each a set of fields; a slot is one field's place in the block
(IMM 5645 page 2: seven siblings, each name / marital status / relationship / date of birth / country of birth /
address / occupation). Returned as cells {name, page, row: the block, col: the slot, block: True}, so the grid checks
(grid_naming.on_pattern, resolve) take a block group as they take a table: each slot one wording, each block one
number.

How: on a page, every pair of fields with the same box (width, height and kind within 2 pt) votes for the step
between them. A step many pairs agree on is a repeat; following it from field to field gives chains, one per slot.
Chains covering the same run of repeats, close together on the page, are one group. It is a block group when a block
holds three or more slots on two or more lines and in two or more columns, its blocks do not overlap,
of two or more box shapes and not all tick boxes, and most (block, slot) places are filled; and when its step does not
take a grid's rows a few at a time (nearly all fields have an alike field nearer along the step); and when each slot's
printed caption is the same in nearly every block (the same thing again, not line items that share boxes), and no
block is two entries side by side (a shifted copy of itself). The same step over single lines is a grid's rows (or a table's columns
across), left to grid_naming. A slot may be
missing from some blocks (IMM 5645 Section A: the applicant has no "will accompany" boxes).

    PYTHONPATH=. venv/bin/python eval/block_groups.py je__ircc_imm_5645 je__faa_8050_1 ...
"""
from __future__ import annotations

import collections
import math
import sys

SIZE_TOL = 2.0          # pt: two boxes are alike when their width and height differ by this or less
POS_TOL = 2.5           # pt: a box is the next one in a chain when it sits this close to where the step puts it
MIN_VOTES = 3           # pairs agreeing on a step before it is tried
MAX_STEPS = 40          # the best-supported steps tried on a page
NEARER = 0.85           # the share of fields with an alike field nearer along the step that makes it a grid's rows
SELF_COPY = 0.8         # the share of a block's fields that one shift inside it maps onto its others: two entries in
                        # one block (measured 2026-10-18: such groups 0.83-1.00, real ones up to 0.75)
CAPTION_SAME = 0.8      # a slot's caption repeats when this share of its blocks print the same one
CAPTION_SHARE = 0.6     # the share of slots whose caption repeats that makes a block group (measured 2026-10-18: real
                        # numbered groups 0.60-1.00; line items sharing boxes 0-0.33, CMS-855A 0.60)
NEAR = 100.0            # pt: chains this far apart are not one group (IMM 5645 Section A: 58 pt between name and
                        # date of birth, where Section B has relationship)
MIN_SLOTS = 3           # a block is a set of three or more fields
MIN_FILL = 0.75         # the share of (block, slot) places filled: a sparse "group" is chains of different things


def _boxes(bp: dict) -> dict[int, list[dict]]:
    """{page: [{name, rect, kind}]}: each field's box (an option group's: the box around its boxes, when they are on
    one page)."""
    out = collections.defaultdict(list)
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        if s.get("widget"):
            w = s["widget"]
            if not w.get("rect"):
                continue
            kind = "box" if w.get("widget_type") in ("checkbox", "radio") else "text"
            out[w["page"]].append({"name": n, "rect": list(w["rect"]), "kind": kind})
        else:
            ws = [w for w in (s.get("widgets") or {}).values() if w.get("rect")]
            if len(ws) < 2 or len({w["page"] for w in ws}) > 1:
                continue
            rs = [w["rect"] for w in ws]
            out[ws[0]["page"]].append({"name": n, "kind": "group",
                                       "rect": [min(r[0] for r in rs), min(r[1] for r in rs),
                                                max(r[2] for r in rs), max(r[3] for r in rs)]})
    return out


def _alike(a: dict, b: dict) -> bool:
    ra, rb = a["rect"], b["rect"]
    return (a["kind"] == b["kind"] and abs((ra[2] - ra[0]) - (rb[2] - rb[0])) <= SIZE_TOL
            and abs((ra[3] - ra[1]) - (rb[3] - rb[1])) <= SIZE_TOL)


def _steps(fs: list[dict]) -> list[tuple[float, float, int]]:
    """Steps (dx, dy) that pairs of alike fields agree on, most votes first; dy > 0, or dy == 0 and dx > 0."""
    votes = collections.Counter()
    for i, a in enumerate(fs):
        for b in fs[i + 1:]:
            if not _alike(a, b):
                continue
            dx, dy = b["rect"][0] - a["rect"][0], b["rect"][1] - a["rect"][1]
            if dy < -POS_TOL or (abs(dy) <= POS_TOL and dx < 0):
                dx, dy = -dx, -dy
            if math.hypot(dx, dy) < 8:
                continue
            votes[(round(dx / 2) * 2, round(dy / 2) * 2)] += 1
    merged: list[list] = []                          # neighbouring bins are one step
    for (dx, dy), v in votes.most_common():
        m = next((m for m in merged if abs(m[0] - dx) <= POS_TOL and abs(m[1] - dy) <= POS_TOL), None)
        if m:
            m[2] += v
        else:
            merged.append([dx, dy, v])
    return sorted(((dx, dy, v) for dx, dy, v in merged if v >= MIN_VOTES), key=lambda t: -t[2])


def _index(fs: list[dict]) -> dict:
    """Fields by kind and whole-point position, to find the field at a spot without scanning the page."""
    ix = collections.defaultdict(list)
    for f in fs:
        ix[(f["kind"], round(f["rect"][0]), round(f["rect"][1]))].append(f)
    return ix


def _at(ix: dict, f: dict, x: float, y: float):
    """The field alike to f whose box starts nearest (x, y), within POS_TOL; None when there is none."""
    best, bd = None, None
    r = math.ceil(POS_TOL)
    for i in range(round(x) - r, round(x) + r + 1):
        for j in range(round(y) - r, round(y) + r + 1):
            for g in ix.get((f["kind"], i, j), ()):
                if g is f or not _alike(f, g):
                    continue
                d = abs(g["rect"][0] - x) + abs(g["rect"][1] - y)
                if abs(g["rect"][0] - x) <= POS_TOL and abs(g["rect"][1] - y) <= POS_TOL and (bd is None or d < bd):
                    best, bd = g, d
    return best


def _chains(fs: list[dict], step: tuple[float, float], ix: dict | None = None) -> list[list[dict]]:
    """Fields linked to the alike field one step on, followed from each field nothing steps into."""
    dx, dy = step
    ix = ix if ix is not None else _index(fs)
    nxt, has_prev = {}, set()
    for a in fs:
        b = _at(ix, a, a["rect"][0] + dx, a["rect"][1] + dy)
        if b is not None:
            nxt[a["name"]] = b
            has_prev.add(b["name"])
    out = []
    for a in fs:
        if a["name"] in has_prev or a["name"] not in nxt:
            continue
        ch, cur = [a], a
        while cur["name"] in nxt and len(ch) < 200:
            cur = nxt[cur["name"]]
            ch.append(cur)
        out.append(ch)
    return out


def _nearer(f: dict, fs: list[dict], dx: float, dy: float, any_dist: bool = False) -> bool:
    """An alike field along the direction (dx, dy) from f, either way, closer than |(dx, dy)| (any distance with
    `any_dist`)."""
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    for g in fs:
        if g is f or not _alike(f, g):
            continue
        vx, vy = g["rect"][0] - f["rect"][0], g["rect"][1] - f["rect"][1]
        along, across = vx * ux + vy * uy, abs(-vx * uy + vy * ux)
        if across <= POS_TOL and POS_TOL < abs(along) and (any_dist or abs(along) < L - POS_TOL):
            return True
    return False


def _columns(rects: list[list[float]]) -> int:
    """How many columns a set of boxes sits in: boxes overlapping across by half the narrower are one column."""
    cols: list[list[float]] = []
    for r in sorted(rects, key=lambda r: (r[0], r[2] - r[0])):
        w = r[2] - r[0]
        c = next((c for c in cols if min(c[1], r[2]) - max(c[0], r[0]) >= 0.5 * min(c[1] - c[0], w)), None)
        if c is None:
            cols.append([r[0], r[2]])
    return len(cols)


def _overlap(a, b) -> float:
    """The share of the smaller box that the two boxes have in common."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    small = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1])) or 1
    return max(0.0, w) * max(0.0, h) / small


def _free_arc(arcs: list[tuple[float, float]], L: float):
    """The middle of the widest stretch of one step that no slot reaches (arcs may run past L and wrap); None when the
    slots cover the whole step."""
    marks = []
    for a, b in arcs:
        if b <= L:
            marks.append((a, b))
        else:
            marks += [(a, L), (0.0, b - L)]
    marks.sort()
    free, end = [], 0.0
    for a, b in marks:
        if a > end:
            free.append((a - end, end))
        end = max(end, b)
    if end < L:
        first = marks[0][0] if marks else L
        free.append((L - end + first, end))          # the stretch around the end of the step and its start
    if not free:
        return None
    w, start = max(free)
    return (start + w / 2) % L


def _lines(rects: list[list[float]]) -> int:
    """How many lines a set of boxes sits on: boxes overlapping from top to bottom by half the smaller height are one
    line."""
    lines: list[list[float]] = []
    for r in sorted(rects, key=lambda r: (r[1], r[3] - r[1])):
        h = r[3] - r[1]
        ln = next((ln for ln in lines if min(ln[1], r[3]) - max(ln[0], r[1]) >= 0.5 * min(ln[1] - ln[0], h)), None)
        if ln is None:
            lines.append([r[1], r[3]])
    return len(lines)


def _norm_caption(t: str) -> str:
    """A caption without its numbers, item letters and punctuation: 'Applicant 2' and 'Applicant 3', '(a) Name' and
    '(b) Name' read the same."""
    import re
    t = re.sub(r"\(\s*[a-z]\s*\)|\b[a-z]\.(?=\s)|\d+[a-z]?\b", " ", (t or "").lower())
    return " ".join(re.sub(r"[^a-z]+", " ", t).split())


def captions_repeat(cells: list[dict], rects: dict, lines: dict) -> tuple[float, int]:
    """(the share of slots whose printed caption is the same in nearly every block, how many slots had captions to
    compare). The caption of a field: the nearest printed line lined up with its box (field_chain.candidate_captions)."""
    from petey.validate.field_chain import candidate_captions
    by_slot = collections.defaultdict(list)
    for c in cells:
        r = rects.get(c["name"])
        cap = (candidate_captions(r, lines.get(c["page"]) or []) or [None])[0] if r else None
        if cap and _norm_caption(cap):
            by_slot[c["col"]].append(_norm_caption(cap))
    judged = agree = 0
    for caps in by_slot.values():
        if len(caps) < 2:
            continue
        judged += 1
        top, n = collections.Counter(caps).most_common(1)[0]
        agree += n >= CAPTION_SAME * len(caps)
    return (agree / judged if judged else 0.0), judged


_TEXT: dict[str, dict] = {}


def _page_text(bp: dict):
    """The blank's printed lines by page (field_chain._page_lines), cached by blank; None without a blank."""
    from petey.validate.retype import resolve_blank
    from petey.validate.field_chain import _page_lines
    blank = resolve_blank(bp)
    if not blank or not blank.exists():
        return None
    if str(blank) not in _TEXT:
        _TEXT[str(blank)] = _page_lines(str(blank))
    return _TEXT[str(blank)]


def captions_doubled(cells: list[dict], rects: dict, lines: dict) -> float:
    """The share of a group's fields whose printed caption another field of the same block also has: a block holding
    two entries side by side (an additional-information page's items in two columns; defendants A and B, then C and
    D) prints each caption twice in it."""
    from petey.validate.field_chain import candidate_captions
    blocks = collections.defaultdict(list)
    for c in cells:
        r = rects.get(c["name"])
        cap = (candidate_captions(r, lines.get(c["page"]) or []) or [None])[0] if r else None
        blocks[c["row"]].append(_norm_caption(cap) if cap else None)
    n = twice = 0
    for caps in blocks.values():
        cnt = collections.Counter(c for c in caps if c)
        for c in caps:
            if c:
                n += 1
                twice += cnt[c] > 1
    return twice / n if n else 0.0


def self_copy(cells: list[dict], boxes_by_name: dict) -> float:
    """The share of a group's fields that one shift inside their own block maps onto an alike field of the same block,
    the best shift per block: a block holding two entries side by side is a copy of itself shifted (item 5's boxes
    onto item 6's; defendant A's onto B's)."""
    blocks = collections.defaultdict(list)
    for c in cells:
        f = boxes_by_name.get(c["name"])
        if f:
            blocks[c["row"]].append(f)
    n = covered = 0
    for fs in blocks.values():
        n += len(fs)
        votes = collections.Counter()
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                if _alike(a, b):
                    votes[(round((b["rect"][0] - a["rect"][0]) / 3), round((b["rect"][1] - a["rect"][1]) / 3))] += 1
        if not votes:
            continue
        (sx, sy), _v = votes.most_common(1)[0]
        hit = set()
        for i, a in enumerate(fs):
            for b in fs[i + 1:]:
                if _alike(a, b) and (round((b["rect"][0] - a["rect"][0]) / 3), round((b["rect"][1] - a["rect"][1]) / 3)) == (sx, sy):
                    hit.update((a["name"], b["name"]))
        covered += len(hit)
    return covered / n if n else 0.0


def find(bp: dict) -> list[list[dict]]:
    """The form's block groups: [[cell]], a cell {name, page, row (block), col (slot), block: True}."""
    out = []
    boxes = _boxes(bp)
    rects = {b["name"]: b["rect"] for fs in boxes.values() for b in fs}
    by_name = {b["name"]: b for fs in boxes.values() for b in fs}
    lines = _page_text(bp)
    for page, fs in sorted(boxes.items()):
        taken: set[str] = set()
        for dx, dy, _v in _steps(fs)[:MAX_STEPS]:
            free = [f for f in fs if f["name"] not in taken]
            ix = _index(free)
            chains = [c for c in _chains(free, (dx, dy), ix) if len(c) >= 2]
            if len(chains) < 2:
                continue
            # a step that takes a grid's rows a few at a time (CBP 7512's lines 1-2 / 3-4, 1040-ES's payments, SF 3107
            # Section C five at a time): nearly all its fields have an alike field nearer along the step, inside one
            # step (measured 2026-10-18: such readings 0.87-1.00; real block groups 0-0.77, I-589's children 0.77,
            # 1040-ES's vouchers 0.64, URLA's properties 0.59: a block may hold a few stacked alike boxes)
            fields = [f for c in chains for f in c]
            if sum(_nearer(f, free, dx, dy) for f in fields) >= NEARER * len(fields):
                taken.update(f["name"] for f in fields)          # a grid's: no other step makes blocks of them
                continue
            L = math.hypot(dx, dy)
            ux, uy = dx / L, dy / L
            proj = lambda f: f["rect"][0] * ux + f["rect"][1] * uy
            p0 = min(proj(c[0]) for c in chains)
            # each chain's first block: where its head falls, counted in steps from the earliest head
            info = []
            for c in chains:
                k0 = int((proj(c[0]) - p0 + POS_TOL) // L)
                xs = [f["rect"][0] for f in c] + [f["rect"][2] for f in c]
                ys = [f["rect"][1] for f in c] + [f["rect"][3] for f in c]
                info.append({"c": c, "k0": k0, "k1": k0 + len(c) - 1, "box": [min(xs), min(ys), max(xs), max(ys)]})
            # chains covering the same run of repeats, close together, are one group
            parent = list(range(len(info)))

            def find_(i):
                while parent[i] != i:
                    i = parent[i]
                return i
            for i, a in enumerate(info):
                for j in range(i + 1, len(info)):
                    b = info[j]
                    if min(a["k1"], b["k1"]) < max(a["k0"], b["k0"]):
                        continue
                    gx = max(0, max(a["box"][0], b["box"][0]) - min(a["box"][2], b["box"][2]))
                    gy = max(0, max(a["box"][1], b["box"][1]) - min(a["box"][3], b["box"][3]))
                    if math.hypot(gx, gy) <= NEAR:
                        parent[find_(i)] = find_(j)
            groups = collections.defaultdict(list)
            for i, x in enumerate(info):
                groups[find_(i)].append(x)
            for members in groups.values():
                if len(members) < 2:
                    continue
                # the blocks' edges: where the slots' starts leave the widest gap along the step, so a block is the
                # compact set of fields it is (FEC 3X page 6 had row A's employer counted with row B's name)
                P = min(proj(m["c"][0]) for m in members)
                span = lambda r: [r[0] * ux + r[1] * uy, r[2] * ux + r[1] * uy, r[0] * ux + r[3] * uy, r[2] * ux + r[3] * uy]
                arcs = []                                # each slot's reach along the step, folded into one step
                for m in members:
                    pts = span(m["c"][0]["rect"])
                    a = (min(pts) - P) % L
                    arcs.append((a, a + min(max(pts) - min(pts), L)))
                cut = _free_arc(arcs, L)
                if cut is not None:
                    # the widest free stretch can lie inside a block (FAA 8050-1: the printed lines between applicant and
                    # signature), and the first chain's start can sit inside one (FEC 3X page 6); a wrong cut shows as an
                    # extra block, part-filled at both ends: the cut that makes fewer blocks wins (ties keep the start)
                    alt = [int(math.floor((proj(m["c"][0]) - P - cut + POS_TOL) / L)) for m in members]
                    n_now = max(m["k0"] + len(m["c"]) for m in members) - min(m["k0"] for m in members)
                    n_alt = max(a + len(m["c"]) for a, m in zip(alt, members)) - min(alt)
                    if n_alt < n_now:
                        for a, m in zip(alt, members):
                            m["k0"], m["k1"] = a, a + len(m["c"]) - 1
                k_lo = min(m["k0"] for m in members)
                first = [m["c"][0]["rect"] for m in members if m["k0"] == k_lo] or [members[0]["c"][0]["rect"]]
                # a block on two or more lines; one line repeated is a grid's rows (or a table's columns)
                block_rects = []
                for m in members:
                    off = m["k0"] - k_lo
                    r = m["c"][0]["rect"]
                    block_rects.append([r[0] - off * dx, r[1] - off * dy, r[2] - off * dx, r[3] - off * dy])
                n_blocks = max(m["k1"] for m in members) - k_lo + 1
                # two or more lines and two or more columns: one line repeated down is a grid's rows, one column
                # repeated across a grid's columns (ACORD 90 NY's coverages, vehicle 1-4)
                if _lines(block_rects) < 2 or _columns(block_rects) < 2 or n_blocks < 2 or len(members) < MIN_SLOTS:
                    continue
                # blocks side by side or one under another, never over each other (alternate rows of one table)
                boxes = collections.defaultdict(list)
                for m in members:
                    for i, f in enumerate(m["c"]):
                        boxes[m["k0"] + i].append(f["rect"])
                bb = {k: [min(r[0] for r in v), min(r[1] for r in v), max(r[2] for r in v), max(r[3] for r in v)]
                      for k, v in boxes.items()}
                if any(_overlap(bb[k], bb[k + 1]) > 0.1 for k in bb if k + 1 in bb):
                    continue
                # every block the same structure, and the lines within it different: a grid sliced into blocks has
                # nearly every line alike, the same columns with the same boxes (UK P60's pay / tax in pounds and
                # pence, the 990-EZ balance sheet, FAA 8710's pilot times)
                # a grid cut into pieces side by side (SF 3107 Section G: children 1-4, then 5-8 beside them): nearly
                # every field has an alike field in its own block straight across the step (its column-mates)
                same = collections.defaultdict(list)
                for m in members:
                    for i, f in enumerate(m["c"]):
                        same[m["k0"] + i].append(f)
                if sum(_nearer(f, same[k], -dy, dx, any_dist=True) for k, fs_ in same.items() for f in fs_) \
                        >= NEARER * sum(len(v) for v in same.values()):
                    taken.update(f["name"] for v in same.values() for f in v)
                    continue
                if sum(len(m["c"]) for m in members) < MIN_FILL * n_blocks * len(members):
                    continue
                # a block is different fields: two or more box shapes, one or more to write in. Slots all one shape
                # are a list (ACORD 125's premiums side by side, loss dates 1-3), all tick boxes a checklist
                shapes = []
                for r in block_rects:
                    if not any(abs((r[2] - r[0]) - (q[2] - q[0])) <= SIZE_TOL and abs((r[3] - r[1]) - (q[3] - q[1])) <= SIZE_TOL
                               for q in shapes):
                        shapes.append(r)
                if len(shapes) < 2 or all(m["c"][0]["kind"] != "text" for m in members):
                    continue
                # slots left to right, stacked ones top first (as the grid view lists columns)
                members.sort(key=lambda m: (round((m["c"][0]["rect"][0] - (m["k0"] - k_lo) * dx) / 6),
                                            m["c"][0]["rect"][1] - (m["k0"] - k_lo) * dy))
                cells = [{"name": f["name"], "page": page, "row": m["k0"] - k_lo + i, "col": si, "block": True}
                         for si, m in enumerate(members) for i, f in enumerate(m["c"])]
                # the same printed captions in every block (Andrew, 2026-10-18: "I would trust it pretty strongly"):
                # a block group is the same thing again, so each slot's caption repeats ('Date of birth' in each
                # sibling's block); line items that only share boxes (the 990-EZ balance sheet, a P60's pay and tax)
                # print a different caption in each. No captions to compare is no evidence: not kept
                if lines is not None:
                    share, judged = captions_repeat(cells, rects, lines)
                    if judged < 2 or share < CAPTION_SHARE:
                        continue
                # two entries in each block (an additional-information page's items in two columns, ACORD 80's losses
                # 1 and 2 side by side): each block is a shifted copy of itself
                if self_copy(cells, by_name) >= SELF_COPY:
                    continue
                out.append(cells)
                taken.update(c["name"] for c in cells)
    return out


def main() -> int:
    sys.path.insert(0, ".")
    from petey.validate import hand_review as h
    for bid in sys.argv[1:]:
        bp = h._load(h.working_path(bid))
        for g in find(bp):
            nr, nc = max(c["row"] for c in g) + 1, max(c["col"] for c in g) + 1
            cells = {(c["row"], c["col"]): c["name"] for c in g}
            print(f"{bid} p{g[0]['page']}: {nr} blocks x {nc} slots")
            for r in range(nr):
                print("   " + " | ".join(cells.get((r, c), "-")[:22] for c in range(nc)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
