"""Chat on the review page: bespoke batch edits for the open form (Andrew, 2026-10-15: "can we add a chatbot so I can
request bespoke batch edits for the current form?").

The person writes a request ("rename every _txt box in Part 3 to _nbr", "group 12-15 as one question", "remove the
boxes over the letterhead"). One call to Opus 5 with the working copy's fields (numbered as the page check numbers
them, with box, type, captions), the pages with every box outlined and numbered, and the conversation so far; it
answers with a short reply and PROPOSED edits, which the page lists for the person to tick. Nothing is written until
the person applies, and then through the paths the page already uses:

    edits    name / type / semantic type / pattern / option keys and captions: `hand_review.clean_edit` (the same
             validation as a correction) and `edit_fields`, each field marked `x_petey_hand_edit` {by: claude, kind:
             chat, why}; the person's verdicts follow a rename
    groups   new option groups through the Groups code (`group_review.plan` / `apply`), as leaving Groups does
    remove   recorded in Add / remove's removals (the server applies them), as Review's remove button does

The page images and field list go first in the request and are cached, so a follow-up in the same conversation
costs little.
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Optional

import yaml

from petey.validate import draft, group_review as g, hand_review as h, page_check as pc
from petey.validate.retype import resolve_blank

MODEL = "claude-opus-5"
MAX_PAGES = 12                 # page images sent; a longer form gets its field list only past this
PRICES = {"claude-opus-5": (5.0, 25.0)}

SYSTEM = """You help a person correct a form blueprint, one form at a time. A blueprint names and types every fillable \
box on a blank form so a program can fill it in and read it back. You see each page with every box outlined in red \
and numbered, and the field list (number, name, type, semantic type, pattern, widget, box in PDF points, description, \
option keys and captions for groups and dropdowns).

The person asks for edits, often in bulk. Propose exactly the edits that carry out the request, and nothing else. \
Refer to fields by their current name. Leave a property "" when it does not change. Kinds of edit:
- edits: rename (snake_case), type (string, number, integer, date, boolean, category, multi_category), semantic \
type, pattern, and for a group or dropdown its option keys (new_key) and captions.
- groups: separate checkboxes that answer one question become one group: a name for the question (no suffix), \
category (pick one) or multi_category (pick any), and the fields it is made of.
- remove: fields that are not a place where a filer writes (a box over printed text, a duplicate).

Naming standard: [description]_[iteration if several]_[suffix]_[part]. Suffixes: _nm any name, _nbr identifiers and \
numbers, _dt dates, _amt money, _cnt / _qty counts, _pct percentages, _cd codes (state_cd), _ind a single checkbox, \
_txt free text, _signature, unit suffixes (_hours, _days, _months, _years, _ft, _miles). Every iteration is numbered \
when there are several, the first too (parent_1_nm, parent_2_nm). Parts of one value go after the suffix \
(birth_dt_month, birth_dt_day, birth_dt_yr, phone_nbr_area); a year on its own is _yr (tax_yr), a month on its own \
_month. A group is named for its question, with no suffix. Keep the form's own words. A table is named on one \
pattern: each column one wording, each row one number (or the transpose), numbered 1..N by the table's own rows; labels \
that change page to page (A-D) become 1, 2, 3; two separate tables of the same columns get a prefix each (short_term_, \
long_term_); a totals row has no number.

When the request is unclear or would touch fields you cannot identify, say so in the reply and propose nothing for \
them. `confirmed` is for a request that asks you to check fields (a grid check): the fields you checked against the \
page and found right as they are (the name says what goes in the box under its own headers, and fits its table); \
leave it empty otherwise, and never list a field you propose to change. The reply is one or two plain sentences: what you propose, and anything left out. Return JSON only."""

_EDIT = {"type": "object", "additionalProperties": False,
         "required": ["field", "name", "type", "semantic_type", "pattern", "options", "why"],
         "properties": {"field": {"type": "string"}, "name": {"type": "string"}, "type": {"type": "string"},
                        "semantic_type": {"type": "string"}, "pattern": {"type": "string"},
                        "options": {"type": "array", "items": {
                            "type": "object", "additionalProperties": False, "required": ["key", "new_key", "caption"],
                            "properties": {"key": {"type": "string"}, "new_key": {"type": "string"},
                                           "caption": {"type": "string"}}}},
                        "why": {"type": "string"}}}
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["reply", "edits", "groups", "remove", "confirmed"],
          "properties": {
              "reply": {"type": "string"},
              "confirmed": {"type": "array", "items": {"type": "string"}},
              "edits": {"type": "array", "items": _EDIT},
              "groups": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False, "required": ["name", "type", "fields", "why"],
                  "properties": {"name": {"type": "string"},
                                 "type": {"type": "string", "enum": ["category", "multi_category"]},
                                 "fields": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}}}},
              "remove": {"type": "array", "items": {
                  "type": "object", "additionalProperties": False, "required": ["field", "why"],
                  "properties": {"field": {"type": "string"}, "why": {"type": "string"}}}}}}


def _context(bp: dict, only_pages: Optional[list[int]] = None) -> tuple[list[dict], dict[str, str]]:
    """(the request's first content blocks: page images and the field list, cached; {number: field name}).
    `only_pages`: those pages' images and fields only (check grid looks at one page: 2026-10-16, twelve page images
    for one page's tables made it slow)."""
    blank = resolve_blank(bp)
    rows = pc.numbered(bp)
    num = {r["id"]: r["name"] for r in rows}
    lines = []
    for r in rows:
        s, b = r["spec"], r["boxes"][0]
        item = {"n": r["id"], "name": r["name"], "page": b["page"], "box": [round(v) for v in b["rect"]],
                "type": s.get("type"), "widget": (s.get("widget") or {}).get("widget_type")}
        for k in ("semantic_type", "pattern"):
            if s.get(k):
                item[k] = s[k]
        if s.get("description"):
            item["description"] = " ".join(str(s["description"]).split())[:120]
        if s.get("widgets"):
            item["options"] = [{"key": k, "caption": w.get("caption")} for k, w in s["widgets"].items()]
        elif isinstance(s.get("options"), dict):
            item["dropdown"] = [{"key": k, "caption": (o or {}).get("caption")} for k, o in list(s["options"].items())[:25]]
        lines.append(json.dumps(item, ensure_ascii=False))
    blocks: list[dict] = []
    pages = sorted({b["page"] for r in rows for b in r["boxes"]})
    if only_pages:
        pages = [pg for pg in pages if pg in only_pages]
        lines = [ln for ln in lines if any(f'"page": {pg},' in ln for pg in only_pages)]
    for page in pages[:MAX_PAGES]:
        png, _, _ = pc.render(blank, page, rows)
        blocks += [{"type": "text", "text": f"Page {page}:"},
                   {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                "data": base64.standard_b64encode(png).decode("ascii")}}]
    note = f" (page images for the first {MAX_PAGES} of {len(pages)} pages only)" if len(pages) > MAX_PAGES else ""
    blocks.append({"type": "text", "text": f"Form: {bp.get('name')}{note}. Fields, one per line:\n" + "\n".join(lines),
                   "cache_control": {"type": "ephemeral"}})
    return blocks, num


def _clean(bp: dict, ans: dict, num: dict[str, str]) -> dict:
    """The model's answer, checked: field names resolved (a bare number is the outlined box), each edit validated
    as a correction is (`clean_edit`), no-ops dropped; what failed goes in `errors`."""
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}

    def resolve(f: str) -> Optional[str]:
        f = (f or "").strip()
        return f if f in fields else num.get(f.lstrip("#"))
    out = {"reply": ans.get("reply") or "", "edits": [], "groups": [], "remove": [], "errors": [],
           "confirmed": [n for n in (resolve(f) for f in ans.get("confirmed") or []) if n]}
    for e in ans.get("edits") or []:
        n = resolve(e.get("field"))
        if n is None:
            out["errors"].append(f"no field {e.get('field')!r}")
            continue
        raw = {k: e[k] for k in ("name", "type", "semantic_type", "pattern") if (e.get(k) or "").strip()}
        opts = {o["key"]: {k: v for k, v in (("key", o.get("new_key")), ("caption", o.get("caption"))) if v}
                for o in e.get("options") or [] if o.get("key")}
        if opts:
            raw["options"] = {k: v for k, v in opts.items() if v}
        try:
            ce = h.clean_edit(n, fields[n], raw)
        except ValueError as err:
            out["errors"].append(f"{n}: {err}")
            continue
        if ce:
            out["edits"].append({"field": n, "edit": ce, "why": e.get("why") or ""})
    for gr in ans.get("groups") or []:
        ms = [resolve(f) for f in gr.get("fields") or []]
        bad = [f for f, m in zip(gr.get("fields") or [], ms) if m is None]
        if bad or len(ms) < 2:
            out["errors"].append(f"group {gr.get('name')!r}: " + (f"no field {', '.join(bad)}" if bad else "fewer than 2 fields"))
            continue
        out["groups"].append({"name": gr["name"], "type": gr["type"], "fields": ms, "why": gr.get("why") or ""})
    for r in ans.get("remove") or []:
        n = resolve(r.get("field"))
        if n is None:
            out["errors"].append(f"no field {r.get('field')!r} to remove")
        else:
            out["remove"].append({"field": n, "why": r.get("why") or ""})
    return out


SKILL = Path(__file__).resolve().parents[2] / ".claude" / "skills" / "grid-validation" / "SKILL.md"


def grid_request(bid: str, page: int) -> str:
    """The review page's "check grid" request (Andrew, 2026-10-15: "run the skill on any grid on the page"): the grid
    rule and decisions from the grid-validation skill (read from the skill file, so the two stay one), and what
    eval/grid_naming.py finds on this page: each table as rows x columns, the cells off its pattern, its mechanical
    renames. The model checks every table on the page, the ones the layout test missed too, and proposes the edits."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))
    import grid_naming as G
    bp = h._load(h.working_path(bid))
    text = SKILL.read_text(encoding="utf-8") if SKILL.exists() else ""
    a, b = text.find("3. **Decide the names**"), text.find("4. **Apply**")
    rules = text[a:b].strip() if a >= 0 and b > a else ""
    found, done = [], []
    for g in G.grids(bp):
        if g[0]["page"] != page:
            continue
        if G.iterated(g) and G.on_pattern(g)[0]:       # passed the code check, its cells accepted: not asked again
            done.append(f"{g[0]['name']} ... {g[-1]['name']}")
            continue
        nr, nc = max(c["row"] for c in g) + 1, max(c["col"] for c in g) + 1
        cells = {(c["row"], c["col"]): c["name"] for c in g}
        found.append(f"Table {nr} rows x {nc} columns (row by row):\n" + "\n".join(
            " | ".join(cells.get((r, c), "-") for c in range(nc)) for r in range(nr)))
        reading, probs = G.breaks(g)
        if probs:
            found.append("Cells off its pattern: " + "; ".join(probs))
    ren, left = G.fixes(bp)
    on_page = {o: n for o, n in ren.items() if ((bp["fields"].get(o) or {}).get("widget") or {}).get("page") == page}
    return (f"Check every table (grid) on page {page} against the grid rule below and propose the renames, and the "
            f"^[YN]$ pattern for a column printed Y / N, that put each table on one pattern. Look at the page image "
            f"too: a table the layout test missed counts, and a block that only lines up (signature, address) is not "
            f"a table. Propose nothing for a table that is already right; say so in the reply. In `confirmed`, list every cell "
            f"of the tables you checked whose name is right as it stands (checked against its column and row headers on "
            f"the page), and none you propose to change: those are accepted for the person.\n\n"
            f"The rule: each column one kind of value with one wording, each row one iteration number (or the "
            f"transpose), names in the naming standard's shape.\n{rules}\n\n"
            f"What the layout test found on page {page}:\n" + ("\n\n".join(found) if found else "no table") +
            ("\n\nAlready on pattern by the code check and accepted (leave these tables alone, propose nothing and "
             "confirm nothing for them): " + "; ".join(done) if done else "") +
            ("\n\nIts mechanical renames (a hint, not an order): " + "; ".join(f"{o} -> {n}" for o, n in on_page.items())
             if on_page else ""))


def ask(bid: str, history: list[dict], *, model: str = MODEL, client=None, only_pages: Optional[list[int]] = None) -> dict:
    """One turn: `history` is the conversation so far, [{role: user | assistant, content: text}], ending with the
    person's request. Returns the checked proposal, the model's raw JSON (to send back as the assistant turn next
    time), usage and cost."""
    if not history or history[-1].get("role") != "user":
        raise ValueError("the conversation must end with a request")
    p = h.working_path(bid)
    bp = h._load(p)
    blocks, num = _context(bp, only_pages)
    msgs = []
    for i, m in enumerate(history):
        text = str(m.get("content") or "")
        if i == 0:
            msgs.append({"role": "user", "content": blocks + [{"type": "text", "text": "Request: " + text}]})
        else:
            msgs.append({"role": m["role"], "content": ("Request: " + text) if m["role"] == "user" else text})
    if client is None:
        from petey.synth.generate import make_client
        client = make_client(model)
    resp = client.messages.create(model=model, max_tokens=32000, system=SYSTEM, messages=msgs,
                                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "{}")
    ans = json.loads(text)
    u = resp.usage
    cached = getattr(u, "cache_read_input_tokens", 0) or 0
    written = getattr(u, "cache_creation_input_tokens", 0) or 0
    pi, po = PRICES.get(model, (0, 0))
    cost = (u.input_tokens * pi + written * pi * 1.25 + cached * pi * 0.1 + u.output_tokens * po) / 1e6
    out = _clean(bp, ans, num)
    out.update(raw=text, model=model, cost_usd=round(cost, 4),
               usage={"input_tokens": u.input_tokens, "cache_read": cached, "cache_write": written,
                      "output_tokens": u.output_tokens})
    return out


def apply(bid: str, edits: list[dict], groups: list[dict]) -> dict:
    """Write the ticked edits and groups into the working copy (removals are the server's: Add / remove). Returns
    {"changes": [...], "errors": [...], "renamed": {old: new}}."""
    p = draft.ensure(bid, h.blueprint_paths()[bid])
    bp = h._load(p)
    fields = bp.get("fields") or {}
    changes, errors, renamed = [], [], {}
    clean, extra = {}, {}
    for e in edits:
        n = e.get("field")
        if n not in fields:
            errors.append(f"no field {n!r}")
            continue
        try:
            ce = h.clean_edit(n, fields[n], e.get("edit") or {})
        except ValueError as err:
            errors.append(f"{n}: {err}")
            continue
        if ce:
            clean[n] = ce
            extra[n] = {"kind": "chat", "why": e.get("why") or "requested in the review page's chat"}
    if clean:
        ren = {n: ce.get("name", n) for n, ce in clean.items()}
        target = [ren.get(n, n) for n in fields]
        clash = {n for n in clean if target.count(ren[n]) > 1}
        for n in clash:
            errors.append(f"{n}: {ren[n]!r} is the name of another field")
            clean.pop(n)
            ren.pop(n)
        if clean:
            before = h._sha(p)
            bp["fields"] = h.edit_fields(fields, clean, ren, time.strftime("%Y-%m-%d %H:%M:%S"),
                                         "petey/validate/form_chat.py", by="claude", extra=extra)
            p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                         encoding="utf-8")
            draft.follow(bid, before, h._sha(p))
            vp = h.verdict_path(bid)                     # the person's verdicts follow a rename
            if vp.exists():
                rec = json.loads(vp.read_text())
                vs = rec.get("verdicts") or {}
                # all at once: in a shifted series (title_1 -> title_2 while title_2 -> title_3) moving one by one
                # overwrote the next field's verdict before it moved (2026-10-16, FAA 8050-1)
                moved = {o: vs.pop(o) for o, nw in ren.items() if o != nw and o in vs}
                vs.update({ren[o]: v for o, v in moved.items()})
                rec["verdicts"] = vs
                vp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
            renamed = {o: nw for o, nw in ren.items() if o != nw}
            changes += [f"{n}: " + ", ".join(f"{k} {v!r}" for k, v in clean[n].items() if k != "options")
                        + (f", {len(clean[n]['options'])} option(s)" if clean[n].get("options") else "")
                        for n in clean]
    if groups:
        bp = h._load(p)
        blank = resolve_blank(bp)
        _, units, _ = g.current_units(bid, bp, h._sha(p))
        items = g.option_items(bp)[0]          # option boxes only: a text box is combined, not grouped
        new_units = []
        for gr in groups:
            ids = []
            for f in gr.get("fields") or []:
                f = renamed.get(f, f)
                spec = (bp.get("fields") or {}).get(f) or {}
                got = [i for i in items if i == f or i.startswith(f + "::")] if spec else []
                if not got:
                    errors.append(f"group {gr.get('name')!r}: {f!r} is not a checkbox or yes / no box (retype it "
                                  "boolean first)")
                ids += got
            if len(ids) >= 2:
                new_units.append({"name": gr["name"], "type": gr.get("type") or "category", "items": ids,
                                  "confirmed": False})
        if new_units:
            taken = {i for u in new_units for i in u["items"]}
            units = [dict(u, items=[i for i in u["items"] if i not in taken]) for u in units]
            units = [u for u in units if u["items"]] + new_units
            pl = g.plan(bp, units, blank)
            if pl["errors"]:
                errors += [f"groups not applied: {x}" for x in pl["errors"]]
            else:
                before = h._sha(p)
                g.State().put_units(bid, {"units": units})
                res = g.apply(bid)
                draft.follow(bid, before, h._sha(h.working_path(bid)))
                changes += res["changes"]
    if changes:
        draft.log(bid, "claude", [f"chat: {c}" for c in changes])
    return {"changes": changes, "errors": errors, "renamed": renamed}
