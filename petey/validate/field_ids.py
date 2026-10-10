"""A fixed identifier for every field, independent of its content: `<page>_<n>`, the n-th field on the page in
reading order (top to bottom, then left to right) when the id was given. Stored on the field as `x_petey_id`.

Andrew, 2026-10-07: names change (renames, relabels) and two people can talk past each other about "the subject of
insurance box"; an id that never changes makes sure they mean the same field. An id is given once and kept: a
rename carries it (the field's spec moves whole), a removed field's id is not reused, and a field added later gets
the next free number on its page, so ids stop being in reading order once fields are added. A field with no box
gets page 0. `x_petey_*` keys are outside the page check's field hash, so its verdicts hold. Ids are for referring
to fields; they are not meant to agree between blueprints.

Given where blueprints are made (`auto_label.build_blueprint`, `flat_label.build_flat_blueprint`) and where fields
are added (the launch loop's writer `form_run._dump`, Groups apply, Add / remove apply). The command below is for
blueprints made before 2026-10-07 (all of them were given ids that day).

Writing the ids changes the file, and the review records (hand review, groups, add / remove) are tied to the file's
sha: a record that matched the file before is moved to the new sha (only ids were added); a stale one stays stale.

    PYTHONPATH=. venv/bin/python -m petey.validate.field_ids              # what would change
    PYTHONPATH=. venv/bin/python -m petey.validate.field_ids --write      # every blueprint the review page offers
    PYTHONPATH=. venv/bin/python -m petey.validate.field_ids --write je__acord_140
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

KEY = "x_petey_id"
_ID = re.compile(r"^(\d+)_(\d+)$")


def _box(spec: dict) -> tuple[int, list[float]]:
    """The field's first box, as the review page lists it: page and rect (page 0 when it has none)."""
    ws = list((spec.get("widgets") or {}).values()) if isinstance(spec.get("widgets"), dict) else []
    for w in ws + [spec.get("widget") or {}]:
        if w.get("rect") and w.get("page"):
            return int(w["page"]), w["rect"]
    return 0, [0, 0, 0, 0]


def assign(bp: dict) -> list[str]:
    """Give every field without an id the next free number on its page, in reading order; returns the fields given
    one. Existing ids are kept, and the field's other keys keep their order (the id goes first)."""
    fields = bp.get("fields") or {}
    taken: dict[int, int] = {}
    for spec in fields.values():
        m = _ID.match(str(spec.get(KEY) or "")) if isinstance(spec, dict) else None
        if m:
            taken[int(m.group(1))] = max(taken.get(int(m.group(1)), 0), int(m.group(2)))
    todo = [n for n, s in fields.items() if isinstance(s, dict) and not s.get(KEY)]
    todo.sort(key=lambda n: (lambda pg, r: (pg, round(r[1] / 6), r[0]))(*_box(fields[n])))
    for n in todo:
        pg = _box(fields[n])[0]
        taken[pg] = taken.get(pg, 0) + 1
        fields[n] = {KEY: f"{pg}_{taken[pg]}", **fields[n]}
    return todo


def _rehash(bid: str, old: str, new: str) -> list[str]:
    """Move the review records that matched the old file to the new one; returns which were moved."""
    from petey.validate import field_add, group_review, hand_review
    moved = []
    for tag, p in (("review", hand_review.verdict_path(bid)), ("groups", group_review.record_path(bid)),
                   ("add", field_add.record_path(bid))):
        if not p.exists():
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        hit = False
        if rec.get("blueprint_sha") == old:
            rec["blueprint_sha"] = new
            hit = True
        ck = rec.get("checked")
        if isinstance(ck, dict) and ck.get("blueprint_sha") == old:
            ck["blueprint_sha"] = new
            hit = True
        if hit:
            p.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
            moved.append(tag)
    return moved


def write(bid: str, p: Path) -> tuple[int, list[str]]:
    """Assign ids in one blueprint file and rehash its records; returns (fields given an id, records moved)."""
    from petey.validate.hand_review import _load, _sha
    old, bp = _sha(p), _load(p)
    added = assign(bp)
    if not added:
        return 0, []
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return len(added), _rehash(bid, old, _sha(p))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="*", help="review ids (default: every blueprint the review page offers)")
    ap.add_argument("--write", action="store_true", help="write the ids (default: report only)")
    args = ap.parse_args()
    from petey.validate.hand_review import _load, blueprint_paths
    paths = blueprint_paths()
    todo = {b: paths[b] for b in args.ids} if args.ids else paths
    files = fields = 0
    moved: dict[str, int] = {}
    for bid, p in todo.items():
        if args.write:
            k, mv = write(bid, p)
            for t in mv:
                moved[t] = moved.get(t, 0) + 1
        else:
            k = len(assign(_load(p)))
        files += bool(k)
        fields += k
    print(f"{'wrote' if args.write else 'would write'} {fields} ids in {files} of {len(todo)} blueprints"
          + (f"; records rehashed: {moved}" if moved else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
