"""A person's correction of a field, checked and applied (2026-10-07: field name and type directly adjustable in the
review page). Shared by the review page's corrections (`hand_review.apply_edits`), Claude's pass
(`eval/claude_pass_apply.py`), the form chat and the name standardizer. Lifted out of `hand_review` (2026-11-05) so the
package does not import the review page."""
from __future__ import annotations

import re
from typing import Optional

EDIT_TYPES = ("string", "number", "integer", "date", "boolean", "category", "multi_category")
_CHOICE = ("category", "multi_category")      # one of / any of: need `values`
SLUG = re.compile(r"^[a-z0-9][a-z0-9_]*$")
_OPT_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]*$")      # an option's key: the value extraction returns


# the parts a name prints from, in the standard's order (petey/naming.py, 2026-10-24)
from petey.naming import ORDER as IDENT_KEYS, print_name as _print_name, standard as _standard  # noqa: E402


def clean_edit(name: str, spec: dict, edit) -> Optional[dict]:
    """A person's correction of a field (2026-10-07: field name and type directly adjustable in the review page):
    only the parts that differ from the blueprint, validated (a snake_case name; a spec type)."""
    if not isinstance(edit, dict):
        return None
    out = {}
    new_name = (edit.get("name") or "").strip()
    # the name's parts (docs/NAMING.md "Identifiers", 2026-10-19): the name is printed from them, never typed
    if isinstance(edit.get("identifiers"), dict):
        ident = {}
        for k in IDENT_KEYS:
            v = str(edit["identifiers"].get(k) or "").strip()
            if v:
                if not SLUG.match(v):
                    raise ValueError(f"{k} {v!r}: lower-case letters, digits and _ only")
                ident[k] = v
        if not ident.get("subject") and not ident.get("suffix"):
            raise ValueError("a field needs a subject (what the box is about)")
        ident = {k: v for k, v in _standard(ident).items() if v}       # short suffix, part1 (petey/naming.py)
        if ident != {k: v for k, v in (spec.get("x_petey_identifiers") or {}).items()
                     if k in IDENT_KEYS and v not in (None, "")}:
            out["identifiers"] = ident
        new_name = _print_name(ident)
    if new_name and new_name != name:
        if not SLUG.match(new_name):
            raise ValueError(f"field name {new_name!r}: lower-case letters, digits and _ only")
        out["name"] = new_name
    new_type = (edit.get("type") or "").strip()
    if new_type and new_type != spec.get("type"):
        if new_type not in EDIT_TYPES:
            raise ValueError(f"type {new_type!r}: one of {', '.join(EDIT_TYPES)}")
        if len(spec.get("widgets") or {}) > 1 and new_type not in _CHOICE:
            raise ValueError("an option group is category (one of) or multi_category (any of)")
        if new_type in _CHOICE and not (spec.get("values") or spec.get("widgets")):
            raise ValueError(f"type {new_type}: the field has no option boxes or values to choose from")
        out["type"] = new_type
    # semantic type and pattern (2026-10-07: Andrew's "type" notes often mean the semantic type, and his ACORD 126
    # notes ask for a Y/N pattern): a value sets it, "none" clears it, absent / empty leaves it
    if "semantic_type" in edit and (edit.get("semantic_type") or "").strip():
        st = edit["semantic_type"].strip()
        from petey.semantic_types import registered_names     # every spec value (REGISTRY lacks money, indicator)
        if st != "none" and st not in set(registered_names()):
            raise ValueError(f"semantic type {st!r}: not in the registry (or 'none' to clear it)")
        if (st == "none") != (not spec.get("semantic_type")) or (st != "none" and st != spec.get("semantic_type")):
            out["semantic_type"] = st
    if "pattern" in edit and (edit.get("pattern") or "").strip():
        pt = edit["pattern"].strip()
        if pt != "none":
            try:
                re.compile(pt)
            except re.error as e:
                raise ValueError(f"pattern {pt!r}: not a valid regular expression ({e})")
        if (pt == "none") != (not spec.get("pattern")) or (pt != "none" and pt != spec.get("pattern")):
            out["pattern"] = pt
    # an option group's keys (what extraction returns) and captions (2026-10-07: captions the page reading got wrong
    # are fixed by hand): {key: {"key": new key, "caption": new caption, "" clears it}}, only what differs
    ws = spec.get("widgets") if isinstance(spec.get("widgets"), dict) else \
        (spec.get("options") if isinstance(spec.get("options"), dict) else {})     # a dropdown's options (2026-10-14)
    if isinstance(edit.get("options"), dict) and ws:
        got = {}
        for k, o in edit["options"].items():
            if k not in ws or not isinstance(o, dict):
                continue
            d = {}
            nk = (o.get("key") or "").strip()
            if nk and nk != k:
                if not _OPT_KEY.match(nk):
                    raise ValueError(f"option key {nk!r}: letters, digits, _ . - only")
                d["key"] = nk
            if "caption" in o and (o.get("caption") or "").strip() != (ws[k].get("caption") or ""):
                d["caption"] = (o.get("caption") or "").strip()
            if d:
                got[k] = d
        keys = [got.get(k, {}).get("key", k) for k in ws]
        if len(set(keys)) != len(keys):
            raise ValueError("two options would have the same key")
        if got:
            out["options"] = got
    return out or None


def edit_fields(fields: dict, edits: dict, renames: dict, now: str, record: str, by: Optional[str] = None,
                extra: Optional[dict] = None) -> dict:
    """The blueprint's fields with `edits` ({name: clean_edit output}) applied, in place, each edited field marked
    `x_petey_hand_edit` {when, from, to, record[, by], **extra[name]} (Claude's pass adds why and kind). `renames` is {name: new name} for every edited field.
    Shared by the review page's corrections and Claude's pass (`eval/claude_pass_apply.py`, by: claude)."""
    out = {}
    for n, spec in fields.items():
        if n in edits:
            e = edits[n]
            spec = dict(spec)
            before = {"name": n, "type": spec.get("type")}
            before.update(semantic_type=spec.get("semantic_type"), pattern=spec.get("pattern"))
            if e.get("identifiers"):            # the parts the name was printed from (membership stays as kept)
                keep = {k: v for k, v in (spec.get("x_petey_identifiers") or {}).items() if k == "grid"}
                before["identifiers"] = spec.get("x_petey_identifiers")
                spec["x_petey_identifiers"] = {**e["identifiers"], **keep}
            if "type" in e:
                spec["type"] = e["type"]
                if e["type"] != "string":
                    spec.pop("pattern", None)
                if e["type"] in ("boolean",) + _CHOICE:
                    spec.pop("semantic_type", None)
                if e["type"] not in _CHOICE:
                    spec.pop("values", None)
                elif not spec.get("values") and spec.get("widgets"):
                    spec["values"] = list(spec["widgets"])      # an option group: its keys (1_126 lost them)
            old_st = spec.get("semantic_type") if "semantic_type" in e else None
            for k in ("semantic_type", "pattern"):
                if k in e:
                    if e[k] == "none":
                        spec.pop(k, None)
                    else:
                        spec[k] = e[k]
            # a semantic type brings its pattern (Andrew, 2026-10-13: "the entire point of having them"); changed or
            # cleared, the old type's pattern goes with it. An explicit pattern in the edit wins.
            if "semantic_type" in e and "pattern" not in e:
                from petey.semantic_types import pattern_for
                if spec.get("pattern") and spec.get("pattern") == pattern_for(old_st):
                    spec.pop("pattern")
                if spec.get("type", "string") == "string" and pattern_for(spec.get("semantic_type")):
                    spec["pattern"] = pattern_for(spec.get("semantic_type"))
            if e.get("options"):
                where = "widgets" if spec.get("widgets") else "options"          # a group's boxes, or a dropdown's entries
                ws, renamed = {}, {}
                for k, w in (spec.get(where) or {}).items():
                    o, w = e["options"].get(k) or {}, dict(w)
                    if "caption" in o:
                        if o["caption"]:
                            w["caption"], w["x_petey_caption_source"] = o["caption"], by or "hand"
                        else:
                            w.pop("caption", None)
                            w.pop("x_petey_caption_source", None)
                    if where == "options" and o.get("key", k) != k and "stored" not in w:
                        w["stored"] = k                 # a dropdown entry renamed: the PDF still stores the old value
                    ws[o.get("key", k)] = w
                    renamed[k] = o.get("key", k)
                spec[where] = ws
                if spec.get("values"):
                    spec["values"] = [renamed.get(x, x) for x in spec["values"]]
                before["options"] = {k: ((fields[n][where].get(k) or {}).get("caption")) for k in e["options"]}
            spec["x_petey_hand_edit"] = {"when": now, "from": before,
                                         "to": {"name": renames[n], "type": spec.get("type"),
                                                "semantic_type": spec.get("semantic_type"), "pattern": spec.get("pattern"),
                                                **({"options": e["options"]} if e.get("options") else {})},
                                         "record": record, **({"by": by} if by else {}),
                                         **((extra or {}).get(n) or {})}
            out[renames[n]] = spec
        else:
            out[n] = spec
    # a name changed with no parts sent (typed in Review, a grid's rename, a chat edit): parts read from the new name,
    # so the two stay in step (petey/naming.sync_parts, 2026-10-26)
    from petey import naming
    naming.sync_parts(out, [renames[n] for n in edits if n in fields and renames.get(n, n) != n])
    return out
