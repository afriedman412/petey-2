"""The naming standard applied to the library (Andrew, 2026-10-24: "yeah sounds good. let's keep the old copies around so
I can do a little more validation against old versions before we let them slide").

For every library blueprint: its fields' parts written as `x_petey_identifiers` (eval/field_identifiers.read_form, the
fields it can read; the flagged ones are left as they are) and its names printed from them (petey/naming.py), in the
blueprint and in its working copy when one is open (the copy's starting point moved along, so Save still works). The
verdicts follow their fields' new names, and the shas that matched the old file are moved to the new one, so a
validated form stays validated. Field rules (`x_petey_rules`) follow the renames; edit history is left as written.

The old versions stay on the review page as `old__<form>` (runs/naming_2026-10-24/before/<form>.bpt, its verdicts
copied), and every record touched is archived first in runs/naming_2026-10-24/records_before/.

    PYTHONPATH=. venv/bin/python eval/naming_library_apply.py [lib__form ...]      # default: every library form
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import field_identifiers as FI  # noqa: E402

from petey import naming  # noqa: E402
from petey.paths import RUNS  # noqa: E402
from petey.validate import draft, hand_review as h  # noqa: E402

OUT = RUNS / "naming_2026-10-24"
BEFORE = OUT / "before"
RECORDS = OUT / "records_before"
KEY = "x_petey_identifiers"
OTHER_RECORDS = (RUNS / "group_review", RUNS / "field_add")


def _load(p: Path) -> dict:
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


def _dump(bp: dict, p: Path) -> None:
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")


def plan(bid: str, bp: dict) -> tuple[dict[str, str], dict[str, dict]]:
    """({old name: new name}, {old name: identifiers}) for the fields read cleanly; renames that would land on a name
    another field has or gets are left out (flagged in the dry run)."""
    got = FI.read_form(bid, bp)
    idents, renames = {}, {}
    for name, (ident, flags) in got.items():
        if any(not f.startswith("no standard suffix") for f in flags):
            continue
        idents[name] = ident
        new = naming.print_name(ident)
        if new != name:
            renames[name] = new
    taken = {}
    for o, n in renames.items():
        taken[n] = taken.get(n, 0) + 1
    renames = {o: n for o, n in renames.items() if taken[n] == 1 and not (n in got and n not in renames)}
    return renames, idents


def rewrite(bp: dict, renames: dict[str, str], idents: dict[str, dict]) -> dict:
    """The blueprint with its fields renamed (order kept), their identifiers written, and the field rules following."""
    fields = {}
    for n, s in (bp.get("fields") or {}).items():
        if isinstance(s, dict) and n in idents:
            s = {**s, KEY: {k: v for k, v in naming.standard(idents[n]).items() if v not in (None, "")}}
        fields[renames.get(n, n)] = s

    def follow(x):
        if isinstance(x, str):
            return renames.get(x, x)
        if isinstance(x, list):
            return [follow(v) for v in x]
        if isinstance(x, dict):
            return {k: follow(v) for k, v in x.items()}
        return x
    out = {k: (fields if k == "fields" else follow(v) if k == "x_petey_rules" else v) for k, v in bp.items()}
    return out


def _archive(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def apply_form(bid: str, paths: dict) -> dict:
    real = paths[bid]
    work = h.working_path(bid, paths)
    has_draft = work != real
    stem = real.stem
    # the old version kept, openable as old__<form> (what the review page showed: the working copy when open)
    _archive(work, BEFORE / f"{stem}.bpt")
    vpath = h.verdict_path(bid)
    _archive(vpath, RECORDS / vpath.name)
    for d in OTHER_RECORDS:
        _archive(d / f"{bid}.json", RECORDS / d.name / f"{bid}.json")
    if has_draft:
        _archive(real, RECORDS / "saved_blueprints" / real.name)
        _archive(draft._dir(bid) / "draft.json", RECORDS / "drafts" / bid / "draft.json")
    if vpath.exists() and not h.verdict_path(f"old__{stem}").exists():     # once: from the record before any rename
        old_rec = json.loads((RECORDS / vpath.name).read_text())
        old_rec.update(blueprint=str(BEFORE / f"{stem}.bpt"), form=stem)
        sha_old = h._sha(BEFORE / f"{stem}.bpt")
        if old_rec.get("blueprint_sha") == h._sha(work):
            old_rec["blueprint_sha"] = sha_old
        ck = old_rec.get("checked")
        if isinstance(ck, dict) and ck.get("blueprint_sha") == h._sha(work):
            ck["blueprint_sha"] = sha_old
        old_rec.pop("promoted_from", None)
        h.verdict_path(f"old__{stem}").write_text(json.dumps(old_rec, indent=1))

    # the working copy (or the blueprint, when none is open)
    w_sha0 = h._sha(work)
    bp = _load(work)
    ren, ids = plan(bid, bp)
    _dump(rewrite(bp, ren, ids), work)
    w_sha1 = h._sha(work)
    out = {"renamed": len(ren), "identifiers": len(ids), "draft": has_draft}
    if has_draft:                                      # the saved blueprint too, and the copy's starting point
        r_bp = _load(real)
        r_ren, r_ids = plan(bid, r_bp)
        _dump(rewrite(r_bp, r_ren, r_ids), real)
        m = draft.meta(bid)
        if m is not None:
            m["base_sha"] = draft._sha(real)
            draft._write_meta(bid, m)
        snap = draft._dir(bid) / "records" / "hand_review.json"    # what Discard puts back: the saved file's names
        if snap.exists():
            _archive(snap, RECORDS / "drafts" / bid / "hand_review.json")
            r = json.loads(snap.read_text())
            r["verdicts"] = {r_ren.get(k, k): v for k, v in (r.get("verdicts") or {}).items()}
            snap.write_text(json.dumps(r, indent=1))
        out["saved_renamed"] = len(r_ren)
    # the verdicts follow their fields; shas that matched the old file move to the new one
    if vpath.exists():
        rec = json.loads(vpath.read_text())
        rec["verdicts"] = {ren.get(k, k): v for k, v in (rec.get("verdicts") or {}).items()}
        if rec.get("blueprint_sha") == w_sha0:
            rec["blueprint_sha"] = w_sha1
        ck = rec.get("checked")
        if isinstance(ck, dict) and ck.get("blueprint_sha") == w_sha0:
            ck["blueprint_sha"] = w_sha1
        vpath.write_text(json.dumps(rec, indent=1))
    for d in OTHER_RECORDS:
        p = d / f"{bid}.json"
        if p.exists():
            r = json.loads(p.read_text())
            if r.get("blueprint_sha") == w_sha0:
                r["blueprint_sha"] = w_sha1
                p.write_text(json.dumps(r, indent=1))
    return out


def main() -> int:
    paths = h.blueprint_paths()
    want = sys.argv[1:] or sorted(b for b in paths if b.startswith("lib__"))
    tot = {"forms": 0, "renamed": 0, "identifiers": 0, "drafts": 0}
    for bid in want:
        r = apply_form(bid, paths)
        tot["forms"] += 1
        tot["renamed"] += r["renamed"]
        tot["identifiers"] += r["identifiers"]
        tot["drafts"] += r["draft"]
    print(tot)
    return 0


if __name__ == "__main__":
    sys.exit(main())
