"""Dropdowns in existing blueprints get their kind and their choice list (Andrew, 2026-10-07: hard-code dropdowns and
their options, even where they only emit strings).

Until 2026-10-07 `enumerate_widgets` read a combobox or list box as a text box and dropped its choices, so the labeler
typed every dropdown as free text (ProofofPriorServiceRE `employment_type`: Full-time / Part-time / Extra help). New
labels now carry them (`auto_label.dropdown_spec`); this writes the same into the blueprints already made: the widget's
`widget_type` becomes `combobox` / `listbox`, and the field takes the choices as `values`, typed `category` (closed
list), `multi_category` (a list box that takes several) or `string` (a combobox that also takes typed text). A field
that already has values (an XFA choice list) keeps them and only gets the widget kind. Marker `dropdown` in
`x_petey_retype`.

The file changes, so the review records that matched it move to the new sha and the page check's verdicts on the
changed fields are re-keyed to the new definitions, as `money_retype` does.

    PYTHONPATH=. venv/bin/python -m petey.validate.dropdowns            # what would change
    PYTHONPATH=. venv/bin/python -m petey.validate.dropdowns --write
"""
from __future__ import annotations

import argparse
import collections
import json

import yaml

from petey.label.auto_label import dropdown_spec
from petey.locate.acroform import enumerate_widgets
from petey.validate import field_ids, hand_review
from petey.validate.money_retype import _rekey
from petey.validate.retype import resolve_blank

KINDS = ("combobox", "listbox")


def apply(bp: dict, by_path: dict[str, dict]) -> dict[str, str]:
    """Set the dropdown fields of one blueprint; {field: what changed}."""
    out = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("widgets"):
            continue
        w = spec.get("widget") or {}
        d = by_path.get(w.get("path") or "")
        if d is None:
            continue
        what = []
        if w.get("widget_type") != d["widget_type"]:
            w["widget_type"] = d["widget_type"]
            what.append("kind")
        if d.get("choices") and not spec.get("values"):
            before = spec.get("type") or "string"
            dropdown_spec(spec, d)
            what.append(f"values ({len(spec['values'])})" + (f", {before} -> {spec['type']}" if spec["type"] != before else ""))
        if what:
            spec["x_petey_retype"] = list(spec.get("x_petey_retype") or []) + ["dropdown"]
            out[name] = "; ".join(what)
    return out


def run(write: bool) -> dict:
    from petey.validate.page_check import spec_hash
    out: collections.Counter = collections.Counter()
    forms = {}
    for bid, p in hand_review.blueprint_paths().items():
        bp = hand_review._load(p)
        blank = resolve_blank(bp)
        if not blank or not blank.exists():
            continue
        widgets, _ = enumerate_widgets(blank)
        by_path = {}
        for w in widgets:
            if w["widget_type"] in KINDS:
                by_path.setdefault(w["path"], w)
        if not by_path:
            continue
        old = {n: spec_hash(s) for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
        changed = apply(bp, by_path)
        if not changed:
            continue
        forms[bid] = len(changed)
        out["fields"] += len(changed)
        out["blueprints"] += 1
        for what in changed.values():
            out["values set" if "values" in what else "kind only"] += 1
        if write:
            sha = hand_review._sha(p)
            p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                         encoding="utf-8")
            for t in field_ids._rehash(bid, sha, hand_review._sha(p)):
                out[f"records rehashed: {t}"] += 1
            moved = {n: (old[n], spec_hash(bp["fields"][n])) for n in changed}
            out["page-check verdicts re-keyed"] += _rekey(bp, moved)
    return {"changed": dict(out), "per blueprint": dict(sorted(forms.items(), key=lambda kv: -kv[1]))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true")
    print(json.dumps(run(ap.parse_args().write), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
