"""After review: an agent turns the person's flags and notes into proposed corrections.

Andrew, 2026-10-07: a field he flags with a note should go to an agent as the post-review process. Until now a flag
and its note were only recorded (31 of the first 50 were never acted on). The review page's "review edits" button
runs this in the background on the fields flagged with a note and no correction of his own. Per field it sends the note (the instruction), a crop of the blank around the box
(adjudicate.crop_png: the box outlined, column headers in view), the field's definition and the publisher's tooltip,
and gets back one proposal:

    edit                              any of a new field name, type, semantic type, pattern ("none" clears the
                                      last two) and description: the review page's correction boxes
    remove                            not a field
    regroup                           belongs in an option group: done in the Groups tab, which the agent cannot do
    none                              the note does not call for a change the agent can make

The proposal is stored on the verdict (`agent`: action, name, type, semantic_type, pattern, description, reason,
model, when, for_note) and
shown in the page with a "use" button that fills the correction boxes (or marks the field for removal). Nothing is
written to a blueprint here: the person applies, as with his own corrections. A proposal is redone when the note
changes.

    PYTHONPATH=. venv/bin/python -m petey.validate.flag_agent je__acord_126 [more ids]   # run it by hand
"""
from __future__ import annotations

import argparse
import base64
import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from petey.validate import hand_review
from petey.validate.retype import resolve_blank

MODEL = "claude-opus-5"
TYPES = ("string", "number", "integer", "date", "boolean", "category", "multi_category")
ACTIONS = ("edit", "remove", "regroup", "none")

SYSTEM = """A person reviewing a form blueprint flagged one field and wrote a note saying what is wrong. A \
blueprint names and types every fillable box on a form so a program can fill it in and read it back. Your job is \
to turn the person's note into one concrete correction. The note is the instruction: follow it, using the page to \
get the details right (the exact wording of the caption, which box is which), not to second-guess it.

You see a crop of the blank form with the field's box outlined in red, the field's current name, type, semantic \
type, pattern and description, the publisher's tooltip, and the definitions of any other fields the note names \
("see X" means: make this field like X). Choose one action:
- edit: change any of name (snake_case; suffixes like _nm name, _dt date, _amt money, _cd code, _ind yes/no, _txt \
text, _cnt count), type (string, number, integer, date, boolean, category = one of, multi_category = any of; \
an option group is only ever category or multi_category), semantic_type (a name from the list \
given, or "none" to clear it), pattern (a regular expression, or "none" to clear it), description. Leave a part \
empty to keep it as it is. A note about the "type" may mean the semantic type: a field that is already a string \
but carries a person_name semantic type for a name-and-address box needs semantic_type "none";
- remove: the box is not a field (nothing is written there);
  For an option group the image numbers each box (1, 2, ...) and `options` lists each box's number, key, \
on-state and caption. In `options` give, for every box whose key or caption should change, its number, a new key \
(snake_case, empty to keep it) and the caption printed at that box, exactly as printed and without its item \
number ("Checking", not "139.a Checking"); leave `options` empty when no box changes. A caption belongs to the \
box it is printed beside on the same line, not to a neighbour;
- regroup: the field should be part of an option group with other boxes (the person will do that by hand);
- none: the note asks for nothing you can express with these actions.
Give a one-line reason that names the caption or the part of the note you relied on."""

SCHEMA = {"type": "object",
          "properties": {"action": {"type": "string", "enum": list(ACTIONS)},
                         "name": {"type": "string"}, "type": {"type": "string", "enum": [""] + list(TYPES)},
                         "semantic_type": {"type": "string"}, "pattern": {"type": "string"},
                         "description": {"type": "string"}, "reason": {"type": "string"},
                         "options": {"type": "array", "items": {
                             "type": "object", "properties": {"box": {"type": "integer"}, "new_key": {"type": "string"},
                                                              "caption": {"type": "string"}},
                             "required": ["box", "new_key", "caption"], "additionalProperties": False}}},
          "required": ["action", "name", "type", "semantic_type", "pattern", "description", "reason", "options"],
          "additionalProperties": False}

WORKERS = 8                                         # fields proposed at once

_RUNNING: set[str] = set()
_LOCK = threading.Lock()
_PDF_LOCK = threading.Lock()


def todo(rec: dict) -> list[str]:
    """Flagged fields with a note, no correction of the person's own, and no proposal for this note yet."""
    out = []
    for n, v in (rec.get("verdicts") or {}).items():
        note = (v.get("note") or "").strip()
        if v.get("verdict") != "flag" or not note or note == "removed" or v.get("edit"):
            continue
        if (v.get("agent") or {}).get("for_note") == note:
            continue
        out.append(n)
    return out


def _box(spec: dict) -> Optional[tuple[int, list[float]]]:
    ws = list((spec.get("widgets") or {}).values()) or [spec.get("widget") or {}]
    ws = [w for w in ws if w.get("rect") and w.get("page")]
    if not ws:
        return None
    pg = ws[0]["page"]
    rs = [w["rect"] for w in ws if w["page"] == pg]
    return pg, [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]


def _option_boxes(spec: dict, page: int) -> list[tuple[str, dict]]:
    ws = spec.get("widgets") if isinstance(spec.get("widgets"), dict) else {}
    return [(k, w) for k, w in ws.items() if w.get("rect") and w.get("page") == page]


def options_png(blank: Path, page_no: int, boxes: list[tuple[str, dict]]) -> bytes:
    """An option group on the blank: every box outlined in red and numbered 1..n (in the order of `boxes`), full page
    width, from a little above the top box to a little below the lowest (the column headers in view)."""
    import pymupdf
    from petey.validate.adjudicate import DPI, PAD_DOWN, PAD_UP
    doc = pymupdf.open(str(blank))
    try:
        page = doc[page_no - 1]
        for i, (_, w) in enumerate(boxes, 1):
            r = pymupdf.Rect(*w["rect"])
            page.draw_rect(r, color=(1, 0, 0), width=1.2)
            page.insert_text((r.x0 - 1, r.y0 - 1.5), str(i), fontsize=7, color=(0.85, 0, 0), fontname="helv")
        top = min(w["rect"][1] for _, w in boxes) - PAD_UP / 2
        bottom = max(w["rect"][3] for _, w in boxes) + PAD_DOWN / 2
        clip = pymupdf.Rect(page.rect.x0, max(page.rect.y0, top), page.rect.x1, min(page.rect.y1, bottom))
        return page.get_pixmap(dpi=DPI, clip=clip).tobytes("png")
    finally:
        doc.close()


def propose(client, blank: Path, name: str, spec: dict, note: str, tooltip: str, others: dict) -> dict:
    from petey.validate.adjudicate import crop_png
    b = _box(spec)
    if b is None:
        return {"action": "none", "reason": "the field has no box on the blank"}
    boxes = _option_boxes(spec, b[0])
    with _PDF_LOCK:                                 # PyMuPDF is not thread-safe; the model calls run in parallel
        png = options_png(blank, b[0], boxes) if boxes else crop_png(blank, b[0], b[1])
    from petey.semantic_types import registered_names
    keep = ("type", "semantic_type", "pattern", "description")
    facts = {"current_name": name, "current_type": spec.get("type"), "semantic_type": spec.get("semantic_type"),
             "pattern": spec.get("pattern"), "description": spec.get("description"), "publisher_tooltip": tooltip or None,
             "options": [{"box": i, "key": k, "on_state": w.get("on_state"), "caption": w.get("caption")}
                         for i, (k, w) in enumerate(boxes, 1)] or None, "person_note": note,
             "fields_named_in_the_note": {o: {k: s.get(k) for k in keep if s.get(k)} for o, s in others.items()} or None,
             "semantic_types": registered_names()}
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                            "data": base64.standard_b64encode(png).decode("ascii")}},
               {"type": "text", "text": "The field (box outlined in red):\n"
                + json.dumps({k: v for k, v in facts.items() if v}, ensure_ascii=False)
                + "\n\nTurn the person's note into one correction. Return JSON."}]
    resp = client.messages.create(model=MODEL, max_tokens=4000, system=SYSTEM,
                                  messages=[{"role": "user", "content": content}],
                                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    text = next((x.text for x in resp.content if getattr(x, "type", None) == "text"), "")
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        return {"action": "none", "reason": f"no usable answer ({resp.stop_reason})"}
    if out.get("name") and not hand_review._SLUG.match(out["name"]):
        out["name"] = ""
    if len(spec.get("widgets") or {}) > 1 and out.get("type") not in ("", None, "category", "multi_category"):
        out["reason"] = f"{out.get('reason') or ''} (type {out['type']} dropped: an option group is category or multi_category)"
        out["type"] = ""
    # per-box keys and captions -> the review page's option edit {key: {key, caption}}, checked like a person's
    opts = {}
    for o in out.get("options") or []:
        if 1 <= int(o.get("box") or 0) <= len(boxes):
            k = boxes[int(o["box"]) - 1][0]
            d = {**({"key": o["new_key"]} if o.get("new_key") and o["new_key"] != k else {}), "caption": (o.get("caption") or "").strip()}
            opts[k] = d
    try:
        cleaned = hand_review.clean_edit(name, spec, {"options": opts}) if opts else None
        out["options"] = (cleaned or {}).get("options") or {}
    except ValueError as e:
        out["reason"] = f"{out.get('reason') or ''} (options dropped: {e})"
        out["options"] = {}
    try:                                            # keep only what the correction boxes would accept
        hand_review.clean_edit(name, spec, {k: out.get(k) for k in ("semantic_type", "pattern")})
    except ValueError as e:
        out["reason"] = f"{out.get('reason') or ''} (dropped: {e})"
        out["semantic_type"] = out["pattern"] = ""
    return out


def process(bid: str, log=print) -> int:
    """Propose a correction for each flagged-with-a-note field of one reviewed blueprint; returns how many."""
    p = hand_review.working_path(bid)
    if p is None:
        return 0
    rec = hand_review.load_verdicts(bid)
    names = todo(rec)
    if not names:
        return 0
    bp = hand_review._load(p)
    blank = resolve_blank(bp)
    if blank is None:
        return 0
    from petey.synth.generate import make_client
    from petey.synth.local import widget_limits
    from petey.validate.adjudicate import publisher_text
    client = make_client(MODEL)
    limits = widget_limits(blank)
    fields = bp.get("fields") or {}

    def one(n: str) -> Optional[dict]:
        spec = fields.get(n)
        if not isinstance(spec, dict):
            return None
        note = rec["verdicts"][n]["note"].strip()
        others = {o: fields[o] for o in fields if o != n and o in note}
        try:
            out = propose(client, blank, n, spec, note, publisher_text(spec, limits), others)
        except Exception as e:                       # one bad call does not stop the form
            out = {"action": "none", "reason": f"failed: {type(e).__name__}: {e}"[:200]}
        a = {**{k: out.get(k) or None for k in ("action", "name", "type", "semantic_type", "pattern",
                                                "description", "reason", "options")},
             "model": MODEL, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "for_note": note}
        parts = " ".join(f"{k}={a[k]}" for k in ("name", "type", "semantic_type", "pattern") if a.get(k))
        log(f"  {bid}.{n}: {a['action']} {parts} | {(a.get('reason') or '')[:90]}")
        return a

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        done = {n: a for n, a in zip(names, ex.map(one, names)) if a is not None}
    # merge into the record as it is now (the page may have written since): only the agent's own key
    with hand_review._VERDICT_LOCK:
        cur = hand_review.load_verdicts(bid)
        for n, a in done.items():
            v = (cur.get("verdicts") or {}).get(n)
            if v and (v.get("note") or "").strip() == a["for_note"]:
                v["agent"] = a
        hand_review._write_verdicts(bid, cur)
    return len(done)


def propose_field(bid: str, name: str, note: str) -> dict:
    """One field, now, for the review page's "fix captions" button (Andrew, 2026-10-07: the loop notices wrong option
    captions and does not fix them; offer the fix in one click). The page check's full reason for the field joins
    the note. The proposal is returned, not stored: the page puts it in the field's boxes and the person saves."""
    p = hand_review.working_path(bid)
    bp = hand_review._load(p) if p else {}
    spec = (bp.get("fields") or {}).get(name)
    blank = resolve_blank(bp) if bp else None
    if not isinstance(spec, dict) or blank is None:
        raise KeyError(name)
    from petey.synth.generate import make_client
    from petey.synth.local import widget_limits
    from petey.validate.adjudicate import publisher_text
    from petey.validate.page_check import verdicts as page_check_verdicts
    pc = (page_check_verdicts(bp) or {}).get(name) or {}
    if pc.get("reason"):
        note = f"{note}\nThe page check, which saw the whole page: {pc['reason']}"
    out = propose(make_client(MODEL), blank, name, spec, note, publisher_text(spec, widget_limits(blank)), {})
    return {**{k: out.get(k) or None for k in ("action", "name", "type", "semantic_type", "pattern", "description",
                                                "reason", "options")}, "model": MODEL}


def start(bid: str) -> bool:
    """Run `process` in the background unless it is already running for this blueprint (the page's trigger)."""
    with _LOCK:
        if bid in _RUNNING:
            return False
        _RUNNING.add(bid)

    def run():
        try:
            process(bid, log=lambda s: print(s, flush=True))
        finally:
            with _LOCK:
                _RUNNING.discard(bid)
    threading.Thread(target=run, daemon=True).start()
    return True


def running(bid: str) -> bool:
    with _LOCK:
        return bid in _RUNNING


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+", help="review ids, e.g. je__acord_126 or lib__5021")
    args = ap.parse_args()
    for bid in args.ids:
        n = process(bid)
        print(f"{bid}: {n} proposal(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
