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
from pathlib import Path
from typing import Optional

from petey.validate import hand_review
from petey.validate.retype import resolve_blank

MODEL = "claude-opus-5"
TYPES = ("string", "number", "integer", "date", "boolean", "category")
ACTIONS = ("edit", "remove", "regroup", "none")

SYSTEM = """A person reviewing a form blueprint flagged one field and wrote a note saying what is wrong. A \
blueprint names and types every fillable box on a form so a program can fill it in and read it back. Your job is \
to turn the person's note into one concrete correction. The note is the instruction: follow it, using the page to \
get the details right (the exact wording of the caption, which box is which), not to second-guess it.

You see a crop of the blank form with the field's box outlined in red, the field's current name, type, semantic \
type, pattern and description, the publisher's tooltip, and the definitions of any other fields the note names \
("see X" means: make this field like X). Choose one action:
- edit: change any of name (snake_case; suffixes like _nm name, _dt date, _amt money, _cd code, _ind yes/no, _txt \
text, _cnt count), type (string, number, integer, date, boolean, category), semantic_type (a name from the list \
given, or "none" to clear it), pattern (a regular expression, or "none" to clear it), description. Leave a part \
empty to keep it as it is. A note about the "type" may mean the semantic type: a field that is already a string \
but carries a person_name semantic type for a name-and-address box needs semantic_type "none";
- remove: the box is not a field (nothing is written there);
- regroup: the field should be part of an option group with other boxes (the person will do that by hand);
- none: the note asks for nothing you can express with these actions.
Give a one-line reason that names the caption or the part of the note you relied on."""

SCHEMA = {"type": "object",
          "properties": {"action": {"type": "string", "enum": list(ACTIONS)},
                         "name": {"type": "string"}, "type": {"type": "string", "enum": [""] + list(TYPES)},
                         "semantic_type": {"type": "string"}, "pattern": {"type": "string"},
                         "description": {"type": "string"}, "reason": {"type": "string"}},
          "required": ["action", "name", "type", "semantic_type", "pattern", "description", "reason"],
          "additionalProperties": False}

_RUNNING: set[str] = set()
_LOCK = threading.Lock()


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


def propose(client, blank: Path, name: str, spec: dict, note: str, tooltip: str, others: dict) -> dict:
    from petey.validate.adjudicate import crop_png
    b = _box(spec)
    if b is None:
        return {"action": "none", "reason": "the field has no box on the blank"}
    png = crop_png(blank, b[0], b[1])
    from petey.semantic_types import REGISTRY
    keep = ("type", "semantic_type", "pattern", "description")
    facts = {"current_name": name, "current_type": spec.get("type"), "semantic_type": spec.get("semantic_type"),
             "pattern": spec.get("pattern"), "description": spec.get("description"), "publisher_tooltip": tooltip or None,
             "options": list((spec.get("widgets") or {}).keys()) or None, "person_note": note,
             "fields_named_in_the_note": {o: {k: s.get(k) for k in keep if s.get(k)} for o, s in others.items()} or None,
             "semantic_types": [t.name for t in REGISTRY]}
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
    try:                                            # keep only what the correction boxes would accept
        hand_review.clean_edit(name, spec, {k: out.get(k) for k in ("semantic_type", "pattern")})
    except ValueError as e:
        out["reason"] = f"{out.get('reason') or ''} (dropped: {e})"
        out["semantic_type"] = out["pattern"] = ""
    return out


def process(bid: str, log=print) -> int:
    """Propose a correction for each flagged-with-a-note field of one reviewed blueprint; returns how many."""
    p = hand_review.blueprint_paths().get(bid)
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
    done = {}
    for n in names:
        spec = (bp.get("fields") or {}).get(n)
        if not isinstance(spec, dict):
            continue
        note = rec["verdicts"][n]["note"].strip()
        fields = bp.get("fields") or {}
        others = {o: fields[o] for o in fields if o != n and o in note}
        try:
            out = propose(client, blank, n, spec, note, publisher_text(spec, limits), others)
        except Exception as e:                       # one bad call does not stop the form
            out = {"action": "none", "reason": f"failed: {type(e).__name__}: {e}"[:200]}
        done[n] = {**{k: out.get(k) or None for k in ("action", "name", "type", "semantic_type", "pattern",
                                                        "description", "reason")},
                   "model": MODEL, "when": time.strftime("%Y-%m-%d %H:%M:%S"), "for_note": note}
        parts = " ".join(f"{k}={done[n][k]}" for k in ("name", "type", "semantic_type", "pattern") if done[n].get(k))
        log(f"  {bid}.{n}: {done[n]['action']} {parts} | {(done[n].get('reason') or '')[:90]}")
    # merge into the record as it is now (the page may have written since): only the agent's own key
    cur = hand_review.load_verdicts(bid)
    for n, a in done.items():
        v = (cur.get("verdicts") or {}).get(n)
        if v and (v.get("note") or "").strip() == a["for_note"]:
            v["agent"] = a
    hand_review.verdict_path(bid).write_text(json.dumps(cur, indent=1, ensure_ascii=False), encoding="utf-8")
    return len(done)


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
