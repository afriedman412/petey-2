"""Grids: the review page's Grids tab (Andrew, 2026-10-16: "add a 'grids and blocks' view to the reviewer and just
route the skill through there ... a button to check and validate it in one click"). Repeated blocks are block types
(block_types.py) since 2026-10-21; the block groups that were kept here are gone (2026-10-22).

Every numbered grid the layout code finds (eval/grid_naming.grids) is listed with its cells, and one click runs the
lightest method that settles it, in order:

  1. the code check: already on pattern -> its cells accepted, nothing else;
  2. the resolver (grid_naming.resolve): each position's wording, settled by the name-check model against the
     position's shared caption, then the numbers (1..N, unless the series continues from another page or the
     numbers are printed line numbers) -> the renames applied as Claude's, the cells accepted;
  3. Jev: a position the model could not settle, chosen from its candidate wordings with the page image ->
     resolved again with that wording, applied and accepted;
  4. Opus (the chat with the grid-validation skill's rules, this page only): only what is still unclear; its
     proposals come back for the person to tick, nothing applied.

Nothing is stored about the grids in the blueprint. The form's grids are kept apart from it (2026-10-17, `listing`:
runs/hand_review/grids/<id>.json): ids that last (p1-G2), cancelled ones ("not a grid"), ones the person drew around
an area and ones combined from others, each with its provenance (finder, person, combined).
"""
from __future__ import annotations

import collections
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


# ------------------------------------------------------------------ the form's grids and blocks, kept (2026-10-17)
# Andrew: "add IDs to grids and blocks; the ability to cancel; to create new ones by selecting an area; to combine
# existing ones of the same kind" and "they should be the same button -- the provenance will distinguish them".
# runs/hand_review/grids/<bid>.json: {"grids": [entry], "types": [block type], "next": {"1T": 3}}; an entry is {id
# (p1-G2), kind (table), page, source (finder | person | combined | edited), status (active | cancelled | combined:
# taken into another), cells: [[field code, row, col]], from: [ids], into: id, when}. Cells are kept by field code (x_petey_id),
# so a rename moves nothing. The finder runs on every read; its grids are matched to their entries by cells (most
# in common, same page) and keep their ids; a new one gets the next id. A grid the person made or combined hides the
# finder's grids that are mostly inside it.

SETS = h.OUT / "grids"


def _set_path(bid: str) -> Path:
    return SETS / f"{bid}.json"


def load_set(bid: str) -> dict:
    import json
    p = _set_path(bid)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"grids": [], "next": {}}
    except (OSError, ValueError):
        return {"grids": [], "next": {}}


def one_block_per_field(rec: dict) -> list[str]:
    """No field in two blocks (Andrew, 2026-10-22: "make sure no field can be in two blocks. larger blocks get
    precedence"): blocks by their fields, most first; a field already held by a larger block leaves the smaller one
    (its position empty), a block left with no field goes, a type left with no block goes. What moved."""
    from petey.validate import block_types as bt
    said, held = [], set()
    types = rec.get("types") or []
    blocks = sorted(((t, b) for t in types for b in t["blocks"]), key=lambda x: -sum(1 for c in x[1] if c))
    for t, b in blocks:
        clash = [c for c in b if c and c in held]
        held |= {c for c in b if c}
        if not clash:
            continue
        i = next(k for k, x in enumerate(t["blocks"]) if x is b)
        nb = [None if c in clash else c for c in b]
        said.append(f"{t['id']}-{i + 1}: {len(clash)} field{'s' if len(clash) > 1 else ''} kept by a larger block")
        if bt._bid(nb) is None:
            t["blocks"][i] = None
        else:
            t["blocks"][i] = nb
            bt._rekey(t, bt._bid(b), bt._bid(nb))
    for t in types:
        t["blocks"] = [b for b in t["blocks"] if b is not None]
    rec["types"] = [t for t in types if t["blocks"]] if "types" in rec else rec.get("types")
    return said


def _save_set(bid: str, rec: dict) -> None:
    import json
    if rec.get("types"):
        one_block_per_field(rec)                 # every block change goes through here
    SETS.mkdir(parents=True, exist_ok=True)
    _set_path(bid).write_text(json.dumps(rec, indent=1), encoding="utf-8")


def _new_id(rec: dict, page: int) -> str:
    """p1-G2: the page and the grid's number on it (G for grid since 2026-10-23, Andrew: "they are grids not tables";
    older records renamed from p1-T2)."""
    k = f"{page}G"
    n = rec.setdefault("next", {}).get(k, 1)
    rec["next"][k] = n + 1
    return f"p{page}-G{n}"


def found(bp: dict, held: list[set] = ()) -> list[list[dict]]:
    """The finder's grids (grid_naming, without its old blocks), less those mostly inside one block (`held`: each block
    type's blocks, as field names). 2026-10-22, in place of the block-group finder that hid them before: of the 173
    grids it hid on 63 forms, 164 sit in block types' blocks."""
    return [g for g in G.grids(bp, blocks=False) if G.iterated(g)
            and not any(len({c["name"] for c in g} & ns) >= 0.5 * len(g) for ns in held)]


def _blocks_held(rec: dict, name: dict) -> list[set]:
    """Each block type's blocks as sets of field names (codes mapped through `name`)."""
    return [{name[c] for c in b if c in name} for y in rec.get("types") or [] for b in y.get("blocks") or []]


def listing(bid: str, bp: dict) -> list[dict]:
    """The form's grids: [{id, kind, page, source, status, from, into, when, grid}] where `grid` is the
    cells as the checks take them ([{name, page, row, col, block?}]). Every finder grid gets (and keeps) an id; the
    record is written when one is new."""
    import time
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    code = {n: str(s.get("x_petey_id")) for n, s in fields.items() if s.get("x_petey_id") is not None}
    name = {c: n for n, c in code.items()}
    rec, changed = load_set(bid), False
    legacy = not_grids(bid)                                   # "not a grid or block" before ids (2026-10-16)
    out, claimed = [], set()

    def at(g):                                  # top, then left: new ids are given in reading order
        rs = [r for r in (_rect(bp, c["name"]) for c in g) if r]
        return (g[0]["page"], min((r[1] for r in rs), default=0), min((r[0] for r in rs), default=0))
    for g in sorted(found(bp, _blocks_held(rec, name)), key=at):
        page = g[0]["page"]
        codes = [code.get(c["name"], c["name"]) for c in g]
        e = next((e for e in rec["grids"] if e["source"] == "finder" and e["page"] == page and id(e) not in claimed
                  and _same([c[0] for c in e["cells"]], codes)), None)
        if e is None:
            e = {"id": _new_id(rec, page), "kind": "table", "page": page, "source": "finder",
                 "status": "cancelled" if dismissed(legacy, page, [c["name"] for c in g]) else "active",
                 "when": time.strftime("%Y-%m-%d %H:%M:%S")}
            rec["grids"].append(e)
            changed = True
        if [list(x) for x in e.get("cells") or []] != [[cd, c["row"], c["col"]] for cd, c in zip(codes, g)]:
            e["cells"] = [[cd, c["row"], c["col"]] for cd, c in zip(codes, g)]
            changed = True
        claimed.add(id(e))
        out.append({**{k: e.get(k) for k in ("id", "kind", "page", "source", "status", "from", "into", "when", "kept")},
                    "grid": [dict(c) for c in g]})
    for e in rec["grids"]:
        if e["source"] == "finder" or e.get("kind") != "table":       # (block groups' entries: gone, 2026-10-22)
            continue
        cells = [{"name": name[c], "page": e["page"], "row": r, "col": k} for c, r, k in e["cells"] if c in name]
        if cells:
            out.append({**{k: e.get(k) for k in ("id", "kind", "page", "source", "status", "from", "into", "when")},
                        "grid": cells})
    mine = [set(c["name"] for c in t["grid"]) for t in out if t["source"] != "finder" and t["status"] == "active"]
    # what the person made, drew, combined or edited holds its fields against the finder (one grid per field,
    # `exclusive`): a finder grid mostly inside one of them, or mostly inside them together (je__uk_ch_psc01 p1-T7,
    # 2026-10-20: the finder's 30 cells over the four grids drawn in its place), is shown as them; one that only
    # shares a few is shown without those
    held = set().union(*mine) if mine else set()
    for t in out:
        if t["source"] != "finder" or t["status"] != "active":
            continue
        names = {c["name"] for c in t["grid"]}
        if any(len(names & m) >= 0.5 * len(names) for m in mine) or len(names & held) >= 0.5 * len(names):
            t["status"] = "replaced"
        elif names & held:
            t["grid"] = [c for c in t["grid"] if c["name"] not in held]
            if len(t["grid"]) < 2:
                t["status"] = "replaced"
    # a finder grid split between blocks is probably not one (Andrew, 2026-10-22: "grids that are split between blocks
    # are probably not correct, unless they are very uniformly shaped"; VA 21P-534EZ p13: three grids across the
    # children's blocks, cancelled by hand): set aside, said why, until the person restores it (`kept`)
    blk = {c: f"{y['id']}-{i}" for y in rec.get("types") or [] for i, b in enumerate(y.get("blocks") or [], 1) for c in b if c}
    for t in out:
        if t["source"] != "finder" or t["status"] != "active" or t.get("kept"):
            continue
        hit = sorted({blk[code[c["name"]]] for c in t["grid"] if code.get(c["name"]) in blk})
        if len(hit) >= 2 and not uniform(bp, t["grid"]):
            t["status"], t["aside_why"] = "split", f"split between blocks {', '.join(hit)}"
    on_page = fields_on_page(bp)
    for t in out:
        if t["source"] != "finder" or t["status"] != "active" or t.get("kept"):
            continue
        why = aside_why(t["grid"], on_page)
        if why:
            t["status"], t["aside_why"] = "split", why
    # a grid that is still active supersedes the blocks lying mostly inside it, two or more of them (Andrew,
    # 2026-10-23: "form_1095_b_check_p3-G2 should supersede the blocks, we don't need both!"; the twelve
    # covered-individual blocks on p3, one per row): the blocks leave their types, a type left with none goes.
    # As labeling does (petey/label/structure.find). Names are left as they are
    if superseded(rec, out, code):
        changed = True
    # and a finder grid lying mostly inside blocks gives way to them (Andrew, 2026-10-23, B 106D p2-G2: claims 3-5's
    # city / state / zip read as a grid, "we want 3 blocks that fill each row"): half its cells or more in blocks,
    # taken together; set aside, restorable (`kept`)
    in_block = {c: f"{y['id']}-{i}" for y in rec.get("types") or [] for i, b in enumerate(y.get("blocks") or [], 1)
                for c in b if c}
    for t in out:
        if t["source"] != "finder" or t["status"] != "active" or t.get("kept"):
            continue
        hit = [in_block[code[c["name"]]] for c in t["grid"] if code.get(c["name"]) in in_block]
        if len(hit) >= 0.5 * len(t["grid"]):
            t["status"], t["aside_why"] = "split", f"inside blocks {', '.join(sorted(set(hit))[:6])}"
    if changed:
        _save_set(bid, rec)
    return out


def superseded(rec: dict, grids: list[dict], code: dict) -> list[str]:
    """Blocks taken out of their types by an active grid holding 2+ of them, each mostly inside it (see `listing`);
    each such grid's entry says which (`supersedes`). What went, as "BT2-3"."""
    types = rec.get("types") or []
    gone: list[str] = []
    for t in grids:
        if t["status"] != "active":
            continue
        mine = {code.get(c["name"]) for c in t["grid"]} - {None}
        over = [(y, b) for y in types for b in y["blocks"] if b and {c for c in b if c} & mine]
        if len(over) < 2 or not all(len({c for c in b if c} & mine) > 0.5 * sum(1 for c in b if c) for _, b in over):
            continue
        names = []
        for y, b in over:
            names.append(f"{y['id']}-{next(i for i, x in enumerate(y['blocks'], 1) if x is b)}")
        for y, b in over:
            y["blocks"] = [x for x in y["blocks"] if x is not b]
        e = next((e for e in rec["grids"] if e.get("id") == t["id"]), None)
        if e is not None:
            e["supersedes"] = sorted(set(e.get("supersedes") or []) | set(names))
        gone += names
    if gone:
        rec["types"] = [y for y in types if y["blocks"]]
    return gone


def fields_on_page(bp: dict) -> dict[int, list]:
    """{page: [(field name, rect)]}, for `aside_why`."""
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    on_page: dict[int, list] = {}
    for n in fields:
        r = _rect(bp, n)
        ws = [fields[n]["widget"]] if fields[n].get("widget") else list((fields[n].get("widgets") or {}).values())
        if r and ws:
            on_page.setdefault(ws[0].get("page"), []).append((n, r))
    return on_page


def aside_why(grid: list[dict], on_page: dict[int, list]) -> str | None:
    """Why a finder grid is set aside, or None: the Grids tab's suggestions and the grids labeling hands the
    labeler (Andrew, 2026-10-23: "might as well try the new grids rules"; grids are more efficient than blocks for
    actual grids, but the finder's are too aggressive)."""
    # small (Andrew, 2026-10-23: "i_829_check_p4-T1 is a frivolous grid": child 1's and child 2's addresses side by
    # side, 3 x 2, two blocks really): under 3 x 3 and under 12 cells, as labeling leaves small tables out
    rows, cols = len({c["row"] for c in grid}), len({c["col"] for c in grid})
    if (rows < 3 or cols < 3) and len(grid) < 12:
        return f"small: {rows} x {cols}"
    # its outline holds as many other fields as its own cells (Andrew, 2026-10-23: "a grid can include a field
    # within the space it covers without it being in the grid ... that's ok to a point"; I-829 p4: 6 cells over 8
    # other fields): mostly grids cutting across blocks (VA 21-686c p9: 24 prior-marriage city boxes over six
    # marriages, 38 other fields inside; I-730 p5: prior spouses with the native language)
    mine = {c["name"] for c in grid}
    page = grid[0]["page"] if grid else None
    rect = {n: r for n, r in on_page.get(page, []) if n in mine}
    rs = list(rect.values())
    if not rs:
        return None
    # its rows are stacks of lines, not lines (Andrew, 2026-10-23, B 106D p3-G1: each party to notify a row of name,
    # two address lines and city / state / zip, "we don't want" it; the rows are blocks): a row over three field
    # heights tall, most rows so
    hs = sorted(r[3] - r[1] for r in rs)
    tall = 0
    for row in {c["row"] for c in grid}:
        rr = [rect[c["name"]] for c in grid if c["row"] == row and c["name"] in rect]
        if rr and max(r[3] for r in rr) - min(r[1] for r in rr) > 3 * hs[len(hs) // 2]:
            tall += 1
    if tall > rows / 2:
        return f"rows of several lines ({tall} of {rows}): blocks, not a grid"
    bb = [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]
    other = sum(1 for n, r in on_page.get(page, []) if n not in mine
                and bb[0] < (r[0] + r[2]) / 2 < bb[2] and bb[1] < (r[1] + r[3]) / 2 < bb[3])
    if other >= len(mine):
        return f"covers {other} other fields, more than its {len(mine)} cells"
    return None


def uniform(bp: dict, g: list[dict]) -> bool:
    """A grid "very uniformly shaped" (Andrew, 2026-10-22; "both rows and columns can be inconsistently sized"): a full
    lattice, each row's cells crossed by one line across, each column's by one line down, no cell missing, and no other field inside
    its outline (VA 21P-534EZ p13-T2: each child's SSN boxes lined up as a lattice, the other children's name boxes
    between its rows). Sizes and spacing may vary."""
    rs = [_rect(bp, c["name"]) for c in g]
    if not rs or any(r is None for r in rs):
        return False
    rows, cols = sorted({c["row"] for c in g}), sorted({c["col"] for c in g})
    if len(g) != len(rows) * len(cols) or len({(c["row"], c["col"]) for c in g}) != len(g):
        return False
    for axis, lines, i in (("row", rows, 1), ("col", cols, 0)):
        for k in lines:                    # lined up: one line across (down) passes through every cell of the row
            spans = [(r[i], r[i + 2]) for c, r in zip(g, rs) if c[axis] == k]       # (column); sizes may differ
            if max(a for a, _ in spans) >= min(b for _, b in spans):
                return False
    box = [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]
    mine = {c["name"] for c in g}
    page = g[0].get("page")
    for n, sp in (bp.get("fields") or {}).items():
        if n in mine or not isinstance(sp, dict):
            continue
        w = sp.get("widget") or next(iter((sp.get("widgets") or {}).values()), {})
        r = _rect(bp, n)
        if r and w.get("page") == page and box[0] < (r[0] + r[2]) / 2 < box[2] and box[1] < (r[1] + r[3]) / 2 < box[3]:
            return False
    return True


def set_status(bid: str, gid: str, cancel: bool, bp: Optional[dict] = None) -> dict:
    """Cancel a grid ("not a grid"), or restore it. Cancelling a combined one gives its parts back. With `bp`, what
    comes back takes its fields from the other grids (`exclusive`)."""
    import time
    rec = load_set(bid)
    e = next((e for e in rec["grids"] if e["id"] == gid), None)
    if e is None:
        raise ValueError(f"no grid {gid}")
    e["status"] = "cancelled" if cancel else "active"
    e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if cancel:                        # restored by the person: a grid, whatever the rules say (`listing`'s split rule)
        e.pop("kept", None)
    else:
        e["kept"] = True
    back = [] if cancel else [gid]
    if e["source"] in ("combined", "edited"):
        for x in rec["grids"]:
            if x["id"] in (e.get("from") or []) and x.get("into") == gid:
                x["status"] = "active" if cancel else "combined"
                back += [x["id"]] if cancel else []
    if cancel:
        _give_back(rec, gid)
    _save_set(bid, rec)
    return {"id": gid, "status": e["status"], "left": exclusive(bid, bp, back) if bp is not None and back else []}


def _give_back(rec: dict, gid: str) -> None:
    """Cancelling one that took fields from others (`exclusive`) gives them back: each grid it took from as it was,
    if it has not changed since and the fields are in no other one now."""
    held = {c[0] for e in rec["grids"] if e["status"] == "active" and e["id"] != gid for c in e.get("cells") or []}
    for x in rec["grids"]:
        u = x.get("undo") or {}
        if u.get("by") != gid or x.get("cells") != u.get("after"):
            continue
        if u.get("drop"):                        # the finder's, whole again; the copy without the fields goes
            orig = next((o for o in rec["grids"] if o["id"] in (x.get("from") or []) and o.get("into") == x["id"]), None)
            if orig is None or x["status"] != "active":
                continue
            x["status"] = "undone"
            orig["status"] = "active"
            orig.pop("into", None)
        else:
            if {c[0] for c in u["cells"]} - {c[0] for c in x["cells"]} & held:
                continue
            x["cells"], x["status"] = u["cells"], "active"
            x.pop("into", None)
        x.pop("undo", None)


def exclusive(bid: str, bp: dict, winners: list[str]) -> list[str]:
    """A field is in one grid at most (Andrew, 2026-10-20: "if you drag it into a group, it should join that one and
    leave the other one"): the fields of `winners` (what was just drawn, combined or restored) leave every other grid
    shown on the form. One the finder found becomes an edited copy without them; one left with fewer than two fields is
    emptied. Cancelling the winner gives them back (`_give_back`). What left where, for the page to say."""
    import time
    shown = {t["id"] for t in listing(bid, bp) if t["status"] == "active"}     # also records any new finder ids
    rec = load_set(bid)
    by = {e["id"]: e for e in rec["grids"]}
    said, changed = [], False
    for w in winners:
        we = by.get(w)
        if we is None or we["status"] != "active":
            continue
        mine = {c[0] for c in we.get("cells") or []}
        for e in list(rec["grids"]):
            if e["id"] == w or e.get("kind") != "table" or e["id"] not in shown or e["status"] != "active":
                continue
            left = [list(c) for c in e.get("cells") or [] if c[0] not in mine]
            n = len(e.get("cells") or []) - len(left)
            if not n:
                continue
            if len(left) < 2:
                e["undo"] = {"by": w, "cells": e.get("cells"), "after": e.get("cells")}
                e["status"], e["into"] = "emptied", w
                said.append(f"{e['id']} emptied ({n} field{'s' if n != 1 else ''} to {w})")
            elif e["source"] == "finder":
                c = {"id": _new_id(rec, e["page"]), "kind": "table", "page": e["page"], "source": "edited",
                     "status": "active", "cells": _compact(left), "from": [e["id"]], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
                c["undo"] = {"by": w, "drop": True, "after": c["cells"]}
                e["status"], e["into"] = "combined", c["id"]
                rec["grids"].append(c)
                by[c["id"]] = c
                shown.add(c["id"])
                said.append(f"{n} field{'s' if n != 1 else ''} left {e['id']} (now {c['id']})")
            else:
                e["undo"] = {"by": w, "cells": e.get("cells"), "after": _compact(left)}
                e["cells"] = e["undo"]["after"]
                e["when"] = time.strftime("%Y-%m-%d %H:%M:%S")
                said.append(f"{n} field{'s' if n != 1 else ''} left {e['id']}")
            changed = True
    if changed:
        _save_set(bid, rec)
    return said


def arrange(bp: dict, names: list[str]) -> list[dict]:
    """Rows and columns for fields the person grouped (an area drawn, or grids combined), from their boxes on the page.
    Lines: a box joins a line it overlaps from top to bottom by half the smaller height; ordinary boxes widen the
    line, a box much taller than most (Form 8949's description, IMM 5645's relationship) joins the line its top is on
    without widening it. Columns: boxes overlapping across by half the narrower (two on one line and column are two
    columns). Each line a row."""
    boxes = [(n, _rect(bp, n)) for n in names]
    boxes = [(n, r) for n, r in boxes if r]
    if not boxes:
        return []
    hs = sorted(r[3] - r[1] for _n, r in boxes)
    tall = 1.6 * hs[len(hs) // 2]
    lines: list[dict] = []
    for n, r in sorted(boxes, key=lambda b: (b[1][1], b[1][3] - b[1][1])):
        h = r[3] - r[1]
        ln = next((ln for ln in lines if min(ln["y1"], r[3]) - max(ln["y0"], r[1])
                   >= 0.5 * min(ln["y1"] - ln["y0"], h)), None)
        if ln is None:
            ln = {"y0": r[1], "y1": r[3] if h <= tall else r[1] + hs[len(hs) // 2], "cells": []}
            lines.append(ln)
        elif h <= tall:
            ln["y0"], ln["y1"] = min(ln["y0"], r[1]), max(ln["y1"], r[3])
        ln["cells"].append((n, r))
    lines.sort(key=lambda ln: ln["y0"])
    cols: list[list] = []
    for _n, r in sorted(boxes, key=lambda b: (b[1][0], b[1][2])):
        c = next((c for c in cols if min(c[1], r[2]) - max(c[0], r[0]) >= 0.5 * min(c[1] - c[0], r[2] - r[0])), None)
        if c is None:
            cols.append([r[0], r[2]])
    cols.sort()
    # the column it overlaps most; a wide box overlapping several alike (N-600 p14's additional information box over
    # the page, part and item columns, 60 pt each, the winner set by float noise, 2026-10-20): the one its left edge is at
    col_of = lambda r: max(range(len(cols)), key=lambda i: (round(min(cols[i][1], r[2]) - max(cols[i][0], r[0])),  # noqa: E731
                                                            -abs(cols[i][0] - r[0])))
    placed = []                                  # (line, column, rank on that line and column, name, box)
    for li, ln in enumerate(lines):
        seen: dict = {}
        for n, r in sorted(ln["cells"], key=lambda b: b[1][0]):
            ci = col_of(r)
            placed.append((li, ci, seen.get(ci, 0), n, r))
            seen[ci] = seen.get(ci, 0) + 1
    slots = sorted({(ci, k) for _li, ci, k, _n, _r in placed})
    slot_ix = {s_: i for i, s_ in enumerate(slots)}
    out = []
    for li, ci, k, n, _r in placed:
        spec = bp["fields"][n]
        w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
        out.append({"name": n, "page": w.get("page"), "row": li, "col": slot_ix[(ci, k)]})
    return out


def _in_area(bp: dict, page: int, rect) -> list[str]:
    """The fields whose box (an option group's box around its boxes) has its middle inside the area."""
    out = []
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        ws = [s["widget"]] if s.get("widget") else list((s.get("widgets") or {}).values())
        if not ws or any(w.get("page") != page for w in ws):
            continue
        r = _rect(bp, n)
        if r and rect[0] <= (r[0] + r[2]) / 2 <= rect[2] and rect[1] <= (r[1] + r[3]) / 2 <= rect[3]:
            out.append(n)
    return out


def create(bid: str, bp: dict, page: int, rect) -> dict:
    """A grid the person drew: the fields inside the area, arranged (`arrange`)."""
    names = _in_area(bp, page, rect)
    if len(names) < 2:
        raise ValueError("fewer than two fields in that area")
    cells = arrange(bp, names)
    out = _add(bid, bp, page, cells, "person", [])
    return {**out, "left": exclusive(bid, bp, [out["id"]])}


def combine(bid: str, bp: dict, gids: list[str]) -> dict:
    """Two or more grids on one page as one: their cells arranged again together. The parts are kept, marked as taken
    into the new one; cancelling it gives them back."""
    have = {t["id"]: t for t in listing(bid, bp)}
    parts = [have[g] for g in gids if g in have]
    if len(parts) < 2:
        raise ValueError("pick two or more grids")
    if len({t["page"] for t in parts}) > 1:
        raise ValueError("grids on different pages cannot be combined yet")
    names = list(dict.fromkeys(c["name"] for t in parts for c in t["grid"]))
    out = _add(bid, bp, parts[0]["page"], arrange(bp, names), "combined", [t["id"] for t in parts])
    rec = load_set(bid)
    for e in rec["grids"]:
        if e["id"] in gids:
            e["status"], e["into"] = "combined", out["id"]
    _save_set(bid, rec)
    return {**out, "left": exclusive(bid, bp, [out["id"]])}


def _add(bid: str, bp: dict, page: int, cells: list[dict], source: str, parts: list[str]) -> dict:
    import time
    code = {n: str(s.get("x_petey_id")) for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    rec = load_set(bid)
    e = {"id": _new_id(rec, page), "kind": "table", "page": page, "source": source, "status": "active",
         "cells": [[code[c["name"]], c["row"], c["col"]] for c in cells], "when": time.strftime("%Y-%m-%d %H:%M:%S")}
    if parts:
        e["from"] = parts
    rec["grids"].append(e)
    _save_set(bid, rec)
    return {"id": e["id"], "cells": len(cells)}


def _compact(cells: list) -> list:
    """Positions numbered 0..n-1 in their order (an emptied one dropped), blocks likewise; cells by block, then
    position."""
    pos = {k: i for i, k in enumerate(sorted({c[2] for c in cells}))}
    blk = {k: i for i, k in enumerate(sorted({c[1] for c in cells}))}
    return sorted([[c[0], blk[c[1]], pos[c[2]]] for c in cells], key=lambda c: (c[1], c[2]))


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


def tables(bp: dict, bid: Optional[str] = None) -> list[dict]:
    """[{id, page, kind, rows, cols, lines, positions, title, bbox, cells: [{name, rect, row, col}], on_pattern, why,
    source, status, from, into}] for every numbered grid, in page order; with `bid`, the form's kept grids
    (`listing`: ids that last, cancelled ones, the person's and combined ones). `lines` is how many rows (or columns,
    when the columns are numbered) it numbers, `positions` each column (or row) with its wording and the caption
    printed for it."""
    blank = resolve_blank(bp)
    page_text = _lines(blank) if blank and blank.exists() else {}
    if blank and blank.exists() and str(blank) not in _HEADS:
        from cheap_names import headings
        _HEADS[str(blank)] = headings(blank)
    heads = _HEADS.get(str(blank), {}) if blank else {}
    out, n = [], {}
    if bid:
        entries = [t for t in listing(bid, bp) if t["status"] in ("active", "cancelled", "split")]
    else:
        entries = []
        for g in G.grids(bp, blocks=False):
            if G.iterated(g):
                n[g[0]["page"]] = n.get(g[0]["page"], 0) + 1
                entries.append({"id": f"p{g[0]['page']}t{n[g[0]['page']]}", "source": "finder", "status": "active",
                                "kind": "table", "grid": g})
    for e in entries:
        g = e["grid"]
        page = g[0]["page"]
        cells = [dict(c, rect=_rect(bp, c["name"])) for c in g]
        rs = [c["rect"] for c in cells if c["rect"]]
        if not rs:
            continue
        ok, why = G.on_pattern(g)
        reading = "columns" if G.keyed(g) else G.breaks(g)[0]      # lines named by role or kind are the rows
        pos_axis, num_axis = ("col", "row") if reading == "columns" else ("row", "col")
        how = reading
        body = G.body(g)
        body_names = {c["name"] for c in body}             # a totals row is outside the check (and the validation)
        positions = []
        F = G._Frame(g) if body else None      # the number that varies down a column is its N, not the last one
        same_axis = bool(F) and F.pos_axis == pos_axis
        number = F.numbers(bp, g, page_text, F.basis())[0] if same_axis and not G.keyed(g) else {}   # as standardize
        for k in sorted({c[pos_axis] for c in body}):
            pcs = [c for c in body if c[pos_axis] == k]
            wordings = sorted({(F.pat_of(c) if same_axis else (G._pattern(c["name"]) or c["name"])).replace("_N", "_#") for c in pcs})
            # cells whose number is not their line's (a column numbered from 2): the column's standardize button
            off = sum(1 for c in pcs if number and number.get(c[num_axis]) is not None and k not in F.locked
                      and (F.num_of(c) or "").isdigit() and int(F.num_of(c)) != number[c[num_axis]]) if same_axis else 0
            positions.append({"pos": k + 1, "wordings": wordings, "off": off, "caption": G.position_caption(bp, pcs, how, page_text)})
        bbox = [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]
        out.append({"id": e["id"], "page": page, "kind": "grid",
                    **{k: e.get(k) for k in ("source", "status", "from", "into", "aside_why")},
                    "lines": len({c[num_axis] for c in body}), "positions": positions, "reading": reading,
                    "rows_info": rows_info(g, body, pos_axis, num_axis), "keyed": G.keyed(g),
                    "aside": [{"row": r + 1, "why": why} for r, why in sorted(G.aside(g).items())],
                    "title": _title(bbox, page_text.get(page), heads.get(page), [p["caption"] for p in positions]),
                    "rows": max(c["row"] for c in g) + 1, "cols": max(c["col"] for c in g) + 1,
                    "bbox": bbox,
                    "cells": [dict({k: c[k] for k in ("name", "rect", "row", "col")}, total=c["name"] not in body_names,
                                   code=str(((bp.get("fields") or {}).get(c["name"]) or {}).get("x_petey_id", "")))
                              for c in cells],
                    "on_pattern": ok, "why": why})
    out.sort(key=lambda t: (t["page"], t["bbox"][1], t["bbox"][0]))
    return out


def rows_info(g: list[dict], body: list[dict], pos_axis: str, num_axis: str) -> dict:
    """The grid's lines (rows, or columns when the columns are numbered) as the card says them (Andrew, 2026-10-19:
    "even if it's just numbers"): {kind: numerical | labelled | lettered | mixed, summary, lines: [{line, number |
    label, numbers: every number its cells carry, cells}]}."""
    if not body:
        return {"kind": "none", "summary": "no rows", "lines": []}
    if G.keyed(g):
        ks = G.keyed_split(g) or {}
        rows = []
        for i in sorted({c[num_axis] for c in body}):
            labels = sorted({"_".join(ks[c["name"]][0]) for c in body if c[num_axis] == i and c["name"] in ks})
            rows.append({"line": i + 1, "label": labels[0] if labels else None, "cells": sum(1 for c in body if c[num_axis] == i)})
        return {"kind": "labelled", "summary": "labelled: " + ", ".join(r["label"] or "?" for r in rows), "lines": rows}
    F = G._Frame(g)
    rows = []
    for i in sorted({c[num_axis] for c in body}):
        cs = [c for c in body if c[num_axis] == i]
        nums = __import__("collections").Counter(F.num_of(c) for c in cs if F.num_of(c))
        rows.append({"line": i + 1, "number": nums.most_common(1)[0][0] if nums else None,
                     "numbers": [n for n, _ in nums.most_common()], "cells": len(cs)})
    seq = [r["number"] for r in rows]
    noun = "rows" if num_axis == "row" else "columns"
    if all(n and n.isdigit() for n in seq):
        ints = [int(n) for n in seq]
        kind = "numerical"
        summary = f"numerical, {noun} {ints[0]} to {ints[-1]}" if ints == list(range(ints[0], ints[0] + len(ints))) \
            else f"numerical, {noun} numbered {', '.join(seq)} (not by steps of 1)"
    elif all(n and len(n) == 1 and n.isalpha() for n in seq):
        kind, summary = "lettered", f"lettered, {noun} {seq[0]} to {seq[-1]}"
    else:
        kind, summary = "mixed", f"{noun} numbered {', '.join(n or '?' for n in seq)}"
    return {"kind": kind, "summary": summary, "lines": rows}


def standardize(bid: str, tid: str, *, apply, pos: Optional[int] = None, line: Optional[int] = None,
                wording: Optional[str] = None) -> dict:
    """The card's "standardize" buttons (Andrew, 2026-10-19): one position (`pos`, 1-based; with `wording`, the one the
    person picked, `_#` or `_N` for the number), every inconsistent position (neither), or one line (`line`, 1-based)
    renumbered. {status, steps, applied, left}; nothing accepted. `steps` say, in plain words, what was done and what
    was left and why (2026-10-22: "it often doesn't work and never says why clearly")."""
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid, bid)
    if not g:
        return {"status": "gone", "steps": ["the grid is no longer found on the page (renamed or moved?)"]}
    blank = resolve_blank(bp)
    lines = _lines(blank) if blank else {}
    forced = {pos - 1: wording.replace("_#", "_N")} if pos and wording else None
    r = G.standardize(bp, g, lines, G.text_match_score(), positions=[pos - 1] if pos else None,
                      lines_=[line - 1] if line else None, forced=forced)
    what = _what(g, pos, line)
    steps = [f"{what}: {r['why']}"] + (
        [f"also renamed, as they held the names: {', '.join(r['pulled'][:4])}{' ...' if len(r['pulled']) > 4 else ''}"]
        if r.get("pulled") else []) + r["left"]
    if not r["renames"]:
        return {"status": "nothing changed", "steps": steps, "applied": [], "left": r["left"]}
    out = apply([{"field": o, "edit": {"name": n}, "why": f"grids: standardize {what} of {tid} ({r['why'][:120]})"}
                 for o, n in r["renames"].items()])
    if out.get("errors"):
        steps.append("not all applied: " + "; ".join(out["errors"][:3]))
    steps.append(f"{len(out.get('changes') or [])} renamed")
    return {"status": f"{len(out.get('changes') or [])} renamed", "steps": steps, "applied": out.get("changes") or [],
            "left": r["left"]}


def relabel_line(bid: str, tid: str, line: int, label: str, *, apply) -> dict:
    """A row's label (or number) edited on the Grids card (Andrew, 2026-10-23: "can we add the ability to edit grid
    labels ... from the grid page"): in every cell of the line (1-based, as the card lists them) the label it carries
    is put to `label`, word for word where it sits in the name (applicant_first_nm -> spouse_first_nm;
    covered_individual_7_ssn -> covered_individual_19_ssn). A cell whose name does not carry the label, or whose new
    name another field holds, is left and said. {status, steps, applied, left}; nothing accepted."""
    import re
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid, bid)
    if not g:
        return {"status": "gone", "steps": ["the grid is no longer found on the page (renamed or moved?)"]}
    new = re.sub(r"[^a-z0-9]+", "_", str(label or "").lower()).strip("_")
    if not new:
        return {"status": "nothing changed", "steps": ["no label given"], "applied": [], "left": []}
    pv = preview(bid, tid)
    x = next((x for x in pv["lines"] if x["line"] == line), None)
    if x is None:
        return {"status": "nothing changed", "steps": [f"no row {line}"], "applied": [], "left": []}
    old = str(x.get("label") if x.get("label") is not None else x.get("number") or "")
    num_axis = "row" if pv["pos_axis"] == "col" else "col"
    what = f"{'row' if num_axis == 'row' else 'column'} {line}"
    if not old:
        return {"status": "nothing changed", "steps": [f"{what}: its cells carry no label or number to change"],
                "applied": [], "left": []}
    olds, news = old.split("_"), new.split("_")
    fields = bp.get("fields") or {}
    renames, left = {}, []
    for c in G.body(g):
        if c[num_axis] != line - 1:
            continue
        w = c["name"].split("_")
        at = next((i for i in range(len(w) - len(olds) + 1) if w[i:i + len(olds)] == olds), None)
        if at is None:
            left.append(f"{c['name']}: does not carry {old!r}")
            continue
        n = "_".join(w[:at] + news + w[at + len(olds):])
        if n != c["name"] and n in fields:
            left.append(f"{c['name']}: {n} is already another field's name")
            continue
        if n != c["name"]:
            renames[c["name"]] = n
    steps = [f"{what}: {old} -> {new}"] + left
    if not renames:
        return {"status": "nothing changed", "steps": steps, "applied": [], "left": left}
    out = apply([{"field": o, "edit": {"name": n}, "why": f"grids: {what} of {tid} relabeled {old} -> {new}"}
                 for o, n in renames.items()])
    if out.get("errors"):
        steps.append("not all applied: " + "; ".join(out["errors"][:3]))
    steps.append(f"{len(out.get('changes') or [])} renamed")
    return {"status": f"{len(out.get('changes') or [])} renamed", "steps": steps, "applied": out.get("changes") or [],
            "left": left}


def _what(g: list[dict], pos: Optional[int], line: Optional[int]) -> str:
    """'column 3' / 'row 2' as the grid lies on the page (positions are columns unless the grid reads by rows)."""
    if not (pos or line):
        return "every position"
    pos_axis = "col" if (G.keyed(g) or G.breaks(g)[0] == "columns") else "row"
    axis = pos_axis if pos else ("row" if pos_axis == "col" else "col")
    return f"{'column' if axis == 'col' else 'row'} {pos or line}"


def preview(bid: str, tid: str) -> dict:
    """What each standardize button on the grid's card would do, without doing it (Andrew, 2026-10-22: "we need a list
    of rows, a list of columns, and better implementation of the standardize functionality"): {pos_axis, keyed,
    positions: [{pos, wordings: [[wording, cells]], caption, off, locked, plan}], lines: [{line, number | label,
    numbers, cells, expect, plan}], all: plan}; a plan is {renames: [[old, new]], left: [why], why, pulled}, given
    only where there is something off. `pos` and `line` are 1-based places on the page's axis (`pos_axis` is the
    one the wordings run along: col, or row when the grid reads by rows)."""
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid, bid)
    if not g:
        raise ValueError(f"{tid} is no longer found on the page")
    blank = resolve_blank(bp)
    lines = _lines(blank) if blank and blank.exists() else {}
    body = G.body(g)
    keyed = G.keyed(g)
    if not body:
        return {"id": tid, "pos_axis": "col", "keyed": keyed, "positions": [], "lines": [], "all": None}
    F = G._Frame(g)
    pos_axis, num_axis = ("col", "row") if keyed else (F.pos_axis, F.num_axis)
    score = G.text_match_score()
    plan = lambda r: {"renames": sorted(r["renames"].items()), "left": r["left"], "why": r["why"],   # noqa: E731
                      "pulled": r.get("pulled") or []}
    number = {} if keyed else F.numbers(bp, g, lines, F.basis())[0]
    positions = []
    import collections
    for k in sorted({c[pos_axis] for c in body}):
        pcs = [c for c in body if c[pos_axis] == k]
        ws = collections.Counter((G._pattern(c["name"]) or c["name"]) if keyed else F.pat_of(c) for c in pcs)
        locked = not keyed and k in F.locked
        off = 0 if keyed or locked else sum(1 for c in pcs if number.get(c[num_axis]) is not None
                                            and (F.num_of(c) or "").isdigit() and int(F.num_of(c)) != number[c[num_axis]])
        p = {"pos": k + 1, "wordings": [[w.replace("_N", "_#"), n] for w, n in ws.most_common()], "off": off,
             "locked": locked, "caption": G.position_caption(bp, pcs, "columns" if pos_axis == "col" else "rows", lines)}
        if not keyed and (len(ws) > 1 or off):
            p["plan"] = plan(G.standardize(bp, g, lines, score, positions=[k]))
        positions.append(p)
    # a column whose renames run into fields outside the grid has another structure's names (Andrew, 2026-10-24,
    # je__acord_140 p1-G2: "the blanket this subject of insurance falls under", blanket_#_nbr, numbered 5-9 beside
    # the page's blanket list blanket_1_nbr .. _4_nbr; "we should be able to automate this cleanup"): offered under
    # the grid's row subject, the first column's start (subject_of_insurance_#_blanket_nbr beside
    # subject_of_insurance_#_txt), when that settles it
    alts = row_subject_wordings(bp, g, lines, score)
    for p in positions:
        if p["pos"] - 1 in alts:
            alt = alts[p["pos"] - 1]
            r = G.standardize(bp, g, lines, score, positions=[p["pos"] - 1], forced={p["pos"] - 1: alt})
            p["alt"] = {"wording": alt.replace("_N", "_#"), "plan": plan(r)}
    info = rows_info(g, body, pos_axis, num_axis)
    out_lines = []
    for ln in info["lines"]:
        i = ln["line"] - 1
        x = dict(ln, expect=number.get(i))
        shifted = not keyed and x.get("number") and number.get(i) is not None and x["number"].isdigit() \
            and int(x["number"]) != number[i]
        if not keyed and (len(ln.get("numbers") or []) > 1 or shifted):
            x["plan"] = plan(G.standardize(bp, g, lines, score, lines_=[i]))
            if not x["plan"]["renames"] and not x["plan"]["left"]:       # nothing for a button to do: say why instead
                free = [c for c in body if c[num_axis] == i and c[pos_axis] not in F.locked]
                x.pop("plan")
                x["note"] = "printed line numbers, kept as they are" if len(free) < len([c for c in body if c[num_axis] == i]) \
                    else "its cells already carry its number"
        out_lines.append(x)
    whole = None if keyed else plan(G.standardize(bp, g, lines, score))
    return {"id": tid, "pos_axis": pos_axis, "keyed": keyed, "summary": info["summary"], "positions": positions,
            "lines": out_lines, "all": whole, "aside": [{"row": r + 1, "why": w} for r, w in sorted(G.aside(g).items())]}


def row_subject_wordings(bp: dict, g: list[dict], lines: dict, score=None) -> dict[int, str]:
    """{position (0-based): wording, `_N` for the number} for each column whose renames run into fields outside the
    grid, put under the grid's row subject, the first column's start (Andrew, 2026-10-24, je__acord_140 p1-G2: the
    blanket each subject of insurance falls under, blanket_5_nbr .. _9_nbr beside the page's blanket list
    blanket_1_nbr .. _4_nbr: subject_of_insurance_#_blanket_nbr; "we should be able to automate this cleanup", in the
    code rather than Opus), where that settles every cell of the column."""
    F = G._Frame(g)
    pats = {k: collections.Counter(F.pat_of(c) for c in F.at(k)).most_common(1)[0][0] for k in F.positions if F.at(k)}
    first = pats.get(min(pats)) if pats else ""
    if not first or "_N" not in first:
        return {}
    row_subject = first.split("_N", 1)[0]
    out = {}
    for k, w in pats.items():
        if not w or "_N" not in w or w.startswith(row_subject + "_N"):
            continue
        r = G.standardize(bp, g, lines, score, positions=[k])
        if not any("a field outside this grid" in x for x in r["left"]):
            continue
        alt = f"{row_subject}_N_{w.replace('_N', '', 1)}"
        r2 = G.standardize(bp, g, lines, score, positions=[k], forced={k: alt})
        if r2["renames"] and not any("outside this grid" in x for x in r2["left"]):
            out[k] = alt
    return out


def _grid(bp: dict, tid: str, bid: Optional[str] = None):
    """(the table listed under `tid`, its grid) or (None, None)."""
    if bid:
        e = next((e for e in listing(bid, bp) if e["id"] == tid and e["status"] == "active"), None)
        if not e:
            return None, None
        # halves side by side read as one, when that is how its names run (grid_naming.unfold, 2026-10-24): the
        # card, the check and standardize then see ACORD 140's blankets 1-4 as four rows, not two rows renumbered
        g = e["grid"]
        halves = G.unfold(g)
        if halves is not None and G.on_pattern(halves)[0]:
            g = halves
        return {"id": tid, "page": g[0]["page"]}, g
    want = next((t for t in tables(bp) if t["id"] == tid), None)
    if not want:
        return None, None
    names = {c["name"] for c in want["cells"]}
    g = next((g for g in G.grids(bp, blocks=False) if {c["name"] for c in g} == names), None)
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
    `apply(edits)` writes renames (form_chat.apply's result), `ask_opus(page, tid, steps)` returns the chat's proposal
    for this table."""
    bp = h._load(h.working_path(bid))
    t, g = _grid(bp, tid, bid)
    if not g:
        return {"status": "gone", "steps": ["the grid is no longer found on the page (renamed or moved?)"]}
    page, steps = t["page"], []
    if G.on_pattern(g)[0]:
        acc = accept(page, [c["name"] for c in G.body(g)])
        return {"status": "validated", "steps": [f"code check: on pattern; {len(acc)} cell(s) accepted"], "accepted": acc}
    blank = resolve_blank(bp)
    lines = _lines(blank) if blank else {}
    r = G.resolve(bp, g, lines, G.text_match_score())
    steps.append(f"resolver: {r['status']} ({r['why']})")
    forced = {}
    if r["status"] not in ("fixed", "ok"):
        # a column holding another set's names, renamed under the grid's row subject first (code, no model call), then
        # the check goes on with the new names
        alts = row_subject_wordings(bp, g, lines, G.text_match_score())
        if alts:
            ren = {}
            for k, w in alts.items():
                ren.update(G.standardize(bp, g, lines, G.text_match_score(), positions=[k], forced={k: w})["renames"])
            out = apply([{"field": o, "edit": {"name": n}, "why": "grids: a column holding another set's names, under the "
                          "grid's row subject"} for o, n in ren.items()])
            steps.append("row subject: " + ", ".join(f"column {k + 1} as {w.replace('_N', '_#')}" for k, w in alts.items())
                         + f" (code, no model call): {len(out.get('changes') or [])} rename(s) applied"
                         + (f"; not all: {'; '.join(out['errors'][:2])}" if out.get("errors") else ""))
            bp = h._load(h.working_path(bid))
            t, g = _grid(bp, tid, bid)
            if not g:
                return {"status": "fixed", "steps": steps + ["the grid is no longer found after the renames"],
                        "applied": out.get("changes") or []}
            if G.on_pattern(g)[0]:
                acc = accept(page, [c["name"] for c in G.body(g)])
                return {"status": "fixed", "steps": steps + [f"code check: on pattern; {len(acc)} cell(s) accepted"],
                        "applied": out.get("changes") or [], "accepted": acc}
            r = G.resolve(bp, g, lines, G.text_match_score())
            steps.append(f"resolver: {r['status']} ({r['why']})")
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
        out = apply([{"field": o, "edit": {"name": n}, "why": "grids: " + ("Jev's wording, " if forced else "")
                      + "each position one wording, each line one number"} for o, n in r["renames"].items()]) \
            if r["renames"] else {"changes": [], "errors": []}
        if out.get("errors"):
            steps.append("not all applied: " + "; ".join(out["errors"][:3]))
        names = [r["renames"].get(c["name"], c["name"]) for c in G.body(g)]
        acc = accept(page, names)
        steps.append(f"{len(out.get('changes') or [])} rename(s) applied; {len(acc)} cell(s) accepted")
        return {"status": "fixed" if r["renames"] else "validated", "steps": steps,
                "applied": out.get("changes") or [], "accepted": acc}
    prop = ask_opus(page, tid, list(steps))
    steps.append(f"Opus ({tid} only): " + (prop.get("reply") or "no proposal"))
    return {"status": "proposed", "steps": steps, "proposals": prop}
