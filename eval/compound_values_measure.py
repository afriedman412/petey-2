"""Measure `petey/validate/compound_values.find` (the page alone) per field against an answer key (Andrew, 2026-10-28:
entities before blocks): the entities tagged on the Groups tab (`--tags`, every form with tags: the benchmark's pages)
or the validated names (`from_names`, on the forms of a kept-copies list).

    right     a field of a key entity, found in an entity of the same type with the same fields (a key entity with no
              type, or "other", matches any type)
    partial   found in an entity of that type that holds some other fields or lacks some
    wrong     found in an entity of another type
    missed    in no entity found
    extra     found in an entity, in none of the key's (the key can miss one: read them)

    PYTHONPATH=. venv/bin/python eval/compound_values_measure.py --tags [out.json]
    PYTHONPATH=. venv/bin/python eval/compound_values_measure.py <kept.json> [out.json]
"""
from __future__ import annotations

import collections
import json
import sys

from petey.validate import compound_values as cv
from petey.validate import group_review as gr
from petey.validate import hand_review as h


def compare(key: list[dict], found: list[dict]) -> dict:
    where = {c: v for v in found for c in v["fields"]}
    keyed = {c for v in key for c in v["fields"]}
    out = collections.Counter()
    by_kind = collections.defaultdict(collections.Counter)
    rows = []
    for v in key:
        for c in v["fields"]:
            f = where.get(c)
            what = ("missed" if f is None else "wrong" if v["kind"] and f["kind"] != v["kind"]
                    else "right" if set(f["fields"]) == set(v["fields"]) else "partial")
            out[what] += 1
            by_kind[v["kind"] or "(any)"][what] += 1
        rows.append({"kind": v["kind"], "fields": v["fields"],
                     "found": sorted({(where[c]["kind"],) + tuple(where[c]["fields"]) for c in v["fields"] if c in where})})
    for f in found:
        n = sum(1 for c in f["fields"] if c not in keyed)
        out["extra"] += n
        by_kind[f["kind"]]["extra"] += n
    return {"total": out, "by_kind": by_kind, "rows": rows,
            "extra": [f for f in found if any(c not in keyed for c in f["fields"])]}


def _tagged() -> list[str]:
    paths = h.blueprint_paths()
    out = []
    for bid in paths:
        p = h.working_path(bid, paths)
        if p and p.exists() and gr.ENTITY_KEY in p.read_text(encoding="utf-8", errors="ignore"):
            out.append(bid)
    return sorted(out)


def main() -> int:
    tags = sys.argv[1] == "--tags"
    ids = _tagged() if tags else [k for k in json.loads(open(sys.argv[1]).read()) if k.startswith(("lib__", "je__"))]
    paths = h.blueprint_paths()
    tot, kinds, log = collections.Counter(), collections.defaultdict(collections.Counter), {}
    for bid in ids:
        bp = h._load(h.working_path(bid, paths))
        names = {str(s.get("x_petey_id")): n for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
        key = cv.from_tags(bp) if tags else cv.from_names(bp)
        if not key:
            continue
        r = compare(key, cv.find(bp))
        tot.update(r["total"])
        for k, c in r["by_kind"].items():
            kinds[k].update(c)
        log[bid] = {"rows": [{**x, "names": [names.get(c) for c in x["fields"]]} for x in r["rows"]],
                    "extra": [{"kind": f["kind"], "page": f["page"], "fields": f["fields"], "parts": f["parts"],
                               "names": [names.get(c) for c in f["fields"]]} for f in r["extra"]]}
    keyed = tot["right"] + tot["partial"] + tot["wrong"] + tot["missed"]
    print(f"{len(log)} forms, {keyed} fields in an entity by the {'tags' if tags else 'names'}")
    print(f"  right {tot['right']} ({tot['right'] / max(keyed, 1):.0%}), partial {tot['partial']}, wrong {tot['wrong']}, "
          f"missed {tot['missed']}; extra {tot['extra']}")
    for k, c in sorted(kinds.items()):
        n = c["right"] + c["partial"] + c["wrong"] + c["missed"]
        print(f"  {k:18} {n:5} keyed: right {c['right']:5} partial {c['partial']:4} wrong {c['wrong']:3} "
              f"missed {c['missed']:5}  extra {c['extra']:4}")
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(json.dumps(log, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
