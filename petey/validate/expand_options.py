"""Retype pass: rebuild option groups in committed blueprints from their blanks.

Before 2026-09-29 the emitter wrote a radio group as ONE widget (the union
box of its members) with `values` = the on-states, and a checkbox FIELD with
several kids (CMS-1500 insurance type) as one boolean on the first kid. A
person comparing form and blueprint could not see the options; a reader
with geometry could not find them; the CMS-1500 case lost six of seven.

The emitter now writes one field per group with a `widgets` map keyed by
on-state, each entry carrying the option's box, its on-state and its
printed caption (`petey/label/auto_label.py: option_widgets`,
`caption_options`). This pass brings existing blueprints to the same shape
without a model call: the blank's AcroForm layer says which paths are
groups and where each option sits; the XFA template (when present) says
what each option is called. Names and descriptions are left alone.

    venv/bin/python -m petey.validate.expand_options            # report
    venv/bin/python -m petey.validate.expand_options --apply    # write in place
    venv/bin/python -m petey.validate.expand_options --form cms1500 --apply
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import yaml

from petey.label import xfa as xfa_mod
import pymupdf

from petey.label.auto_label import caption_options, option_group_paths, option_widgets
from petey.label.captions import caption_options_from_page
from petey.locate.acroform import enumerate_widgets
from petey.paths import BLUEPRINTS
from petey.validate.retype import resolve_blank


def expand_blueprint(bp: dict, blank: Path) -> collections.Counter:
    changes: collections.Counter = collections.Counter()
    widgets, _dropped = enumerate_widgets(blank)
    grouped = option_group_paths(widgets)
    has_clusters = any(s.get("widgets") for s in (bp.get("fields") or {}).values())
    if not grouped and not has_clusters:
        return changes
    members_by_path: dict[str, list[dict]] = collections.defaultdict(list)
    for w in widgets:
        if w["path"] in grouped:
            members_by_path[w["path"]].append(w)
    try:
        tpl = xfa_mod.parse(blank)
    except Exception:
        tpl = None

    on_by_path = {w["path"]: w.get("on_state") for w in widgets if w.get("on_state")}
    for name, spec in (bp.get("fields") or {}).items():
        widget = spec.get("widget") or {}
        if not widget and spec.get("widgets"):
            widget = next(iter(spec["widgets"].values()))
        path = widget.get("path")
        if spec.get("widgets") and path and path not in grouped:
            # a labeler cluster: separate checkbox fields grouped by name;
            # give each option its on-state and a caption from it
            n_on = n_cap = 0
            for v, wb in spec["widgets"].items():
                st = on_by_path.get(wb.get("path"))
                if st and not wb.get("on_state"):
                    wb["on_state"] = st; n_on += 1
                st = wb.get("on_state")
                if st and not wb.get("caption") and not st.isdigit() and st.lower() not in ("on", "off", "yes", "no", "true", "false"):
                    wb["caption"] = st; n_cap += 1
            changes["cluster_on_state"] += n_on; changes["cluster_captions"] += n_cap
            continue
        if not path or path not in grouped:
            continue
        if spec.get("widgets"):
            # already per-option: refresh captions only (declared choices
            # re-derived with the current join guard, then the state rule)
            before = {k: b.get("caption") for k, b in spec["widgets"].items()}
            old_choices = spec.get("x_petey_xfa", {}).pop("choices", None)
            if old_choices and spec.get("description") == xfa_mod.choices_description(old_choices):
                # the description IS the old join's choice list, nothing
                # more; drop it and let the re-derivation (or the describe
                # pass) put back what holds. A reviewer's rewrite that kept
                # the source tag (526EZ branch of service) is left alone.
                spec.pop("description", None)
                spec.pop("x_petey_description_source", None)
            if tpl is not None:
                rec = tpl.lookup(path)
                if rec is not None and rec.kind == "excl":
                    probe = {"values": list(spec.get("values") or [])}
                    xfa_mod.apply_declared(probe, rec)
                    if probe.get("x_petey_xfa", {}).get("choices"):
                        spec.setdefault("x_petey_xfa", {})["choices"] = probe["x_petey_xfa"]["choices"]
                        if probe.get("description") and not spec.get("description"):
                            spec["description"] = probe["description"]
                            spec["x_petey_description_source"] = "xfa_choices"
            if spec.get("x_petey_xfa") == {}:
                spec.pop("x_petey_xfa")
            caption_options(spec)
            after = {k: b.get("caption") for k, b in spec["widgets"].items()}
            if after != before:
                changes["recaptioned_groups"] += 1
                changes["captions_added"] += sum(1 for k in after if after[k] and not before[k])
                changes["captions_removed"] += sum(1 for k in after if before[k] and not after[k])
                changes["captions_changed"] += sum(1 for k in after if before[k] and after[k] and before[k] != after[k])
            continue
        members = sorted(members_by_path[path], key=lambda w: (w["page"], w["id"]))
        states: list[str] = []
        for m in members:
            st = m.get("on_state")
            if st and st not in states:
                states.append(st)
        note = list(spec.get("x_petey_retype") or [])
        if len(states) <= 1:
            # one state drawn in several places: a boolean; keep the first box
            first = members[0]
            spec["widget"] = {"page": first["page"], "rect": first["rect"],
                              "widget_type": first["widget_type"], "path": path}
            spec["x_petey_appearances"] = len(members)
            note.append("option_group:appearances")
            changes["appearances"] += 1
        else:
            was = spec.get("type")
            spec["type"] = "category"
            spec["values"] = states
            spec.pop("widget", None)
            spec.pop("pattern", None)
            spec.pop("semantic_type", None)
            group = {"path": path, "true_widget_type": members[0]["widget_type"]}
            spec["widgets"] = option_widgets(members, group)
            if tpl is not None:
                rec = tpl.lookup(path)
                if rec is not None and rec.kind == "excl":
                    probe = {"values": list(states)}
                    xfa_mod.apply_declared(probe, rec)
                    if probe.get("x_petey_xfa", {}).get("choices"):
                        spec.setdefault("x_petey_xfa", {})["choices"] = probe["x_petey_xfa"]["choices"]
                    if probe.get("description") and not spec.get("description"):
                        spec["description"] = probe["description"]
                        spec["x_petey_description_source"] = "xfa_choices"
            caption_options(spec)
            # reorder keys for a readable file: type, values, description..., widgets last
            w = spec.pop("widgets")
            spec["widgets"] = w
            note.append(f"option_group:{was}->category[{len(states)}]")
            changes["boolean_to_group" if was == "boolean" else "single_widget_to_group"] += 1
            changes["options"] += len(states)
            changes["captioned"] += sum(1 for b in w.values() if b.get("caption"))
        spec["x_petey_retype"] = note

    # page-text captions for options still uncaptioned (a boolean group was
    # never created here, so this only ever adds)
    groups = [s["widgets"] for s in (bp.get("fields") or {}).values()
              if s.get("widgets") and any(b.get("on_state") and not b.get("caption") for b in s["widgets"].values())]
    if groups:
        doc = pymupdf.open(str(blank))
        try:
            rects: dict[int, list] = {}
            for s in (bp.get("fields") or {}).values():
                for b in list((s.get("widgets") or {}).values()):
                    rects.setdefault(b["page"], []).append(b["rect"])
            n = sum(caption_options_from_page(doc, ws, rects) for ws in groups)
        finally:
            doc.close()
        if n:
            changes["captions_from_page"] += n
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", default=None, help="one blueprint stem; default all")
    ap.add_argument("--apply", action="store_true", help="write changes in place (default: report only)")
    args = ap.parse_args()
    paths = ([BLUEPRINTS / f"{args.form}.bpt"] if args.form else sorted(BLUEPRINTS.glob("*.bpt")))
    total: collections.Counter = collections.Counter()
    per_form: dict[str, dict] = {}
    for p in paths:
        bp = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not bp or "fields" not in bp:
            continue
        blank = resolve_blank(bp)
        if not blank:
            total["no_blank"] += 1
            continue
        changes = expand_blueprint(bp, Path(blank))
        if not changes:
            continue
        per_form[p.stem] = dict(changes)
        total.update(changes)
        if args.apply:
            p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True,
                                        default_flow_style=False), encoding="utf-8")
    print(json.dumps({"forms_changed": len(per_form), "changes": dict(total),
                      "mode": "applied" if args.apply else "dry-run"}))
    for form, c in sorted(per_form.items(), key=lambda kv: -sum(kv[1].values()))[:15]:
        print(f"  {form:<28} {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
