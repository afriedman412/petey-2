"""Blueprint review: one web page for checking a blueprint against its blank, in three modes over the same picker,
page and zoom (and a read-only audit):

    Review       accept / flag / note per field, risk-first by witness tier   (`hand_review`, runs/hand_review/)
    Groups       confirm option groups, drag boxes to regroup, drag text boxes together to combine them
                                                                                (`group_review`, runs/group_review/)
    Add / remove suggestions and drawn areas -> proposed fields; not-a-field; remove a field
                                                                                (`field_add`, runs/field_add/)
    Audit        read only: each version of the form (library copy, fresh run) with its numbers per page, and the
                 run history (generation, runs, checks, review); a batch table of the forms at the top   (`run_audit`)

    PYTHONPATH=. venv/bin/python -m petey.validate.blueprint_review [--port 5005] [--mode review|groups|add]

Each mode's logic, record and command line stay in its own module; this file serves the one page and routes to
them. The old entry points (`python -m petey.validate.hand_review`, `group_review`, `field_add` with no subcommand)
open this page in their mode.

One working copy (2026-10-13, Andrew: "everything should be reading from the same source"): the page's first change
to a blueprint opens a copy of it (`draft.py`), and every change is applied to the copy at once, so all three modes
show the same file: a Review correction or removal as it is saved, an Add / remove change as it is saved, a Groups
regrouping when you leave Groups (or press its apply button; mid-regrouping states are often not valid yet). The
header's "save blueprint" copies it over the blueprint; "discard" throws it away and puts the three records back.
The modules' `--apply` command lines still write whichever file the page would (the copy while one is open).
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import pymupdf

from petey import web
from petey.validate import draft, field_add, group_review, hand_review, run_audit
from petey.validate.retype import resolve_blank

HTML_PATH = Path(__file__).with_suffix(".html")
DPI = 144                      # option boxes are 8-10 pt; at 110 dpi (the old hand review) they are 12 px targets
MODES = ("review", "groups", "add", "grids", "blocks", "audit")


class Audit:
    """Audit mode (`run_audit`): one form's versions and history; the batch table for the forms at the top."""

    def __init__(self, app: "App") -> None:
        self.app = app

    def detail(self, bid: str) -> dict:
        return run_audit.audit(bid, self.app.paths, self.app.review._index)

    def batch(self) -> dict:
        forms = list((hand_review._focus().get("forms") or {}))
        return {"why": hand_review._focus().get("why"), "rows": run_audit.batch(forms, self.app.paths, self.app.review._index)}


class Cancelled(Exception):
    """A grid / block check stopped by its cancel button."""


def until(fn, stopped, every: float = 0.2):
    """fn() on a thread, given up as soon as stopped() is true (its answer, when it comes, is dropped)."""
    import concurrent.futures as cf
    if stopped():
        raise Cancelled
    ex = cf.ThreadPoolExecutor(1)
    fut = ex.submit(fn)
    try:
        while True:
            try:
                return fut.result(timeout=every)
            except cf.TimeoutError:
                if stopped():
                    raise Cancelled
    finally:
        ex.shutdown(wait=False)


def page_sizes(bp: dict) -> list[dict]:
    blank = resolve_blank(bp)
    if not (blank and blank.exists()):
        return []
    doc = pymupdf.open(str(blank))
    try:
        return [{"page": i, "w_pt": pg.rect.width, "h_pt": pg.rect.height} for i, pg in enumerate(doc, start=1)]
    finally:
        doc.close()


class Grids:
    """The Grids tab (`grid_check`): every numbered grid of the form, and one click to check and validate one."""

    def __init__(self, app: "App") -> None:
        self.app = app
        self.running: set[tuple] = set()             # (bid, tid) of each check under way
        self.stop: set[tuple] = set()                # ... and the ones cancelled

    def detail(self, bid: str) -> dict:
        from petey.validate import grid_check
        p = self.app.working(bid)
        bp = hand_review._load(p)
        vs = hand_review.load_verdicts(bid).get("verdicts") or {}
        tabs = grid_check.tables(bp, bid)             # the form's kept grids: ids, cancelled, ...
        for t in tabs:
            t["dismissed"] = t.get("status") in ("cancelled", "split")       # split: set aside by rule, restorable
            for c in t["cells"]:
                c["accepted"] = (vs.get(c["name"]) or {}).get("verdict") == "accept"
            t["accepted"] = sum(c["accepted"] for c in t["cells"] if not c.get("total"))
            t["body"] = sum(not c.get("total") for c in t["cells"])     # validated when every one is accepted
        return {"id": bid, "path": str(self.app.paths[bid]), "pages": page_sizes(bp), "tables": tabs,
                "sha": hand_review._sha(p)}

    def preview(self, bid: str, tid: str) -> dict:
        """What each standardize button on a grid's card would do (2026-10-22)."""
        from petey.validate import grid_check
        return grid_check.preview(bid, tid)

    def dismiss(self, bid: str, tid: str, on: bool) -> dict:
        """Cancel ("not a grid") a grid, the finder's or the person's, or restore it (2026-10-17: one button, the
        provenance tells them apart)."""
        from petey.validate import grid_check
        return grid_check.set_status(bid, tid, on, hand_review._load(self.app.working(bid)))

    def create(self, bid: str, page: int, rect) -> dict:
        """A grid drawn on the page: the fields inside, arranged into rows and columns."""
        from petey.validate import grid_check
        return grid_check.create(bid, hand_review._load(self.app.working(bid)), page, rect)

    def combine(self, bid: str, ids: list[str]) -> dict:
        from petey.validate import grid_check
        return grid_check.combine(bid, hand_review._load(self.app.working(bid)), ids)

    def _apply(self, bid: str):
        return _apply_as_claude(self.app, bid)

    def standardize(self, bid: str, tid: str, pos=None, line=None, wording=None) -> dict:
        """One position (with the person's pick of wording, or not), every inconsistent position, or one line of a
        grid to one wording / its number (2026-10-19; 2026-10-22: the pick, and plain reasons)."""
        from petey.validate import grid_check
        out = grid_check.standardize(bid, tid, apply=self._apply(bid), pos=int(pos) if pos else None,
                                     line=int(line) if line else None, wording=wording or None)
        self.app.refresh()
        return {**out, "entry": self.app.entry(bid)}

    def relabel(self, bid: str, tid: str, line, label: str) -> dict:
        """A row's label or number edited on the card (2026-10-23)."""
        from petey.validate import grid_check
        out = grid_check.relabel_line(bid, tid, int(line), label, apply=self._apply(bid))
        self.app.refresh()
        return {**out, "entry": self.app.entry(bid)}

    def check(self, bid: str, tid: str) -> dict:
        from petey.validate import form_chat, grid_check
        apply = self._apply(bid)

        def ask_opus(page, tid, steps):                 # this grid only (form_chat.table_request, 2026-10-21)
            req = form_chat.table_request(bid, tid, steps)
            return {"request": req, **form_chat.ask(bid, [{"role": "user", "content": req}], only_pages=[page])}
        key = (bid, tid)
        self.stop.discard(key)
        self.running.add(key)
        stopped = lambda: key in self.stop             # noqa: E731

        def before(fn):          # a write is not started once the check is cancelled (one started runs to its end)
            def go(*a):
                if stopped():
                    raise Cancelled
                return fn(*a)
            return go
        try:
            refused: list = []
            out = grid_check.check(bid, tid, accept=before(lambda page, names: self.app.accept_grid(bid, page, set(names),
                                                                                    refused=refused)),
                                   apply=before(apply), ask_opus=lambda *a: until(lambda: ask_opus(*a), stopped))
            if refused:
                out["steps"] = (out.get("steps") or []) + [f"not accepted: {x['grid']}: {x['why']}" for x in refused]
                out["refused"] = refused
        except Cancelled:
            out = {"status": "cancelled", "steps": ["cancelled: nothing written after the cancel"]}
        finally:
            self.running.discard(key)
            self.stop.discard(key)
        self.app.refresh()
        return {**out, "entry": self.app.entry(bid)}

    def cancel(self, bid: str, tid: str) -> dict:
        """Stop the check under way on one grid (Andrew, 2026-10-21: "can the cancel button cancel the validation
        query"): nothing is written after it, and a call to Opus under way is given up."""
        key = (bid, tid)
        if key in self.running:
            self.stop.add(key)
        return {"cancelled": key in self.stop}


def _apply_as_claude(app: "App", bid: str):
    """Renames into the working copy as Claude's (form_chat.apply), logged with the draft."""
    from petey.validate import form_chat

    def apply(edits):
        app.open_draft(bid)
        before = hand_review._sha(app.working(bid))
        out = form_chat.apply(bid, edits, [])
        app.follow(bid, before)
        draft.log(bid, "claude", out.get("changes") or [])
        return out
    return apply


class Blocks:
    """The Blocks tab (`block_types`, 2026-10-21): block types and their blocks; no block groups since 2026-10-22."""

    def __init__(self, app: "App") -> None:
        self.app = app

    def detail(self, bid: str) -> dict:
        from petey.validate import block_types, grid_check
        p = self.app.working(bid)
        bp = hand_review._load(p)
        vs = hand_review.load_verdicts(bid).get("verdicts") or {}
        block_types.reattach(bid, bp)           # positions whose field was regrouped or combined: the field there now
        rec = grid_check.load_set(bid)
        held = {c for t in rec.get("types") or [] for b in t["blocks"] for c in b if c}
        # the fields in no block, drawn on the page to be dragged onto one (2026-10-22)
        loose = [{"code": x["code"], "name": x["name"], "page": x["page"], "rect": x["rect"], "kind": block_types.said(x["kind"])}
                 for x in block_types._boxes(bp) if x["code"] not in held]
        return {"id": bid, "path": str(self.app.paths[bid]), "pages": page_sizes(bp), "sha": hand_review._sha(p),
                "types": block_types.listing(bp, rec, vs), "loose": loose}

    def _apply(self, bid: str):
        return _apply_as_claude(self.app, bid)

    def block_draw(self, bid: str, page: int, rect) -> dict:
        """An area drawn on the Blocks tab: a block of an existing block type, or a new type (2026-10-21)."""
        from petey.validate import block_types
        return block_types.draw(bid, hand_review._load(self.app.working(bid)), page, rect)

    def type_confirm(self, bid: str, tid: str, words: list) -> dict:
        """A block type's positions confirmed by the person (2026-10-21): each a field's parts (subject, suffix, part;
        2026-10-22) or a wording."""
        from petey.validate import block_types
        return block_types.confirm(bid, hand_review._load(self.app.working(bid)), tid, words)

    def block_validate(self, bid: str, code: str) -> dict:
        """Check & validate one block against its confirmed type: its cells accepted when
        every name is the block's start and the type's wording (a field with a verdict keeps it)."""
        from petey.validate import block_types
        res = block_types.validate_block(bid, hand_review._load(self.app.working(bid)), code)
        acc = []
        if res["ok"]:
            have = hand_review.load_verdicts(bid).get("verdicts") or {}
            acc = [n for n in res["names"] if not (have.get(n) or {}).get("verdict")]
            if acc:
                self.app.put_verdicts(bid, {"verdicts": {n: {"verdict": "accept", "note": f"block type {res['type']}"}
                                                         for n in acc}})
        self.app.refresh()
        return {**res, "accepted": acc, "entry": self.app.entry(bid)}

    def block_parts(self, bid: str, code: str, prefix, iteration, by=None) -> dict:
        """A block's prefix and iteration, set by the person, and whether a number or its prefix tells it apart."""
        from petey.validate import block_types
        return block_types.set_parts(bid, code, prefix, iteration, by)

    def type_auto(self, bid: str, tid: str, on: bool) -> dict:
        """A block type's blocks named from its label and numbered, or not."""
        from petey.validate import block_types
        return block_types.set_auto(bid, tid, on)

    def type_label(self, bid: str, tid: str, label: str) -> dict:
        """A block type's label."""
        from petey.validate import block_types
        return block_types.set_label(bid, tid, label)

    def block_detect(self, bid: str, page: int) -> dict:
        """Every block type's copies on a page added as its blocks."""
        from petey.validate import block_types
        return block_types.detect(bid, hand_review._load(self.app.working(bid)), page)

    def run_finders(self, bid: str) -> dict:
        """"run finders" (2026-10-23): SIA's repeated blocks as new block types; the Grids tab's finder then leaves out
        what they hold when it next loads. The suggested groups first (Andrew, 2026-10-25: "make sure the finder groups
        related ind fields instead of putting them in a single block"): made and applied as leaving Groups applies
        them, the blocks there pointed at them (`reattach`: a group over several positions of every block becomes one),
        then the blocks looked for, a group one box among them."""
        from petey.validate import block_types
        made, err = [], None
        applied = False
        try:
            made = self.app.groups.make_suggested(bid)
            # also groups the Groups tab made as it opened, waiting in its record until the tab is left
            if made or self.app.groups.plan_for(bid)["changes"]:
                self.app.apply_groups(bid)
                applied = True
        except Exception as e:                   # noqa: BLE001  the blocks still run; the groups wait in Groups
            err = str(e)
        bp = hand_review._load(self.app.working(bid))
        if applied:
            block_types.reattach(bid, bp)
        out = block_types.discover(bid, bp)
        out["groups_made"] = made
        if err:
            out["groups_error"] = err
        return out

    def block_rescan(self, bid: str, page: int) -> dict:
        """The page rescanned (Andrew, 2026-10-22: "we should be able to rescan a page to allow blocks to reform"): each
        type with a block on it takes in the free fields that repeat in all its blocks, then its copies are looked for."""
        from petey.validate import block_types
        return block_types.rescan(bid, hand_review._load(self.app.working(bid)), page)

    def block_assign(self, bid: str, code: str, tid: str) -> dict:
        """A block given another block type by hand, its boxes paired by place, and its names put to the type's
        wordings at once, as Claude's renames (Andrew, 2026-10-22: "assigning a block to a type should just overwrite
        the labels using the type info, by location"); held renames and same-name blocks said, nothing accepted."""
        from petey.validate import block_types
        out = block_types.assign(bid, hand_review._load(self.app.working(bid)), code, tid)
        fix = self.block_fix(bid, out["code"])
        return {**out, "renamed": fix["renamed"], "rename_errors": fix["errors"], "held": fix["held"], "same": fix["same"]}

    def block_add_field(self, bid: str, code: str, field: str, grow: bool = False) -> dict:
        """A field dropped on a block (2026-10-22): into the block's empty position of its kind nearest its place, or
        a new position of the type when `grow`; then that field's name put to its position's wording (only that field:
        the block's other names are left as they are)."""
        from petey.validate import block_types
        out = block_types.add_field(bid, hand_review._load(self.app.working(bid)), code, field, grow)
        if out.get("grow_needed"):
            return out
        bp = hand_review._load(self.app.working(bid))
        name = block_types._names(bp).get(str(field))
        r = block_types.block_renames(bid, bp, out["code"])
        fix = self._renames(bid, r["type"], [d for d in r["renames"] if d["name"] == name],
                            [d for d in r["held"] if d["name"] == name], r["same_as"])
        return {**out, "renamed": fix["renamed"], "rename_errors": fix["errors"], "held": fix["held"], "same": fix["same"]}

    def type_fix(self, bid: str, tid: str) -> dict:
        """Every block of a block type put to its wordings (each block's own start kept, cancelled renames left), as
        Claude's renames in one go; nothing accepted (Andrew, 2026-10-21: "changing the block type wordings should raise
        the option to change every block of that type")."""
        from petey.validate import block_types, grid_check
        bp = hand_review._load(self.app.working(bid))
        t = next((x for x in grid_check.load_set(bid).get("types") or [] if x["id"] == tid), None)
        if t is None:
            raise ValueError(f"no block type {tid}")
        r = block_types.type_renames(bid, bp, tid)
        return self._renames(bid, tid, r["renames"], r["held"], r["same"])

    def block_keep(self, bid: str, code: str, pos: int, on: bool) -> dict:
        """A suggested rename cancelled (the name kept as it is), or the cancel undone."""
        from petey.validate import block_types
        return block_types.keep_name(bid, code, int(pos), on)

    def type_validate(self, bid: str, tid: str) -> dict:
        """Check & validate every block of a confirmed block type (Andrew, 2026-10-21: "need a 'validate all' button on
        the block type"): the cells of each block that follows the type's wordings accepted, in one write (a field with
        a verdict keeps it); the others said, nothing of theirs accepted."""
        from petey.validate import block_types, grid_check
        bp = hand_review._load(self.app.working(bid))
        t = next((x for x in grid_check.load_set(bid).get("types") or [] if x["id"] == tid), None)
        if t is None:
            raise ValueError(f"no block type {tid}")
        have = hand_review.load_verdicts(bid).get("verdicts") or {}
        ok, off, acc = [], [], []
        for i, b in enumerate(t["blocks"], 1):
            res = block_types.validate_block(bid, bp, b[0])
            if res["ok"]:
                ok.append(f"{tid}-{i}")
                acc += [n for n in res["names"] if not (have.get(n) or {}).get("verdict")]
            else:
                off.append({"block": f"{tid}-{i}", "off": len(res["differs"])})
        if acc:
            self.app.put_verdicts(bid, {"verdicts": {n: {"verdict": "accept", "note": f"block type {tid}"} for n in acc}})
        self.app.refresh()
        return {"type": tid, "validated": ok, "off": off, "accepted": len(acc), "entry": self.app.entry(bid)}

    def block_fix(self, bid: str, code: str) -> dict:
        """A block's names put to its type's wordings (its own start kept), as Claude's renames; nothing accepted. The
        other blocks whose names it moves onto move with it, in one batch (a swap); renames onto a name a field
        keeps are left and said."""
        from petey.validate import block_types
        r = block_types.block_renames(bid, hand_review._load(self.app.working(bid)), code)
        return self._renames(bid, r["type"], r["renames"], r["held"], r["same_as"])

    def _renames(self, bid: str, tid: str, renames: list, held: list, same: list) -> dict:
        # the parts go in as a field's do (the parts panel's edit): the name printed from them, the parts stored
        edits = [{"field": d["name"], "edit": {"identifiers": d["ident"]} if d.get("ident") else {"name": d["want"]},
                  "why": f"block type {tid}: the type's parts"} for d in renames]
        out = self._apply(bid)(edits) if edits else {"changes": [], "errors": []}
        self.app.refresh()
        return {"renamed": len(out.get("changes") or []), "errors": out.get("errors") or [],
                "held": [f"{d['name']} -> {d['want']} (held by {d['held']})" for d in held], "same": same,
                "entry": self.app.entry(bid)}

    def block_out(self, bid: str, code: str, whole: bool = True) -> dict:
        """A block that is no longer one."""
        from petey.validate import block_types
        return block_types.remove_block(bid, hand_review._load(self.app.working(bid)), code)


def name_parts(bid: str, field: str, new: str) -> dict:
    """A proposed name read into its parts, as the form's other names are (Andrew, 2026-10-25: '"improve name" should
    also change "subject"'): field_identifiers.read with the form's names around it, so a block's number after
    its subject and a field's own number are told apart; in the standard's shape (petey/naming.py)."""
    import sys
    from petey.validate.standardize_names import PARTS_AFTER, SUFFIXES, _is_group
    from petey import naming
    bp = hand_review._load(hand_review.working_path(bid))
    spec = (bp.get("fields") or {}).get(field) or {}
    ident = naming.parse(new, set(SUFFIXES), set(PARTS_AFTER), group=_is_group(spec))
    return {k: v for k, v in ident.items() if v not in (None, "") and k in naming.ORDER}


def overlay(bp: dict, bid: str, verdicts: dict) -> dict:
    """`App.overlay` for one blueprint and its verdicts."""
    import sys
    from petey.validate import grid_naming
    from petey.validate import block_types, grid_check
    acc = {n for n, v in verdicts.items() if (v or {}).get("verdict") == "accept"}
    fields = []
    for n, sp in (bp.get("fields") or {}).items():
        if not isinstance(sp, dict):
            continue
        ws = [sp["widget"]] if sp.get("widget") else list((sp.get("widgets") or {}).values())
        rs = [{"page": w.get("page"), "rect": w.get("rect")} for w in ws if w.get("rect")]
        if rs:
            fields.append({"name": n, "id": str(sp.get("x_petey_id", "")), "page": rs[0]["page"], "rects": rs,
                           "accepted": n in acc, "group": len(rs) > 1 and sp.get("type") in ("category", "multi_category")})

    def bbox(rs):
        return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]
    grids = []
    for t in grid_check.listing(bid, bp):
        if t["status"] != "active":
            continue
        rs = [r for r in (grid_check._rect(bp, c["name"]) for c in t["grid"]) if r]
        if rs:
            body = grid_naming.body(t["grid"])
            grids.append({"id": t["id"], "page": t["page"], "bbox": bbox(rs),
                          "validated": bool(body) and all(c["name"] in acc for c in body)})
    rec, boxes = grid_check.load_set(bid), {b["code"]: b for b in block_types._boxes(bp)}
    name = {str(sp.get("x_petey_id")): n for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}
    blocks = []
    for y in rec.get("types") or []:
        for i, b in enumerate(y.get("blocks") or [], 1):
            bs = [boxes[c] for c in b if c in boxes]
            if bs:
                blocks.append({"id": f"{y['id']}-{i}", "label": y.get("label") or "", "page": bs[0]["page"],
                               "bbox": bbox([x["rect"] for x in bs]),
                               "validated": all(name.get(c) in acc for c in b if c)})
    return {"fields": fields, "grids": grids, "blocks": blocks}


class App:
    def __init__(self) -> None:
        self.review = hand_review.State()
        self.groups = group_review.State()
        self.add = field_add.State()
        self.audit = Audit(self)
        self.grids = Grids(self)
        self.blocks = Blocks(self)
        self.paths = self.review.paths
        self.png: dict[tuple[str, int], bytes] = {}
        self.mtimes: dict[str, float] = {}

    def index(self) -> None:
        t0 = time.time()                 # parsed copies of the blueprints brought up to date on all cores first, so
        n = hand_review.warm_parsed([self.working(b) for b in self.paths])     # both indexes below read them
        print(f"  {n} blueprint(s) parsed again ({time.time() - t0:.1f}s)")
        self.review.index()
        self.groups.index()
        self.mtimes = {bid: self.working(bid).stat().st_mtime for bid in self.paths}

    def working(self, bid: str) -> Path:
        return hand_review.working_path(bid, self.paths)

    def open_draft(self, bid: str) -> Path:
        return draft.ensure(bid, self.paths[bid])

    def follow(self, bid: str, before: str) -> None:
        """After a change the page made itself (a regrouping, fields added or removed): `draft.follow`."""
        draft.follow(bid, before, hand_review._sha(self.working(bid)))

    def refresh(self) -> None:
        """Re-read the picker rows of blueprints whose file changed since they were indexed (an --apply, a loop, an
        edit by hand): the indexes are built once at startup."""
        for bid in list(self.paths):
            try:
                m = self.working(bid).stat().st_mtime
            except FileNotFoundError:              # a blueprint removed while the server runs (2026-10-13: i-485)
                for d in (self.paths, self.mtimes, self.review._index, self.groups._index):
                    d.pop(bid, None)
                continue
            if self.mtimes.get(bid) == m:
                continue
            self.mtimes[bid] = m
            self.review._index[bid] = self.review._entry(bid)
            g = self.groups._entry(bid)
            if g:
                self.groups._index[bid] = g
            else:
                self.groups._index.pop(bid, None)

    def overlay(self, bid: str) -> dict:
        """What every tab can draw over the page besides its own (Andrew, 2026-10-22: "add block and grid overlays and
        validated fields to all views, so it's clear what is and isn't already accounted for"): {fields: [{name, id,
        page, rects, accepted, group}], grids: [{id, page, bbox, validated}], blocks: [{id, page, bbox, validated}]}.
        Boxes only, nothing checked: cheap enough to read again after every change."""
        return overlay(hand_review._load(self.working(bid)), bid,
                       hand_review.load_verdicts(bid).get("verdicts") or {})

    def entry(self, bid: str) -> dict:
        """One picker row: what each mode has recorded for this blueprint."""
        r = self.review._index.get(bid) or self.review._entry(bid)
        g = self.groups._index.get(bid)
        rec = field_add.load_record(bid)
        return {**r,
                "groups": ({k: g[k] for k in ("groups", "orphans", "confirmed", "units", "combos", "stale")} if g else None),
                "add": {"added": len(rec.get("added") or []), "dismissed": len(rec.get("dismissed") or []),
                        "removed": len(rec.get("removed") or []),
                        "applied": sum(len(a.get("changes") or []) for a in rec.get("applied") or [])},
                "passes": hand_review.passes_record().get(bid)}       # read fresh: the passes record changes on its own

    def apply_groups(self, bid: str) -> dict:
        """Groups' regrouping into the working copy (on leaving Groups, its apply button, or Save)."""
        before = hand_review._sha(self.open_draft(bid))
        try:
            pl = group_review.apply(bid)
        except SystemExit as e:                 # apply's refusals (stale record, plan errors) are SystemExit
            raise ValueError(str(e)) from None
        self.follow(bid, before)
        draft.log(bid, "groups", pl["changes"])
        self.refresh()
        return {"changes": pl["changes"], "entry": self.entry(bid)}

    def apply_review(self, bid: str) -> dict:
        """The record's corrections not yet applied, into the working copy. A refusal (a rename onto a name another
        field still has) leaves them pending and comes back as `apply_error`; applying again once the other field is
        renamed takes both."""
        vs = hand_review.load_verdicts(bid).get("verdicts") or {}
        if not any(v.get("edit") and not v.get("applied") for v in vs.values()):
            return {}
        self.open_draft(bid)
        lines: list[str] = []
        try:
            hand_review.apply_edits(bid, log=lines.append)
        except SystemExit as e:
            return {"apply_error": str(e)}
        changes = [ln.strip() for ln in lines if ln.startswith("  ")]
        draft.log(bid, "review", changes)
        self.refresh()
        return {"applied": changes}

    def apply_add(self, bid: str, out: dict) -> dict:
        """Add / remove's recorded additions and removals, into the working copy, when they plan cleanly."""
        if not out.get("changes") or out.get("errors"):
            return out
        before = hand_review._sha(self.open_draft(bid))
        try:
            pl = field_add.apply(bid) or {}
        except SystemExit as e:
            return {**out, "apply_error": str(e)}
        self.follow(bid, before)
        draft.log(bid, "add", pl.get("changes") or [])
        self.refresh()
        return {**out, "applied": pl.get("changes") or [], "changes": [], "skipped": pl.get("skipped") or []}

    def reset_verdicts(self, bid: str) -> dict:
        """The Review bar's "reset validation" (2026-10-22): every verdict cleared, the record kept aside."""
        out = hand_review.reset_verdicts(bid)
        self.review._index[bid] = self.review._entry(bid)
        return {**out, "entry": self.entry(bid)}

    def put_verdicts(self, bid: str, body: dict) -> dict:
        out = self.review.put_verdicts(bid, body, on_pending=lambda: self.open_draft(bid))
        ap = self.apply_review(bid)
        if ap.get("applied"):
            out = hand_review.load_verdicts(bid)
        return {**out, **ap, "entry": self.entry(bid)}

    def code_grid(self, bid: str, page: int) -> tuple[list, list]:
        """The numbered tables on the page split by the code check that runs before any model (Andrew, 2026-10-15:
        "a quick validation check with code for CHECK GRID before we do anything with AI"; grid_naming.on_pattern):
        ([table body passing], [table failing]). A passing table's cells are accepted without the model; the page goes
        to the model only when a table fails, or the layout finds none."""
        import sys
        from petey.validate import grid_naming
        bp = hand_review._load(self.working(bid))
        passed, failed = [], []
        for g in grid_naming.grids(bp, blocks=False):
            if g[0]["page"] == page and grid_naming.iterated(g):
                (passed.append(grid_naming.body(g)) if grid_naming.on_pattern(g)[0] else failed.append(g))
        return passed, failed

    def code_fix(self, bid: str, failed: list) -> tuple[list[dict], list[str], list]:
        """The renumbering the code can do itself for tables that fail its check (Andrew, 2026-10-16: "we have a
        programmatic check to see if it's already set up right, we should be able to programmatically just number
        things if they are out of order"): grid_naming's fixes for a table, kept only when they leave nothing
        unexplained, put the table on pattern and take no name another field keeps. ([edit], [cells now on pattern],
        [tables the code cannot fix])."""
        import sys
        from petey.validate import grid_naming
        bp = hand_review._load(self.working(bid))
        fields = bp.get("fields") or {}
        ren, left = grid_naming.fixes(bp, blocks=False)
        edits, cells, rest = [], [], []
        for g in failed:
            names = {c["name"] for c in g}
            mine = {o: n for o, n in ren.items() if o in names}
            unexplained = [ln for ln in left if ln.split(":")[0] in names or ln.startswith(f"grid p{g[0]['page']} ")]
            after = [dict(c, name=mine.get(c["name"], c["name"])) for c in g]
            free = all(n not in fields or n in mine for n in mine.values())
            if mine and not unexplained and free and grid_naming.on_pattern(after)[0]:
                edits += [{"field": o, "edit": {"name": n}, "why": "renumbered by the grid check's code: each column one "
                           "wording, each row one number"} for o, n in mine.items()]
                cells += [c["name"] for c in grid_naming.body(g)]     # current names: the apply maps them through the renames
            else:
                rest.append(g)
        return edits, cells, rest

    def accept_grid(self, bid: str, page: int, ok: set, refused: Optional[list] = None) -> list[str]:
        """Accept the cells a grid check vouched for (Andrew, 2026-10-15: "automatically accept any grid fields
        checked by the grid validator"; and: "if it's checking for it why doesn't it consider it when accepting?"): a
        cell is accepted when it is in `ok` and its grid passes the same test "check & validate" uses (the code
        check, or the resolver's "ok"; 2026-10-24: a stricter gate of its own refused ACORD 131's labelled rows,
        silently, after the check had passed them); a field with a verdict already keeps it. A grid with vouched
        cells that fails the test is said in `refused` ({grid, why}), shown under the button pressed. Note: "grid
        check"."""
        import sys
        from petey.validate import grid_naming
        from petey.validate import grid_check
        from petey.validate.retype import resolve_blank
        bp = hand_review._load(self.working(bid))
        have = hand_review.load_verdicts(bid).get("verdicts") or {}
        names, lines = [], None
        for t in grid_check.listing(bid, bp):
            g = t["grid"]
            if t["status"] != "active" or g[0]["page"] != page or not any(c["name"] in ok for c in g):
                continue
            passes, why = grid_naming.on_pattern(g)
            if not passes:
                if lines is None:
                    blank = resolve_blank(bp)
                    lines = grid_check._lines(blank) if blank and blank.exists() else {}
                r = grid_naming.resolve(bp, g, lines, grid_naming.text_match_score())
                passes = r["status"] == "ok"
                if not passes:
                    why = r["why"] if r["status"] != "fixed" else f"{len(r['renames'])} cell(s) to rename first ({r['why']})"
            if not passes:
                if refused is not None:
                    refused.append({"grid": t.get("id"), "why": why})
                continue
            names += [c["name"] for c in g if c["name"] in ok and not (have.get(c["name"]) or {}).get("verdict")]
        if names:
            self.put_verdicts(bid, {"verdicts": {n: {"verdict": "accept", "note": "grid check"} for n in names}})
        return names

    def chat_apply(self, bid: str, body: dict) -> dict:
        """The chat's ticked proposal (`form_chat`): edits and groups into the working copy, removals recorded in Add /
        remove and applied as Review's remove button does."""
        from petey.validate import form_chat
        self.open_draft(bid)
        out = form_chat.apply(bid, body.get("edits") or [], body.get("groups") or [])
        ren = out.get("renamed") or {}
        rem = [ren.get(r.get("field"), r.get("field")) for r in body.get("remove") or []]
        if rem:
            bp = hand_review._load(self.working(bid))
            have = field_add.load_record(bid).get("removed") or []
            new = []
            for n in rem:
                spec = (bp.get("fields") or {}).get(n)
                if not isinstance(spec, dict) or any(r.get("name") == n for r in have):
                    continue
                w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
                new.append({"name": n, "page": w.get("page"), "rect": w.get("rect"),
                            "when": time.strftime("%Y-%m-%d %H:%M:%S"), "from": "chat"})
            if new:
                ad = self.save_add(bid, {"removed": have + new})
                out["changes"] += [f"removed {r['name']}" for r in new] if ad.get("applied") else []
                if ad.get("apply_error") or ad.get("errors"):
                    out["errors"].append("removals recorded, not applied yet: "
                                         + (ad.get("apply_error") or "; ".join(ad.get("errors") or [])))
        if body.get("grid_page"):                # a "check grid" turn: the cells it vouched for, tables now on pattern
            ren = out.get("renamed") or {}
            ok = {ren.get(n, n) for n in body.get("confirmed") or []} | \
                 {ren.get(e.get("field"), e.get("field")) for e in body.get("edits") or []}
            out["refused"] = []
            out["accepted"] = self.accept_grid(bid, int(body["grid_page"]), ok, out["refused"])
        self.refresh()
        return {**out, "entry": self.entry(bid)}

    def save_add(self, bid: str, body: dict) -> dict:
        if body.get("added") or body.get("removed"):
            self.open_draft(bid)
        out = self.apply_add(bid, self.add.save(bid, body))
        return {**out, "entry": self.entry(bid)}

    def save_draft(self, bid: str, force: bool = False) -> dict:
        """The header's save: whatever is still pending goes into the copy first (a Groups regrouping not applied
        yet); a correction that cannot be applied, or a regrouping or addition with errors, stops it."""
        p = self.working(bid)
        if p == self.paths[bid]:
            raise ValueError("no working copy open")
        bp = hand_review._load(p)
        _, units, _ = group_review.current_units(bid, bp, hand_review._sha(p))
        gp = group_review.plan(bp, units, resolve_blank(bp))
        if gp["errors"]:
            raise ValueError("Groups has errors to fix first:\n  " + "\n  ".join(gp["errors"]))
        if gp["changes"]:
            self.apply_groups(bid)
        self.apply_review(bid)                  # corrections saved before the working copy (the old apply button)
        vs = hand_review.load_verdicts(bid).get("verdicts") or {}
        fields = hand_review._load(self.working(bid)).get("fields") or {}
        stuck = [n for n, v in vs.items() if v.get("edit") and not v.get("applied") and n in fields]
        if stuck:
            raise ValueError(f"{len(stuck)} correction(s) could not be applied (a name another field has): "
                             + ", ".join(stuck))
        rec = field_add.load_record(bid)
        if rec.get("added") or rec.get("removed"):
            pl = field_add.plan(hand_review._load(self.working(bid)), rec.get("added") or [], rec.get("removed") or [])
            if not pl["changes"] and not pl["errors"]:
                # only entries with nothing left to do (a removed field renamed by a rerun: 1014r, 2026-10-15):
                # applying clears them, instead of the record blocking the save for good
                field_add.apply(bid)
                rec = field_add.load_record(bid)
        if rec.get("added") or rec.get("removed"):
            raise ValueError("Add / remove has changes that do not apply cleanly; see its change list")
        out = draft.save(bid, self.paths[bid], force)
        self.refresh()
        return {**out, "entry": self.entry(bid)}

    def discard_draft(self, bid: str) -> dict:
        out = draft.discard(bid, self.paths[bid])
        self.refresh()
        return {**out, "entry": self.entry(bid)}

    def listing(self) -> list[dict]:
        if not self.review._index:
            self.index()
        self.refresh()
        # the top section's list is read fresh: a row is re-read only when its blueprint changes, and focus.json
        # changes on its own (2026-10-14: a new batch put at the top did not show)
        focus = hand_review._focus().get("forms") or {}
        return [dict(self.entry(bid), focus=focus.get(bid)) for bid in self.paths]

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key not in self.png:
            p = self.working(bid) if bid in self.paths else None
            blank = resolve_blank(hand_review._load(p)) if p else None
            if not blank or not blank.exists():
                return None
            doc = pymupdf.open(str(blank))
            try:
                if not 1 <= page <= len(doc):
                    return None
                self.png[key] = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
            finally:
                doc.close()
        return self.png[key]


APP: Optional[App] = None
SERVED: dict = {}                       # the port and mode serve() was started with, for the restart button


def restart() -> None:
    """The page's reboot button: replace this process with a fresh one on the same port, so edited code (this
    file, the modes' modules, the page) loads without going back to the terminal. The listening socket is not
    inherited across exec (PEP 446), so the new process binds the port again."""
    time.sleep(0.3)                     # let the handler's reply reach the page first
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, "-m", "petey.validate.blueprint_review",
                              "--port", str(SERVED["port"]), "--mode", SERVED["mode"], "--no-open"])


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, default=str).encode(), "application/json", code)

    def _body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")

    def _route(self, fn, bid: Optional[str] = None):
        if bid is not None and bid not in APP.paths:
            return self._send(b"no such blueprint", "text/plain", 404)
        try:
            out = fn()
        except KeyError as e:
            return self._send(f"not found: {e}".encode(), "text/plain", 404)
        except Exception as e:  # noqa: BLE001
            return self._send(f"{type(e).__name__}: {e}".encode(), "text/plain", 400)
        if out is None:
            return self._send(b"not found", "text/plain", 404)
        self._json(out)

    def _parts(self) -> list[str]:
        return unquote(urlparse(self.path).path).strip("/").split("/")

    def do_GET(self):
        if web.route(self, "GET"):                       # the extractor (petey.web), at /extract
            return
        path = unquote(urlparse(self.path).path)
        parts = self._parts()
        if path in ("/", "/index.html"):
            return self._send(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/blueprints":
            return self._json(APP.listing())
        if path == "/api/audit-batch":
            return self._route(APP.audit.batch)
        if len(parts) == 4 and parts[:2] == ["api", "blueprints"] and parts[3] == "sha":
            return self._route(lambda: {"sha": hand_review._sha(APP.working(parts[2]))}, parts[2])
        if len(parts) == 3 and parts[:2] == ["api", "draft"]:
            return self._route(lambda: {"draft": draft.status(parts[2], APP.paths[parts[2]])}, parts[2])
        if len(parts) == 5 and parts[:2] == ["api", "blueprints"] and parts[3] == "png":
            png = APP.page_png(parts[2], int(parts[4]))
            return self._send(png, "image/png") if png else self._send(b"no such page", "text/plain", 404)
        if len(parts) == 4 and parts[:2] == ["api", "review"] and parts[3] == "removals":
            return self._route(lambda: {"removed": field_add.load_record(parts[2]).get("removed") or []}, parts[2])
        if len(parts) == 3 and parts[:2] == ["api", "overlay"]:       # what every tab draws besides its own
            return self._route(lambda: APP.overlay(parts[2]), parts[2])
        if len(parts) == 3 and parts[0] == "api" and parts[1] in MODES:
            mode, bid = parts[1], parts[2]
            state = getattr(APP, mode)
            return self._route(lambda: state.detail(bid), bid)
        self._send(b"not found", "text/plain", 404)

    def do_PUT(self):
        parts = self._parts()
        if len(parts) != 4 or parts[0] != "api":
            return self._send(b"not found", "text/plain", 404)
        mode, bid, what = parts[1], parts[2], parts[3]
        body = self._body()
        if (mode, what) == ("review", "verdicts"):
            return self._route(lambda: APP.put_verdicts(bid, body), bid)
        if (mode, what) == ("review", "reset"):             # every verdict on the form cleared
            return self._route(lambda: APP.reset_verdicts(bid), bid)
        if (mode, what) == ("form", "note"):                 # the notes panel: one note per form
            def note():
                n = hand_review.set_form_note(bid, body.get("text") or "")
                if bid in APP.review._index:
                    APP.review._index[bid]["note"] = n if n.get("text") else None
                return {"note": n, "entry": APP.entry(bid)}
            return self._route(note, bid)
        if (mode, what) == ("groups", "notgroup"):           # a suggested group that is not one (group_finder)
            from petey.validate import group_finder
            return self._route(lambda: group_finder.dismiss(bid, list(body.get("items") or [])), bid)
        if (mode, what) == ("groups", "units"):
            def units():
                APP.open_draft(bid)
                return APP.groups.put_units(bid, body) | {"entry": APP.entry(bid)}
            return self._route(units, bid)
        if (mode, what) == ("review", "removals"):           # Review's remove button: the field-add record's removals
            return self._route(lambda: APP.save_add(bid, {"removed": body.get("removed") or []}), bid)
        if (mode, what) == ("add", "record"):
            return self._route(lambda: APP.save_add(bid, body), bid)
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        if web.route(self, "POST"):
            return
        parts = self._parts()
        if parts == ["api", "restart"]:
            self._json({"restarting": True})
            threading.Thread(target=restart, daemon=True).start()
            return
        if len(parts) != 4 or parts[0] != "api":
            return self._send(b"not found", "text/plain", 404)
        mode, bid, what = parts[1], parts[2], parts[3]
        body = self._body()
        if (mode, what) == ("draft", "save"):
            return self._route(lambda: APP.save_draft(bid, bool(body.get("force"))), bid)
        if (mode, what) == ("draft", "discard"):
            return self._route(lambda: APP.discard_draft(bid), bid)
        if (mode, what) == ("groups", "captions"):       # "re-read captions" on a group
            return self._route(lambda: APP.groups.captions_for(bid, body), bid)
        if (mode, what) == ("groups", "plan"):
            return self._route(lambda: APP.groups.plan_for(bid, body), bid)
        if (mode, what) == ("groups", "apply"):
            return self._route(lambda: APP.apply_groups(bid), bid)
        if (mode, what) == ("add", "propose"):
            return self._route(lambda: field_add.propose(APP.add.ctx(bid), int(body.get("page") or 1), body.get("rect"),
                                                         body.get("sid"), set(body.get("taken") or [])), bid)
        if (mode, what) == ("add", "kind"):              # the card's box: text box / checkbox, by hand
            return self._route(lambda: {"proposal": field_add.switch_kind(
                body["proposal"], body["kind"], APP.add.ctx(bid).names | set(body.get("taken") or []))}, bid)
        if (mode, what) == ("add", "labeler"):
            return self._route(lambda: {"name": field_add.labeler_name(APP.add.ctx(bid), body["proposal"],
                                                                       think=body.get("from") != "groups"),
                                        "model": field_add.LABEL_MODEL}, bid)
        if (mode, what) == ("add", "labeler_page"):     # "rescan page" in Groups: the page's groups in one call
            return self._route(lambda: {"names": field_add.labeler_names(APP.add.ctx(bid), body["proposals"],
                                                                         think=False),
                                        "model": field_add.LABEL_MODEL}, bid)
        if (mode, what) == ("add", "finder"):
            def run():
                APP.add.ctx(bid).load_finder(run=True)
                return APP.add.detail(bid)
            return self._route(run, bid)
        if (mode, what) == ("review", "apply"):          # a retry, after a clash that held a correction back
            return self._route(lambda: {**APP.apply_review(bid), "entry": APP.entry(bid)}, bid)
        if (mode, what) == ("add", "apply"):
            return self._route(lambda: APP.save_add(bid, {}), bid)
        if (mode, what) == ("review", "agent"):          # "review edits": the flags with notes go to the agent
            from petey.validate import flag_agent
            return self._route(lambda: {"started": flag_agent.start(bid)}, bid)
        if (mode, what) == ("review", "chat"):           # the chat's request: a proposal, nothing written (form_chat)
            from petey.validate import form_chat
            return self._route(lambda: form_chat.ask(bid, body.get("history") or []), bid)
        if (mode, what) == ("review", "grid"):           # "check grid": the grid skill's request for this page, asked
            from petey.validate import form_chat
            def grid():
                pg = int(body.get("page") or 1)
                passed, failed = APP.code_grid(bid, pg)
                refused: list = []
                accepted = APP.accept_grid(bid, pg, {c["name"] for g in passed for c in g}, refused)
                if passed and not failed:            # every table on the page passes the code check: no model call
                    n = sum(len(g) for g in passed)
                    return {"reply": f"Page {pg}: {len(passed)} grid(s), {n} cell(s): each column one pattern that "
                                     f"varies only by its iteration, rows numbered by steps of 1 (code check, no "
                                     f"model call).", "edits": [], "groups": [], "remove": [], "errors": [],
                            "confirmed": [], "cost_usd": 0, "accepted": accepted, "refused": refused}
                edits, fixed, rest = APP.code_fix(bid, failed)
                if failed and not rest:              # the code can renumber every failing table: no model call
                    n = sum(len(g) for g in passed)
                    return {"reply": f"Page {pg}: {len(failed)} grid(s) out of order, renumbered by code ({len(edits)} "
                                     f"rename(s)); tick and apply" + (f"; {len(passed)} grid(s) already right, "
                                     f"{n} cell(s) accepted" if passed else "") + " (no model call).",
                            "edits": edits, "groups": [], "remove": [], "errors": [], "confirmed": fixed,
                            "cost_usd": 0, "accepted": accepted, "refused": refused}
                req = form_chat.grid_request(bid, pg)     # tables the code cannot fix, or none found: the model,
                out = {"request": req, **form_chat.ask(bid, (body.get("history") or []) + [{"role": "user", "content": req}],
                                                       only_pages=[pg])}          # with that page only
                if not (out["edits"] or out["groups"] or out["remove"]):     # nothing to change: accept what it vouched for
                    accepted += APP.accept_grid(bid, pg, set(out.get("confirmed") or []), refused)
                out["accepted"], out["refused"] = accepted, refused
                return out
            return self._route(grid, bid)
        if (mode, what) == ("blocks", "draw"):          # an area drawn: a block (block_types.py, 2026-10-21)
            return self._route(lambda: APP.blocks.block_draw(bid, int(body["page"]), body["rect"]), bid)
        if (mode, what) == ("blocks", "out"):           # a block that is no longer one
            return self._route(lambda: APP.blocks.block_out(bid, body["block"]), bid)
        if (mode, what) == ("blocks", "confirm"):       # a block type's positions confirmed: parts, or wordings
            return self._route(lambda: APP.blocks.type_confirm(bid, body["type"],
                                                               list(body.get("slots") or body.get("wordings") or [])), bid)
        if (mode, what) == ("blocks", "bvalidate"):     # one block checked against its type, its cells accepted
            return self._route(lambda: APP.blocks.block_validate(bid, body["block"]), bid)
        if (mode, what) == ("blocks", "bparts"):        # a block's prefix and iteration
            return self._route(lambda: APP.blocks.block_parts(bid, body["block"], body.get("prefix"), body.get("iteration"),
                                                              body.get("by")), bid)
        if (mode, what) == ("blocks", "tauto"):         # a block type's blocks named from its label, numbered
            return self._route(lambda: APP.blocks.type_auto(bid, body["type"], bool(body.get("on"))), bid)
        if (mode, what) == ("blocks", "tlabel"):        # a block type's label
            return self._route(lambda: APP.blocks.type_label(bid, body["type"], body.get("label") or ""), bid)
        if (mode, what) == ("blocks", "finders"):       # the whole form: SIA's blocks as new types
            return self._route(lambda: APP.blocks.run_finders(bid), bid)
        if (mode, what) == ("blocks", "detect"):        # every block type's copies on a page found
            return self._route(lambda: APP.blocks.block_detect(bid, int(body["page"])), bid)
        if (mode, what) == ("blocks", "rescan"):        # blocks grown to the free fields repeating in them, then copies
            return self._route(lambda: APP.blocks.block_rescan(bid, int(body["page"])), bid)
        if (mode, what) == ("blocks", "assign"):        # a block given another block type
            return self._route(lambda: APP.blocks.block_assign(bid, body["block"], body["type"]), bid)
        if (mode, what) == ("blocks", "addfield"):      # a field dropped on a block
            return self._route(lambda: APP.blocks.block_add_field(bid, body["block"], str(body["field"]),
                                                                  bool(body.get("grow"))), bid)
        if (mode, what) == ("blocks", "tvalidate"):     # every block of a confirmed type checked and validated
            return self._route(lambda: APP.blocks.type_validate(bid, body["type"]), bid)
        if (mode, what) == ("blocks", "tfix"):          # every block of a type put to its wordings
            return self._route(lambda: APP.blocks.type_fix(bid, body["type"]), bid)
        if (mode, what) == ("blocks", "bkeep"):         # a suggested rename cancelled, or the cancel undone
            return self._route(lambda: APP.blocks.block_keep(bid, body["block"], body["pos"], bool(body.get("on", True))), bid)
        if (mode, what) == ("blocks", "bfix"):          # one block's names put to its type's wordings
            return self._route(lambda: APP.blocks.block_fix(bid, body["block"]), bid)
        if mode == "grids" and what in ("check", "cancel", "dismiss", "create", "combine", "standardize", "preview",
                                        "relabel"):
            tab = APP.grids
            if what == "preview":                        # what each standardize button would do, nothing written
                return self._route(lambda: tab.preview(bid, body["table"]), bid)
            if what == "check":                          # check and validate one
                return self._route(lambda: tab.check(bid, body["table"]), bid)
            if what == "cancel":                         # stop the check under way on one
                return self._route(lambda: tab.cancel(bid, body["table"]), bid)
            if what == "standardize":                    # a position (a wording picked, or not), all of them, or a line
                return self._route(lambda: tab.standardize(bid, body["table"], body.get("pos"), body.get("line"),
                                                           body.get("wording")), bid)
            if what == "relabel":                        # a row's label or number edited (2026-10-23)
                return self._route(lambda: tab.relabel(bid, body["table"], body["line"], body.get("label") or ""), bid)
            if what == "dismiss":                        # "not a grid", or restore
                return self._route(lambda: tab.dismiss(bid, body["table"], bool(body.get("on", True))), bid)
            if what == "create":                         # drawn on the page
                return self._route(lambda: tab.create(bid, int(body["page"]), body["rect"]), bid)
            return self._route(lambda: tab.combine(bid, list(body.get("tables") or [])), bid)   # combine, one page
        if (mode, what) == ("review", "chat_apply"):     # the ticked part of the proposal, written
            return self._route(lambda: APP.chat_apply(bid, body), bid)
        if (mode, what) == ("review", "captions"):       # "re-read captions" on a group, from Review (2026-10-15)
            return self._route(lambda: group_review.field_captions(hand_review.working_path(bid), body["name"]), bid)
        if (mode, what) == ("review", "agent_field"):    # "fix captions": one field, answered now, not stored
            from petey.validate import flag_agent
            def field():
                out = flag_agent.propose_field(bid, body["name"], body.get("note") or "")
                if out.get("name") and out["name"] != body["name"]:
                    out["identifiers"] = name_parts(bid, body["name"], out["name"])
                return out
            return self._route(field, bid)
        self._send(b"not found", "text/plain", 404)


def serve(port: int = 5005, mode: str = "review", open_browser: bool = True) -> int:
    global APP
    SERVED.update(port=port, mode=mode)
    APP = App()
    print(f"blueprint review: {len(APP.paths)} blueprints")
    t0 = time.time()
    APP.index()
    print(f"  indexed in {time.time() - t0:.1f}s")
    web.REVIEW["on"] = True
    web.start()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as srv:
        url = f"http://127.0.0.1:{port}/#{mode}"
        print(f"blueprint review -> {url}")
        if open_browser:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--mode", choices=MODES, default="review")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    return serve(args.port, args.mode, not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
