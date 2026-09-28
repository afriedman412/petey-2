"""In-place, deterministic retyping of committed blueprints (tier 2).

Three narrow corrections, each visible in the library and each checkable
without a model. Nothing else is touched — names, rects and the types
another labeler set on purpose stay as they are.

  1. `pattern` on a non-string type is dropped (spec §5.6 forbids it; the
     emitter used to write the registry's canonical date shape onto
     `type: date` fields — 1,282 fields library-wide).
  2. A field whose NAME says it is a part — `_mm`, `_dd`, `_yyyy`, `_part1`,
     `_last_four` — but which is typed `date` / `number` / `integer` becomes
     a string with the part's pattern (`semantic_types` date_month, date_day,
     date_year, id_part).
  3. A `date` field whose WIDGET cannot hold a date — max length 1-4, or a
     box narrower than `NARROW_PT` — becomes a string with `^\\d{1,n}$`.
     The name may say "date" (`gulf_war_service_from_dt` on 526EZ holds
     "03"); the box says otherwise, and the box was drawn by the publisher.

Dry run by default; `--apply` writes. Every change is recorded under
`x_petey_retype` on the field so it can be found and reverted.

    venv/bin/python -m petey.validate.retype [--form vba21526ez] [--apply]
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path
from typing import Optional

import yaml

from petey.paths import BLUEPRINTS, SOURCE_PDFS
from petey.semantic_types import lookup
from petey.synth.local import widget_limits

PART_TYPES = {"date_month", "date_day", "date_year", "id_part"}
NARROW_PT = 28.0


def resolve_blank(bp: dict) -> Optional[Path]:
    src = bp.get("source_pdf")
    if not src:
        return None
    direct = SOURCE_PDFS / str(src)
    if direct.is_file():
        return direct
    hits = [h for h in SOURCE_PDFS.rglob(Path(str(src)).name)
            if "source_pdfs_old" not in h.parts and h.is_file()]
    return hits[0] if hits else None


def retype_blueprint(bp: dict, limits: dict[str, dict]) -> collections.Counter:
    changes: collections.Counter = collections.Counter()
    for name, spec in (bp.get("fields") or {}).items():
        ftype = spec.get("type", "string")
        note = []

        if "pattern" in spec and ftype != "string":
            spec.pop("pattern")
            note.append("pattern_dropped")
            changes["pattern_dropped"] += 1

        widget = spec.get("widget") or {}
        wt = widget.get("widget_type") or "text"
        if wt in ("checkbox", "radiobutton") or spec.get("widgets"):
            if note:
                spec["x_petey_retype"] = note
            continue

        st = lookup(name, widget_type=wt)
        if st is not None and st.name in PART_TYPES and ftype in ("date", "number", "integer"):
            spec["type"] = "string"
            spec["semantic_type"] = st.name
            if st.pattern:
                spec["pattern"] = st.pattern
            note.append(f"part_by_name:{st.name}")
            changes[f"part_by_name:{ftype}->string"] += 1
        elif ftype == "date":
            lim = limits.get(widget.get("path") or "") or {}
            maxlen = int(lim.get("maxlen") or 0)
            width = float(lim.get("width") or 0)
            if 0 < maxlen <= 4 or (width and width < NARROW_PT):
                n = maxlen if maxlen else 4
                spec["type"] = "string"
                spec.pop("semantic_type", None)
                spec["pattern"] = rf"^\d{{1,{n}}}$"
                note.append(f"narrow_widget:maxlen={maxlen},width={width:.0f}")
                changes["date_narrow_widget->string"] += 1
        if note:
            spec["x_petey_retype"] = note
    return changes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", default=None, help="one blueprint stem; default all")
    ap.add_argument("--apply", action="store_true", help="write changes (default: report only)")
    ap.add_argument("--out-dir", type=Path, default=None,
                    help="write retyped copies here instead of in place")
    args = ap.parse_args()
    paths = ([BLUEPRINTS / f"{args.form}.bpt"] if args.form
             else sorted(BLUEPRINTS.glob("*.bpt")))
    total: collections.Counter = collections.Counter()
    per_form: dict[str, dict] = {}
    for p in paths:
        bp = yaml.safe_load(p.read_text(encoding="utf-8"))
        if not bp or "fields" not in bp:
            continue
        blank = resolve_blank(bp)
        limits = widget_limits(blank) if blank else {}
        changes = retype_blueprint(bp, limits)
        if not changes:
            continue
        per_form[p.stem] = dict(changes)
        total.update(changes)
        if args.apply or args.out_dir:
            target = (args.out_dir / p.name) if args.out_dir else p
            if args.out_dir:
                args.out_dir.mkdir(parents=True, exist_ok=True)
            target.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True,
                                             default_flow_style=False), encoding="utf-8")
    print(json.dumps({"forms_changed": len(per_form), "changes": dict(total),
                      "mode": "applied" if (args.apply or args.out_dir) else "dry-run"}))
    for form, c in sorted(per_form.items(), key=lambda kv: -sum(kv[1].values()))[:12]:
        print(f"  {form:<24} {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
