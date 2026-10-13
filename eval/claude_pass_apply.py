"""Claude's pass over a blueprint, applied (2026-10-13, Andrew: "give the current blueprints a once-over given your own
memory and whatever tools you have"). A reviewer reads a form's dump (`eval/claude_pass_dump.py`) and writes
`runs/claude_pass/proposals/<id>.json`; this puts the sure changes into the review page's working copy of the
blueprint (`petey/validate/draft.py`), where Andrew checks them and saves or discards, and the unsure ones beside it
as suggestions the page shows on the field with a "use" button.

    {"changes": [
      {"field": "x", "sure": true, "kind": "wrong|clarity|suffix|type|caption", "why": "...",
       "name": "...", "type": "...", "semantic_type": "...|none", "pattern": "...|none",
       "options": {"<key>": {"caption": "...", "key": "..."}}},
      {"add": "<suggestion id from an UNCLAIMED line>", "name": "...", "type": "...", "semantic_type": "...", "why": "..."},
      {"remove": "<field>", "sure": true, "why": "..."}]}

Rules this enforces whatever the proposal says: a field Andrew accepted by hand is only ever a suggestion; an option
caption from the XFA template or set by hand is never changed (both unless the entry carries `"asked_by": "andrew"`,
a change he asked for); a rename onto a name another field keeps becomes a
suggestion; a value the review page would refuse (`hand_review.clean_edit`) is dropped with a note. Every field
still typed `person_name` loses it (no longer assigned, 2026-10-13). Each applied edit carries `x_petey_hand_edit`
{by: claude, kind, why}; the draft's log reads "claude: ..." line by line, so the page's save button lists them.

    PYTHONPATH=. venv/bin/python eval/claude_pass_apply.py lib__faa8710 [more ids] [--dry]
"""
from __future__ import annotations

import argparse
import json
import sys
import time

import yaml

from petey.paths import RUNS
from petey.validate import draft, field_add, field_ids
from petey.validate.hand_review import (_load, blueprint_paths, clean_edit, edit_fields, load_verdicts,
                                        working_path)

PROPOSALS = RUNS / "claude_pass" / "proposals"
SUGGESTIONS = RUNS / "claude_pass" / "suggestions"
EDIT_KEYS = ("name", "type", "semantic_type", "pattern", "options")


def _hand_accepted(v: dict) -> bool:
    return v.get("verdict") == "accept" and not (v.get("note") or "").startswith(("bulk", "auto"))


def apply(bid: str, dry: bool = False, log=print) -> dict:
    real = blueprint_paths()[bid]
    prop = json.loads((PROPOSALS / f"{bid}.json").read_text())
    p = working_path(bid)
    bp = _load(p)
    fields = bp.get("fields") or {}
    vs = load_verdicts(bid).get("verdicts") or {}
    edits, extra, sugg, notes = {}, {}, {}, []

    def suggest(n, text, fix=None):
        sugg.setdefault(n, []).append({"text": f"Claude: {text}", **({"fix": fix} if fix else {})})

    for c in prop.get("changes") or []:
        if c.get("add") or c.get("remove"):
            continue
        n = c.get("field")
        spec = fields.get(n)
        if not isinstance(spec, dict):
            notes.append(f"{n}: no such field (any more)")
            continue
        e = {k: c[k] for k in EDIT_KEYS if c.get(k) not in (None, "")}
        ws = spec.get("widgets") or {}
        asked = c.get("asked_by") == "andrew"          # his own request, carried out here: may change what he locked
        locked = set() if asked else {k for k, w in ws.items() if (w.get("x_petey_caption_source") in ("xfa", "hand")
                                      or k in ((spec.get("x_petey_xfa") or {}).get("choices") or {}))}
        if e.get("options"):
            e["options"] = {k: {x: y for x, y in o.items() if not (x == "caption" and k in locked)}
                            for k, o in e["options"].items() if k in ws}
            e["options"] = {k: o for k, o in e["options"].items() if o} or None
            if not e["options"]:
                e.pop("options")
        try:
            ce = clean_edit(n, spec, e)
        except ValueError as err:
            notes.append(f"{n}: dropped ({err})")
            continue
        if not ce:
            continue
        why = (c.get("why") or "").strip()
        if not c.get("sure") or (_hand_accepted(vs.get(n) or {}) and not asked):
            suggest(n, why or "a better definition", {k: ce[k] for k in ("name", "type", "semantic_type", "pattern")
                                                      if k in ce} | ({"options": ce["options"]} if ce.get("options") else {}))
            continue
        edits[n] = ce
        extra[n] = {"kind": c.get("kind") or "wrong", "why": why, **({"asked_by": "andrew"} if asked else {})}
    for n, spec in fields.items():                        # person_name is no longer assigned (2026-10-13)
        if isinstance(spec, dict) and spec.get("semantic_type") == "person_name" and "semantic_type" not in edits.get(n, {}):
            edits.setdefault(n, {})["semantic_type"] = "none"
            extra.setdefault(n, {"kind": "type", "why": "person_name is no longer assigned (it changed nothing)"})
    # a rename onto a name some other field ends up with is held back; holding one back can block the next in a
    # chain (A -> B, B -> C held: A now lands on B), so repeat until nothing changes
    while True:
        renames = {n: e.get("name", n) for n, e in edits.items()}
        final = [renames.get(n, n) for n in fields]
        held = [n for n in edits if renames[n] != n and final.count(renames[n]) > 1]
        if not held:
            break
        for n in held:
            suggest(n, f"{extra[n]['why']} (held back: another field is named {renames[n]})", {"name": renames[n]})
            edits[n].pop("name")
            if not edits[n]:
                edits.pop(n)
    final = [renames.get(n, n) for n in fields]
    assert len(set(final)) == len(final), f"{bid}: two fields would share a name"
    adds = [c for c in prop.get("changes") or [] if c.get("add")]
    removes = [c for c in prop.get("changes") or [] if c.get("remove")]
    lines = [f"{n} " + ", ".join(f"{k} -> {v}" for k, v in e.items() if k != "options")
             + (f", {len(e['options'])} option(s)" if e.get("options") else "") + f" ({extra[n]['why'][:90]})"
             for n, e in edits.items()]
    if dry:
        print("\n".join(lines + [f"suggest {n}: {x['text'][:100]}" for n, xs in sugg.items() for x in xs] + notes))
        return {"edits": len(edits), "suggestions": sum(map(len, sugg.values())), "adds": len(adds), "removes": len(removes)}
    if edits or adds or removes:
        p = draft.ensure(bid, real)
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    if edits:
        bp["fields"] = fields = edit_fields(fields, edits, renames, now, f"runs/claude_pass/proposals/{bid}.json",
                                            by="claude", extra=extra)
    # fields added from the Add / remove suggestions, and removals: field_add's plan, so they are placed and marked
    # the way the page's Add / remove writes them
    added, removed = [], []
    if adds or removes:
        ctx = field_add.Context(bid, p)
        ctx.bp, ctx.names = bp, set(fields)
        for c in adds:
            pr = (field_add.propose(ctx, 0, sid=c["add"]).get("proposals") or [None])[0]
            if pr is None:
                notes.append(f"add {c['add']}: no such suggestion")
                continue
            pr.update({k: c[k] for k in ("name", "type", "semantic_type", "description") if c.get(k)})
            pr["name_source"], pr["when"] = "labeler", now
            added.append(pr)
            lines.append(f"add {c['name']} ({c.get('why', '')[:90]})")
        for c in removes:
            if not c.get("sure") or _hand_accepted(vs.get(c["remove"]) or {}):
                suggest(c["remove"], f"maybe not a field: {c.get('why', '')}")
                continue
            removed.append({"name": c["remove"]})
            lines.append(f"remove {c['remove']} ({c.get('why', '')[:90]})")
        pl = field_add.plan(bp, added, removed)
        if pl["errors"]:
            notes += [f"add/remove not applied: {x}" for x in pl["errors"]]
        else:
            bp["fields"] = pl["fields"]
            for c, pr in zip(adds, added):
                s = bp["fields"].get(pr["name"])
                if isinstance(s, dict):
                    s["label_source"] = "llm"
                    s["x_petey_added"].update(name_from="claude", why=c.get("why"))
            notes += [f"skipped {x}" for x in pl["skipped"]]
    if edits or adds or removes:
        field_ids.assign(bp)
        p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        draft.log(bid, "claude", lines)
    SUGGESTIONS.mkdir(parents=True, exist_ok=True)
    (SUGGESTIONS / f"{bid}.json").write_text(json.dumps(sugg, indent=1, ensure_ascii=False))
    for x in notes:
        log(f"  note {x}")
    out = {"edits": len(edits), "adds": len(added), "removes": len(removed), "suggestions": sum(map(len, sugg.values()))}
    log(f"{bid}: {out}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    for bid in args.ids:
        apply(bid, dry=args.dry)
    return 0


if __name__ == "__main__":
    sys.exit(main())
