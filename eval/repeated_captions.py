"""Option groups holding several questions, split by their repeated answers (Andrew, 2026-10-28: "lets fix the
overzealous grouper for good"; bm__sd_537564's publisher radio field Group2 over every round button on the page,
bm__mu_0bfb2573afdf's "Yes Checkbox" / "No Checkbox" columns, bm__sd_2801296's one field over five Yes / No questions).

One question does not offer the same answer twice: a group in which two options print the same short caption (3
words or fewer; Y / N read as Yes / No) holds several questions. Each option's caption is read from the page on both
sides of its box (the words on its line up to a gap, another option box, or 8 words); a group is left alone when the
other side gives every option a different short caption (it201's "or" between account types named on the right). The
boxes of the most repeated caption are anchors, one a question; each other option joins the anchor on its line, else
the nearest anchor nearer to it than that anchor's nearest other anchor, else it is set aside. Each piece is split
again while it repeats; the set-aside boxes are split the same way, and where nothing repeats among them they are
kept together as neighbours (on one line within ROW_GAP, stacked within STACK_GAP).

Measured 2026-10-28 (read-only, the validated library's 3,294 option groups with a blank): 2 split (acord_90_ny's
"F G" per vehicle, 8 options); sd_537564 Group2 15 options -> its 7 questions, sd_5514549 Group3 -> 6, sd_2801296 -> its
5 Yes / No pairs, sd_4885390 Group1 -> 3; mu_0bfb2573afdf's two columns -> loose boxes (the Yes / No rule pairs them
by line after). Not caught: sd_5952614 Group30 (Y / N on one line, "Yes, if yes who" on the next), sd_480300's "2" (two
different captions). A fixed distance does not separate these (single linkage, 30-250 pt: 65 validated groups broken
at the loosest, 9 of 44 reported ones split): the questions sit no further apart than one question's options.

    split_groups(groups, boxes, words) -> groups   groups: [set of names]; boxes {name: (page, rect)}; words {page: ...}
"""
from __future__ import annotations

import collections
import math
import re
from typing import Optional

SHORT = 3                    # words: a caption this short is an answer (Yes, No, normal, abnormal); longer, a question
LINE = 4.0                   # pt: centres this close vertically are on one line
ROW_GAP, STACK_GAP = 60.0, 20.0
_WORD = re.compile(r"[a-z0-9]+")


def _read(words: list, r, side: str, stops: list) -> str:
    """The words beside the box on its line, on one side: up to a gap, another option box, or 8 words; normalised."""
    ym = (r[1] + r[3]) / 2
    line = [w for w in words if w[1] - 2 <= ym <= w[3] + 2]
    bars = [q for q in stops if q[1] - 2 <= ym <= q[3] + 2 and tuple(q) != tuple(r)]
    got = []
    if side == "right":
        edge, limit = r[2], min([q[0] for q in bars if q[0] >= r[2] - 1] or [1e9])
        for w in sorted((w for w in line if w[0] >= r[2] - 2), key=lambda w: w[0]):
            if w[0] - edge > (15 if not got else 8) or w[2] > limit + 1 or len(got) >= 8:
                break
            got.append(w[4])
            edge = w[2]
    else:
        edge, limit = r[0], max([q[2] for q in bars if q[2] <= r[0] + 1] or [-1e9])
        for w in sorted((w for w in line if w[2] <= r[0] + 2), key=lambda w: -w[2]):
            if edge - w[2] > (15 if not got else 8) or w[0] < limit - 1 or len(got) >= 8:
                break
            got.insert(0, w[4])
            edge = w[0]
    return " ".join(_WORD.findall(" ".join(got).lower()))


def _short(c: str) -> str:
    c = {"y": "yes", "n": "no"}.get(c, c)
    return c if c and len(c.split()) <= SHORT else ""


def _cen(r) -> tuple:
    return (r[0] + r[2]) / 2, (r[1] + r[3]) / 2


def _neighbours(opts: list, idx: list[int]) -> list[list[int]]:
    parent = {i: i for i in idx}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a in idx:
        for b in idx:
            if a < b and opts[a][0] == opts[b][0]:
                ra, rb = opts[a][1], opts[b][1]
                gx = max(0.0, max(ra[0], rb[0]) - min(ra[2], rb[2]))
                gy = max(0.0, max(ra[1], rb[1]) - min(ra[3], rb[3]))
                if (abs(_cen(ra)[1] - _cen(rb)[1]) <= LINE and gx <= ROW_GAP) or (gx == 0 and gy <= STACK_GAP):
                    parent[find(a)] = find(b)
    out = collections.defaultdict(list)
    for i in idx:
        out[find(i)].append(i)
    return list(out.values())


def split(opts: list, caps: dict[str, list[str]], idx: Optional[list[int]] = None, flagged: bool = False) -> list[list[int]]:
    """A group's pieces (index lists into `opts`, [(page, rect)]); `caps` {side: short caption per option}. One piece,
    the whole group, unless a short caption repeats."""
    idx = list(range(len(opts))) if idx is None else idx
    best = None
    for side, cs in caps.items():
        other = [caps[o][i] for o in caps if o != side for i in idx]
        if other and all(other) and len(set(other)) == len(other):
            continue                     # the other side names every option apart: one question, read that way
        cnt = collections.Counter(cs[i] for i in idx if cs[i])
        rep = [c for c, n in cnt.items() if n > 1]
        if rep:
            top = max(rep, key=lambda c: (cnt[c], c))
            if best is None or cnt[top] > best[0]:
                best = (cnt[top], side, top)
    if not best:
        return _neighbours(opts, idx) if flagged else [idx]
    _, side, top = best
    anchors = [i for i in idx if caps[side][i] == top]
    parts = {a: [a] for a in anchors}
    c = {i: _cen(opts[i][1]) for i in idx}
    reach = {a: min([math.dist(c[a], c[b]) for b in anchors if b != a and opts[b][0] == opts[a][0]] or [1e9])
             for a in anchors}
    aside = []
    for i in idx:
        if i in parts:
            continue
        pool = [a for a in anchors if opts[a][0] == opts[i][0]]
        line = [a for a in pool if abs(c[a][1] - c[i][1]) <= LINE]
        near = line or [a for a in pool if math.dist(c[a], c[i]) < reach[a]]
        if near:
            parts[min(near, key=lambda a: math.dist(c[a], c[i]))].append(i)
        else:
            aside.append(i)
    out = []
    for ps in parts.values():                 # an anchor and its options stay one question unless they repeat again
        out += split(opts, caps, ps)
    if aside:
        out += split(opts, caps, aside, flagged=True)
    return out


def split_groups(groups: list[set[str]], boxes: dict[str, tuple], words: dict[int, list]) -> list[set[str]]:
    """Each group of 2+ split where its options repeat an answer; pieces of one box are loose again. `boxes`: every
    option box on the form, {name: (page, rect)} (the other boxes stop a caption); `words`: {page: page.get_text("words")}."""
    stops = collections.defaultdict(list)
    for p, r in boxes.values():
        stops[p].append(r)
    out = []
    for g in groups:
        names = sorted(n for n in g if n in boxes)
        if len(names) < 2 or len(names) < len(g):
            out.append(g)
            continue
        opts = [boxes[n] for n in names]
        caps = {side: [_short(_read(words.get(p) or [], r, side, stops[p])) for p, r in opts] for side in ("right", "left")}
        pieces = split(opts, caps)
        out += [{names[i] for i in ps} for ps in pieces if len(ps) > 1]
    return out
