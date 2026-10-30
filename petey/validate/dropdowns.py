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

Options (Andrew, 2026-10-14: "we should have separate formatting for dropdowns, the options should appear like group
options"): a dropdown's entries become `options: {key: {caption, stored}}`, as an option group's boxes carry a key and
a caption. The key is what extraction returns, the caption what the filer sees in the list, `stored` (only where it
differs from the key) what the PDF writes when that entry is picked. `values` is the list of keys. Most lists store
their codes (key = stored, caption = the full name: AB / Alberta); some store an index (CBP 7501 countries: 0 =
Afghanistan; key = the caption as a slug) or codes shifted by a blank first entry (CRA NR4 box 11: code 1 stored as 2;
key = the shown code). The list's empty entry (a blank label, "Select one") is no option and is dropped. The
extractor maps a stored value back to its key (`petey.extract`).

    PYTHONPATH=. venv/bin/python -m petey.validate.dropdowns --options je__cra-t4 ...   # into the working copies
"""
from __future__ import annotations

import argparse
import collections
import json
import re

import yaml

from petey.label.auto_label import dropdown_spec
from petey.locate.acroform import enumerate_widgets
from petey.validate import field_ids, hand_review
from petey.validate.money_retype import _rekey
from petey.validate.retype import resolve_blank

KINDS = ("combobox", "listbox")


def labels_of(spec: dict, template=None) -> dict[str, str]:
    """{stored value: shown label} for a dropdown: the XFA labels the blueprint kept, the AcroForm display texts, or
    the blank's XFA template (`template`, `petey.label.xfa.parse`)."""
    lab = ((spec.get("x_petey_xfa") or {}).get("labels")) or spec.get("x_petey_choice_labels") or {}
    path = (spec.get("widget") or {}).get("path")
    if not lab and template is not None and path:
        f = template.lookup(path)
        if f and f.items and len(f.item_labels) == len(f.items):
            lab = dict(zip(f.items, f.item_labels))
    return {str(k): str(v) for k, v in lab.items()}


def _slug(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()     # Español -> Espanol
    return re.sub(r"_+", "_", re.sub(r"[^a-z0-9]+", "_", s.lower())).strip("_") or "option"


def to_options(spec: dict, labels: dict[str, str]) -> tuple[dict, list[str]]:
    """(options {key: {caption[, stored]}}, the stored values dropped as the list's empty entry)."""
    from petey.label.xfa import is_blank_choice
    vals = [str(v) for v in spec.get("values") or []]
    pairs, dropped = [], []
    for v in vals:
        shown = labels.get(v, v) if labels else v
        if not v.strip() or is_blank_choice(shown):
            dropped.append(v)
        else:
            pairs.append((v, str(shown).strip()))
    stored = [v for v, _ in pairs]
    digits = bool(stored) and all(v.isdigit() for v in stored)
    index = digits and bool(labels) and not all(c.isdigit() for _, c in pairs)
    shifted = digits and bool(labels) and all(c.isdigit() for _, c in pairs) and any(c != v for v, c in pairs)
    opts = {}
    for v, cap in pairs:
        key = _slug(cap) if index else cap if shifted else v
        base, i = key, 2
        while key in opts:
            key, i = f"{base}_{i}", i + 1
        opts[key] = {"caption": cap, **({"stored": v} if key != v else {})}
    return opts, dropped


def options_into_working(bid: str) -> list[str]:
    """Options on every dropdown of one blueprint, written into its review-page working copy; the change lines."""
    from petey.label import xfa
    from petey.validate import draft
    from petey.validate.page_check import spec_hash
    real = hand_review.blueprint_paths()[bid]
    p = draft.ensure(bid, real)
    bp = hand_review._load(p)
    blank = resolve_blank(bp)
    t = None
    try:
        t = xfa.parse(blank) if blank and blank.exists() else None
    except Exception:                       # no XFA template: the AcroForm display texts the blueprint kept, if any
        t = None
    lines, moved = [], {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("widgets") or not spec.get("values") or spec.get("options"):
            continue
        if (spec.get("widget") or {}).get("widget_type") not in KINDS:
            continue
        old = spec_hash(spec)
        opts, dropped = to_options(spec, labels_of(spec, t))
        spec["options"] = opts
        spec["values"] = list(opts)
        spec["x_petey_retype"] = list(spec.get("x_petey_retype") or []) + ["dropdown_options"]
        moved[name] = (old, spec_hash(spec))
        lines.append(f"{name}: {len(opts)} dropdown options" + (f", the empty entry {dropped} dropped" if dropped else "")
                     + (" (stored values differ from the keys)" if any("stored" in o for o in opts.values()) else ""))
    if lines:
        before = hand_review._sha(p)
        p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        _rekey(bp, moved)
        draft.follow(bid, before, hand_review._sha(p))
        draft.log(bid, "claude", lines)
    return lines


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
    ap.add_argument("--options", nargs="+", metavar="ID", help="options on these blueprints' dropdowns (working copies)")
    args = ap.parse_args()
    if args.options:
        for bid in args.options:
            lines = options_into_working(bid)
            print(f"{bid}: {len(lines)} dropdowns")
            for ln in lines:
                print("   " + ln)
        return 0
    print(json.dumps(run(args.write), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
