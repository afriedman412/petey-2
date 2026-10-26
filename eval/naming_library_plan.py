"""The naming standard on the library (Andrew, 2026-10-24): every field's parts read from its name
(field_identifiers.read_form, the block-number rule) and its name printed from them (petey/naming.py). Nothing
written but the plan: runs/naming_2026-10-24/library_plan.json and library_renames.md.

    PYTHONPATH=. venv/bin/python eval/naming_library_plan.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from petey.validate import field_identifiers as FI  # noqa: E402

from petey import naming  # noqa: E402
from petey.paths import RUNS  # noqa: E402
from petey.validate import hand_review as h  # noqa: E402

OUT = RUNS / "naming_2026-10-24"


def plan_form(bid: str, paths: dict) -> dict:
    bp = h._load(h.working_path(bid, paths))
    got = FI.read_form(bid, bp)
    renames, flagged, idents = {}, {}, {}
    for name, (ident, flags) in got.items():
        real = [f for f in flags if not f.startswith("no standard suffix")]
        if real:
            flagged[name] = real
            continue
        idents[name] = ident
        new = naming.print_name(ident)
        if new != name:
            renames[name] = new
    taken = collections.Counter(renames.values())
    held = {o: n for o, n in renames.items() if taken[n] > 1 or (n in got and n not in renames)}
    for o, n in held.items():
        flagged[o] = [f"would become {n}, a name another field has or gets"]
        del renames[o]
    return {"renames": renames, "flagged": flagged, "identifiers": idents}


def main() -> int:
    paths = h.blueprint_paths()
    res = {bid: plan_form(bid, paths) for bid in sorted(paths) if bid.startswith("lib__")}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "library_plan.json").write_text(json.dumps(res, indent=1))
    kind = lambda o, n: ("short suffix" if naming.short_suffix(o) == n else         # noqa: E731
                         "number after the suffix" if sorted(o.split("_")) == sorted(n.split("_")) else "both")
    k = collections.Counter(kind(o, n) for p in res.values() for o, n in p["renames"].items())
    lines = ["# The naming standard on the library: renames (dry run, 2026-10-24)", "",
             f"{len(res)} forms, {sum(len(p['identifiers']) + len(p['flagged']) for p in res.values())} fields: "
             f"{sum(len(p['renames']) for p in res.values())} renames ({', '.join(f'{v} {k_}' for k_, v in k.most_common())}), "
             f"{sum(len(p['flagged']) for p in res.values())} flagged (left as they are), the rest unchanged.", "",
             "Standard: `[block subject]_[block iteration]_[field subject]_[suffix]_[field iteration]_[part]` "
             "(docs/NAMING.md). A number with field words after it is the block's and stays; a number directly "
             "before the suffix is the field's and moves after it; a line label (line_14, row_3) stays with its word.", ""]
    for bid, p in res.items():
        if not p["renames"] and not p["flagged"]:
            continue
        lines.append(f"## [{bid}](http://localhost:5005/#review/{bid}): {len(p['renames'])} renames, {len(p['flagged'])} flagged")
        for o, n in sorted(p["renames"].items()):
            lines.append(f"- `{o}` -> `{n}`")
        for o, why in sorted(p["flagged"].items()):
            lines.append(f"- flagged `{o}`: {'; '.join(why)}")
        lines.append("")
    (OUT / "library_renames.md").write_text("\n".join(lines))
    print(lines[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
