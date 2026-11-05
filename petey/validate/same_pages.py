"""Identical pages filled from each other (Andrew, 2026-10-31: "can you try to leverage existing pages to fill in the
info on identical pages"; "everything should carry over").

Two pages are the same page as `eval/page_dups.py` says (`same_page`, on the page inventory's fingerprints:
runs/inventory/pages.jsonl, a form missing from it read on the spot): a copy page of the same form (Copy A / B / C, an
ATF form printed twice) or a page another form shares (a USCIS instruction page, a lender's addendum). The review
page offers each page's identical pages that hold fields, and "fill from" one (`fill`) makes the page open what the
source page is, in the form's working copy (`draft.py`), saved or discarded with it:

  * the boxes are paired by place (the source's moved by the pages' common offset, then within `TOL` points, sizes
    too); a field whose boxes all pair is replaced by the source's field on its boxes (its own path and on-state, the
    PDF's), a source field with no box here is added on the source's place, a field here that pairs with nothing
    stays as it is and is flagged;
  * everything on the source's field comes with it: kind, type, printed tag, entity, identifiers, description, name
    (on a copy page of the same form `p2_` becomes `p9_`, else `_p9` is added, as `eval/cross_page_groups.py` names
    copies; from another form the name as it is, numbered when taken), its Review verdict, its Groups confirmation,
    its blocks (a block of the same form joins its type; another form's type comes along when its template is on
    the source page) and its grids (with their status: a grid cancelled there is cancelled here);
  * each field filled carries `x_petey_same_page: {form, page, field, when}`, where it came from.
"""
from __future__ import annotations

import collections
import copy
import json
import re
import statistics
import threading
import time
from pathlib import Path
from typing import Optional

from petey.paths import RUNS
import petey_dataset as D

INV = RUNS / "inventory"
TOL = 3.0                # pt: a box here pairs with the source's box at its place (after the offset), sizes too
TAG = "x_petey_same_page"
HAM, JAC, HAM_IMAGE, MIN_WORDS, INK = 40, 0.85, 12, 20, 24
_LOCK = threading.Lock()


# ---- the same page (eval/page_dups.py reads these too)

def ham(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def jac(a: list, b: list) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def ink(p: dict) -> int:
    return bin(int(p["dhash"], 16)).count("1")


def same_page(p: dict, q: dict) -> bool:
    """Two pages are the same page when their words are the same (20 words or more), or they look alike (image hashes
    at most HAM bits apart of 256) and share most words (Jaccard of their word sets at least JAC), or they look the
    same (HAM_IMAGE bits or fewer apart) with about as many words (within a tenth), whatever the words are (the text
    layer may be garbled); never for a page with little drawn on it (fewer than INK of the hash's bits set), as
    near-empty pages all look alike."""
    if p["n_words"] >= MIN_WORDS and p["words_sha"] == q["words_sha"]:
        return True
    d = ham(p["dhash"], q["dhash"])
    if d <= HAM_IMAGE and min(ink(p), ink(q)) >= INK and abs(p["n_words"] - q["n_words"]) <= max(p["n_words"], q["n_words"]) / 10:
        return True
    return d <= HAM and p["n_words"] >= MIN_WORDS and q["n_words"] >= MIN_WORDS and jac(p["vocab"], q["vocab"]) >= JAC


def bands(p: dict) -> list[tuple]:
    """The keys a page is looked up by: its image hash cut in 8 bands (a pair shares a band exactly), and its words."""
    h = f"{int(p['dhash'], 16):064x}"
    out = [("band", i, h[i * 8:(i + 1) * 8]) for i in range(8)]
    if p["n_words"] >= MIN_WORDS:
        out.append(("text", p["words_sha"]))
    return out


# ---- the inventory, read once (again when the files change)

_INV: dict = {}


def _inventory() -> dict:
    """{"blanks": {blank: [page]}, "forms": {review id: blank}, "index": {band: {(blank, page)}}}."""
    pj, fj = INV / "pages.jsonl", INV / "forms.json"
    try:
        stamp = (pj.stat().st_mtime, fj.stat().st_mtime)
    except OSError:
        return {"blanks": {}, "forms": {}, "index": {}, "stamp": None}
    with _LOCK:
        if _INV.get("stamp") != stamp:
            blanks = {}
            for ln in pj.read_text().splitlines():
                if ln:
                    b = json.loads(ln)
                    if b.get("pages"):
                        blanks[b["blank"]] = b["pages"]
            index = collections.defaultdict(set)
            for k, pages in blanks.items():
                for p in pages:
                    for key in bands(p):
                        index[key].add((k, p["page"]))
            _INV.clear()
            _INV.update(blanks=blanks, forms=json.loads(fj.read_text()), index=index, stamp=stamp)
        return _INV


def _pages_of(bid: str, bp: dict, inv: dict) -> tuple[Optional[str], list[dict]]:
    """(blank key, its pages' fingerprints): from the inventory, else read now (a form added since it was made)."""
    key = inv["forms"].get(bid)
    if key and key in inv["blanks"]:
        return key, inv["blanks"][key]
    from petey.validate.retype import resolve_blank
    pdf = resolve_blank(bp)
    if not pdf:
        return None, []
    key = bp.get("source_pdf_hash") or str(pdf)
    if key in inv["blanks"]:
        return key, inv["blanks"][key]
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    import page_inventory                                  # noqa: E402
    return key, page_inventory.read_blank((key, str(pdf))).get("pages") or []


# ---- boxes

def boxes(bp: dict, page: int) -> list[dict]:
    """The page's boxes: [{field, key (an option's key, None for a one-box field), rect}]."""
    out = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("widgets"):
            for k, w in spec["widgets"].items():
                if isinstance(w, dict) and w.get("rect") and int(w.get("page") or 0) == page:
                    out.append({"field": name, "key": str(k), "rect": [float(c) for c in w["rect"]]})
        else:
            w = spec.get("widget") or {}
            if w.get("rect") and int(w.get("page") or 0) == page:
                out.append({"field": name, "key": None, "rect": [float(c) for c in w["rect"]]})
    return out


def field_pages(spec: dict) -> set[int]:
    if not isinstance(spec, dict):
        return set()
    ws = list((spec.get("widgets") or {}).values()) if spec.get("widgets") else [spec.get("widget") or {}]
    return {int(w["page"]) for w in ws if isinstance(w, dict) and w.get("page")}


def offset(src: list[dict], dst: list[dict]) -> tuple[float, float]:
    """The pages' common offset: the median of each box here's shift to its nearest source box (0, 0 with none)."""
    if not src or not dst:
        return 0.0, 0.0
    sx, sy = [], []
    for d in dst:
        s = min(src, key=lambda s: abs(s["rect"][0] - d["rect"][0]) + abs(s["rect"][1] - d["rect"][1]))
        sx.append(d["rect"][0] - s["rect"][0])
        sy.append(d["rect"][1] - s["rect"][1])
    return statistics.median(sx), statistics.median(sy)


def pair(src: list[dict], dst: list[dict], tol: float = TOL) -> tuple[dict[int, int], tuple[float, float]]:
    """({source box index: box here index}, offset): each source box with the nearest box here at its place."""
    dx, dy = offset(src, dst)
    out, used = {}, set()
    cands = []
    for i, s in enumerate(src):
        want = [s["rect"][0] + dx, s["rect"][1] + dy, s["rect"][2] + dx, s["rect"][3] + dy]
        for j, d in enumerate(dst):
            err = max(abs(a - b) for a, b in zip(want, d["rect"]))
            if err <= tol:
                cands.append((err, i, j))
    for _err, i, j in sorted(cands):
        if i not in out and j not in used:
            out[i] = j
            used.add(j)
    return out, (dx, dy)


# ---- what the review page offers

def _fields_on(bp: dict, page: int) -> int:
    return len({b["field"] for b in boxes(bp, page)})


def same_pages(bid: str) -> dict:
    """{page: [{form, page, fields, done, same_form}]}: each page's identical pages that hold fields, this form's
    lower copies first, then forms whose structure is accepted, then by fields."""
    paths = D.blueprint_paths()
    bp = D.load(D.working_path(bid, paths))
    inv = _inventory()
    key, mine = _pages_of(bid, bp, inv)
    if not mine:
        return {}
    by_blank = collections.defaultdict(list)
    for b, k in inv["forms"].items():
        if b in paths:
            by_blank[k].append(b)
    loaded: dict[str, tuple[dict, bool]] = {}

    def form(b: str):
        if b not in loaded:
            try:
                p = D.working_path(b, paths)
                other = D.load(p)
                loaded[b] = (other, D.structure_ok(D.load_verdicts(b) or {}, paths[b], D.load(paths[b])))
            except Exception:  # noqa: BLE001
                loaded[b] = ({}, False)
        return loaded[b]

    out: dict[int, list[dict]] = {}
    for p in mine:
        hits = set()
        for q in mine:                                     # copies within the form
            if q["page"] != p["page"] and same_page(p, q):
                hits.add((key, q["page"]))
        for k in bands(p):
            keys = inv["index"].get(k) or ()
            if len(keys) > 400:                            # a band every blank page shares says nothing
                continue
            for kb, pg in keys:
                if kb != key and (kb, pg) not in hits and same_page(p, next(x for x in inv["blanks"][kb] if x["page"] == pg)):
                    hits.add((kb, pg))
        rows = []
        for kb, pg in hits:
            for b in ([bid] if kb == key else by_blank.get(kb, [])[:1]):
                other, done = (bp, False) if b == bid else form(b)
                n = _fields_on(other, pg)
                if n:
                    rows.append({"form": b, "page": pg, "fields": n, "done": done, "same_form": b == bid})
        rows.sort(key=lambda r: (not r["same_form"], r["page"] if r["same_form"] else 0, not r["done"], -r["fields"], r["form"]))
        if rows:
            out[p["page"]] = rows
    return out


# ---- the fill

def _rename(name: str, p: int, q: int) -> str:
    return re.sub(rf"^p{p}_", f"p{q}_", name) if name.startswith(f"p{p}_") else f"{name}_p{q}"


def _codes(bp: dict) -> dict[str, str]:
    return {n: str(s["x_petey_id"]) for n, s in (bp.get("fields") or {}).items()
            if isinstance(s, dict) and s.get("x_petey_id") is not None}


def plan(bp: dict, src_bp: dict, page: int, src_page: int, same_form: bool, src_form: str = "") -> dict:
    """What the fill makes of the page, without writing: {fields (the blueprint's new fields, in order), names
    {source name: name here}, codes {source code: code here}, removed [names here replaced], left [names here
    paired with nothing], added, replaced, offset}."""
    src = boxes(src_bp, src_page)
    dst = boxes(bp, page)
    m, (dx, dy) = pair(src, dst)
    fields = bp.get("fields") or {}
    sfields = src_bp.get("fields") or {}
    # a field here is replaced when every box of it on this page pairs with a source box
    paired_dst = set(m.values())
    on_page = collections.defaultdict(list)
    for j, d in enumerate(dst):
        on_page[d["field"]].append(j)
    removed = [n for n, js in on_page.items() if all(j in paired_dst for j in js) and field_pages(fields[n]) == {page}]
    partial = {n for n, js in on_page.items() if n not in removed and any(j in paired_dst for j in js)}
    left = [n for n, js in on_page.items() if not any(j in paired_dst for j in js)]
    taken = set(fields) - set(removed)
    used_codes = {c for n, c in _codes(bp).items() if n not in removed}
    nexts = [int(c.split("_")[1]) for c in used_codes if re.fullmatch(rf"{page}_\d+", c)]
    nxt = [max(nexts, default=0) + 1]

    def fresh(name: str) -> str:
        n, k = name, 2
        while n in taken:
            n, k = f"{name}_{k}", k + 1
        taken.add(n)
        return n

    def new_code() -> str:
        c = f"{page}_{nxt[0]}"
        while c in used_codes:
            nxt[0] += 1
            c = f"{page}_{nxt[0]}"
        nxt[0] += 1
        used_codes.add(c)
        return c

    def place(i: int, w: dict) -> dict:
        """The source box's widget on this page: on the box it pairs with (its rect, path, on-state), else moved."""
        w = copy.deepcopy(w)
        w["page"] = page
        if i in m:
            d = dst[m[i]]
            have = fields[d["field"]]
            hw = (have.get("widgets") or {}).get(d["key"]) if d["key"] is not None else have.get("widget")
            hw = hw or {}
            w["rect"] = list(hw.get("rect") or d["rect"])
            for k in ("path", "on_state"):
                if hw.get(k) is not None:
                    w[k] = hw[k]
                else:
                    w.pop(k, None)
        else:
            r = w["rect"]
            w["rect"] = [round(float(r[0]) + dx, 2), round(float(r[1]) + dy, 2), round(float(r[2]) + dx, 2), round(float(r[3]) + dy, 2)]
            w.pop("path", None)
            w.pop("on_state", None)
        return w

    src_index = {(b["field"], b["key"]): i for i, b in enumerate(src)}
    made: dict[str, dict] = {}
    names: dict[str, str] = {}
    codes: dict[str, str] = {}
    added = replaced = 0
    kept_code: set[str] = set()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    scodes = _codes(src_bp)
    for sname in dict.fromkeys(b["field"] for b in src):
        sspec = sfields[sname]
        spec = copy.deepcopy(sspec)
        idx = []
        if sspec.get("widgets"):
            ws = {}
            for k, w in sspec["widgets"].items():
                i = src_index.get((sname, str(k)))
                if i is None:                              # the group's boxes on another page stay there
                    continue
                ws[k] = place(i, w)
                idx.append(i)
            spec["widgets"] = ws
        else:
            i = src_index[(sname, None)]
            spec["widget"] = place(i, sspec["widget"])
            idx.append(i)
        # the code: the one field here this one lands on wholly, else a new one on this page
        here = {dst[m[i]]["field"] for i in idx if i in m}
        one = next(iter(here)) if len(here) == 1 and all(i in m for i in idx) else None
        code = (_codes(bp).get(one) if one in removed and one not in kept_code else None) or new_code()
        if one in removed:
            kept_code.add(one)
        if any(i in m for i in idx):
            replaced += 1
        else:
            added += 1
        spec["x_petey_id"] = code
        name = fresh(_rename(sname, src_page, page) if same_form else sname)
        ent = spec.get("x_petey_entity")
        if same_form and isinstance(ent, dict) and ent.get("name"):
            ent["name"] = _rename(ent["name"], src_page, page)
        spec[TAG] = {"form": src_form, "page": src_page, "field": sname, "when": now}
        made[name] = spec
        names[sname] = name
        if sname in scodes:
            codes[scodes[sname]] = code
    # the blueprint's fields: the page's new ones where its first field was (else before the next page's), the
    # replaced ones out, boxes paired out of a field partly replaced
    out: dict[str, dict] = {}
    put = False
    for n, s in fields.items():
        pages = field_pages(s)
        if not put and (page in pages or (pages and min(pages) > page)):
            out.update(made)
            put = True
        if n in removed:
            continue
        if n in partial:
            s = copy.deepcopy(s)
            gone = {dst[j]["key"] for j in on_page[n] if j in paired_dst}
            s["widgets"] = {k: w for k, w in s["widgets"].items() if str(k) not in gone}
        out[n] = s
    if not put:
        out.update(made)
    return {"fields": out, "names": names, "codes": codes, "removed": removed, "left": left,
            "partial": sorted(partial), "added": added, "replaced": replaced, "offset": (round(dx, 1), round(dy, 1))}


def _carry_groups(bid: str, bp: dict, before_units: list[dict], src_units: list[dict], pl: dict, page: int,
                  sha: str) -> int:
    """The Groups record written over the new file: the units off this page as they were, the page's units from the
    blueprint as filled, each confirmed as its source unit was. Returns the confirmations carried."""
    from petey.validate import group_review as G
    items, base = G.option_items(bp)
    items = {**G.as_converted_items(bp, items), **G.text_items(bp)}
    base = base + G.entity_units(bp)
    gone = set(pl["removed"])
    units = []
    for u in before_units:
        ids = [i for i in u.get("items") or [] if i in items and i.partition("::")[0] not in gone
               and items[i]["page"] != page]
        if ids and (u.get("kind") != "text" or len(ids) > 1):
            units.append(dict(u, items=ids))
    held = {i for u in units for i in u["items"]}
    back = {v: k for k, v in pl["names"].items()}
    confirmed = {u["name"]: bool(u.get("confirmed")) for u in src_units}
    n = 0
    for u in base:
        ids = [i for i in u["items"] if i not in held and items[i]["page"] == page]
        if not ids or (u.get("kind") == "text" and len(ids) < 2):
            continue
        src_name = back.get(u["name"]) or next((back.get(i.partition("::")[0]) for i in ids
                                               if back.get(i.partition("::")[0])), None)
        ok = bool(src_name and confirmed.get(src_name))
        n += ok
        units.append(dict(u, items=ids, confirmed=ok))
    rec = G.load_record(bid)
    rec.update({"blueprint_sha": sha, "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "units": units,
                "boxes": G.item_boxes(items, units)})
    if rec.get("to_text"):
        rec["to_text"] = [i for i in rec["to_text"] if i in items]
    G.OUT.mkdir(parents=True, exist_ok=True)
    G.record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return n


def _carry_sets(bid: str, src: str, pl: dict, page: int, src_page: int, src_codes_on_page: set,
                gone_codes: set) -> tuple[int, int, list[str]]:
    """Blocks and grids (runs/hand_review/grids/<id>.json): the page's own that lost their fields dropped, the
    source page's mapped here. (blocks, grids, notes)."""
    from petey.validate import block_types as B
    from petey.validate import grid_check as gc
    rec = gc.load_set(bid)
    srec = copy.deepcopy(rec) if src == bid else gc.load_set(src)
    cmap = pl["codes"]
    notes: list[str] = []
    # this page's: the replaced fields' codes out
    for e in rec.get("grids") or []:
        if e.get("page") == page:
            e["cells"] = [c for c in e.get("cells") or [] if str(c[0]) not in gone_codes]
    rec["grids"] = [e for e in rec.get("grids") or [] if e.get("page") != page or e["cells"]]
    for t in rec.get("types") or []:
        t["blocks"] = [[None if c is not None and str(c) in gone_codes else c for c in b] for b in t.get("blocks") or []]
        t["blocks"] = [b for b in t["blocks"] if any(c is not None for c in b)]
    rec["types"] = [t for t in rec.get("types") or [] if t["blocks"] or src == bid]
    # grids
    ngrids = 0
    for e in srec.get("grids") or []:
        if e.get("page") != src_page or e.get("kind") != "table":
            continue
        cells = [[cmap[str(c)], r, k] for c, r, k in e.get("cells") or [] if str(c) in cmap]
        if len(cells) < 2:
            continue
        ne = {k: v for k, v in e.items() if k not in ("id", "cells", "page", "from", "into")}
        ne.update(id=gc._new_id(rec, page), page=page, cells=cells, when=time.strftime("%Y-%m-%d %H:%M:%S"))
        rec["grids"].append(ne)
        ngrids += 1
    # blocks
    nblocks = 0
    on_src = lambda b: all(c is None or str(c) in src_codes_on_page for c in b) and any(c is not None for c in b)  # noqa: E731
    for t in srec.get("types") or []:
        mine = [b for b in t.get("blocks") or [] if on_src(b)]
        if not mine:
            continue
        mapped = [[cmap.get(str(c)) if c is not None else None for c in b] for b in mine]
        ids = {B._bid(b): B._bid(nb) for b, nb in zip(mine, mapped)}
        if src == bid:
            into = next(x for x in rec["types"] if x["id"] == t["id"])
        else:
            tpl = [str(x["code"]) for x in t.get("boxes") or []]
            if not tpl or not all(c in src_codes_on_page and c in cmap for c in tpl):
                notes.append(f"block type {t['id']} not carried: its template is not on p{src_page}")
                continue
            into = copy.deepcopy(t)
            into.update(id=B._new_type_id(rec), page=page, blocks=[], parts={}, keep={})
            dx, dy = pl["offset"]
            if into.get("rect"):
                r = into["rect"]
                into["rect"] = [r[0] + dx, r[1] + dy, r[2] + dx, r[3] + dy]
            for x in into.get("boxes") or []:
                x["code"] = cmap[str(x["code"])]
            rec.setdefault("types", []).append(into)
        for b, nb in zip(mine, mapped):
            if nb not in into["blocks"]:
                into["blocks"].append(nb)
                nblocks += 1
            for k in ("parts", "keep"):
                v = (t.get(k) or {}).get(B._bid(b))
                if v is not None and ids.get(B._bid(b)):
                    into.setdefault(k, {})[ids[B._bid(b)]] = copy.deepcopy(v)
    gc._save_set(bid, rec)
    return nblocks, ngrids, notes


def fill(bid: str, page: int, src: str, src_page: int, real: Optional[Path] = None) -> dict:
    """Page `page` of `bid` made what page `src_page` of `src` is, in the working copy (see the module's doc).
    {changes: [lines], left: [names here paired with nothing, flagged]}."""
    from petey.validate import draft, group_review as G
    from petey.validate.printed_fields import _dump
    paths = D.blueprint_paths()
    real = real or paths[bid]
    if src == bid and src_page == page:
        raise ValueError("a page cannot be filled from itself")
    src_bp = D.load(D.working_path(src, paths))
    if not boxes(src_bp, src_page):
        raise ValueError(f"{src} p{src_page} has no fields to fill from")
    p = draft.ensure(bid, real)
    before = D.sha(p)
    bp = D.load(p)
    if src == bid:
        src_bp = bp
    _items, before_units, _info = G.current_units(bid, bp, before)
    src_units = before_units if src == bid else G.current_units(src, src_bp, D.sha(D.working_path(src, paths)))[1]
    pl = plan(bp, src_bp, page, src_page, src == bid, src)
    gone_codes = {c for n, c in _codes(bp).items() if n in pl["removed"]} - set(pl["codes"].values())
    src_codes_on_page = {c for n, c in _codes(src_bp).items() if n in pl["names"]}
    src_verdicts = (D.load_verdicts(src).get("verdicts") or {})
    bp["fields"] = pl["fields"]
    dropped = (bp.get("x_petey_copy_pages_log") or {}).get("dropped_as_copies")
    if isinstance(dropped, dict):                  # the labeler's note that it left this page out as a copy
        dropped.pop(page, None)
        dropped.pop(str(page), None)
    p.write_text(_dump(bp), encoding="utf-8")
    after = D.sha(p)
    draft.follow(bid, before, after)
    confirmed = _carry_groups(bid, bp, before_units, src_units, pl, page, after)
    nblocks, ngrids, notes = _carry_sets(bid, src, pl, page, src_page, src_codes_on_page, gone_codes)
    # Review verdicts: the source field's, the replaced fields' gone, the fields paired with nothing flagged
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    where = f"p{src_page}" if src == bid else f"{src} p{src_page}"
    with D.LOCK:
        rec = D.load_verdicts(bid) or {"blueprint": str(real), "form": real.stem, "verdicts": {}, "blueprint_sha": after}
        vs = rec.setdefault("verdicts", {})
        for n in pl["removed"]:
            if n not in pl["names"].values():
                vs.pop(n, None)
        carried = 0
        for sname, name in pl["names"].items():
            v = src_verdicts.get(sname)
            if v and v.get("verdict") and not (v.get("edit") and not v.get("applied")):
                vs[name] = {k: x for k, x in v.items() if k not in ("edit", "applied")}
                carried += 1
            else:
                vs.pop(name, None)
        for n in pl["left"]:
            vs[n] = {"verdict": "flag", "note": f"not on {where}, which this page was filled from", "when": now}
        D.write_verdicts(bid, rec)
    lines = [f"p{page} filled from {where}: {len(pl['names'])} fields ({pl['replaced']} on the boxes here, "
             f"{pl['added']} added), {carried} verdicts, {confirmed} group confirmations, {nblocks} blocks, "
             f"{ngrids} grids carried"]
    if pl["left"]:
        lines.append(f"p{page}: {len(pl['left'])} field(s) not on {where} kept and flagged: {', '.join(pl['left'])}")
    lines += [f"p{page}: {n}" for n in notes]
    draft.log(bid, "same page", lines)
    return {"changes": lines, "left": pl["left"]}
