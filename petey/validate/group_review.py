"""Group review: a web page for checking the option groups of a blueprint against its blank, and regrouping the
options that the labeler left loose. Every radio/checkbox item of the blueprint is a unit: a group (a field with a
`widgets` map, one option per box) or an orphan (a lone boolean checkbox or radio). The person steps through the
units in reading order and confirms each one ("this group is right", "this box stands alone"); an option that
belongs elsewhere is dragged onto the group it belongs to, or onto another orphan to start a new group, or onto the
orphan tray to take it out of its group.

Text fields can be combined the same way (Andrew, 2026-10-05: text to text only, the result a plain text field):
drag one text box onto another to start a combined field, onto a combined field to add to it, onto the tray to take
it back out. Any unit can be named by the labeler from the page ("ask the labeler": the same one call as
`field_add.labeler_name`; the field then carries `label_source: llm` and `name_from: labeler`). Text and option
boxes never mix, and a combination stays on one page. A combined field is one `string`
(no semantic type or pattern) over the union of its members' boxes with `path: null`, since the box covers several
AcroForm widgets and a field names one: the reader clips the text layer to the box, which reads every part, and the
filler already splits one value over the text widgets inside a box (ACORD 25's PRODUCER block). It takes the first
member's place in reading order; what each member was (name, path, box, type) is kept in `x_petey_combined`.

    PYTHONPATH=. venv/bin/python -m petey.validate.group_review [--port 5006]   # then open http://127.0.0.1:5006/
    PYTHONPATH=. venv/bin/python -m petey.validate.group_review --summary       # reviews so far
    PYTHONPATH=. venv/bin/python -m petey.validate.group_review --plan <id>     # what --apply would change
    PYTHONPATH=. venv/bin/python -m petey.validate.group_review --apply <id>    # write it into the blueprint

The page only records: `runs/group_review/<id>.json` holds the grouping as the person left it (units, their names,
one-of or any-of, confirmed or not) with the blueprint's sha. `--apply` rewrites the blueprint from that record and
then re-derives the record from the new file, keeping the confirmations. Blueprints offered are the hand review's
(library, judge-eval and relabel side copies, flat forms). Since 2026-10-13 the review page applies the record to its
working copy of the blueprint when you leave Groups (`draft.py`), and `--apply` writes that copy while it is open.

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
import json
import re
import time
from pathlib import Path
from typing import Optional

import yaml

from petey.paths import RUNS
from petey.label.captions import text_rects
from petey.validate import field_ids
from petey.validate.hand_review import _load, _sha, blueprint_paths, working_path
from petey.validate.retype import resolve_blank

OUT = RUNS / "group_review"
DPI = 144                    # option boxes are 8-10 pt; the hand review's 110 dpi makes them 12 px targets
OPTION_TYPES = ("checkbox", "radiobutton")
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")     # spec 5.2 allows digits anywhere (f5500sh 4a_...)


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


def text_items(bp: dict) -> dict[str, dict]:
    """Every field with one text widget, as an item that can be combined (`kind: text`, id = field name)."""
    out = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("widgets"):
            continue
        w = spec.get("widget") or {}
        if w.get("widget_type") == "text" and w.get("rect") and w.get("page"):
            out[name] = {"id": name, "field": name, "key": None, "kind": "text", "page": int(w["page"]),
                         "rect": [float(c) for c in w["rect"]], "path": w.get("path"), "widget_type": "text",
                         "type": spec.get("type"), "semantic_type": spec.get("semantic_type"),
                         "caption": None, "description": spec.get("description")}
    return out


def _order_key(items: dict, u: dict) -> tuple:
    first = min((items[i] for i in u["items"]), key=lambda it: (it["page"], round(it["rect"][1] / 6), it["rect"][0]))
    return first["page"], round(first["rect"][1] / 6), first["rect"][0]


def _signature(u: dict) -> tuple:
    return u["name"], u["type"], tuple(sorted(u["items"]))


def _box(it: dict) -> str:
    """An item's box: page and rect, which a rename never moves."""
    return f"{it['page']}:" + ",".join(str(round(float(c))) for c in it["rect"])


def item_boxes(items: dict[str, dict], units: list[dict]) -> dict[str, str]:
    """{item id: box} for every item the units hold, kept with the record so a later rename cannot move an item to
    another box (Andrew, 2026-10-13: a group saved, then a Review apply that renamed its boxes, then a rebase by name
    that put the wrong box in the group)."""
    return {i: _box(items[i]) for u in units for i in u.get("items") or [] if i in items}


def _rebase(rec: dict, bp: dict, items: dict[str, dict]) -> dict[str, str]:
    """{id in the record: id now} for a record written against another version of the blueprint. By box when the
    record kept its boxes; else (older records) through the renames the blueprint notes on its fields
    (`x_petey_hand_edit` from -> to: the last rename of each field)."""
    if rec.get("boxes"):
        now = {_box(it): i for i, it in items.items()}
        return {i: now[b] for i, b in rec["boxes"].items() if b in now and now[b] != i}
    renamed = {}
    for name, spec in (bp.get("fields") or {}).items():
        was = (((spec or {}).get("x_petey_hand_edit") or {}).get("from") or {}).get("name") if isinstance(spec, dict) else None
        if was and was != name:
            renamed[was] = name
    out = {}
    for u in rec.get("units") or []:
        for i in u.get("items") or []:
            field, sep, key = i.partition("::")
            if field in renamed:
                out[i] = renamed[field] + sep + key
    return out


def current_units(bid: str, bp: dict, sha: str) -> tuple[dict, list[dict], dict]:
    """The units as the page should show them: the record's grouping laid over the blueprint's. A record written
    against another version of the file is rebased: each item follows its box to whatever the blueprint calls it now
    (`_rebase`), units keep the items that still exist, items it never saw stay where the blueprint has them, and
    it is reported stale."""
    items, base = option_items(bp)
    items = {**items, **text_items(bp)}
    rec = load_record(bid)
    info = {"stale": bool(rec) and rec.get("blueprint_sha") != sha, "updated": rec.get("updated"),
            "applied": rec.get("applied")}
    if not rec.get("units"):
        units = [dict(u, confirmed=False) for u in base]
    else:
        units, seen = [], set()
        moved = _rebase(rec, bp, items) if info["stale"] else {}
        info["rebased"] = len(moved)
        for u in rec["units"]:
            ids = [moved.get(i, i) for i in u.get("items") or []]
            ids = [i for i in ids if i in items and i not in seen]
            if not ids or (u.get("kind") == "text" and len(ids) < 2):
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


def _page_captions(blank: Optional[Path], blocks: dict[str, dict], all_items: dict,
                   texts: Optional[dict[int, list]] = None) -> dict[str, str]:
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
        caption_options_from_page(doc, need, others, texts)
    finally:
        doc.close()
    return {k: b["caption"] for k, b in need.items() if b.get("caption")}


def plan(bp: dict, units: list[dict], blank: Optional[Path] = None, page_captions: bool = True) -> dict:
    """What writing `units` into `bp` changes: `{changes, errors, fields}` with `fields` the new field map (None
    when there are errors). Fields whose unit is unchanged keep their spec untouched and their place; a new or
    changed unit is written where its origin field was, or where its first option's field was. Units the person
    left as the blueprint has them are not checked: the blueprint's own names and types stand. `page_captions`
    off: an option without a caption or tooltip stays uncaptioned (2026-10-05, Yes/No grids read as '??', line
    numbers or the next question's first word)."""
    text_units = [u for u in units if u.get("kind") == "text"]
    units = [u for u in units if u.get("kind") != "text"]
    items, base = option_items(bp)
    fields = bp.get("fields") or {}
    base_by_origin = {u["origin"]: u for u in base}
    option_fields = {it["field"] for it in items.values()}
    errors, changes = [], []

    def unchanged(u: dict) -> bool:
        b = base_by_origin.get(u.get("origin"))
        return b is not None and _signature(b) == _signature(u)

    names = [u["name"] for u in units]
    for n in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"two units are both named {n!r}")
    for u in units:
        if unchanged(u):
            continue
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
                    # a short tooltip is the option's caption; a sentence ('Check the box (if applicable): Indicates
                    # the legal entity code ... is "Corporation"') is not, and the review page's caption chooser
                    # proposes one from the page instead (2026-10-10: 575 such captions)
                    if src.get("description") and src.get("x_petey_description_source") in ("tooltip", "xfa") \
                            and len(src["description"].split()) <= 8:
                        block.setdefault("caption", src["description"])
                        block.setdefault("x_petey_caption_source", src["x_petey_description_source"])
                k, n = key, 2
                while k in blocks:
                    k, n = f"{key}_{n}", n + 1
                blocks[k] = block
            for k, cap in (_page_captions(blank, blocks, items, text_rects(fields)) if page_captions else {}).items():
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
        if u.get("name_from") == "labeler":          # the page's "ask the labeler" (field_add.labeler_name)
            spec["label_source"] = "llm"
        spec["x_petey_grouping"] = {"source": "group_review", "when": now, "from": list(u["items"]),
                                    **({"renamed_from": b["name"]} if b is not None and b["name"] != u["name"] else {}),
                                    **({"name_from": u["name_from"]} if u.get("name_from") else {})}
        emitted.setdefault(anchor, []).append((u["name"], spec))

    removed = option_fields - {u.get("origin") for u in units}     # every box of the field went to other units
    gone = sorted(f for f in removed if not fields[f].get("widgets"))
    if gone:
        changes.append(f"{len(gone)} field(s) removed, their boxes now options of a group: {', '.join(gone)}")
    for f in sorted(removed - set(gone)):
        changes.append(f"group {f} removed: every option moved to other units")
    errors.extend(_check_text(fields, text_units, {u["name"] for u in units}))
    if errors:
        return {"changes": changes, "errors": errors, "fields": None}
    out: dict = {}
    for name, spec in fields.items():
        if name in option_fields:
            for n, s in emitted.get(name, []):
                out[n] = s
        else:
            out[name] = spec
    out = _combine_text(bp, out, text_units, now, changes)
    return {"changes": changes, "errors": [], "fields": out}


def _check_text(fields: dict, text_units: list[dict], option_names: set[str]) -> list[str]:
    texts = text_items({"fields": fields})
    errors, used = [], {}
    members = {m for u in text_units for m in u["items"]}
    names = [u["name"] for u in text_units]
    for u in text_units:
        n = u.get("name") or ""
        if len(u["items"]) < 2:
            errors.append(f"{n!r} combines fewer than two text fields")
        missing = [m for m in u["items"] if m not in texts]
        if missing:
            errors.append(f"{n!r}: {', '.join(missing)} not a text field of this blueprint (any more)")
        elif len({texts[m]["page"] for m in u["items"]}) > 1:
            errors.append(f"{n!r}: combines text fields on more than one page")
        for m in u["items"]:
            if m in used:
                errors.append(f"{m} is in two combinations ({used[m]!r} and {n!r})")
            used[m] = n
        if not NAME_RE.match(n):
            errors.append(f"{n!r} is not a field name (lower case, digits, underscores)")
        elif names.count(n) > 1 or n in option_names:
            errors.append(f"two units are both named {n!r}")
        elif n in fields and n not in members:
            errors.append(f"{n!r} is already the name of another field")
    return errors


def _combine_text(bp: dict, out: dict, text_units: list[dict], now: str, changes: list[str]) -> dict:
    """Write each text combination in place of its first member (reading order); drop the other members."""
    if not text_units:
        return out
    texts = text_items(bp)
    at, gone = {}, set()
    for u in text_units:
        members = sorted(u["items"], key=lambda m: _order_key(texts, {"items": [m]}))
        rects = [texts[m]["rect"] for m in members]
        spec = {"type": "string"}
        desc = (u.get("description") or "").strip() or " / ".join(dict.fromkeys(
            (texts[m]["description"] or "").strip() for m in members if (texts[m]["description"] or "").strip()))
        if desc:
            spec["description"] = desc
        spec["widget"] = {"page": texts[members[0]]["page"],
                          "rect": [round(min(r[0] for r in rects), 3), round(min(r[1] for r in rects), 3),
                                   round(max(r[2] for r in rects), 3), round(max(r[3] for r in rects), 3)],
                          "widget_type": "text", "path": None}
        spec["label_source"] = "llm" if u.get("name_from") == "labeler" else "hand"
        spec["x_petey_combined"] = {"source": "group_review", "when": u.get("when") or now,
                                    **({"name_from": u["name_from"]} if u.get("name_from") else {}),
                                    "from": [{k: texts[m][k] for k in ("field", "path", "rect", "type", "semantic_type")
                                              if texts[m][k] is not None} for m in members]}
        at[members[0]] = (u["name"], spec)
        gone.update(members)
        changes.append(f"text fields {', '.join(members)} -> {u['name']} (p{texts[members[0]]['page']}, "
                       f"one text box over {len(members)})")
    new: dict = {}
    for name, spec in out.items():
        if name in at:
            n, s = at[name]
            new[n] = s
        elif name not in gone:
            new[name] = spec
    return new


def apply(bid: str, page_captions: bool = True) -> dict:
    """Write the record into the blueprint, then re-derive the record from the new file (confirmations kept by unit
    name and membership). Writes the working copy while one is open (`draft.py`)."""
    real = blueprint_paths()[bid]
    p = working_path(bid)
    bp = _load(p)
    sha = _sha(p)
    items, units, info = current_units(bid, bp, sha)
    if info["stale"] and not load_record(bid).get("boxes"):     # a record with its boxes rebases safely
        raise SystemExit(f"{bid}: the record was written against another version of the blueprint; open it in the "
                         f"page, check the grouping and save again before applying")
    pl = plan(bp, units, resolve_blank(bp), page_captions)
    if pl["errors"]:
        raise SystemExit(f"{bid}: not applied:\n  " + "\n  ".join(pl["errors"]))
    if not pl["changes"]:
        print(f"{bid}: nothing to change")
        return pl
    bp["fields"] = pl["fields"]
    field_ids.assign(bp)                    # a new field gets the next free id on its page
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True), encoding="utf-8")
    new_sha = _sha(p)
    confirmed = {(u["name"], len(u["items"])) for u in units if u.get("confirmed")}
    _, fresh = option_items(bp)
    rec = {"blueprint": str(real), "form": real.stem, "blueprint_sha": new_sha,
           "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
           "applied": {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "sha_before": sha, "sha_after": new_sha,
                       "changes": pl["changes"]},
           "units": [dict(u, confirmed=(u["name"], len(u["items"])) in confirmed) for u in fresh]}
    fresh_items, _ = option_items(bp)
    rec["boxes"] = item_boxes({**fresh_items, **text_items(bp)}, rec["units"])
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

    def path(self, bid: str) -> Optional[Path]:
        return working_path(bid, self.paths)

    def _entry(self, bid: str) -> Optional[dict]:
        p = self.path(bid)
        bp = _load(p)
        items, units, info = current_units(bid, bp, _sha(p))
        combos = sum(1 for u in units if u.get("kind") == "text")
        units = [u for u in units if u.get("kind") != "text"]
        if not units and not combos and not any(it.get("kind") == "text" for it in items.values()):
            return None
        groups = sum(1 for u in units if len(u["items"]) > 1 or u["type"] != "boolean")
        return {"id": bid, "source": bid.split("__")[0], "form": p.stem, "groups": groups,
                "orphans": len(units) - groups, "confirmed": sum(1 for u in units if u.get("confirmed")),
                "units": len(units), "combos": combos, "stale": info["stale"], "edited": bool(info["updated"])}

    def index(self) -> None:
        t0 = time.time()
        for bid in self.paths:
            e = self._entry(bid)
            if e:
                self._index[bid] = e
        print(f"  {len(self._index)} of {len(self.paths)} blueprints have option or text boxes ({time.time() - t0:.1f}s)")

    def listing(self) -> list[dict]:
        if not self._index:
            self.index()
        return list(self._index.values())

    def detail(self, bid: str) -> Optional[dict]:
        p = self.path(bid)
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
        opt_items, base = option_items(bp)
        option_fields = {it["field"] for it in opt_items.values()}
        return {"id": bid, "path": str(self.paths[bid]), "blank": str(blank) if blank else None, "sha": sha, "pages": pages,
                "items": items, "units": units, "base": [{k: u[k] for k in ("name", "type", "items")} for u in base],
                "other_names": sorted(n for n in (bp.get("fields") or {}) if n not in option_fields),
                "info": info}

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key not in self.png:
            p = self.path(bid)
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
        p = self.path(bid)
        if p is None:
            raise KeyError(bid)
        bp = _load(p)
        items, _ = option_items(bp)
        items = {**items, **text_items(bp)}
        keep = ("name", "type", "items", "origin", "confirmed", "description", "locked", "kind", "when", "name_from")
        units = [{k: u.get(k) for k in keep if u.get(k) is not None} for u in incoming.get("units") or []]
        for u in units:
            u["items"] = [i for i in u.get("items") or [] if i in items]
        units = [u for u in units if u["items"]]
        rec = {"blueprint": str(self.paths[bid]), "form": p.stem, "blueprint_sha": _sha(p),
               "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "applied": load_record(bid).get("applied"),
               "units": units, "boxes": item_boxes(items, units)}
        OUT.mkdir(parents=True, exist_ok=True)
        record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        e = self._entry(bid)
        if e:
            self._index[bid] = e
        return {"saved": rec["updated"], "entry": e}

    def plan_for(self, bid: str, incoming: Optional[dict] = None) -> dict:
        p = self.path(bid)
        bp = _load(p)
        units = (incoming or {}).get("units") or current_units(bid, bp, _sha(p))[1]
        pl = plan(bp, units, resolve_blank(bp))
        return {"changes": pl["changes"], "errors": pl["errors"]}


def summary() -> None:
    paths = blueprint_paths()
    print(f"{'blueprint':44} {'units':>5} {'confirmed':>9} {'changes':>7} {'stale':>5}  updated")
    n = 0
    for rp in sorted(OUT.glob("*.json")):
        rec = json.loads(rp.read_text(encoding="utf-8"))
        p = working_path(rp.stem, paths)
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
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5006)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--plan", metavar="ID", help="print what --apply would change for this blueprint id")
    ap.add_argument("--apply", metavar="ID", help="write the recorded grouping into this blueprint")
    ap.add_argument("--no-page-captions", action="store_true",
                    help="do not read captions from the page for options that have none (they stay uncaptioned)")
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
            apply(bid, page_captions=not args.no_page_captions)
            return 0
        p = working_path(bid)
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
    from petey.validate.blueprint_review import serve
    return serve(args.port, "groups", not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
