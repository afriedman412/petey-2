"""Associated fields on standardized names (Andrew, 2026-10-14: a GROUP is an option group; ASSOCIATED fields make an
ENTITY, fields about one thing, or a COMPOUND VALUE, one value in several boxes). Read from the names that
`eval/standardize_names.py` writes ([description]_[iteration]_[suffix]_[part], docs/NAMING.md) and from where the boxes
sit; no model.

    compound value   the boxes whose names are the same up to and including the suffix, with a part after it:
                     dob_dt_month / _day / _yr, telephone_nbr_area / _prefix / _line, ssn_1 / _2 / _3, a paragraph
                     over numbered lines (summary_txt_1 .. _6). A closed list of kinds (KINDS), each with a `join`
                     template for downstream parsing.
    entity           fields about one thing: the name prefix several fields on a page share, an instance prefix first
                     (premises_1_*, parent_1_*). Not when the prefix holds a preposition ("date of" names an
                     attribute, not a thing: date_of_marriage_*) or when the members do not sit together (more other fields inside their block than members:
                     intend_to_* on two separate questions). A compound value counts as one member.
                     Rows numbered before the suffix are instances too (`numbered_rows`): fields that share a stem
                     and the same number (other_insurance_line_of_business_1_txt, other_insurance_policy_1_nbr ->
                     other_insurance_1).
    repeat           entities that are instances of one thing: the same base with a number or letter (parent_1 /
                     parent_2, premises_1 .. _4) and mostly the same attributes.

Written into a COPY (runs/associations/<id>[__standardized]/<file>.bpt, the source untouched) as
`x_petey_associations`, a list of {name, kind, page, fields | of, kind_of_value, join}.

    PYTHONPATH=. venv/bin/python eval/associate.py --standardized --all-validated je__ds11
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml

from petey.paths import RUNS
from petey.validate import hand_review as h

sys.path.insert(0, str(Path(__file__).resolve().parent))
from standardize_names import SUFFIXES  # noqa: E402

OUT = RUNS / "associations"

# compound value kinds by suffix and parts: {kind: (suffix, the part words or None for numbers, join template)}
KINDS = {
    "date": ("dt", ("month", "day", "yr"), "{month}/{day}/{yr}"),
    "phone": ("nbr", ("area", "prefix", "line", "local"), "{area}-{prefix}-{line}"),
    "money": ("amt", ("dollars", "cents"), "{dollars}.{cents}"),
    "ssn": ("ssn", None, "-"),
    "ein": ("ein", None, "-"),
    "zip": ("cd", None, "-"),
    "lines": ("txt", None, "\n"),
    "digits": ("qty", None, ""),
}
PREPOSITIONS = {"of", "to", "for", "in", "on", "by", "from", "with", "at"}
STRUCTURE = {"part", "page", "section", "item", "line", "box", "q", "question", "column", "col", "p"}   # part_2: the form's
ATTR = set("""name nm first middle last full given family city state zip country email phone telephone address line
street unit apt suite nbr num number dt date dob birth place sex gender height hair eye color occupation type txt ind
cd code amt status id other additional recent has ever lost signature title""".split())


def _box(spec: dict):
    w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
    return (w or {}).get("page"), (w or {}).get("rect") or [0, 0, 0, 0]


def compound_values(fields: dict) -> list[dict]:
    by = collections.defaultdict(dict)
    for n, s in fields.items():
        if not isinstance(s, dict) or s.get("widgets"):
            continue
        t = n.split("_")
        if len(t) < 2 or t[-2] not in SUFFIXES:              # ssn_1: the name can be the suffix and the part
            continue
        suf, part = t[-2], t[-1]
        kind = next((k for k, (ks, words, _) in KINDS.items()
                     if ks == suf and ((words and part in words) or (not words and part.isdigit()))), None)
        if kind == "zip" and "zip" not in t:
            kind = None
        if kind:
            by[("_".join(t[:-1]), kind, _box(s)[0])][part] = n
    out = []
    for (stem, kind, pg), parts in by.items():
        if len(parts) < 2:
            continue
        words, tmpl = KINDS[kind][1], KINDS[kind][2]
        if words:
            order = [w for w in words if w in parts]
            if kind == "phone" and "local" in parts:
                join = "{area}-{local}"
            else:
                join = tmpl if all(w in parts for w in re.findall(r"{(\w+)}", tmpl)) else \
                    {"date": "/", "money": ".", "phone": "-"}[kind].join("{" + w + "}" for w in order)
        else:
            order = sorted(parts, key=int)
            join = tmpl.join("{" + p + "}" for p in order)
        out.append({"name": stem, "kind": "compound_value", "kind_of_value": kind, "page": pg,
                    "fields": {p: parts[p] for p in order}, "join": join})
    return out


def _split_index(prefix: str):
    """parent_1 -> ('parent', '1'); other_name_a -> ('other_name', 'a'); spouse -> ('spouse', None)."""
    m = re.match(r"^(.*?)_(\d+|[a-z])$", prefix)
    return (m[1], m[2]) if m and m[1] else (prefix, None)


def _together(members: list[str], others: list[str], fields: dict) -> bool:
    """The members sit together: no more other fields inside their block (the union of their boxes) than members."""
    rs = [_box(fields[n])[1] for n in members]
    x0, y0, x1, y1 = min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)
    inside = sum(1 for o in others for r in [_box(fields[o])[1]]
                 if x0 - 1 <= (r[0] + r[2]) / 2 <= x1 + 1 and y0 - 1 <= (r[1] + r[3]) / 2 <= y1 + 1)
    return inside <= len(members)


def numbered_rows(units: dict) -> dict[str, str]:
    """{unit: instance name} for rows numbered before the suffix ([description]_[iteration]_[suffix], Andrew
    2026-10-14): other_insurance_line_of_business_1_txt and other_insurance_policy_1_nbr share the stem
    other_insurance and the number 1, so both are instance other_insurance_1. The stem is the longest start the
    numbered names share across at least two numbers, the shortest that says more than an attribute word."""
    num = {}
    for u, (pg, toks, _) in units.items():
        ds = [i for i, t in enumerate(toks) if t.isdigit()]
        if len(ds) == 1 and 0 < ds[0] < len(toks) - 1 and toks[ds[0] - 1] not in STRUCTURE:
            num[u] = (pg, toks[:ds[0]], toks[ds[0]])
    out = {}
    by_page = collections.defaultdict(list)
    for u, (pg, pre, n) in num.items():
        by_page[pg].append((u, pre, n))
    for pg, items in by_page.items():
        for u, pre, n in items:
            # the shortest start of `pre` that names a thing (not only an attribute word), shared with a
            # differently-described field of the same number and with a field under another number: ACORD 125's loss
            # rows are loss_occurrence_1_dt, loss_claim_1_dt, loss_amount_paid_1_amt -> loss_1, not loss_amount_1
            best = None
            for k in range(1, len(pre) + 1):
                stem = pre[:k]
                same_n = [x for x in items if x[2] == n and x[1][:k] == stem and x[0] != u]
                other_n = [x for x in items if x[2] != n and x[1][:k] == stem]
                if same_n and other_n and not set(stem) <= ATTR:
                    best = stem
                    break
            if best:
                out[u] = (tuple(best), n)
    # each instance is named for all its members share (attachment_other_1, not attachment_1)
    named = {}
    groups = collections.defaultdict(list)
    for u, key in out.items():
        groups[key].append(num[u][1])
    for u, key in out.items():
        pres = groups[key]
        common = []
        for i in range(min(len(x) for x in pres)):
            if len({x[i] for x in pres}) > 1:
                break
            common.append(pres[0][i])
        named[u] = "_".join(common or list(key[0])) + "_" + key[1]
    return named


def entities(fields: dict, values: list[dict]) -> list[dict]:
    member = {f: v["name"] for v in values for f in v["fields"].values()}     # a compound value's boxes -> its stem
    units = {}
    for n, s in fields.items():
        if isinstance(s, dict):
            u = member.get(n, n)
            units.setdefault(u, (_box(s)[0], u.split("_"), n))
    counts = collections.Counter()
    for u, (pg, toks, _) in units.items():
        for k in range(1, min(5, len(toks))):
            counts[(pg, "_".join(toks[:k]))] += 1
    out = collections.defaultdict(list)
    rows = numbered_rows(units)
    for u, inst in rows.items():
        out[(units[u][0], inst)].append(u)
    for u, (pg, toks, _) in units.items():
        if u in rows:
            continue
        best = None
        for k in range(1, min(5, len(toks))):
            pre = "_".join(toks[:k])
            if counts[(pg, pre)] < 2 or PREPOSITIONS & set(toks[:k]):
                continue                          # "date of …", "country of …" names an attribute, not a thing
            if k == 1 and set(re.split(r"_|\d", pre)) <= ATTR | {""}:
                continue                          # one word that only names an attribute (first_, city_)
            if set(t for t in toks[:k] if not t.isdigit()) <= STRUCTURE:
                continue                          # part_, part_2_: the form's structure names no thing
            if re.fullmatch(r"\d+", toks[k - 1]) and k > 1 and toks[k - 2] in STRUCTURE:
                continue                          # part_2, line_3: the form's own structure, not an instance
            if re.fullmatch(r"\d+", toks[k - 1]):
                best = pre                        # an instance prefix (premises_1) wins over a longer shared one
                break
            best = pre
        if best:
            out[(pg, best)].append(u)
    ents = []
    for (pg, pre), us in out.items():
        if len(us) < 2:
            continue
        fs = sorted(f for u in us for f in ([f for f, m in member.items() if m == u] or [u]))
        others = [n for n, s in fields.items() if isinstance(s, dict) and _box(s)[0] == pg and n not in fs]
        if not _together(fs, others, fields):
            continue
        ents.append({"name": pre, "kind": "entity", "page": pg, "units": sorted(us), "fields": fs})
    return sorted(ents, key=lambda e: (e["page"] or 0, e["name"]))


def repeats(ents: list[dict]) -> list[dict]:
    by = collections.defaultdict(list)
    for e in ents:
        base, idx = _split_index(e["name"])
        if idx:
            by[base].append((idx, e["name"], {u[len(e["name"]):].strip("_") for u in e["units"]}))
    out = []
    for base, inst in by.items():
        if len(inst) < 2:
            continue
        common = set.intersection(*[x[2] for x in inst])
        if len(common) >= 0.6 * max(len(x[2]) for x in inst):
            out.append({"name": base, "kind": "repeat", "of": [x[1] for x in sorted(inst)], "attributes": sorted(common)})
    return out


def associate(bp: dict) -> list[dict]:
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    vals = compound_values(fields)
    ents = entities(fields, vals)
    return vals + ents + repeats(ents)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*")
    ap.add_argument("--standardized", action="store_true", help="read the standardized copies (runs/standardized)")
    ap.add_argument("--all-validated", action="store_true")
    args = ap.parse_args()
    ids = args.ids + (list(json.loads((RUNS / "belongs_to" / "validated_forms_2026-10-14.json").read_text())["forms"])
                      if args.all_validated else [])
    tot = collections.Counter()
    for bid in ids:
        p = h.working_path(bid)
        if args.standardized:
            p = RUNS / "standardized" / bid / p.name
        bp = h._load(p)
        assoc = associate(bp)
        bp["x_petey_associations"] = assoc
        out = OUT / (bid + ("__standardized" if args.standardized else "")) / p.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        n_f = sum(1 for s in (bp.get("fields") or {}).values() if isinstance(s, dict))
        covered = {f for a in assoc if a["kind"] == "entity" for f in a["fields"]} | \
                  {f for a in assoc if a["kind"] == "compound_value" for f in a["fields"].values()}
        c = collections.Counter(a["kind"] for a in assoc)
        tot.update(c)
        tot["fields"] += n_f
        tot["covered"] += len(covered)
        print(f"{bid:28} {c['compound_value']:3} compound values, {c['entity']:4} entities, {c['repeat']:2} repeats; "
              f"{len(covered)}/{n_f} fields in one")
    print(f"total: {tot['compound_value']} compound values, {tot['entity']} entities, {tot['repeat']} repeats; "
          f"{tot['covered']}/{tot['fields']} fields in one ({tot['covered'] / max(1, tot['fields']):.0%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
