"""Field identifiers filled in from today's names (docs/PLAN_FIELD_IDENTIFIERS.md steps 2 and 3; the record format is
in docs/NAMING.md "Identifiers"). Each field's name is read once into its parts and the parts are written on a COPY
(runs/identifiers/<id>/<file>.bpt, the source untouched) as `x_petey_identifiers`:

    subject      the name's words once the iteration, suffix and part are taken out
    suffix       the last word when it is a standard suffix (standardize_names.SUFFIXES); an option group has none
    iteration    the field's number (or letter) in its series, the Nth field holding this information (Andrew,
                 2026-10-19): for a cell of a kept grid, the number its row (or column) carries;
                 elsewhere, a number that varies across otherwise identical names (parent_1_nm / parent_2_nm). A
                 lone number nothing varies against stays in the subject (line_6). No membership is needed
    grid         the kept grid the field is a cell of (grid_check.listing: the review page's lasting ids), from the
                 active entries only (block groups, and their block_group / block keys, gone 2026-10-22)
    part         the last word when the field is one box of a compound value (associate.compound_values)

Flag rather than guess: a name that cannot be read one way is written with what is certain and listed in the report
with why (no standard suffix; a numbered grid's cell without a number; a cell whose number is not its row's; two
numbers and no way to tell which iterates; in two kept grids).

Then every name is printed back from its parts (`print_name`): in the order the names were written in (today's
standard, [subject]_[iteration]_[suffix]_[part]) to show the reading is faithful, and in the decided order
([subject]_[suffix]_[iteration]_[part], the iteration last; Andrew, 2026-10-19), whose differences are the renames
the migration makes.

    PYTHONPATH=. venv/bin/python -m petey.validate.field_identifiers je__acord_90_ny ...   [--tiers 1,2]  [--all]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

import yaml

from petey.paths import RUNS
from petey.validate import grid_check as gc, hand_review as h
from petey.validate import grid_naming as G  # noqa: E402
from petey.validate.associate import compound_values  # noqa: E402
from petey.validate.standardize_names import SUFFIXES, _is_group  # noqa: E402

OUT = RUNS / "identifiers"
KEY = "x_petey_identifiers"
# a block's prefix and number lead (Andrew, 2026-10-22: "the validated names should be the guide -- [block prefix]_
# [block iteration]_[field subject]_[field iteration] ... child_2_ssn_1 would be the first ssn field of the second
# 'child' block"); a field in no block has neither and prints as decided 2026-10-19, its own iteration last
ORDERS = {"iteration_last": ("block_prefix", "block_iteration", "subject", "suffix", "iteration", "part"),
          "old": ("block_prefix", "block_iteration", "subject", "iteration", "suffix", "part")}   # docs/NAMING.md before
IDENT_KEYS = ORDERS["iteration_last"]                                                      # identifiers
ORDER = "iteration_last"


def print_name(ident: dict, order: str = ORDER) -> str:
    """The field name from its parts: the parts in order, absent ones skipped, joined by `_`; the standard's order and
    rules (petey/naming.py, 2026-10-24) unless another order is asked for."""
    if order == ORDER:
        from petey import naming
        return naming.print_name(ident)
    return "_".join(str(ident[k]) for k in ORDERS[order] if ident.get(k) not in (None, ""))


def _iter_positions(toks: list[str]) -> list[int]:
    return [i for i, t in enumerate(toks) if G.LINE.match(t) or (len(t) == 1 and t.isalpha() and i > 0)]


def _series_index(names: list[str]) -> dict[tuple, set]:
    """{(tokens before, tokens after): {values}} for every number or letter position of every name: a position
    is a series when another name has the same words around it and another value there."""
    ix = collections.defaultdict(set)
    for n in names:
        toks = n.split("_")
        for i in _iter_positions(toks):
            ix[(tuple(toks[:i]), tuple(toks[i + 1:]))].add(toks[i])
    return ix


def _kind(name: str, printed: str) -> str:
    """Why a printed name differs from the one it was read from."""
    a, b = name.split("_"), printed.split("_")
    if sorted(a) == sorted(b):
        return "same words, iteration moved next to the suffix"
    if set(b) < set(a):
        return "a word dropped (the subject was the suffix)"
    return "other"


def read_form(bid: str, bp: dict) -> dict[str, tuple[dict, list[str]]]:
    """{field name: (identifiers, flags)} for every field of a blueprint: the stored record (`x_petey_identifiers`,
    once the person or a pass wrote it), its grid membership refreshed, else the name read with the form's context
    (`read_parts`, petey/naming.read_name). What the review page shows under the field name."""
    from petey import naming
    got = read_parts(bid, bp)
    out = {}
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        stored = s.get(KEY) if isinstance(s.get(KEY), dict) else None
        if stored:
            ident = {k: v for k, v in stored.items() if k in IDENT_KEYS and v not in (None, "")}
            if got[n][0].get("grid"):
                ident["grid"] = got[n][0]["grid"]
            flags = [] if naming.print_name(ident) == n else [f"the name is not what its parts print "
                                                              f"({naming.print_name(ident)})"]
            out[n] = (ident, flags)
        else:
            out[n] = got[n]
    return out


def run(bid: str, paths: dict) -> dict:
    p = h.working_path(bid, paths)
    bp = h._load(p)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    got = read_form(bid, bp)
    per_page: dict = collections.defaultdict(collections.Counter)
    flagged, diffs = {}, {}
    tot = collections.Counter()
    for n, s in fields.items():
        ident, flags = got[n]
        s[KEY] = ident
        pg = (s.get("widget") or next(iter((s.get("widgets") or {}).values()), {}) or {}).get("page") or 0
        hard = flags
        per_page[pg]["fields"] += 1
        tot["fields"] += 1
        if "part" in ident:
            tot["parts"] += 1
        if "grid" in ident:
            tot["in_kept"] += 1
            per_page[pg]["in_kept"] += 1
        if "iteration" in ident:
            tot["iterated"] += 1
        if hard:
            flagged[n] = hard
            per_page[pg]["flagged"] += 1
            tot["flagged"] += 1
            for f in hard:
                tot["why: " + re.sub(r"\d+[a-z]?|p\d+-(?:T|BG)\d+", "N", f)] += 1
        else:
            tot["clean"] += 1
            per_page[pg]["clean"] += 1
        back = print_name(ident, "old")
        if back != n:
            tot["old_order_differs"] += 1
            tot["old_order_differs: " + _kind(n, back)] += 1
        new = print_name(ident)
        if new != n:
            diffs[n] = {"printed": new, "flags": flags}
            per_page[pg]["renamed"] += 1
            tot["renamed"] += 1
    bp[KEY + "_fill"] = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "record": "petey/validate/field_identifiers.py",
                         "from": str(p), "order": ORDER, "flags": flagged, "renames": diffs}
    d = OUT / bid
    d.mkdir(parents=True, exist_ok=True)
    (d / p.name).write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return {"bid": bid, "pages": {str(k): dict(v) for k, v in sorted(per_page.items())}, **tot,
            "flag_list": flagged, "renames": diffs}


def tiers(paths: dict, want: set[str]) -> list[str]:
    out = []
    for bid, p in paths.items():
        if bid.startswith("je__"):
            bp = h._load(h.working_path(bid, paths))
            if h.LAUNCH_TIERS.get(Path(str(bp.get("source_pdf") or "")).name) in want:
                out.append(bid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--tiers", help="launch tiers to run (1,2)")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    paths = h.blueprint_paths()
    ids = args.ids + (tiers(paths, set(args.tiers.split(","))) if args.tiers else []) + (list(paths) if args.all else [])
    rows, tot, t0 = [], collections.Counter(), time.time()
    for i, bid in enumerate(ids, 1):
        r = run(bid, paths)
        rows.append(r)
        tot.update({k: v for k, v in r.items() if isinstance(v, int)})
        tot["forms"] += 1
        tot["pages"] += len(r["pages"])
        g = lambda k: r.get(k, 0)  # noqa: E731
        print(f"{bid:34} {g('fields'):5} fields  {g('clean'):5} clean  {g('flagged'):4} flagged  "
              f"{g('iterated'):4} iterated  {g('in_kept'):4} in kept grids/blocks  {g('renamed'):4} renamed"
              + (f"   [{i}/{len(ids)} {time.time() - t0:.0f}s]" if i % 25 == 0 else ""))
    f, p = tot["fields"], tot["pages"]
    print(f"\n{tot['forms']} forms, {p} pages, {f} fields")
    print(f"  clean {tot['clean']} ({tot['clean'] / max(1, f):.1%}); flagged {tot['flagged']} ({tot['flagged'] / max(1, f):.1%}, "
          f"{tot['flagged'] / max(1, p):.1f} per page)")
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k.startswith("why: "):
            print(f"    {v:6}  {k[5:]}")
    print(f"  with an iteration {tot['iterated']}; in a kept grid {tot['in_kept']}; "
          f"parts of compound values {tot['parts']}")
    print(f"  printed back in the old order: {f - tot['old_order_differs']} same, {tot['old_order_differs']} differ "
          f"({tot['old_order_differs'] / max(1, f):.1%})")
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k.startswith("old_order_differs: "):
            print(f"    {v:6}  {k[19:]}")
    print(f"  printed in the decided order ({ORDER}): {tot['renamed']} renames ({tot['renamed'] / max(1, f):.1%})")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps({"totals": dict(tot), "forms": rows}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())


def context(bid: str, bp: dict) -> tuple[dict, dict]:
    """({field code: (block prefix, block iteration)}, {field name: (line identifier, keyed, grid id)}): what the form's
    records say about each field (2026-10-26, one parts reader): its block from the block types (block_types.
    block_parts: what the person set, else what the block's parts or names say), its grid line from the active grids
    read by identifiers (grid_naming.identify, through _Frame's sure reading)."""
    from petey.validate import block_types as bt
    blocks, lines = {}, {}
    rec = gc.load_set(bid)
    for t in rec.get("types") or []:
        try:
            parts = bt.block_parts(bp, t)
        except Exception:
            continue
        for b in t["blocks"]:
            pi = parts.get(bt._bid(b)) or {}
            if pi.get("prefix"):
                for c in b:
                    if c:
                        blocks[str(c)] = (pi["prefix"], pi.get("iteration"))
    for t in gc.listing(bid, bp):
        if t["status"] != "active":
            continue
        g = G.read_as_checked(t["grid"])
        R = G._Frame(g).ident
        if not R["ids"]:
            continue
        keyed = any(G._count_key(v) is None for v in R["ids"].values())
        for c in G.body(g):
            if c[R["num_axis"]] in R["ids"] and c["name"] not in lines:
                lines[c["name"]] = (R["ids"][c[R["num_axis"]]], keyed, t["id"])
    return blocks, lines


def read_parts(bid: str, bp: dict) -> dict[str, tuple[dict, list[str]]]:
    """{field name: (parts, flags)} for every field, read in the standard's order with the form's context
    (`context`, petey/naming.read_name), whatever is stored: the reading the stored parts are checked against."""
    from petey import naming
    blocks, lines = context(bid, bp)
    # names alike but for one number inside (other_coverage_1_limit_amt, other_coverage_2_limit_amt): that number
    # counts, as a grid line's does (`_series_index`)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    series = _series_index([n for n, s in fields.items() if not _is_group(s)])
    for n, s in fields.items():
        if n in lines or _is_group(s):
            continue
        toks = n.split("_")
        vary = [i for i in _iter_positions(toks) if 0 < i < len(toks) - 1
                and len(series[(tuple(toks[:i]), tuple(toks[i + 1:]))]) > 1]
        if len(vary) == 1:
            lines[n] = (toks[vary[0]], False, None)
    parts_of = {f: part for cv in compound_values(fields) for part, f in cv["fields"].items()}
    out = {}
    for n, s in fields.items():
        ln = lines.get(n)
        parts, flags = naming.read_name(n, s, blocks.get(str(s.get("x_petey_id"))), ln[0] if ln else None,
                                        bool(ln and ln[1]), parts_of.get(n))
        if ln and ln[2]:
            parts["grid"] = ln[2]
        out[n] = (parts, flags)
    return out
