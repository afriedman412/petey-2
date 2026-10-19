"""Field identifiers filled in from today's names (docs/PLAN_FIELD_IDENTIFIERS.md steps 2 and 3; the record format is
in docs/NAMING.md "Identifiers"). Each field's name is read once into its parts and the parts are written on a COPY
(runs/identifiers/<id>/<file>.bpt, the source untouched) as `x_petey_identifiers`:

    subject      the name's words once the iteration, suffix and part are taken out
    suffix       the last word when it is a standard suffix (standardize_names.SUFFIXES); an option group has none
    iteration    the field's number (or letter) in its series: for a cell of a kept grid or block group, the number
                 its row (or column) carries; outside one, a number that varies across otherwise identical names
                 (parent_1_nm / parent_2_nm). A lone number nothing varies against stays in the subject (line_6)
    grid / block_group + block   the kept grid or block group the field is a cell of (grid_check.listing: the
                 review page's lasting ids), from the active entries only
    part         the last word when the field is one box of a compound value (associate.compound_values)

Flag rather than guess: a name that cannot be read one way is written with what is certain and listed in the report
with why (no standard suffix; a numbered grid's cell without a number; a cell whose number is not its row's; two
numbers and no way to tell which iterates; in two kept grids). Series outside any kept grid or block group are
counted apart: they are what the kept list does not yet explain.

Then every name is printed back from its parts (`print_name`, today's order [subject]_[iteration]_[suffix]_[part])
and compared with the name it was read from: the differences are the renames the migration would make, listed by
kind. The other order Andrew leans to ([subject]_[suffix]_[iteration]_[part]) is counted too.

    PYTHONPATH=. venv/bin/python eval/field_identifiers.py je__acord_90_ny ...   [--tiers 1,2]  [--all]
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
import grid_naming as G  # noqa: E402
from associate import compound_values  # noqa: E402
from standardize_names import SUFFIXES, _is_group  # noqa: E402

OUT = RUNS / "identifiers"
KEY = "x_petey_identifiers"
ORDERS = {"standard": ("subject", "iteration", "suffix", "part"),          # docs/NAMING.md today
          "iteration_last": ("subject", "suffix", "iteration", "part")}    # Andrew's lean (2026-10-19)


def print_name(ident: dict, order: str = "standard") -> str:
    """The field name from its parts: the parts in order, absent ones skipped, joined by `_`."""
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


def _membership(bid: str, bp: dict) -> tuple[dict[str, dict], dict[str, str]]:
    """{field name: {grid | block_group, block?, expect: the number its line carries or None, keyed}} from the
    kept list's active grids and block groups, and {name: why} for fields in two of them."""
    out, twice = {}, {}
    for t in gc.listing(bid, bp):
        if t["status"] != "active":
            continue
        cells = t["grid"]
        keyed = G.keyed(cells)
        reading, _ = G.breaks(cells) if not keyed else ("keyed", [])
        num_axis = "row" if reading == "columns" else "col"
        expect = {}
        if not keyed:
            line = collections.defaultdict(collections.Counter)
            for c in cells:
                n = G._number(c["name"])
                if n is not None:
                    line[c[num_axis]][G._core(n)] += 1
            expect = {k: v.most_common(1)[0][0] for k, v in line.items() if v}
        totals = {c["name"] for c in cells} - {c["name"] for c in G.body(cells)}    # a last row of totals: not iterated
        for c in cells:
            m = {"block_group": t["id"], "block": c["row"]} if t["kind"] == "block" else {"grid": t["id"]}
            m["expect"], m["keyed"] = expect.get(c[num_axis]), keyed or c["name"] in totals
            if c["name"] in out:
                twice[c["name"]] = f"in {out[c['name']].get('grid') or out[c['name']].get('block_group')} and {t['id']}"
            else:
                out[c["name"]] = m
    return out, twice


def read(name: str, spec: dict, parts: dict[str, str], member: dict | None, series: dict) -> tuple[dict, list[str]]:
    """(identifiers, flags) for one field from its name and what is known about it."""
    group = _is_group(spec)
    toks, flags = name.split("_"), []
    ident: dict = {"subject": None, "suffix": None, "iteration": None, "part": None}
    if name in parts and not group:
        ident["part"] = toks[-1]
        toks = toks[:-1]
    if not group and toks and toks[-1] in SUFFIXES:
        ident["suffix"] = toks[-1]
        toks = toks[:-1]
        if not toks:
            flags.append("name is only a suffix")
    elif not group:
        flags.append("no standard suffix")
    its = _iter_positions(toks)
    pick = None
    if member:
        for k in ("grid", "block_group", "block"):
            if k in member:
                ident[k] = member[k]
        if member["keyed"]:
            pass                                    # rows named by role or kind: the key stays in the subject
        elif member["expect"] is None:
            flags.append("its row (or column) carries no number")
        else:
            hit = [i for i in its if G._core(toks[i]) == member["expect"]]
            if hit:
                pick = hit[-1]
            elif its:
                pick = its[-1]
                flags.append(f"number {toks[pick]} is not its row's (or column's) {member['expect']}")
            else:
                flags.append(f"unnumbered cell of a numbered grid (its line is {member['expect']})")
    else:
        full = name.split("_")
        vary = [i for i in _iter_positions(full) if len(series[(tuple(full[:i]), tuple(full[i + 1:]))]) > 1]
        vary = [i for i in vary if i < len(toks)]            # not the part, not the suffix
        if len(vary) == 1:
            pick = vary[0]
            flags.append("series outside any kept grid or block group")
        elif len(vary) > 1:
            flags.append(f"{len(vary)} numbers vary ({', '.join(toks[i] for i in vary)}): which one iterates?")
    if pick is not None:
        ident["iteration"] = toks[pick]
        toks = toks[:pick] + toks[pick + 1:]
    ident["subject"] = "_".join(toks)
    if not ident["subject"]:
        ident["subject"] = None                     # ssn_1: the suffix is all the name says (flagged above)
    return {k: v for k, v in ident.items() if v is not None}, flags


SOFT = ("series outside any kept grid or block group",)      # counted, not an error


def _kind(name: str, printed: str) -> str:
    """Why a printed name differs from the one it was read from."""
    a, b = name.split("_"), printed.split("_")
    if sorted(a) == sorted(b):
        return "same words, iteration moved next to the suffix"
    if set(b) < set(a):
        return "a word dropped (the subject was the suffix)"
    return "other"


def run(bid: str, paths: dict) -> dict:
    p = h.working_path(bid, paths)
    bp = h._load(p)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    parts = {n: part for cv in compound_values(fields) for part, n in cv["fields"].items()}
    member, twice = _membership(bid, bp)
    series = _series_index([n for n, s in fields.items() if not _is_group(s)])
    per_page: dict = collections.defaultdict(collections.Counter)
    flagged, soft, diffs = {}, {}, {}
    tot = collections.Counter()
    for n, s in fields.items():
        ident, flags = read(n, s, parts, member.get(n), series)
        if n in twice:
            flags.append(twice[n])
        s[KEY] = ident
        pg = (s.get("widget") or next(iter((s.get("widgets") or {}).values()), {}) or {}).get("page") or 0
        hard = [f for f in flags if f not in SOFT]
        per_page[pg]["fields"] += 1
        tot["fields"] += 1
        if "part" in ident:
            tot["parts"] += 1
        if "grid" in ident or "block_group" in ident:
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
        if any(f in SOFT for f in flags):
            soft[n] = ident["iteration"]
            per_page[pg]["series_outside_kept"] += 1
            tot["series_outside_kept"] += 1
        back = print_name(ident)
        if back != n:
            diffs[n] = {"printed": back, "kind": _kind(n, back), "flags": flags}
            per_page[pg]["differs"] += 1
            tot["differs"] += 1
            tot["differs: " + diffs[n]["kind"]] += 1
        if print_name(ident, "iteration_last") != n:
            tot["differs_iteration_last"] += 1
    bp[KEY + "_fill"] = {"when": time.strftime("%Y-%m-%d %H:%M:%S"), "record": "eval/field_identifiers.py",
                         "from": str(p), "flags": flagged, "series_outside_kept": soft, "printed_differently": diffs}
    d = OUT / bid
    d.mkdir(parents=True, exist_ok=True)
    (d / p.name).write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return {"bid": bid, "pages": {str(k): dict(v) for k, v in sorted(per_page.items())}, **tot,
            "flag_list": flagged, "series_list": soft, "diff_list": diffs}


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
              f"{g('in_kept'):4} in kept grids/blocks  {g('series_outside_kept'):4} series outside  {g('differs'):4} print differently"
              + (f"   [{i}/{len(ids)} {time.time() - t0:.0f}s]" if i % 25 == 0 else ""))
    f, p = tot["fields"], tot["pages"]
    print(f"\n{tot['forms']} forms, {p} pages, {f} fields")
    print(f"  clean {tot['clean']} ({tot['clean'] / max(1, f):.1%}); flagged {tot['flagged']} ({tot['flagged'] / max(1, f):.1%}, "
          f"{tot['flagged'] / max(1, p):.1f} per page)")
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k.startswith("why: "):
            print(f"    {v:6}  {k[5:]}")
    print(f"  in a kept grid or block group {tot['in_kept']}; with an iteration {tot['iterated']}; "
          f"series outside any kept grid or block group {tot['series_outside_kept']} ({tot['series_outside_kept'] / max(1, p):.1f} per page); "
          f"parts of compound values {tot['parts']}")
    print(f"  printed back: {f - tot['differs']} same, {tot['differs']} differ ({tot['differs'] / max(1, f):.1%}); "
          f"with the iteration last {tot['differs_iteration_last']} would differ")
    for k, v in sorted(tot.items(), key=lambda kv: -kv[1]):
        if k.startswith("differs: "):
            print(f"    {v:6}  {k[9:]}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "report.json").write_text(json.dumps({"totals": dict(tot), "forms": rows}, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
