"""Field names to the shape in docs/NAMING.md, on COPIES (Andrew, 2026-10-14: "lets do copies for now so we can
workshop the higher-level structure"): runs/standardized/<id>/<file>.bpt, the renames recorded on the copy as
`x_petey_standardized` {old: new}. The source blueprints are never written.

Shape: [description]_[iteration if needed]_[suffix]_[part] (Andrew, 2026-10-14). A number before the suffix is an
iteration (loss_occurrence_2_dt), what comes after it is a part of one value (veteran_ssn_1, birth_dt_month,
daytime_phone_nbr_area, premium_amt_cents); `part_sets` tells existing parts from iterations: named parts by their
words, numbered ones only when the boxes sit side by side on one line.

What it does, in order, per field (option groups keep their names: a group is named for its question, no suffix):

    1. glued numbers become words: parent1 -> parent_1, address_line1 -> address_line_1 (two-letter stems such as
       q5, p2, w2, i9 stay: they are item or form numbers)
    2. a number after the suffix moves before it: agency_customer_id_2 -> agency_customer_2_nbr
    3. the tail takes the standard suffix: _name -> _nm, _number / _num / _no / _id -> _nbr, _code -> _cd,
       _date -> _dt, _year / _yyyy -> _yr, _mm -> _month, _dd -> _day, _signature_txt -> _signature, bare
       _description / _address / _explanation get _txt, bare state / country / zip get _cd, state_abbreviation_cd / state_abbr -> state_cd, the apartment / suite /
       unit spellings become unit_nbr
    4. a name with still no suffix gets one from its type when that is unambiguous (a count -> _cnt, a single
       checkbox -> _ind, money -> _amt); otherwise it is listed as unplaced, not guessed
    0. per form: duplicates the labeler counted from zero (name, name_1, name_2) count from one (name_1, name_2,
       name_3)
    5. per form: when a thing is numbered from 2 up, the un-numbered first one gets its 1 (parent_nm + parent_2_nm ->
       parent_1_nm)

A rename that would collide with another field is skipped and listed.

    PYTHONPATH=. venv/bin/python eval/standardize_names.py lib__i130 lib__acord125 ...   [--all-validated]

`--apply` (2026-10-15, the next tranche: Andrew reviews the standardized names, so they go in before the page check)
writes the renames into the review page's working copy instead (`draft`), each a correction by Claude
(`x_petey_hand_edit` {by: claude, kind: name, why}), still skipping clashes; the copy under runs/standardized/ is
written too.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml

from petey.paths import RUNS
from petey.validate import hand_review as h

OUT = RUNS / "standardized"
SUFFIXES = {"nm", "nbr", "ssn", "ein", "tin", "npi", "cd", "dt", "month", "day", "yr", "time", "amt", "cnt", "qty", "pct",
            "ft", "miles", "hours", "bbl", "mcf", "ind", "txt", "signature", "initial", "itin", "ptin",
            "rate", "factor"}             # rate / factor: provisional (2026-10-14, to confirm with Andrew)
UNIT = [("apt", "ste", "flr", "number", "txt"), ("apt", "ste", "flr", "number"), ("apt", "suite", "no"), ("apt", "suite", "nbr"),
        ("apt", "no", "txt"), ("apt", "no"), ("apt", "nbr"), ("apt", "num"), ("unit", "number", "txt"), ("unit", "number"),
        ("unit", "nbr"), ("unit", "no"), ("unit", "txt"), ("unit",), ("ste", "num"), ("suite", "no"), ("suite", "nbr"),
        ("apt", "suite", "no")]
# (tail tokens, replacement tokens, only for these field types or None); longest tails are tried first
TAIL = [(u, ("unit", "nbr"), None) for u in UNIT] + [
    (("name", "txt"), ("nm",), None), (("nm", "txt"), ("nm",), None), (("name",), ("nm",), None),
    (("signature", "txt"), ("signature",), None), (("sig",), ("signature",), None),
    (("number", "txt"), ("nbr",), None), (("number",), ("nbr",), ("string", "integer", None)), (("num",), ("nbr",), None),
    (("no",), ("nbr",), ("string", None)), (("id",), ("nbr",), ("string", None)),
    (("code",), ("cd",), None), (("date",), ("dt",), None), (("year",), ("yr",), None), (("yyyy",), ("yr",), None),
    (("mm",), ("month",), None), (("dd",), ("day",), None),
    (("zip", "code", "txt"), ("zip", "cd"), None), (("zip", "code"), ("zip", "cd"), None), (("zip", "txt"), ("zip", "cd"), None),
    (("zip",), ("zip", "cd"), None), (("postal", "code", "txt"), ("postal", "cd"), None), (("postal", "code"), ("postal", "cd"), None),
    (("state", "abbreviation", "cd"), ("state", "cd"), None), (("state", "abbr", "cd"), ("state", "cd"), None),
    (("state", "abbr"), ("state", "cd"), None), (("state", "abbreviation"), ("state", "cd"), None),
    (("state", "txt"), ("state", "cd"), ("string",)), (("state",), ("state", "cd"), ("string",)),
    (("country", "txt"), ("country", "cd"), ("string",)), (("country",), ("country", "cd"), ("string",)),
    (("description",), ("description", "txt"), ("string",)), (("desc",), ("desc", "txt"), ("string",)),
    (("explanation",), ("explanation", "txt"), ("string",)), (("address",), ("address", "txt"), ("string",)),
    (("phone",), ("phone", "nbr"), ("string", None)), (("telephone",), ("telephone", "nbr"), ("string", None)),
    (("fax",), ("fax", "nbr"), ("string", None)), (("dob",), ("dob", "dt"), None),
    (("sic",), ("sic", "cd"), None), (("naics",), ("naics", "cd"), None), (("ptan",), ("ptan", "nbr"), None),
    *[((w,), (w, "txt"), ("string",)) for w in ("classifications", "sources", "resolution", "relationship", "province",
                                               "info", "comments", "remarks", "notes", "reason", "purpose")],
]
# a percentage of something is _pct, not _qty (Andrew, 2026-10-15)
TAIL += [((w, x), ("pct",), None) for w in ("percent", "percentage") for x in ("qty", "cnt", "txt", "nbr")] + \
        [(("percent",), ("pct",), None), (("percentage",), ("pct",), None), (("pct", "qty"), ("pct",), None)]
TAIL.sort(key=lambda t: -len(t[0]))

# parts of one value (a compound value) come AFTER the suffix: [description]_[iteration]_[suffix]_[part] (Andrew,
# 2026-10-14). Named parts by the words; numbered parts by where the boxes sit (side by side on one line)
DATE_PARTS = {"month": "month", "mm": "month", "mo": "month", "day": "day", "dd": "day", "year": "yr", "yyyy": "yr",
              "yr": "yr", "yy": "yr"}
PHONE_PARTS = {("area", "code"): "area", ("area", "cd"): "area", ("prefix",): "prefix", ("line", "number"): "line",
               ("last", "four", "num"): "line", ("last", "four", "nbr"): "line", ("last", "four"): "line",
               ("line", "nbr"): "line", ("exchange",): "prefix"}
MONEY_PARTS = {"dollars": "dollars", "cents": "cents"}
NUM_PART = re.compile(r"^(?P<stem>.+?)_(?:(?P<kw>part|pt|digit)_?)?(?P<n>\d)(?:_(?P<suf>[a-z]{2,4}))?$")


def _is_group(spec: dict) -> bool:
    """An option group (several boxes answering one question): named for the question, no suffix. A dropdown is one
    box with a list (type category, `values`) and takes a suffix like any field (I-485's state lists: _state_cd)."""
    return len(spec.get("widgets") or {}) > 1 or (spec.get("type") in ("category", "multi_category")
                                                   and not spec.get("widget") and not spec.get("values"))


def _split_glued(toks: list[str]) -> list[str]:
    out = []
    for t in toks:
        m = re.fullmatch(r"([a-z]{3,})(\d+)", t)
        out += [m[1], m[2]] if m else [t]
    return out


def _box(spec: dict):
    w = spec.get("widget") or {}
    return w.get("page"), w.get("rect")


# compound values are a closed list of kinds (Andrew, 2026-10-14: "we can limit compound values to specific examples"):
# {kind: (words that name the kind, {number of boxes: part names in reading order}, suffix)}
KINDS = {
    "phone": ({"phone", "telephone", "tel", "fax"}, {3: ["area", "prefix", "line"], 2: ["area", "local"]}, "nbr"),
    "date": ({"dt", "date", "dob", "birth"}, {3: ["month", "day", "yr"], 2: ["month", "yr"]}, "dt"),
    "ssn": ({"ssn"}, {3: ["1", "2", "3"]}, "ssn"),
    "ein": ({"ein", "fein"}, {2: ["1", "2"]}, "ein"),
    "zip": ({"zip"}, {2: ["1", "2"]}, "cd"),
    "money": ({"amt", "dollars", "cents"}, {2: ["dollars", "cents"]}, "amt"),
}
PART_WORDS = ("area_code", "area_cd", "prefix", "line_number", "last_four_num", "last_four", "middle_three_num", "local_num", "month",
              "mm", "mo", "day", "dd", "year", "yyyy", "yr", "yy", "dollars", "cents")
_STRIP = re.compile(r"_(?:" + "|".join(sorted(PART_WORDS, key=len, reverse=True)) + r"|num_\d|nbr_\d|number|num|\d|part_?\d|digit_?\d)$")
_NAMED_PART = {"area_code": "area", "area_cd": "area", "prefix": "prefix", "middle_three_num": "prefix", "line_number": "line",
               "last_four_num": "line", "last_four": "line", "local_num": "line", "month": "month", "mm": "month", "mo": "month", "day": "day",
               "dd": "day", "year": "yr", "yyyy": "yr", "yr": "yr", "yy": "yr", "dollars": "dollars", "cents": "cents"}
_PART_RX = re.compile(r"_(" + "|".join(sorted(_NAMED_PART, key=len, reverse=True)) + r")$")
GENERIC = {"txt", "nbr", "num", "number", "cd", "code", "dt", "date", "amt", "nm", "name", "ind", "1", "2", "3"}


def _base(name: str) -> str:
    """The name without its part word: billing_dentist_phone_area_cd -> billing_dentist_phone; veteran_ssn_part1_p10
    -> veteran_ssn_p10."""
    name = re.sub(r"_(?:part|digit)_?\d(?=_|$)", "", name)
    prev = None
    while prev != name:
        prev, name = name, _STRIP.sub("", name)
    return name


def part_sets(fields: dict) -> dict[str, tuple[str, str, str]]:
    """{field: (stem, kind, part)} for the boxes of one compound value. A run of small boxes side by side on one line
    (each gap within 2.5 box heights), whose names share their words, and which names a kind (KINDS) or its parts:
    a phone in area code / prefix / line (billing_dentist_phone_area_cd, _prefix, _num_3), a date in month / day /
    year, an SSN in three. The part names come from the kind, in reading order, so mixed spellings end up alike. Boxes
    the form calls parts or digits (eligibility_category_part1, weight_pounds_digit2_qty) are one value too."""
    boxes = [(n, sp, _box(sp)) for n, sp in fields.items() if isinstance(sp, dict) and not _is_group(sp)]
    by_page = collections.defaultdict(list)
    for n, sp, (pg, r) in boxes:
        if r:
            by_page[pg].append((r, n))
    out = {}
    for pg, items in by_page.items():
        # rows: centres within 3 pt of the row's first box (a fixed grid split DS-11's SSN at y 224 / 225)
        items.sort(key=lambda x: (x[0][1] + x[0][3]) / 2)
        rows, cur, cy0 = [], [], None
        for r, n in items:
            cy = (r[1] + r[3]) / 2
            if cur and abs(cy - cy0) > 3:
                rows.append(cur)
                cur = []
            if not cur:
                cy0 = cy
            cur.append((r, n))
        if cur:
            rows.append(cur)
        rows = {k: v for k, v in enumerate(rows)}
        for row in rows.values():
            row.sort(key=lambda x: x[0][0])
            i = 0
            while i < len(row):
                j = i + 1
                base = _base(row[i][1])
                while j < len(row):           # same name once the part words are gone: daytime_phone_area_cd and
                    (a, _), (b, nb) = row[j - 1], row[j]          # daytime_phone_number, not daytime / mobile_phone
                    h_ = max(1.0, a[3] - a[1], b[3] - b[1])
                    if b[0] - a[2] > max(2.5 * h_, 18) or _base(nb) != base:
                        break
                    j += 1
                run = [n for _, n in row[i:j]]
                i = j
                if len(run) < 2:
                    continue
                stem = _base(run[0])
                toks = set("_".join(run).split("_"))
                said = all(re.search(r"_(?:part|digit)_?\d(?=_|$)", n) for n in run)
                kind = next((k for k, (cue, shapes, _) in KINDS.items() if len(run) in shapes and (toks & cue)), None)
                if kind == "date" and not any(re.search(r"_(month|mm|mo|day|dd|year|yyyy|yr|yy)$", n) for n in run):
                    kind = None                                 # dt in several boxes needs a date part word
                if kind:
                    # a part word in the name wins (treating_dentist_phone_area_cd + _prefix: area, prefix); the
                    # rest take the kind's parts in reading order
                    named = {n: _NAMED_PART.get(m.group(1)) for n in run if (m := _PART_RX.search(n))}
                    free = [p for p in KINDS[kind][1][len(run)] if p not in named.values()]
                    for n in run:
                        out[n] = (stem, kind, named.get(n) or (free.pop(0) if free else str(run.index(n) + 1)))
                elif said:
                    for k, n in enumerate(run, 1):
                        out[n] = (stem, "parts", str(k))
    return out


def standard(name: str, spec: dict, part: tuple | None = None) -> tuple[str, list[str]]:
    """(new name, what was changed); the name itself when nothing applies. `part`: (stem, family, part) when the
    field is one box of a compound value, which keeps the part after the suffix."""
    if _is_group(spec):                  # a group keeps its name (no suffix); only its glued numbers split
        split = "_".join(_split_glued(name.split("_")))
        return split, (["number split off"] if split != name else [])
    toks0 = name.split("_")
    if (not part and len(toks0) > 2 and toks0[-2] == "line" and toks0[-1].isdigit() and spec.get("type") in ("string", None)
            and "address" not in toks0 and toks0[-3] not in ("number", "nbr", "num", "no")):
        part = ("_".join(toks0[:-2]), "lines", toks0[-1])     # a paragraph over numbered lines: one text value
    if part:
        stem, fam, pt = part
        st_name, did = standard(stem, {"type": "string"})
        toks = st_name.split("_")
        want = KINDS[fam][2] if fam in KINDS else ("txt" if fam == "lines" else None)
        if want and toks[-1] != want:          # the kind's suffix goes last (veteran_ssn_p10 -> veteran_p10_ssn)
            toks = [t for t in (toks[:-1] if toks[-1] in SUFFIXES else toks) if t != want] + [want]
        elif toks[-1] not in SUFFIXES:
            toks.append("nbr")
        new = "_".join(toks + [pt])
        return new, (did + [f"part '{pt}' of one {fam if fam != 'parts' else ''} value after the suffix".replace("  ", " ")]
                     if new != name else [])
    toks, did = _split_glued(name.split("_")), []
    if toks != name.split("_"):
        did.append("number split off")
    it = None
    if len(toks) > 2 and toks[-1].isdigit():                 # step 2: a number after the suffix
        it, toks = toks[-1], toks[:-1]
    typ = spec.get("type")
    for tail, rep, types in TAIL:
        n = len(tail)
        if len(toks) >= n and tuple(toks[-n:]) == tail and (types is None or typ in types) and (len(toks) > n or len(rep) > 1 or rep != tail[-1:]):
            toks = toks[:-n] + list(rep)
            did.append(f"{'_'.join(tail)} -> {'_'.join(rep)}")
            break
    st = spec.get("semantic_type")
    if st == "percent" and toks[-1] in ("qty", "cnt"):        # a percentage named as a count or quantity
        toks = toks[:-1] + ["pct"]
        did.append(f"_{name.split('_')[-1] if name.split('_')[-1] in ('qty', 'cnt') else 'qty'} -> _pct (a percentage)")
    if toks[-1] not in SUFFIXES:                              # step 4: from the type, when unambiguous
        # the type's default suffix: a date _dt, a count _cnt, money _amt, another number _qty, free text _txt (a
        # country / city / state named in it: _cd / _nm / _cd); a leftover phone part word is left for a person
        add = ("ind" if typ == "boolean" else
               "dt" if typ == "date" else
               "cnt" if typ == "integer" else
               "amt" if typ == "number" and (st or "").startswith("money") else
               "pct" if typ == "number" and st == "percent" else
               "qty" if typ == "number" else
               None if toks[-1] in ("area", "prefix", "line", "local") else
               "cd" if typ in ("string", None) and ("country" in toks or "state" in toks) else
               "nm" if typ in ("string", None) and "city" in toks else
               "txt" if typ in ("string", None) else None)
        if add:
            toks.append(add)
            did.append(f"+_{add} (type)")
    if it is not None:
        if toks[-1] in SUFFIXES:
            toks = toks[:-1] + [it, toks[-1]]
            did.append("number moved before the suffix")
        else:
            toks.append(it)
    return "_".join(toks), did


PARTS_AFTER = {"area", "prefix", "line", "local", "month", "day", "yr", "dollars", "cents"}


def has_suffix(name: str) -> bool:
    """Ends in a standard suffix, or in a suffix and a part (telephone_nbr_area, ssn_2, summary_txt_3)."""
    t = name.split("_")
    return t[-1] in SUFFIXES or (len(t) > 1 and t[-2] in SUFFIXES and (t[-1] in PARTS_AFTER or t[-1].isdigit()))


def number_firsts(names: list[str]) -> dict[str, str]:
    """{name: name with its 1} for the un-numbered first of a numbered set (parent_nm next to parent_2_nm). Only
    single-level numbering, and never onto a name that exists: ACORD 125's page-3 automobile_premium_amt is a summary
    next to page 4's automobile_premium_1_amt / _2_amt rows, and CMS-855A's page-34 section repeat (_1_2_txt) is
    numbered twice."""
    have, out = set(names), {}
    for n in names:
        toks = n.split("_")
        digits = [i for i, t in enumerate(toks) if t.isdigit()]
        if len(digits) != 1:
            continue
        i = digits[0]
        if toks[i] != "1" and 0 < i < len(toks):
            first = "_".join(toks[:i] + toks[i + 1:])
            one = "_".join(toks[:i] + ["1"] + toks[i + 1:])
            if first in have and first not in out and one not in have and not any(t.isdigit() for t in first.split("_")):
                out[first] = one
    return out


def zero_based(names: list[str]) -> dict[str, str]:
    """The labeler's duplicate numbering counts from zero: `automobile_effective_dt` is the first, `_dt_1` the second.
    Where a name and its `_1` both exist, the set shifts up by one ({name: renumbered name}), so the first is 1."""
    have, out = set(names), {}
    for n in names:
        if f"{n}_1" in have and not re.search(r"_\d+$", n):
            out[n] = f"{n}_1"
            k = 1
            while f"{n}_{k}" in have:
                out[f"{n}_{k}"] = f"{n}_{k + 1}"
                k += 1
    return out


def apply(bid: str, ren: dict, why: dict) -> int:
    """The renames into the working copy as Claude's corrections; returns how many were written."""
    import time
    from petey.validate import draft
    if not ren:
        return 0
    p = draft.ensure(bid, h.blueprint_paths()[bid])
    bp = h._load(p)
    fields = bp["fields"]
    clean = {n: e for n, e in ((n, h.clean_edit(n, fields[n], {"name": new})) for n, new in ren.items() if n in fields) if e}
    before = h._sha(p)
    extra = {n: {"kind": "name", "why": "naming standard: " + "; ".join(why.get(n) or [])} for n in clean}
    bp["fields"] = h.edit_fields(fields, clean, {n: ren[n] for n in clean}, time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "eval/standardize_names.py", by="claude", extra=extra)
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    draft.follow(bid, before, h._sha(p))
    vp = h.verdict_path(bid)                     # the person's verdicts follow the rename
    if vp.exists():
        rec = json.loads(vp.read_text())
        vs = rec.get("verdicts") or {}
        for n in clean:
            if n in vs:
                vs[ren[n]] = vs.pop(n)
        rec["verdicts"] = vs
        vp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    draft.log(bid, "claude", [f"{n} -> {ren[n]}: {extra[n]['why']}" for n in clean])
    return len(clean)


def run(bid: str, write: bool = False, only: str | None = None) -> dict:
    p = h.working_path(bid)
    bp = h._load(p)
    fields = bp.get("fields") or {}
    ren, why = {}, {}
    parts = part_sets(fields)
    zb = zero_based([n for n, s in fields.items() if isinstance(s, dict) and not _is_group(s) and n not in parts])
    for n, s in fields.items():
        if isinstance(s, dict):
            new, did = standard(zb.get(n, n), s, parts.get(n))
            if n in zb:
                did = ["duplicates counted from 1, not 0"] + did
            if new != n:
                ren[n], why[n] = new, did
    names_after = [ren.get(n, n) for n in fields if n not in parts]
    for old_after, new in number_firsts(names_after).items():
        src = next((o for o in fields if ren.get(o, o) == old_after), None)
        if src is not None:
            ren[src] = new
            why.setdefault(src, []).append("first of a numbered set gets 1")
    # collisions: two fields onto one name, or onto a field that keeps its name
    target = collections.Counter(ren.get(n, n) for n in fields)
    clash = {n for n in ren if target[ren[n]] > 1}
    for n in clash:
        ren.pop(n)
    if only:                             # one rule's renames only (2026-10-15: _pct on forms already in review)
        ren = {o: n for o, n in ren.items() if re.search(only, n)}
    applied = apply(bid, ren, why) if write else 0
    out_fields = {ren.get(n, n): s for n, s in fields.items()}
    bp["fields"] = out_fields
    bp["x_petey_standardized"] = ren
    d = OUT / bid
    d.mkdir(parents=True, exist_ok=True)
    (d / p.name).write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    plain = [n for n, s in out_fields.items() if isinstance(s, dict) and not _is_group(s)]
    unplaced = [n for n in plain if not has_suffix(n)]
    before = [n for n, s in fields.items() if isinstance(s, dict) and not _is_group(s)]
    return {"bid": bid, "fields": len(fields), "renamed": len(ren), "applied": applied, "clashes": sorted(clash), "unplaced": unplaced,
            "suffix_ok_before": sum(1 for n in before if has_suffix(n)), "plain": len(before),
            "suffix_ok_after": len(plain) - len(unplaced), "renames": {k: [v, why.get(k)] for k, v in ren.items()}}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--all-validated", action="store_true", help="the 19 forms validated on 2026-10-13/14")
    ap.add_argument("--apply", action="store_true", help="write the renames into the review page's working copy")
    ap.add_argument("--only", help="keep only renames whose new name matches this regex (e.g. '_pct$')")
    args = ap.parse_args()
    ids = args.ids + (list(json.loads((RUNS / "belongs_to" / "validated_forms_2026-10-14.json").read_text())["forms"])
                      if args.all_validated else [])
    rows = [run(b, args.apply, args.only) for b in ids]
    tot = collections.Counter()
    for r in rows:
        tot.update({k: r[k] for k in ("fields", "renamed", "plain", "suffix_ok_before", "suffix_ok_after")})
        tot["clashes"] += len(r["clashes"])
        print(f"{r['bid']:28} {r['renamed']:4} renamed of {r['fields']:4}; suffix ok {r['suffix_ok_before']}/{r['plain']} -> "
              f"{r['suffix_ok_after']}/{r['plain']}; {len(r['unplaced'])} unplaced, {len(r['clashes'])} clashes")
    print(f"total: {tot['renamed']} renamed of {tot['fields']} fields; non-group fields with a standard suffix "
          f"{tot['suffix_ok_before']}/{tot['plain']} ({tot['suffix_ok_before'] / max(1, tot['plain']):.0%}) -> "
          f"{tot['suffix_ok_after']}/{tot['plain']} ({tot['suffix_ok_after'] / max(1, tot['plain']):.0%}); {tot['clashes']} clashes")
    (OUT / ("applied_" + __import__("time").strftime("%Y-%m-%d") + ".json" if args.apply else "report.json")).write_text(json.dumps(rows, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
