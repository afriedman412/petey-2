"""Group review: a web page for checking the option groups of a blueprint against its blank, and regrouping the
options that the labeler left loose. Every radio/checkbox item of the blueprint is a unit: a group (a field with a
`widgets` map, one option per box) or an orphan (a lone boolean checkbox or radio). The person steps through the
units in reading order and confirms each one ("this group is right", "this box stands alone"); an option that
belongs elsewhere is dragged onto the group it belongs to, or onto another orphan to start a new group, or onto the
orphan tray to take it out of its group.

    PYTHONPATH=. venv/bin/python -m petey.validate.group_review [--port 5006]   # then open http://127.0.0.1:5006/
    PYTHONPATH=. venv/bin/python -m petey.validate.group_review --summary       # reviews so far
    PYTHONPATH=. venv/bin/python -m petey.validate.group_review --plan <id>     # what --apply would change
    PYTHONPATH=. venv/bin/python -m petey.validate.group_review --apply <id>    # write it into the blueprint

The page only records: `runs/group_review/<id>.json` holds the grouping as the person left it (units, their names,
one-of or any-of, confirmed or not) with the blueprint's sha. `--apply` rewrites the blueprint from that record and
then re-derives the record from the new file, keeping the confirmations. Blueprints offered are the hand review's
(library, judge-eval and relabel side copies, flat forms).

What --apply writes, in the shape `expand_options` gave the library (2026-09-29): a group is one `category` (or
`multi_category`) field whose `widgets` are keyed by option; an orphan that joins a group is keyed by its former
field name (as 5500-EZ's `return_type` already is), keeps its own path, gains the `on_state` the blank's widget
declares (so the reader selects by state, `extract._selected_states`) and a printed caption from the page text when
it had none (`captions.caption_options_from_page`). An option taken out of a group becomes a boolean `indicator`
field carrying its box, path and on-state. Every field --apply makes or changes carries `x_petey_grouping`.
"""
from __future__ import annotations

import argparse
import copy
import http.server
import json
import re
import socketserver
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import yaml

from petey.paths import RUNS
from petey.validate.hand_review import _load, _sha, blueprint_paths
from petey.validate.retype import resolve_blank

OUT = RUNS / "group_review"
HTML_PATH = Path(__file__).with_suffix(".html")
DPI = 144                    # option boxes are 8-10 pt; the hand review's 110 dpi makes them 12 px targets
OPTION_TYPES = ("checkbox", "radiobutton")
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def record_path(bid: str) -> Path:
    return OUT / f"{bid}.json"


def load_record(bid: str) -> dict:
    p = record_path(bid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _is_orphan(spec: dict) -> bool:
    w = spec.get("widget") or {}
    return (not spec.get("widgets") and spec.get("type") == "boolean" and w.get("widget_type") in OPTION_TYPES
            and bool(w.get("rect")) and w.get("page") is not None)


def _is_union(spec: dict) -> bool:
    """A radio group still in the pre-2026-09-29 shape: one widget (the union box of its members) with `values` =
    the on-states. Shown, not regroupable: `expand_options` rebuilds it from the blank."""
    w = spec.get("widget") or {}
    return (not spec.get("widgets") and spec.get("type") == "category" and w.get("widget_type") == "radiobutton"
            and bool(w.get("rect")))


def option_items(bp: dict) -> tuple[dict, list[dict]]:
    """`(items, units)` as the blueprint has them. An item is one option box: `<field>::<key>` for an option of a
    group, `<field>` for an orphan or a union box. A unit is a group or an orphan, with its `origin` field."""
    items: dict[str, dict] = {}
    units: list[dict] = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        if spec.get("widgets"):
            ids = []
            for key, w in spec["widgets"].items():
                if not (w.get("rect") and w.get("page")):
                    continue
                iid = f"{name}::{key}"
                items[iid] = {"id": iid, "field": name, "key": str(key), "page": int(w["page"]), "rect": w["rect"],
                              "caption": w.get("caption"), "on_state": w.get("on_state"), "path": w.get("path"),
                              "widget_type": w.get("widget_type")}
                ids.append(iid)
            if ids:
                units.append({"name": name, "type": spec.get("type") or "category", "items": ids, "origin": name,
                              "description": spec.get("description")})
        elif _is_orphan(spec) or _is_union(spec):
            w = spec["widget"]
            items[name] = {"id": name, "field": name, "key": None, "page": int(w["page"]), "rect": w["rect"],
                           "caption": w.get("caption") or (spec.get("description") if _is_orphan(spec) else None),
                           "on_state": w.get("on_state"), "path": w.get("path"), "widget_type": w.get("widget_type"),
                           "appearances": spec.get("x_petey_appearances")}
            units.append({"name": name, "type": spec.get("type"), "items": [name], "origin": name,
                          "description": spec.get("description"),
                          **({"locked": "one union box for the whole group (pre-2026-09-29 shape); "
                                        "expand_options rebuilds it from the blank"} if _is_union(spec) else {})})
    return items, units


def _order_key(items: dict, u: dict) -> tuple:
    first = min((items[i] for i in u["items"]), key=lambda it: (it["page"], round(it["rect"][1] / 6), it["rect"][0]))
    return first["page"], round(first["rect"][1] / 6), first["rect"][0]


def _signature(u: dict) -> tuple:
    return u["name"], u["type"], tuple(sorted(u["items"]))


def current_units(bid: str, bp: dict, sha: str) -> tuple[dict, list[dict], dict]:
    """The units as the page should show them: the record's grouping laid over the blueprint's. A record written
    against another version of the file is rebased: its units keep the items that still exist, items it never saw
    stay where the blueprint has them, and it is reported stale."""
    items, base = option_items(bp)
    rec = load_record(bid)
    info = {"stale": bool(rec) and rec.get("blueprint_sha") != sha, "updated": rec.get("updated"),
            "applied": rec.get("applied")}
    if not rec.get("units"):
        units = [dict(u, confirmed=False) for u in base]
    else:
        units, seen = [], set()
        for u in rec["units"]:
            ids = [i for i in u.get("items") or [] if i in items and i not in seen]
            if not ids:
                continue
            seen.update(ids)
            units.append({k: v for k, v in u.items() if k != "items"} | {"items": ids})
        for u in base:                                   # items the record never saw
            ids = [i for i in u["items"] if i not in seen]
            if ids:
                units.append(dict(u, items=ids, confirmed=False))
    locked = {u["origin"]: u.get("locked") for u in base if u.get("locked")}
    for u in units:
        if u.get("origin") in locked:
            u["locked"] = locked[u["origin"]]
    units.sort(key=lambda u: _order_key(items, u))
    return items, units, info


# ---------------------------------------------------------------- the plan: record -> blueprint

def _blank_on_states(blank: Optional[Path], items: list[dict]) -> dict[str, str]:
    """On-state of each item's AcroForm widget on the blank, matched by path and box (a checkbox field with kids
    has one path and several boxes). Empty for a flat blank."""
    want = [it for it in items if it.get("path") and not it.get("on_state")]
    if not want or not blank or not blank.exists():
        return {}
    import pymupdf
    out: dict[str, str] = {}
    doc = pymupdf.open(str(blank))
    try:
        for it in want:
            if not 1 <= it["page"] <= len(doc):
                continue
            page = doc[it["page"] - 1]                   # keep the page alive while its widgets are read
            cx, cy = (it["rect"][0] + it["rect"][2]) / 2, (it["rect"][1] + it["rect"][3]) / 2
            for w in page.widgets() or []:
                r = w.rect
                if w.field_name == it["path"] and r.x0 - 1 <= cx <= r.x1 + 1 and r.y0 - 1 <= cy <= r.y1 + 1:
                    st = w.on_state()
                    if st and st != "Off":
                        out[it["id"]] = str(st)
                    break
    finally:
        doc.close()
    return out


def _page_captions(blank: Optional[Path], blocks: dict[str, dict], all_items: dict) -> dict[str, str]:
    """Printed captions for option blocks that have none, read from the page beside the box."""
    need = {k: copy.deepcopy(b) for k, b in blocks.items() if not b.get("caption")}
    if not need or not blank or not blank.exists():
        return {}
    import pymupdf
    from petey.label.captions import caption_options_from_page
    others: dict[int, list] = {}
    for it in all_items.values():
        others.setdefault(it["page"], []).append(it["rect"])
    doc = pymupdf.open(str(blank))
    try:
        caption_options_from_page(doc, need, others)
    finally:
        doc.close()
    return {k: b["caption"] for k, b in need.items() if b.get("caption")}


def plan(bp: dict, units: list[dict], blank: Optional[Path] = None) -> dict:
    """What writing `units` into `bp` changes: `{changes, errors, fields}` with `fields` the new field map (None
    when there are errors). Fields whose unit is unchanged keep their spec untouched and their place; a new or
    changed unit is written where its origin field was, or where its first option's field was."""
    items, base = option_items(bp)
    fields = bp.get("fields") or {}
    base_by_origin = {u["origin"]: u for u in base}
    option_fields = {it["field"] for it in items.values()}
    errors, changes = [], []

    names = [u["name"] for u in units]
    for n in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"two units are both named {n!r}")
    for u in units:
        if not NAME_RE.match(u["name"] or ""):
            errors.append(f"{u['name']!r} is not a field name (lower case, digits, underscores)")
        elif u["name"] in fields and u["name"] not in option_fields:
            errors.append(f"{u['name']!r} is already the name of another field")
        if len(u["items"]) > 1 and u["type"] not in ("category", "multi_category"):
            errors.append(f"{u['name']!r} groups {len(u['items'])} options but its type is {u['type']!r}")
        b = base_by_origin.get(u.get("origin"))
        if u.get("locked") and (b is None or _signature(u) != _signature(b)):
            errors.append(f"{u['name']!r} is a union box (old shape); run expand_options before regrouping it")
    covered = [i for u in units for i in u["items"]]
    missing = set(items) - set(covered)
    if missing:
        errors.append(f"{len(missing)} option(s) belong to no unit: {', '.join(sorted(missing)[:5])}")

    def unchanged(u: dict) -> bool:
        b = base_by_origin.get(u.get("origin"))
        return b is not None and _signature(b) == _signature(u)

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    on_states = _blank_on_states(blank, [items[i] for u in units if not unchanged(u) and len(u["items"]) > 1
                                         for i in u["items"]])
    emitted: dict[str, list[tuple[str, dict]]] = {}
    for u in units:
        if unchanged(u):
            emitted.setdefault(u["origin"], []).append((u["name"], fields[u["origin"]]))
            continue
        anchor = u.get("origin") if u.get("origin") in fields else items[u["items"][0]]["field"]
        origin = fields.get(u.get("origin")) if u.get("origin") else None
        b = base_by_origin.get(u.get("origin"))
        if len(u["items"]) == 1 and u["type"] == "boolean":
            it = items[u["items"][0]]
            if origin is not None and _is_orphan(origin):
                spec = copy.deepcopy(origin)                 # an orphan renamed
            else:
                block = copy.deepcopy(fields[it["field"]]["widgets"][it["key"]])
                cap = block.pop("caption", None)
                block.pop("x_petey_caption_source", None)
                spec = {"type": "boolean", "semantic_type": "indicator", "widget": block}
                if cap:
                    spec["description"] = cap
                changes.append(f"{it['field']} option {it['key']!r} taken out of the group as boolean {u['name']}")
        else:
            spec = copy.deepcopy(origin) if origin is not None and origin.get("widgets") else {}
            spec.pop("widget", None)
            spec["type"] = u["type"]
            blocks: dict[str, dict] = {}
            for iid in u["items"]:
                it = items[iid]
                if it["key"] is not None:
                    key, block = it["key"], copy.deepcopy(fields[it["field"]]["widgets"][it["key"]])
                else:
                    src = fields[it["field"]]
                    key, block = it["field"], copy.deepcopy(src["widget"])
                    if iid in on_states:
                        block["on_state"] = on_states[iid]
                    if src.get("description") and src.get("x_petey_description_source") in ("tooltip", "xfa"):
                        block.setdefault("caption", src["description"])
                        block.setdefault("x_petey_caption_source", src["x_petey_description_source"])
                k, n = key, 2
                while k in blocks:
                    k, n = f"{key}_{n}", n + 1
                blocks[k] = block
            for k, cap in _page_captions(blank, blocks, items).items():
                blocks[k]["caption"], blocks[k]["x_petey_caption_source"] = cap, "page_text"
            spec["values"] = list(blocks)
            spec["widgets"] = blocks
            def shown(ks):          # the key and the caption the reader will show for it
                return ", ".join(f"{k} ({blocks[k]['caption']!r})" if blocks[k].get("caption") else f"{k} (no caption)"
                                 for k in ks)
            key_of = dict(zip(u["items"], blocks))
            if b is None:
                changes.append(f"new {u['type']} group {u['name']}: {shown(blocks)}")
            else:
                before, after = set(b["items"]), set(u["items"])
                if after - before:
                    changes.append(f"group {u['name']}: + {shown(key_of[i] for i in u['items'] if i in after - before)}")
                if before - after:
                    changes.append(f"group {u['name']}: - {', '.join(sorted(before - after))}")
                if b["type"] != u["type"]:
                    changes.append(f"group {u['name']}: {b['type']} -> {u['type']}")
        if b is not None and b["name"] != u["name"]:
            changes.append(f"{b['name']} renamed {u['name']}")
        spec["x_petey_grouping"] = {"source": "group_review", "when": now, "from": list(u["items"]),
                                    **({"renamed_from": b["name"]} if b is not None and b["name"] != u["name"] else {})}
        emitted.setdefault(anchor, []).append((u["name"], spec))

    removed = option_fields - {u.get("origin") for u in units}     # every box of the field went to other units
    gone = sorted(f for f in removed if not fields[f].get("widgets"))
    if gone:
        changes.append(f"{len(gone)} field(s) removed, their boxes now options of a group: {', '.join(gone)}")
    for f in sorted(removed - set(gone)):
        changes.append(f"group {f} removed: every option moved to other units")
    if errors:
        return {"changes": changes, "errors": errors, "fields": None}
    out: dict = {}
    for name, spec in fields.items():
        if name in option_fields:
            for n, s in emitted.get(name, []):
                out[n] = s
        else:
            out[name] = spec
    return {"changes": changes, "errors": [], "fields": out}


def apply(bid: str) -> dict:
    """Write the record into the blueprint, then re-derive the record from the new file (confirmations kept by unit
    name and membership)."""
    p = blueprint_paths()[bid]
    bp = _load(p)
    sha = _sha(p)
    items, units, info = current_units(bid, bp, sha)
    if info["stale"]:
        raise SystemExit(f"{bid}: the record was written against another version of the blueprint; open it in the "
                         f"page, check the grouping and save again before applying")
    pl = plan(bp, units, resolve_blank(bp))
    if pl["errors"]:
        raise SystemExit(f"{bid}: not applied:\n  " + "\n  ".join(pl["errors"]))
    if not pl["changes"]:
        print(f"{bid}: nothing to change")
        return pl
    bp["fields"] = pl["fields"]
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True), encoding="utf-8")
    new_sha = _sha(p)
    confirmed = {(u["name"], len(u["items"])) for u in units if u.get("confirmed")}
    _, fresh = option_items(bp)
    rec = {"blueprint": str(p), "form": p.stem, "blueprint_sha": new_sha,
           "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
           "applied": {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "sha_before": sha, "sha_after": new_sha,
                       "changes": pl["changes"]},
           "units": [dict(u, confirmed=(u["name"], len(u["items"])) in confirmed) for u in fresh]}
    record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{bid}: wrote {p}")
    for c in pl["changes"]:
        print(f"  {c}")
    return pl


# ---------------------------------------------------------------- server

class State:
    def __init__(self) -> None:
        self.paths = blueprint_paths()
        self.png: dict[tuple[str, int], bytes] = {}
        self._index: dict[str, dict] = {}

    def _entry(self, bid: str) -> Optional[dict]:
        p = self.paths[bid]
        bp = _load(p)
        items, units, info = current_units(bid, bp, _sha(p))
        if not units:
            return None
        groups = sum(1 for u in units if len(u["items"]) > 1 or u["type"] != "boolean")
        return {"id": bid, "source": bid.split("__")[0], "form": p.stem, "groups": groups,
                "orphans": len(units) - groups, "confirmed": sum(1 for u in units if u.get("confirmed")),
                "units": len(units), "stale": info["stale"], "edited": bool(info["updated"])}

    def index(self) -> None:
        t0 = time.time()
        for bid in self.paths:
            e = self._entry(bid)
            if e:
                self._index[bid] = e
        print(f"  {len(self._index)} of {len(self.paths)} blueprints have option boxes ({time.time() - t0:.1f}s)")

    def listing(self) -> list[dict]:
        if not self._index:
            self.index()
        return list(self._index.values())

    def detail(self, bid: str) -> Optional[dict]:
        p = self.paths.get(bid)
        if p is None:
            return None
        bp = _load(p)
        blank = resolve_blank(bp)
        pages = []
        if blank and blank.exists():
            import pymupdf
            doc = pymupdf.open(str(blank))
            try:
                pages = [{"page": i, "w_pt": pg.rect.width, "h_pt": pg.rect.height} for i, pg in enumerate(doc, 1)]
            finally:
                doc.close()
        sha = _sha(p)
        items, units, info = current_units(bid, bp, sha)
        _, base = option_items(bp)
        option_fields = {it["field"] for it in items.values()}
        return {"id": bid, "path": str(p), "blank": str(blank) if blank else None, "sha": sha, "pages": pages,
                "items": items, "units": units, "base": [{k: u[k] for k in ("name", "type", "items")} for u in base],
                "other_names": sorted(n for n in (bp.get("fields") or {}) if n not in option_fields),
                "info": info}

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key not in self.png:
            p = self.paths.get(bid)
            blank = resolve_blank(_load(p)) if p else None
            if not blank or not blank.exists():
                return None
            import pymupdf
            doc = pymupdf.open(str(blank))
            try:
                if not 1 <= page <= len(doc):
                    return None
                self.png[key] = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
            finally:
                doc.close()
        return self.png[key]

    def put_units(self, bid: str, incoming: dict) -> dict:
        p = self.paths.get(bid)
        if p is None:
            raise KeyError(bid)
        bp = _load(p)
        items, _ = option_items(bp)
        keep = ("name", "type", "items", "origin", "confirmed", "description", "locked")
        units = [{k: u.get(k) for k in keep if u.get(k) is not None} for u in incoming.get("units") or []]
        for u in units:
            u["items"] = [i for i in u.get("items") or [] if i in items]
        units = [u for u in units if u["items"]]
        rec = {"blueprint": str(p), "form": p.stem, "blueprint_sha": _sha(p),
               "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "applied": load_record(bid).get("applied"),
               "units": units}
        OUT.mkdir(parents=True, exist_ok=True)
        record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        e = self._entry(bid)
        if e:
            self._index[bid] = e
        return {"saved": rec["updated"], "entry": e}

    def plan_for(self, bid: str, incoming: Optional[dict] = None) -> dict:
        p = self.paths[bid]
        bp = _load(p)
        units = (incoming or {}).get("units") or current_units(bid, bp, _sha(p))[1]
        pl = plan(bp, units, resolve_blank(bp))
        return {"changes": pl["changes"], "errors": pl["errors"]}


STATE: Optional[State] = None


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

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        parts = path.strip("/").split("/")
        if path in ("/", "/index.html"):
            self._send(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/blueprints":
            self._json(STATE.listing())
        elif len(parts) == 3 and parts[:2] == ["api", "blueprints"]:
            d = STATE.detail(parts[2])
            self._json(d) if d else self._send(b"no such blueprint", "text/plain", 404)
        elif len(parts) == 5 and parts[:2] == ["api", "blueprints"] and parts[3] == "png":
            png = STATE.page_png(parts[2], int(parts[4]))
            self._send(png, "image/png") if png else self._send(b"no such page", "text/plain", 404)
        else:
            self._send(b"not found", "text/plain", 404)

    def do_PUT(self):
        parts = unquote(urlparse(self.path).path).strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "blueprints"] and parts[3] == "units":
            try:
                self._json(STATE.put_units(parts[2], self._body()))
            except KeyError:
                self._send(b"no such blueprint", "text/plain", 404)
            except Exception as e:  # noqa: BLE001
                self._send(str(e).encode(), "text/plain", 400)
        else:
            self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        parts = unquote(urlparse(self.path).path).strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "blueprints"] and parts[3] == "plan":
            try:
                self._json(STATE.plan_for(parts[2], self._body()))
            except KeyError:
                self._send(b"no such blueprint", "text/plain", 404)
            except Exception as e:  # noqa: BLE001
                self._send(f"{type(e).__name__}: {e}".encode(), "text/plain", 400)
        else:
            self._send(b"not found", "text/plain", 404)


def summary() -> None:
    paths = blueprint_paths()
    print(f"{'blueprint':44} {'units':>5} {'confirmed':>9} {'changes':>7} {'stale':>5}  updated")
    n = 0
    for rp in sorted(OUT.glob("*.json")):
        rec = json.loads(rp.read_text(encoding="utf-8"))
        p = paths.get(rp.stem)
        if p is None:
            continue
        bp = _load(p)
        _, units, info = current_units(rp.stem, bp, _sha(p))
        pl = plan(bp, units)
        print(f"{rp.stem[:44]:44} {len(units):5} {sum(1 for u in units if u.get('confirmed')):9} "
              f"{len(pl['changes']):7} {'yes' if info['stale'] else '':>5}  {rec.get('updated')}")
        n += 1
    if not n:
        print(f"no group reviews yet under {OUT}")


def main() -> int:
    global STATE
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--plan", metavar="ID", help="print what --apply would change for this blueprint id")
    ap.add_argument("--apply", metavar="ID", help="write the recorded grouping into this blueprint")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if args.summary:
        summary()
        return 0
    if args.plan or args.apply:
        bid = args.plan or args.apply
        if bid not in blueprint_paths():
            raise SystemExit(f"no blueprint {bid!r} (ids look like lib__fw9, je__<form>, rl__<form>, fl__<form>)")
        if args.apply:
            apply(bid)
            return 0
        p = blueprint_paths()[bid]
        bp = _load(p)
        _, units, info = current_units(bid, bp, _sha(p))
        pl = plan(bp, units, resolve_blank(bp))
        if info["stale"]:
            print("(the record predates this version of the blueprint)")
        for c in pl["changes"] or ["nothing to change"]:
            print(f"  {c}")
        for e in pl["errors"]:
            print(f"  ERROR {e}")
        return 0
    STATE = State()
    print(f"group review: {len(STATE.paths)} blueprints; records in {OUT}")
    STATE.index()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as srv:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"group review -> {url}")
        if not args.no_open:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
