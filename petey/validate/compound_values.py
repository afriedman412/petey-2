"""Entities: one value written in several fields next to each other on a line (Andrew, 2026-10-14: a COMPOUND VALUE,
"an SSN in three boxes, a phone in area code / prefix / line"; 2026-10-28: "sequential fields on a single line that
can be combined logically", tagged on the Groups tab as an ENTITY with an entity type, `group_review.ENTITY_TYPES`).
Gathered before blocks are found, so a three-part name and a date are two slots of a block, not six fields whose
spacing must match copy to copy.

The types (`TYPES`, as the Groups tab's) and their parts in reading order (`PARTS`):

    date               month / day / yr          time          hour / minute / ampm
    name               first / middle / last / suffix
    phone              area / prefix / line      id_number     1 / 2 / 3 ... (SSN, EIN, routing, account numbers)
    address_line_1     street / unit             address_line_2   city / county / state / zip / country
    full_address       the whole address on one line ("full address is when the whole address is on one line")
    signature_complex  signature / name / title / date (a signature and its date on one line)
    money              dollars / cents

Lines of one answer stacked one under another are no entity ("that can be something else"), nor is an address over
two lines (its two lines are two).

Three readings, each -> [{"kind": type, "page", "fields": [code, reading order], "parts": [part per field], "rect"}]:

    find(bp)         from the page alone (geometry and the blank's printed words, no names, no widget metadata, so
                     it runs on the light path and before the labeler; see `find`)
    from_tags(bp)    the entities tagged on the Groups tab (`group_review.ENTITY_KEY`): the answer key on the
                     benchmark's pages, whose names are positions
    from_names(bp)   the answer key on validated library blueprints: the part words in the fields' names
                     (dob_dt_month, applicant_first_nm, mailing_city_nm, veteran_ssn_2) and where the fields sit
"""
from __future__ import annotations

import collections
import re
from typing import Optional

from petey.validate import block_types as bt

TYPES = ("date", "time", "address_line_1", "address_line_2", "full_address", "signature_complex", "phone",
         "id_number", "money", "name", "other")          # group_review.ENTITY_TYPES
PARTS = {
    "date": ("month", "day", "yr"), "time": ("hour", "minute", "ampm"),
    "name": ("first", "middle", "last", "suffix"), "phone": ("area", "prefix", "line"),
    "address_line_1": ("street", "unit"), "address_line_2": ("city", "county", "state", "zip", "country"),
    "full_address": ("street", "unit", "city", "county", "state", "zip", "country"),
    "signature_complex": ("signature", "name", "title", "date"), "id_number": (), "money": ("dollars", "cents"),
}
_LINE_2 = set(PARTS["address_line_2"])

LINE_GAP = 60.0       # pt: fields of one value on a line sit at most this far apart, edge to edge (names)


def _value(kind: str, codes: list[str], parts: dict[str, str], at: dict) -> dict:
    """A value's record, its fields in reading order (top to bottom, left to right)."""
    codes = sorted(codes, key=lambda c: (round(at[c]["rect"][1] / 3), at[c]["rect"][0]))
    rs = [at[c]["rect"] for c in codes]
    return {"kind": kind, "page": at[codes[0]]["page"], "fields": codes, "parts": [parts[c] for c in codes],
            "rect": [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]}


def address_type(ps: list[str]) -> Optional[str]:
    """Which address entity these parts make on one line, or None: a street with any of city / state / zip a full
    address, a street with its unit line 1, two or more of city / county / state / zip / country line 2."""
    s = set(ps)
    if len(s) != len(ps):
        return None
    if "street" in s and s & _LINE_2:
        return "full_address"
    if s == {"street", "unit"}:
        return "address_line_1"
    if "street" not in s and len(s & _LINE_2) >= 2:
        return "address_line_2"
    return None


def _enough(kind: str, ps: list[str]) -> bool:
    """A reading is an entity only with two different parts; a name has a first and a last, a signature complex its
    signature."""
    s = set(ps)
    if len(s) < 2 or len(ps) != len(s):
        return False
    if kind == "name":
        return "first" in s and "last" in s
    if kind == "signature_complex":
        return "signature" in s
    return True


def _boxes(bp: dict) -> list[dict]:
    """The text fields as block_types reads them (an option group is never part of an entity), codes as strings."""
    out = [b for b in bt._boxes(bp) if not bt.kind_key(b["kind"]).startswith("choice")]
    for b in out:
        b["code"] = str(b["code"])
    return out


# ---- the answer keys ----

def from_tags(bp: dict) -> list[dict]:
    """The entities tagged on the Groups tab, as values (kind = the entity type, None when none was picked or
    "other"; parts unknown)."""
    from petey.validate import group_review
    at = {b["name"]: b for b in _boxes(bp)}
    out = []
    for u in group_review.entity_units(bp):
        ms = [at[m] for m in u["items"] if m in at]
        if len(ms) < 2:
            continue
        t = u.get("entity_type")
        out.append(_value(t if t in PARTS else None, [b["code"] for b in ms], {b["code"]: "" for b in ms},
                          {b["code"]: b for b in ms}))
    return out


_NAME_PART = {"first": "first", "given": "first", "middle": "middle", "mi": "middle", "initial": "middle",
              "last": "last", "family": "last", "surname": "last", "suffix": "suffix"}
_ADDR_PART = {"street": "street", "address": "street", "apt": "unit", "unit": "unit", "suite": "unit",
              "city": "city", "town": "city", "county": "county", "state": "state", "province": "state",
              "zip": "zip", "postal": "zip", "country": "country"}
_DATE_PART = {"month": "month", "mo": "month", "mm": "month", "day": "day", "dd": "day", "yr": "yr", "year": "yr",
              "yyyy": "yr"}
_PHONE_PART = {"area": "area", "prefix": "prefix", "line": "line", "local": "line", "exchange": "prefix"}
_PHONE = {"phone", "telephone", "tel", "fax", "cell", "mobile"}
_FILLER = {"nm", "cd", "txt", "nbr", "dt", "amt", "ssn", "ein", "or", "and", "code", "name", "number", "of"}


def _part_of(tokens: list[str]) -> Optional[tuple[str, str, list[str]]]:
    """(kind, part, the name without its part words) for a field name's tokens, or None; an address's kind is
    "address" until its line's parts say which (`address_type`)."""
    t = tokens
    if "dt" in t or "date" in t or "dob" in t:
        hit = [i for i, w in enumerate(t) if w in _DATE_PART]
        if hit:
            return "date", _DATE_PART[t[hit[-1]]], t[:hit[-1]] + t[hit[-1] + 1:]
    if _PHONE & set(t):
        hit = [i for i, w in enumerate(t) if w in _PHONE_PART]
        if hit and t[hit[-1]] != "line" or (hit and t[hit[-1]] == "line" and "nbr" in t):
            return "phone", _PHONE_PART[t[hit[-1]]], t[:hit[-1]] + t[hit[-1] + 1:]
    for k in ("ssn", "ein"):
        if k in t and t[-1].isdigit() and t.index(k) == len(t) - 2:
            return "id_number", t[-1], t[:-1]
        if k in t and re.fullmatch(r"part\d", t[-1]):
            return "id_number", t[-1][4:], t[:-1]
    if "amt" in t and t[-1] in ("dollars", "cents"):
        return "money", t[-1], t[:-1]
    hit = [i for i, w in enumerate(t) if w in _NAME_PART]
    if hit and ("nm" in t or "name" in t or {"mi", "initial"} & set(t)) and "amt" not in t and "dt" not in t:
        i = hit[0]
        return "name", _NAME_PART[t[i]], t[:i] + t[i + 1:]
    hit = [i for i, w in enumerate(t) if w in _ADDR_PART]
    if hit and "dt" not in t and "amt" not in t:
        return "address", _ADDR_PART[t[hit[0]]], t[:hit[0]]
    return None


def _stem(tokens: list[str]) -> str:
    return "_".join(w for w in tokens if w not in _FILLER)


def _same_line(a: list, b: list) -> bool:
    return min(a[3], b[3]) - max(a[1], b[1]) > 0.4 * min(a[3] - a[1], b[3] - b[1])


def _chains(items: list[tuple[str, list]]) -> list[list[str]]:
    """Single-link clusters of (code, rect): on one line within `LINE_GAP` of each other."""
    parent = {c: c for c, _ in items}

    def root(c):
        while parent[c] != c:
            parent[c] = parent[parent[c]]
            c = parent[c]
        return c
    for i, (c, r) in enumerate(items):
        for d, s in items[i + 1:]:
            if _same_line(r, s) and max(r[0], s[0]) - min(r[2], s[2]) <= LINE_GAP:
                parent[root(c)] = root(d)
    out = collections.defaultdict(list)
    for c, _ in items:
        out[root(c)].append(c)
    return list(out.values())


def from_names(bp: dict) -> list[dict]:
    """The entities the fields' names describe, one line each."""
    boxes = _boxes(bp)
    at = {b["code"]: b for b in boxes}
    by = collections.defaultdict(list)
    parts: dict[str, str] = {}
    for b in boxes:
        got = _part_of(b["name"].split("_"))
        if not got:
            continue
        kind, part, rest = got
        parts[b["code"]] = part
        by[(b["page"], kind, _stem(rest))].append(b["code"])
    out = []
    for (pg, kind, _), codes in by.items():
        if len(codes) < 2:
            continue
        for chain in _chains([(c, at[c]["rect"]) for c in codes]):
            ps = [parts[c] for c in chain]
            k = address_type(ps) if kind == "address" else kind if _enough(kind, ps) else None
            if k:
                out.append(_value(k, chain, parts, at))
    return sorted(out, key=lambda v: (v["page"], v["rect"][1], v["rect"][0]))


# ---- from the page ----

RUN_GAP = 48.0        # pt: fields of one value along a line, edge to edge, at most this far apart
RUN_OVERLAP = 4.0     # pt: ... or overlapping this much (comb cells drawn a few points into each other)
HEIGHT_SHARE = 0.6    # ... and their heights at least this alike
ABOVE, BELOW = 14.0, 11.0   # pt: a field's caption printed this far above its top, or under its bottom
PHRASE_GAP = 6.0      # pt: words of one caption phrase sit closer than this (CMS-116: "TELEPHONE NO. (Include area
                      # code)" 9 pt before "FAX NO.")
PART_WIDTH = {"date": 90.0, "time": 60.0, "phone": 140.0, "id_number": 140.0}   # pt: a digits part at most this wide
COMB_WIDTH = 25.0     # pt: an ID number in more than 9 fields is one digit a field, each at most this wide
SIGNATURE_GAP = 260.0  # pt: a signature and its date on one line at most this far apart

# part words, printed: what a field's own caption says it is (the closed list of very common words, Andrew's
# no-hard-coding rule aside: "unless extremely common"); an address's type follows from its line's parts
_PRINTED = {
    "name": {"first": "first", "given": "first", "middle": "middle", "mi": "middle", "m.i.": "middle",
             "initial": "middle", "initials": "middle", "last": "last", "family": "last", "surname": "last",
             "suffix": "suffix", "jr": "suffix"},
    "address": {"street": "street", "address": "street", "apt": "unit", "apartment": "unit", "suite": "unit",
                "ste": "unit", "unit": "unit", "lot": "unit", "room": "unit", "flr": "unit", "city": "city",
                "town": "city", "county": "county", "state": "state", "province": "state", "zip": "zip",
                "postal": "zip", "country": "country"},
    "date": {"month": "month", "mo": "month", "mm": "month", "day": "day", "dd": "day", "year": "yr", "yr": "yr",
             "yyyy": "yr", "yy": "yr"},
    "time": {"hour": "hour", "hr": "hour", "hh": "hour", "minute": "minute", "minutes": "minute", "am": "ampm",
             "pm": "ampm", "a.m.": "ampm", "p.m.": "ampm"},
}
_KIND_WORDS = {      # one caption over a run names its kind
    "id_number": ("social security", "ssn", "employer identification", "fein", "ein", "tax id", "taxpayer id",
                  "tin", "itin", "routing", "account number", "account no", "identification number", "id number",
                  "id no"),
    "phone": ("phone", "telephone", "tel.", "fax", "area code", "mobile", "cell"),
    "time": ("time",),
    "date": ("date", "dob", "birth"),
}
_DATE_PATTERN = re.compile(r"\b(mm|dd|yy|yyyy|month|day|year)\b[\s/.\-]*(mm|dd|yy|yyyy|month|day|year)\b")
_TOKEN = re.compile(r"[a-z][a-z.]*")
_SEPARATOR = set("()/-–—.:")
_ITEM = re.compile(r"\(?[0-9a-z]{1,4}[.)]?\)?")      # 4., vi., (a), 12b: an item's number, no caption
_SIGNED = re.compile(r"\bsignature|\bsigned\b|\bsign here\b")
_DATED = re.compile(r"\bdated?\b")
_SIGN_ALSO = {"name": re.compile(r"\bname\b"), "title": re.compile(r"\btitle\b")}


def _words_over(words: list, x0: float, x1: float, y_lo: float, y_hi: float) -> list:
    """The words whose middle is over [x0, x1] with their bottom (above) or top (below) in [y_lo, y_hi]."""
    return [w for w in words if x0 - 2 <= (w[0] + w[2]) / 2 <= x1 + 2 and y_lo <= (w[1] + w[3]) / 2 <= y_hi]


def _label_left(words: list, r: list) -> list:
    """The words printed just before a box on its line (chained leftward, gaps under 12 pt, the first within 40)."""
    line = sorted((w for w in words if r[1] - 2 <= (w[1] + w[3]) / 2 <= r[3] + 2 and w[2] <= r[0] + 2),
                  key=lambda w: -w[2])
    out, edge = [], r[0]
    for w in line:
        if edge - w[2] > (40 if not out else 12):
            break
        out.append(w)
        edge = w[0]
    return out[::-1]


def _own_words(b: dict, words: list, side: str, page: list = ()) -> list:
    """A field's own caption: above it, printed inside it and the label before it on its line (`side` "above"), or
    under it, the words nearer to it than to a field below them ("below": the next row's captions are its)."""
    x0, y0, x1, y1 = b["rect"]
    if side == "above":
        return (_words_over(words, x0, x1, y0 - ABOVE, y0 + 1)
                + [w for w in words if w[0] >= x0 - 1 and w[2] <= x1 + 1 and w[1] >= y0 - 1 and w[3] <= y1 + 1]
                + _label_left(words, b["rect"]))
    return [w for w in _words_over(words, x0, x1, y1 - 1, y1 + BELOW)
            if not any(o["rect"][1] >= w[1] and o["rect"][1] - w[3] < w[1] - y1
                       and min(o["rect"][2], w[2]) > max(o["rect"][0], w[0]) for o in page)]


def _part_words(ws: list) -> list[tuple[str, str]]:
    """(kind, part) for each part word among these words, in reading order."""
    out = []
    for w in sorted(ws, key=lambda w: (round(w[1] / 3), w[0])):
        got = []
        for tok in _TOKEN.findall(w[4].lower()):
            for kind, parts in _PRINTED.items():
                p = parts.get(tok) or parts.get(tok.rstrip("."))
                if p:
                    got.append((kind, p))
        if len(set(got)) == 1:          # STATE/PROVINCE is one part; (MM-DD-YYYY), City/State a pattern or several
            out.append(got[0])
    return out


def _text(ws: list) -> str:
    return " ".join(w[4] for w in sorted(ws, key=lambda w: (round(w[1] / 3), w[0]))).lower()


def _runs(boxes: list[dict]) -> list[list[dict]]:
    """The page's text fields chained along lines: neighbours on one line, alike in height, within `RUN_GAP` (or
    overlapping up to `RUN_OVERLAP`), no other field between them."""
    out, used = [], set()
    rows = sorted(boxes, key=lambda b: (b["rect"][1], b["rect"][0]))
    for b in rows:
        if b["code"] in used:
            continue
        run, r = [b], b["rect"]
        while True:
            h = r[3] - r[1]
            nxt = [c for c in boxes if c["code"] not in used and c not in run
                   and c["rect"][0] >= r[2] - RUN_OVERLAP and c["rect"][0] > r[0] and c["rect"][0] - r[2] <= RUN_GAP
                   and min(c["rect"][3], r[3]) - max(c["rect"][1], r[1]) > 0.5 * min(h, c["rect"][3] - c["rect"][1])
                   and min(h, c["rect"][3] - c["rect"][1]) >= HEIGHT_SHARE * max(h, c["rect"][3] - c["rect"][1])]
            if not nxt:
                break
            c = min(nxt, key=lambda c: c["rect"][0])
            run.append(c)
            r = c["rect"]
        used |= {c["code"] for c in run}
        out.append(run)
    return out


def _segments(run: list[dict], words: list, side: str = "above") -> list[list[dict]]:
    """A run cut where a caption starts over (`side` "above") or under ("below") one of its fields: the text line just
    above (below) the run, in phrases (words within `PHRASE_GAP` of each other), each phrase's first word starting the
    field it is over or the next one along (2026-10-28: VA 21-686c's SSN, VA file number and date of birth chain into
    one run of seven fields; the benchmark's phones under "Telephone No." into their neighbours)."""
    if len(run) < 2:
        return [run]
    x0, x1 = run[0]["rect"][0], run[-1]["rect"][2]
    y0, y1 = min(b["rect"][1] for b in run), max(b["rect"][3] for b in run)
    if side == "above":
        near_line = [w for w in words if x0 - 40 <= w[0] <= x1 and y0 - ABOVE <= (w[1] + w[3]) / 2 <= y0 + 1]
    else:
        near_line = [w for w in words if x0 - 40 <= w[0] <= x1 and y1 - 1 <= (w[1] + w[3]) / 2 <= y1 + BELOW]
    if not near_line:
        return [run]
    if side == "above":
        near = max(w[3] for w in near_line)
        line = sorted((w for w in near_line if w[3] >= near - 4), key=lambda w: w[0])
    else:
        near = min(w[1] for w in near_line)
        line = sorted((w for w in near_line if w[1] <= near + 4), key=lambda w: w[0])
    starts = [line[0][0]] + [b[0] for a, b in zip(line, line[1:]) if b[0] - a[2] > PHRASE_GAP]
    cuts = set()
    for x in starts:
        k = next((i for i, b in enumerate(run) if x < b["rect"][2] - 2), None)
        if k:
            cuts.add(k)
    out, cur = [], [run[0]]
    for i, b in enumerate(run[1:], 1):
        if i in cuts:
            out.append(cur)
            cur = []
        cur.append(b)
    return out + [cur]


def _by_own(run: list[dict], words: list, page: list = ()) -> list[tuple[str, list[dict], list[str]]]:
    """(type, fields, parts) for each stretch of a run whose own captions name parts of one kind, read above the
    fields or under them, whichever explains more fields (FMCSA MCS-150B: "Same as principal address" above the
    mailing address, its captions under it); an address stretch typed by its parts (`address_type`)."""
    best: list = []
    for side in ("above", "below"):
        parts = [(_part_words(_own_words(b, words, side, page)) or [None])[0] for b in run]
        found, i = [], 0
        while i < len(run):
            if not parts[i]:
                i += 1
                continue
            kind, j = parts[i][0], i
            while j + 1 < len(run) and parts[j + 1] and parts[j + 1][0] == kind \
                    and parts[j + 1][1] not in [p[1] for p in parts[i:j + 1]]:
                j += 1
            ps = [p[1] for p in parts[i:j + 1]]
            k = address_type(ps) if kind == "address" else kind if _enough(kind, ps) else None
            if k:
                found.append((k, run[i:j + 1], ps))
            i = j + 1
        if sum(len(f[1]) for f in found) > sum(len(f[1]) for f in best):
            best = found
    return best


def _spanning(run: list[dict], words: list, page: list = ()) -> Optional[tuple[str, list[str]]]:
    """(type, parts) when one caption over a run of 2-20 fields names a kind of value: printed above the run (one
    phrase, not one caption per field), under it (nearer to it than to the next row), as the label before its first
    field, or inside it (separators)."""
    n = len(run)
    if not 2 <= n <= 20:
        return None
    x0, y0 = run[0]["rect"][0], min(b["rect"][1] for b in run)
    x1, y1 = run[-1]["rect"][2], max(b["rect"][3] for b in run)
    above = _words_over(words, x0, x1, y0 - ABOVE, y0 + 1)
    inside = [w for w in words if w[0] >= x0 - 1 and w[2] <= x1 + 1 and w[1] >= y0 - 1 and w[3] <= y1 + 1]
    if any(not set(w[4]) <= _SEPARATOR and not _TOKEN.fullmatch(w[4].lower().strip("()")) for w in inside):
        return None                               # printed words between the fields: they are separate answers
    # one caption per field above it (Home phone | Work phone) is several answers, not one
    heads = [b for b in run if _words_over(words, b["rect"][0], b["rect"][2], y0 - ABOVE, y0 + 1)]
    if len(heads) == n and n > 1 and not _DATE_PATTERN.search(_text(above)):
        gaps = sorted(above, key=lambda w: w[0])
        if any(b[0] - a[2] > 15 for a, b in zip(gaps, gaps[1:])):
            return None
    left = _label_left(words, run[0]["rect"])
    under = [w for w in _words_over(words, x0, x1, y1 - 1, y1 + BELOW)
             if not any(o["rect"][1] >= w[1] and o["rect"][1] - w[3] < w[1] - y1
                        and min(o["rect"][2], w[2]) > max(o["rect"][0], w[0]) for o in page)]
    cap = _text(above + inside + left + under)
    widths = [b["rect"][2] - b["rect"][0] for b in run]
    # ( ___ ) ___: a bracket printed before the first field and closed after it, an area code
    bracketed = n in (2, 3) and left and left[-1][4].endswith("(") and any(")" in w[4] for w in inside)
    m = _DATE_PATTERN.search(cap)
    if m and n in (2, 3):
        order = re.findall(r"\b(mm|dd|yyyy|yy|month|day|year)\b", cap[m.start():])
        order = order[:next((i for i in range(1, len(order)) if order[i] in order[:i]), len(order))]
        ps = [_PRINTED["date"][o] for o in order]   # the whole pattern, once: MM/DD/YYYY - MM/DD/YYYY over two
        ok = len(ps) == n and len(set(ps)) == n and max(widths) <= PART_WIDTH["date"]   # fields is two dates
        return ("date", ps) if ok else None
    for kind, cues in _KIND_WORDS.items():
        if any(re.search(r"(?<![a-z])" + re.escape(c) + r"(?![a-z])", cap) for c in cues) or \
                (kind == "phone" and bracketed):
            if max(widths) > PART_WIDTH[kind] or (kind == "phone" and widths[0] > 0.8 * widths[-1]):
                return None                       # a digits part is short; an area code shorter than the number
            if kind == "id_number":
                if n > 9 and max(widths) > COMB_WIDTH:
                    return None                   # past 9 fields only one digit a field
                return kind, [str(i + 1) for i in range(n)]
            if n > 3:
                return None
            if kind == "date":
                return ("date", ["month", "day", "yr"]) if n == 3 else None
            if kind == "time":
                return "time", ["hour", "minute", "ampm"][:n]
            return "phone", (["area", "prefix", "line"] if n == 3 else ["area", "line"])
    listed = next((x for x in re.findall(r"\(([a-z ,.]+)\)", cap) if "," in x), None)
    if listed:              # (First, Middle Initial, Last): one part per item, in order
        got = [_part_words([(0, 0, 0, 0, item)]) for item in listed.split(",")]
        got = [g[0] for g in got if g]
        kinds = {k for k, _ in got}
        ps = [p for _, p in got]
        if len(ps) == n and len(kinds) == 1 and next(iter(kinds)) == "name" and _enough("name", ps):
            return "name", ps
    return None


def _repeats(found: list[dict], runs: list[list[dict]], taken: set, at: dict) -> list[dict]:
    """Rows laid out as a value found just above them, with no captions of their own (the captions printed once over
    the first row: I-129's other names, 1095-B's covered individuals), are values of the same kind and parts: each
    field's left edge and width within 4 pt of the one above it, the rows within three row heights of each other."""
    out = []
    for v in sorted(found, key=lambda v: v["rect"][1]):
        if len({round(at[c]["rect"][1]) for c in v["fields"]}) != 1:
            continue
        cur = sorted(v["fields"], key=lambda c: at[c]["rect"][0])
        parts = dict(zip(v["fields"], v["parts"]))
        while True:
            top = at[cur[0]]["rect"]
            h = top[3] - top[1]
            nxt = None
            for run in runs:
                cs = [b for b in run if b["code"] not in taken]
                for i in range(len(cs) - len(cur) + 1):
                    seg = cs[i:i + len(cur)]
                    if all(abs(b["rect"][0] - at[c]["rect"][0]) <= 4 and
                           abs((b["rect"][2] - b["rect"][0]) - (at[c]["rect"][2] - at[c]["rect"][0])) <= 4
                           for b, c in zip(seg, cur)) and 0 < seg[0]["rect"][1] - top[3] <= 3 * h:
                        nxt = seg
                        break
                if nxt:
                    break
            if not nxt:
                break
            codes = [b["code"] for b in nxt]
            out.append(_value(v["kind"], codes, {b["code"]: parts[c] for b, c in zip(nxt, cur)}, at))
            taken |= set(codes)
            parts = {b["code"]: parts[c] for b, c in zip(nxt, cur)}
            cur = codes
    return out


def _signatures(bs: list[dict], words: list, taken: set, at: dict) -> list[dict]:
    """A signature and its date on one line (Andrew's "signature complex"): a field whose own caption says signature
    (above, inside, before or under it) and the nearest field along its line, within `SIGNATURE_GAP`, whose caption
    says date; fields between them captioned name or title join them; any other field between, they are apart."""
    def cap(b: dict) -> str:
        return _text(_own_words(b, words, "above", bs) + _own_words(b, words, "below", bs))
    caps = {b["code"]: cap(b) for b in bs if b["code"] not in taken}
    out = []
    for b in bs:
        c = caps.get(b["code"])
        if c is None or not _SIGNED.search(c) or b["code"] in taken:
            continue
        line = sorted((o for o in bs if o is not b and _same_line(o["rect"], b["rect"])), key=lambda o: o["rect"][0])
        best = None
        for o in line:
            oc = caps.get(o["code"])
            gap = max(o["rect"][0], b["rect"][0]) - min(o["rect"][2], b["rect"][2])
            if oc is None or gap > SIGNATURE_GAP or not _DATED.search(oc) or _SIGNED.search(oc) or "birth" in oc:
                continue
            if best is None or gap < best[0]:
                best = (gap, o)
        if not best:
            continue
        d = best[1]
        lo, hi = sorted((b["rect"][0], d["rect"][0]))
        between = [o for o in line if lo < o["rect"][0] < hi and o is not d]
        extra = {}
        for o in between:
            oc = caps.get(o["code"]) or ""
            hit = next((p for p, rx in _SIGN_ALSO.items() if rx.search(oc)), None)
            if hit is None or hit in extra.values():
                extra = None
                break
            extra[o["code"]] = hit
        if extra is None:
            continue
        parts = {b["code"]: "signature", d["code"]: "date", **extra}
        out.append(_value("signature_complex", list(parts), parts, at))
        taken |= set(parts)
    return out


def find(bp: dict, pw=None) -> list[dict]:
    """The form's entities from the page: [{kind, page, fields, parts, rect}], text fields only; nothing without a
    blank (no printed words)."""
    from petey.validate.same_box import PageWords
    pw = pw or PageWords(bp)
    boxes = _boxes(bp)
    at = {b["code"]: b for b in boxes}
    out = []
    by_page = collections.defaultdict(list)
    for b in boxes:
        by_page[b["page"]].append(b)
    for pg, bs in sorted(by_page.items()):
        words = pw.words(pg)
        if not words:
            continue
        found = []
        runs = _runs(bs)
        for run in runs:
            got = _by_own(run, words, bs)
            for kind, fs, ps in got:
                found.append(_value(kind, [b["code"] for b in fs], dict(zip([b["code"] for b in fs], ps)), at))
            if got:
                continue
            # the run cut by the captions over it or by those under it, whichever explains more fields
            best: list = []
            for side in ("above", "below"):
                got = [(seg, sp) for seg in _segments(run, words, side) for sp in [_spanning(seg, words, bs)] if sp]
                if sum(len(seg) for seg, _ in got) > sum(len(seg) for seg, _ in best):
                    best = got
            for seg, (kind, ps) in best:
                codes = [b["code"] for b in seg]
                found.append(_value(kind, codes, dict(zip(codes, ps)), at))
        taken = {c for v in found for c in v["fields"]}
        found += _repeats(found, runs, taken, at)
        found += _signatures(bs, words, {c for v in found for c in v["fields"]}, at)
        out += found
    return sorted(out, key=lambda v: (v["page"], v["rect"][1], v["rect"][0]))
