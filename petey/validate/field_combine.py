"""Field combine: merge text fields that are one value into one bigger text field. The Combine mode of the blueprint
review page (`blueprint_review`): click text fields on a page (or drag a box over them), name the whole, and the
page records the combination; `--apply` writes it.

Text to text only (Andrew, 2026-10-05): every member is a field with one text widget, all on one page, and the
result is a plain `string` field (no semantic type or pattern; the parts' typing does not describe the whole) whose
box is the union of the members' boxes. Its `path` is null: the box covers several AcroForm widgets and a field
names one. The reader then clips the text layer to the union box, which reads every part (`extract._extract_widget`,
no path -> text clip; the text layer misses widget values on 21-526EZ, MA Form 1 and VA 760, see the repo gotchas),
and the filler already splits one value over the text widgets inside a box (`render`, ACORD 25's PRODUCER block).
What each member was (name, path, box, type) is kept in `x_petey_combined`.

    PYTHONPATH=. venv/bin/python -m petey.validate.blueprint_review --mode combine
    PYTHONPATH=. venv/bin/python -m petey.validate.field_combine --summary
    PYTHONPATH=. venv/bin/python -m petey.validate.field_combine --plan <id>
    PYTHONPATH=. venv/bin/python -m petey.validate.field_combine --apply <id>

Records: `runs/field_combine/<id>.json` (the combinations, the blueprint's sha). The combined field takes the place
of its first member in reading order; the other members are removed.
"""
from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Optional

import pymupdf
import yaml

from petey.paths import RUNS
from petey.validate.hand_review import _load, _sha, blueprint_paths
from petey.validate.retype import resolve_blank

OUT = RUNS / "field_combine"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def record_path(bid: str) -> Path:
    return OUT / f"{bid}.json"


def load_record(bid: str) -> dict:
    p = record_path(bid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _order(page: int, rect) -> tuple:
    return int(page), round(rect[1] / 6), rect[0]


def _union(rects) -> list[float]:
    return [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]


def text_fields(bp: dict) -> dict[str, dict]:
    """The fields that can be combined: one widget, a text widget, with a box."""
    out = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("widgets"):
            continue
        w = spec.get("widget") or {}
        if w.get("widget_type") == "text" and w.get("rect") and w.get("page"):
            out[name] = {"name": name, "page": int(w["page"]), "rect": [float(c) for c in w["rect"]],
                         "path": w.get("path"), "type": spec.get("type"), "semantic_type": spec.get("semantic_type"),
                         "description": spec.get("description")}
    return out


def plan(bp: dict, combos: list[dict]) -> dict:
    """`{changes, errors, fields}`: the blueprint's fields with each combination written in place of its first
    member (reading order) and its other members removed."""
    fields = bp.get("fields") or {}
    texts = text_fields(bp)
    errors, changes = [], []
    used: dict[str, str] = {}
    for c in combos:
        members = c.get("members") or []
        if len(members) < 2:
            errors.append(f"{c.get('name')!r} combines fewer than two fields")
            continue
        missing = [m for m in members if m not in texts]
        if missing:
            errors.append(f"{c.get('name')!r}: {', '.join(missing)} not a text field of this blueprint (any more)")
            continue
        if len({texts[m]["page"] for m in members}) > 1:
            errors.append(f"{c.get('name')!r}: members on more than one page")
        for m in members:
            if m in used:
                errors.append(f"{m} is in two combinations ({used[m]!r} and {c.get('name')!r})")
            used[m] = c.get("name")
    gone = set(used)
    names = [c.get("name") for c in combos]
    for c in combos:
        n = c.get("name") or ""
        if not NAME_RE.match(n):
            errors.append(f"{n!r} is not a field name (lower case, digits, underscores)")
        elif names.count(n) > 1:
            errors.append(f"two combinations are both named {n!r}")
        elif n in fields and n not in gone:
            errors.append(f"{n!r} is already the name of another field")
    if errors:
        return {"changes": changes, "errors": sorted(set(errors), key=errors.index), "fields": None}
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    at: dict[str, tuple[str, dict]] = {}
    for c in combos:
        members = sorted(c["members"], key=lambda m: _order(texts[m]["page"], texts[m]["rect"]))
        first = texts[members[0]]
        spec = {"type": "string"}
        if (c.get("description") or "").strip():
            spec["description"] = c["description"].strip()
        spec["widget"] = {"page": first["page"], "rect": [round(v, 3) for v in _union([texts[m]["rect"] for m in members])],
                          "widget_type": "text", "path": None}
        spec["label_source"] = "hand"
        spec["x_petey_combined"] = {"source": "field_combine", "when": c.get("when") or now,
                                    "from": [{k: texts[m][k] for k in ("name", "path", "rect", "type", "semantic_type")
                                              if texts[m][k] is not None} for m in members]}
        at[members[0]] = (c["name"], spec)
        changes.append(f"{', '.join(members)} -> {c['name']} (p{first['page']}, one text box over {len(members)})")
    out: dict = {}
    for name, spec in fields.items():
        if name in at:
            n, s = at[name]
            out[n] = s
        elif name not in gone:
            out[name] = spec
    return {"changes": changes, "errors": [], "fields": out}


def apply(bid: str) -> dict:
    p = blueprint_paths()[bid]
    bp = _load(p)
    rec = load_record(bid)
    combos = rec.get("combos") or []
    if not combos:
        print(f"{bid}: nothing recorded to combine")
        return {}
    pl = plan(bp, combos)
    if pl["errors"]:
        raise SystemExit(f"{bid}: not applied:\n  " + "\n  ".join(pl["errors"]))
    bp["fields"] = pl["fields"]
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True), encoding="utf-8")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rec.setdefault("applied", []).append({"when": now, "sha_before": rec.get("blueprint_sha"), "sha_after": _sha(p),
                                          "changes": pl["changes"]})
    rec["combos"], rec["blueprint_sha"], rec["updated"] = [], _sha(p), now
    record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{bid}: wrote {p}")
    for c in pl["changes"]:
        print(f"  {c}")
    return pl


class State:
    def __init__(self) -> None:
        self.paths = blueprint_paths()

    def detail(self, bid: str) -> dict:
        p = self.paths[bid]
        bp = _load(p)
        blank = resolve_blank(bp)
        pages = []
        if blank and blank.exists():
            doc = pymupdf.open(str(blank))
            try:
                pages = [{"page": i, "w_pt": pg.rect.width, "h_pt": pg.rect.height} for i, pg in enumerate(doc, 1)]
            finally:
                doc.close()
        texts = text_fields(bp)
        others = []
        for name, spec in (bp.get("fields") or {}).items():
            if name in texts or not isinstance(spec, dict):
                continue
            for w in list((spec.get("widgets") or {}).values()) or ([spec["widget"]] if spec.get("widget") else []):
                if w.get("rect") and w.get("page"):
                    others.append({"name": name, "page": int(w["page"]), "rect": w["rect"]})
        rec = load_record(bid)
        sha = _sha(p)
        combos = rec.get("combos") or []
        pl = plan(bp, combos)
        return {"id": bid, "path": str(p), "sha": sha, "pages": pages, "texts": list(texts.values()),
                "others": others, "names": sorted((bp.get("fields") or {}).keys()), "combos": combos,
                "stale": bool(rec) and rec.get("blueprint_sha") != sha, "applied": rec.get("applied") or [],
                "plan": {"changes": pl["changes"], "errors": pl["errors"]}}

    def save(self, bid: str, body: dict) -> dict:
        p = self.paths[bid]
        rec = load_record(bid)
        rec.update({"blueprint": str(p), "form": p.stem, "blueprint_sha": _sha(p),
                    "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "combos": body.get("combos") or []})
        OUT.mkdir(parents=True, exist_ok=True)
        record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        pl = plan(_load(p), rec["combos"])
        return {"saved": rec["updated"], "changes": pl["changes"], "errors": pl["errors"]}


def summary() -> None:
    paths = blueprint_paths()
    print(f"{'blueprint':44} {'combos':>6} {'applied':>7} {'stale':>5}  updated")
    n = 0
    for rp in sorted(OUT.glob("*.json")):
        rec = json.loads(rp.read_text(encoding="utf-8"))
        p = paths.get(rp.stem)
        if p is None:
            continue
        print(f"{rp.stem[:44]:44} {len(rec.get('combos') or []):6} "
              f"{sum(len(a.get('changes') or []) for a in rec.get('applied') or []):7} "
              f"{'yes' if rec.get('blueprint_sha') != _sha(p) else '':>5}  {rec.get('updated')}")
        n += 1
    if not n:
        print(f"no records yet under {OUT}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--plan", metavar="ID", help="print what --apply would change in this blueprint")
    ap.add_argument("--apply", metavar="ID", help="write the recorded combinations into this blueprint")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if args.summary:
        summary()
        return 0
    if args.plan or args.apply:
        bid = args.plan or args.apply
        if bid not in blueprint_paths():
            raise SystemExit(f"no blueprint {bid!r} (ids look like lib__fw9, je__<form>, rl__<form>, fl__<form>)")
        if args.apply:
            apply(bid)
            return 0
        pl = plan(_load(blueprint_paths()[bid]), load_record(bid).get("combos") or [])
        for c in pl["changes"] or ["nothing to combine"]:
            print(f"  {c}")
        for e in pl["errors"]:
            print(f"  ERROR {e}")
        return 0
    from petey.validate.blueprint_review import serve
    return serve(args.port, "combine", not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
