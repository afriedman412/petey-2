"""Block discovery: repeated blocks found with no template drawn (Andrew, 2026-10-22: can block finding be automated
with an existing mathematical method; then "write SIA into the production finder"). Geometry and the page's printed
text; the last pass a ten-number "same kind of box" model (`same_box`), local, no API.

SIA (Meredith, Lemstrom & Wiggins 2002), as for repeated themes in music: the points are a form's boxes, each with its
kind and size. Every pair of alike boxes (same kind, size within `SIZE`) votes for the translation between them; the
boxes voting for one translation are its maximal translatable pattern. Each is cut into compact pieces (SIACT, Collins
et al. 2010: boxes within `GAP` of each other), each piece's copies on the form found (SIATEC's translational
equivalence class, `block_types.copies_in`), then grown box by box where most copies have an alike box at the offset
(`MOST`: "mostly the same fields", a copy without it gets an empty position). Kept when:

    - each copy has at least `MIN_BOXES` fields (an option group counts as one);
    - not every box is a tick box (2026-10-22: lists of different Yes / No questions laid out alike, I-360's "in
      removal proceedings / worked without permission ...", are no block; measured: 164 such fields dropped, no
      field of a saved type lost);
    - the printed caption of each slot repeats across the copies (`CAPTION_SAME`, `CAPTION_SHARE`, as the old
      block-group finder had them; without it ~900 fields went wrong, same-size neighbouring boxes paired: SF 330
      p12's columns, 941-X's lines). Exact captions, numbers and item letters aside: word-tolerant captions were
      tried and gave +61 right fields of ~2,700 for 6 new real errors.

Then larger blocks first (Andrew: "try larger blocks first, then pick up what's left with smaller"): patterns by
boxes per copy, most first, each taking its copies among the fields not yet taken; a pattern made of copies of a
smaller, more numerous one glued together gives way to it. Two patterns whose copies move together, side by side
further apart than `GAP`, are one (`lockstep`: a party's two columns). Last, each pattern kept grows by the boxes its copies have
that are the same kind of box though not quite alike (`same_box`, 2026-10-27: a copy's box a few points shorter, a
question set further along its line), its copies as they are, fields of other patterns left alone (`grow_more`).

Measured 2026-10-22 per field on the 119 forms with saved block types (21,662 fields; a field in copy 2+ named from
copy 1: right when the saved types put the two at one position of one type): 2,702 right, 290 wrong (most of them
the saved types disagreeing with themselves: one block saved as two types, nested types), 3,608 on no saved type;
the old block-group finder 2,070 right, 127 wrong. About 4 s per 1,000 fields.

    find(bp) -> [{"boxes": fields per copy, "slots": [[code or None per position] per copy]}]
"""
from __future__ import annotations

import collections
import itertools
from typing import Optional

from petey.validate import block_types as bt

Q = 4.0               # pt: translation bins
SIZE = 3.0            # pt: alike boxes' width / height
GAP = 30.0            # pt: boxes of one piece within this of each other (single link, edge to edge)
MIN_BOXES = 3         # fields per copy
MOST = 0.75           # a box joins a pattern when this share of the other copies have an alike box at its offset
NEAR_GROW = 30.0      # pt: boxes tried for growing sit this close to the first copy
GROW_TOL = 8.0        # pt: ... at the offset within this
CAPTION_SAME, CAPTION_SHARE = 0.8, 0.6     # a slot's caption repeats in this share of copies; this share of the
                                           # slots with captions repeat
TICK = ("checkbox", "radiobutton", "radio", "choice")
REPEAT_CAPTION = 0.6       # grow_more: a box this alike in caption to one copy 1 has is a repeat (another copy's)
LOCKSTEP_TOL = 12.0        # pt: two patterns' copies at shifts this alike move together (`lockstep`)


def _gap(a: dict, b: dict) -> float:
    ra, rb = a["rect"], b["rect"]
    return max(max(0.0, max(ra[0], rb[0]) - min(ra[2], rb[2])), max(0.0, max(ra[1], rb[1]) - min(ra[3], rb[3])))


def _alike(a: dict, b: dict) -> bool:
    return (bt.same_kind(a["kind"], b["kind"]) and abs((a["rect"][2] - a["rect"][0]) - (b["rect"][2] - b["rect"][0])) <= SIZE
            and abs((a["rect"][3] - a["rect"][1]) - (b["rect"][3] - b["rect"][1])) <= SIZE)


def mtps(boxes: list[dict]) -> dict[tuple, list[dict]]:
    """{translation bin: [box]}: every alike pair votes for the translation between them (SIA)."""
    out: dict[tuple, list[dict]] = collections.defaultdict(list)
    by_kind = collections.defaultdict(list)
    for b in boxes:
        by_kind[bt.kind_key(b["kind"])].append(b)
    for bs in by_kind.values():
        bs = sorted(bs, key=lambda b: (b["page"], b["rect"][1], b["rect"][0]))
        for i, a in enumerate(bs):
            for b in bs[i + 1:]:
                if not _alike(a, b):
                    continue
                v = (b["page"] - a["page"], round((b["rect"][0] - a["rect"][0]) / Q),
                     round((b["rect"][1] - a["rect"][1]) / Q))
                if v != (0, 0, 0):
                    out[v].append(a)
    return out


def pieces(pat: list[dict]) -> list[list[dict]]:
    """A pattern's compact pieces: per page, boxes linked within `GAP` (SIACT)."""
    out = []
    by_page = collections.defaultdict(list)
    for b in pat:
        by_page[b["page"]].append(b)
    for bs in by_page.values():
        bs = list({b["code"]: b for b in bs}.values())
        parent = list(range(len(bs)))

        def root(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        for i, j in itertools.combinations(range(len(bs)), 2):
            if _gap(bs[i], bs[j]) <= GAP:
                parent[root(i)] = root(j)
        groups = collections.defaultdict(list)
        for i, b in enumerate(bs):
            groups[root(i)].append(b)
        out += [g for g in groups.values() if len(g) >= MIN_BOXES]
    return out


def _tpl(bs: list[dict]) -> dict:
    bs = sorted(bs, key=lambda b: (b["rect"][1], b["rect"][0]))
    x0, y0 = bs[0]["rect"][0], bs[0]["rect"][1]
    return {"boxes": [{"code": b["code"], "dx": b["rect"][0] - x0, "dy": b["rect"][1] - y0,
                       "w": b["rect"][2] - b["rect"][0], "h": b["rect"][3] - b["rect"][1], "kind": b["kind"]}
                      for b in bs]}


def _bbox(codes: list[str], at: dict) -> tuple:
    rs = [at[c]["rect"] for c in codes]
    return (at[codes[0]]["page"], min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs),
            max(r[3] for r in rs))


def _overlap(a: tuple, b: tuple) -> bool:
    return a[0] == b[0] and min(a[3], b[3]) > max(a[1], b[1]) + 1 and min(a[4], b[4]) > max(a[2], b[2]) + 1


def _shift(occ: list[list], at: dict) -> list[tuple]:
    """Each copy's translation from copy 1 (the median over its slots): [(page, dx, dy)]."""
    out = []
    for o in occ:
        dx = sorted(at[c]["rect"][0] - at[c0]["rect"][0] for c, c0 in zip(o, occ[0]))
        dy = sorted(at[c]["rect"][1] - at[c0]["rect"][1] for c, c0 in zip(o, occ[0]))
        out.append((at[o[0]]["page"], dx[len(dx) // 2], dy[len(dy) // 2]))
    return out


def grow(occ: list[list], boxes: list[dict], at: dict) -> list[list[Optional[str]]]:
    """"Mostly the same fields": each box near copy 1 that most other copies also have at its offset joins every
    copy; a copy without it gets an empty position. Copies stay apart."""
    occ = [list(o) for o in occ]
    sh = _shift(occ, at)
    taken = {c for o in occ for c in o if c}
    by_page = collections.defaultdict(list)
    for b in boxes:
        by_page[b["page"]].append(b)
    p0 = sh[0][0]
    changed = True
    while changed:
        changed = False
        bb0 = _bbox([c for c in occ[0] if c], at)
        for b in by_page[p0]:
            if b["code"] in taken:
                continue
            r = b["rect"]
            if max(bb0[1] - r[2], r[0] - bb0[3], bb0[2] - r[3], r[1] - bb0[4]) > NEAR_GROW:
                continue
            col = [b["code"]]
            for pg, dx, dy in sh[1:]:
                hit = next((c for c in by_page[pg] if c["code"] not in taken and _alike(c, b)
                            and abs(c["rect"][0] - r[0] - dx) <= GROW_TOL
                            and abs(c["rect"][1] - r[1] - dy) <= GROW_TOL), None)
                col.append(hit["code"] if hit else None)
            if sum(c is not None for c in col[1:]) < MOST * (len(occ) - 1):
                continue
            trial = [o + [c] for o, c in zip(occ, col)]
            bbs = [_bbox([c for c in o if c], at) for o in trial]
            if any(_overlap(x, y) for x, y in itertools.combinations(bbs, 2)):
                continue
            occ = trial
            taken |= {c for c in col if c}
            changed = True
    return occ


def captions_agree(slots: list[list], cap) -> tuple[Optional[float], int]:
    """(the share of the slots with captions whose printed caption repeats across the copies, those slots)."""
    judged = agree = 0
    for k in range(max(map(len, slots))):
        cs = [c for c in (cap(o[k]) for o in slots if k < len(o) and o[k]) if c]
        if len(cs) < 2:
            continue
        judged += 1
        agree += collections.Counter(cs).most_common(1)[0][1] >= CAPTION_SAME * len(cs)
    return (agree / judged if judged else None), judged


def _glued(i: int, sets: list[list[set]]) -> bool:
    """Pattern i is copies of a smaller, more numerous pattern glued together. A small copy counts as inside a big one
    when the majority of its fields are: the big pattern's copies can lack a field or two (2026-10-27, fl__sd_252381
    pp. 3-8: three wines of 7 fields a page; the page as one copy of 18-20 fields, the vintage line whose caption
    differs left out, kept the third wine from being wholly inside, so 6 page-sized copies beat 18 wines)."""
    S = sets[i]
    for j, Sm in enumerate(sets):
        if i != j and len(Sm) > len(S) and sum(map(len, Sm)) / len(Sm) < sum(map(len, S)) / len(S):
            def made_of(s: set) -> bool:
                inside = [m & s for m in Sm if 2 * len(m & s) > len(m)]
                return len(inside) >= 2 and len(set().union(*inside)) >= 0.9 * len(s)
            if all(made_of(s) for s in S):
                return True
    return False


def cover(ok: list[list[list]], sets: list[list[set]]) -> list[dict]:
    """Larger blocks first: patterns by boxes per copy, most first; each takes its copies among the fields not yet
    taken (a copy with a taken box is not its copy), passed over with fewer than 2 left."""
    order = sorted((i for i in range(len(sets)) if not _glued(i, sets)),
                   key=lambda i: (-max(map(len, sets[i])), -len(sets[i])))
    taken: set = set()
    out = []
    for i in order:
        left = [(o, s) for o, s in zip(ok[i], sets[i]) if not s & taken]
        if len(left) < 2:
            continue
        taken |= set().union(*(s for _, s in left))
        out.append({"boxes": max(len(s) for _, s in left), "slots": [o for o, _ in left]})
    return out


def _captions(bp: dict, at: dict):
    """A field's printed caption (the nearest line lined up with its box, `field_chain.candidate_captions`), numbers
    and item letters aside; None without a blank or a caption."""
    from petey.validate import block_groups as bg
    from petey.validate.field_chain import candidate_captions
    lines = bg._page_text(bp)
    if lines is None:
        return None
    memo: dict = {}

    def cap(c: str) -> Optional[str]:
        if c not in memo:
            b = at[c]
            got = candidate_captions(b["rect"], lines.get(b["page"]) or [])
            memo[c] = (bg._norm_caption(got[0]) if got else None) or None
        return memo[c]
    return cap


def find(bp: dict) -> list[dict]:
    """The form's repeated blocks: [{"boxes", "slots"}], each pattern's copies (2+) as lists of field codes, one per
    position, None where a copy lacks it; larger blocks first. Without a blank (no captions) nothing is found: the
    caption check is what keeps same-size neighbours from pairing."""
    boxes = bt._boxes(bp)
    for b in boxes:
        b["code"] = str(b["code"])
    at = {b["code"]: b for b in boxes}
    cap = _captions(bp, at)
    if cap is None:
        return []
    cands: dict = {}
    for pat in mtps(boxes).values():
        if len(pat) < MIN_BOXES:
            continue
        for pc in pieces(pat):
            cands.setdefault(frozenset(b["code"] for b in pc), pc)
    seen, ok = set(), []
    for pc in cands.values():
        occ = bt.copies_in(boxes, _tpl(pc))
        if len(occ) < 2:
            continue
        if any(_overlap(x, y) for x, y in itertools.combinations([_bbox(o, at) for o in occ], 2)):
            continue
        occ = grow(occ, boxes, at)
        key = frozenset(frozenset(c for c in o if c) for o in occ)
        if key in seen:
            continue
        seen.add(key)
        if all(at[c]["kind"].rsplit("x", 1)[0] in TICK for c in occ[0] if c):
            continue
        if (captions_agree(occ, cap)[0] or 0) < CAPTION_SHARE:
            continue
        ok.append(occ)
    found = cover(ok, [[{c for c in o if c} for o in occ] for occ in ok])
    found = _more_by_labels(bp, found, boxes, at)
    found = lockstep(found, at)
    from petey.validate.same_box import PageWords
    pw = PageWords(bp)
    for f in found:
        held = {c for g in found if g is not f for o in g["slots"] for c in o if c}
        f["slots"] = grow_more(f["slots"], boxes, at, pw, held)
    return found


def _reading(o: list, at: dict) -> tuple:
    bb = _bbox([c for c in o if c], at)
    return bb[0], round(bb[2] / 2), bb[1]


def _apart(a: tuple, b: tuple) -> float:
    """The gap between two copies' boxes (edge to edge), endless across pages."""
    if a[0] != b[0]:
        return float("inf")
    return max(0.0, max(a[1], b[1]) - min(a[3], b[3]), max(a[2], b[2]) - min(a[4], b[4]))


def lockstep(found: list[dict], at: dict) -> list[dict]:
    """Two patterns whose copies move together are one block (2026-10-27, bm__sd_3867602 p2: each party's name /
    address / email / signature and company / phone / invoices / date, two columns 38.7 pt apart, past `GAP`, found
    as two patterns): as many copies, copy i of one at the shift from its copy 1 that copy i of the other is at
    (within `LOCKSTEP_TOL`, same page), and each copy nearer its partner than its own nearest copy (two lists side by
    side that repeat alike are not glued). Copies of one block side by side are one pattern already, never two.
    Measured on 151 forms with saved types: +12 right fields (gsa_sf_1199a, cra_t4a_nr), no wrong one."""
    found = [dict(f, slots=[list(o) for o in f["slots"]]) for f in found]
    merged = True
    while merged:
        merged = False
        for i, j in itertools.combinations(range(len(found)), 2):
            P = sorted(found[i]["slots"], key=lambda o: _reading(o, at))
            Q = sorted(found[j]["slots"], key=lambda o: _reading(o, at))
            if len(P) != len(Q) or len(P) < 2:
                continue
            bP, bQ = [_bbox([c for c in o if c], at) for o in P], [_bbox([c for c in o if c], at) for o in Q]
            if any(p[0] != q[0] for p, q in zip(bP, bQ)):
                continue
            if any(abs((p[1] - bP[0][1]) - (q[1] - bQ[0][1])) > LOCKSTEP_TOL
                   or abs((p[2] - bP[0][2]) - (q[2] - bQ[0][2])) > LOCKSTEP_TOL for p, q in zip(bP, bQ)):
                continue
            if any(_apart(bP[k], bQ[k]) >= min(_apart(bP[k], bP[m]) for m in range(len(P)) if m != k)
                   for k in range(len(P))):
                continue
            slots = [p + q for p, q in zip(P, Q)]
            if any(_overlap(x, y) for x, y in itertools.combinations([_bbox([c for c in o if c], at) for o in slots], 2)):
                continue
            found[i] = {"boxes": max(sum(1 for c in o if c) for o in slots), "slots": slots}
            del found[j]
            merged = True
            break
    return found


def grow_more(occ: list[list], boxes: list[dict], at: dict, pw, held: set = frozenset()) -> list[list[Optional[str]]]:
    """A pattern SIA kept, grown by the "same kind of box" model (`same_box`): a box near copy 1 joins when most other
    copies (`MOST`) have a box of the same kind most likely to be it, where their frames put it, none of them a repeat of
    a box copy 1 already has; a copy without one gets an empty position. The copies stay the ones SIA chose (inside
    SIA's own growing this glued neighbouring copies: je__acord_80), and fields in `held` (other patterns) stay theirs."""
    from petey.validate import same_box
    occ = [list(o) for o in occ]
    full = [k for k in range(len(occ[0])) if all(k < len(o) and o[k] for o in occ)]
    if not full:
        return occ
    sh = _shift([[o[k] for k in full] for o in occ], at)
    taken = {c for o in occ for c in o if c} | set(held)
    by_page = collections.defaultdict(list)
    for b in boxes:
        by_page[b["page"]].append(b)
    p0 = sh[0][0]
    changed = True
    while changed:
        changed = False
        bb0 = _bbox([c for c in occ[0] if c], at)
        height, width = max(bb0[4] - bb0[2], 1.0), max(bb0[3] - bb0[1], 1.0)
        for b in by_page[p0]:
            r = b["rect"]
            if b["code"] in taken or max(bb0[1] - r[2], r[0] - bb0[3], bb0[2] - r[3], r[1] - bb0[4]) > NEAR_GROW:
                continue
            cb = pw.caption(b)
            if any(_alike(b, at[c]) and len(cb & pw.caption(at[c])) >= REPEAT_CAPTION * max(len(cb | pw.caption(at[c])), 1)
                   for c in occ[0] if c):
                continue                         # a repeat of a box copy 1 has: another copy's, not a new position
            col = [b["code"]]
            for pg, dx, dy in sh[1:]:
                cands = [c for c in by_page[pg] if c["code"] not in taken and c["code"] not in col
                         and abs(c["rect"][0] - r[0] - dx) <= 60 and abs(c["rect"][1] - r[1] - dy) <= 30]
                hit = same_box.best(b, cands, dx, dy, height, width, pw)
                col.append(hit[1]["code"] if hit else None)
            if sum(c is not None for c in col[1:]) < MOST * (len(occ) - 1):
                continue
            trial = [o + [c] for o, c in zip(occ, col)]
            bbs = [_bbox([c for c in o if c], at) for o in trial]
            if any(_overlap(x, y) for x, y in itertools.combinations(bbs, 2)):
                continue
            occ = trial
            taken |= {c for c in col if c}
            changed = True
    return occ


def _more_by_labels(bp: dict, found: list[dict], boxes: list[dict], at: dict) -> list[dict]:
    """More copies of each pattern where its printed lines repeat (`block_types.label_copies`, as detection finds
    them), among the fields no pattern took: a copy drawn off the others' layout (2026-10-22, Andrew: B 106D page 2
    "should be three blocks": the middle claim's description box is 26 pt tall, not 34, and the boxes under it sit
    8-20 pt higher, past the layout's tolerance; its labels are where the others' are). A copy found so can lack a box
    or two."""
    from petey.validate.retype import resolve_blank
    blank = resolve_blank(bp)
    if not blank or not blank.exists() or not found:
        return found
    taken = {c for p in found for o in p["slots"] for c in o if c}
    for p in found:
        first = next(o for o in p["slots"] if all(o)) if any(all(o) for o in p["slots"]) else p["slots"][0]
        tpl = _tpl([at[c] for c in first if c])
        order = {b["code"]: k for k, b in enumerate(tpl["boxes"])}
        t = {"boxes": tpl["boxes"], "blocks": [[c for c in first if c]]}
        t["blocks"] = [[b["code"] for b in tpl["boxes"]]]
        labs = bt.type_labels(t, blank, at)
        if len(labs) < 2:
            continue
        pages = sorted({at[c]["page"] for o in p["slots"] for c in o if c})
        for pg in pages:
            free = [b for b in boxes if b["page"] == pg and b["code"] not in taken]
            for codes in bt.label_copies(t, bt.page_lines(blank, pg), free, labs):
                slot = [None] * len(first)
                for k, c in enumerate(codes):        # template order -> the pattern's position order
                    if c:
                        slot[first.index(tpl["boxes"][k]["code"])] = c
                if sum(1 for c in slot if c) >= MIN_BOXES:
                    p["slots"].append(slot)
                    taken |= {c for c in slot if c}
    return found
