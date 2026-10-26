"""Every field's parts stored and its name printed from them, on the most recent validated copy of each form (Andrew,
2026-10-26: "you can limit the edits to the most recent validated copies of the forms in the library"; "let's just
rename everything -- if the code is right, it should fix what's wrong when I look at it").

As eval/naming_library_apply.py (2026-10-24), with three differences: the forms are the kept validated copies (lib__ and
je__), the fields the reader flags are written too (their reading, whatever the flag), and stored parts that no longer
print the field's name (a name changed by hand since 2026-10-24) are read again from the name, which wins. Fields whose
stored parts print their name are left. A rename onto a name another field has or gets is left out. Verdicts follow
their fields; shas that matched the old file move to the new one, so a validated form stays validated.

Before: every file touched copied to runs/naming_2026-10-26/before/ and records_before/ (not listed on the review page).

    PYTHONPATH=. venv/bin/python eval/naming_apply_2026_10_26.py <blueprint list json> [--do]
"""
from __future__ import annotations

import collections
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from petey.validate import field_identifiers as FI  # noqa: E402
from naming_library_apply import KEY, OTHER_RECORDS, _dump, _load, rewrite  # noqa: E402

from petey import naming  # noqa: E402
from petey.paths import RUNS  # noqa: E402
from petey.validate import draft, hand_review as h  # noqa: E402

OUT = RUNS / "naming_2026-10-26"
BEFORE = OUT / "before"
RECORDS = OUT / "records_before"


def kept_copies(listing: list[dict]) -> list[str]:
    """The most recently validated copy of each blank."""
    by = collections.defaultdict(list)
    for b in listing:
        if (b.get("checked") or {}).get("validated"):
            by[b["blank"]].append(b)
    when = lambda b: ((b.get("checked") or {}).get("when") or "", b.get("touched") or "")  # noqa: E731
    return sorted(max(bs, key=when)["id"] for bs in by.values())


def plan(bid: str, bp: dict) -> tuple[dict[str, str], dict[str, dict], dict]:
    """({old name: new name}, {old name: parts to store}, counts)."""
    got = FI.read_form(bid, bp)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    idents, renames, n = {}, {}, collections.Counter()
    for name, s in fields.items():
        st = s.get(KEY)
        if st and naming.print_name(st) == name:
            n["kept"] += 1
            continue
        ident = (got.get(name) or (None, []))[0]
        if not ident:
            n["unread"] += 1
            continue
        n["stale" if st else "new"] += 1
        flags = [f for f in got[name][1] if not f.startswith("no standard suffix")]
        n["flagged"] += bool(flags)
        idents[name] = ident
        new = naming.print_name(ident)
        if new and new != name:
            renames[name] = new
    taken = collections.Counter(renames.values())
    ok = {o: v for o, v in renames.items() if taken[v] == 1 and not (v in fields and v not in renames)}
    n["renamed"], n["clash"] = len(ok), len(renames) - len(ok)
    return ok, idents, n


def _archive(src: Path, dst: Path) -> None:
    if src.exists() and not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def apply_form(bid: str, paths: dict, do: bool, given=None) -> tuple[dict, dict]:
    """`given` ({old name: new name}, {old name: parts}): a plan made elsewhere (`reread`), applied the same way."""
    real = paths[bid]
    work = h.working_path(bid, paths)
    has_draft = work != real
    bp = _load(work)
    ren, ids, n = (given[0], given[1], {"renamed": len(given[0]), "parts": len(given[1])}) if given else plan(bid, bp)
    if not do or not ids:
        return n, ren
    vpath = h.verdict_path(bid)
    _archive(work, BEFORE / f"{bid}.bpt")
    _archive(vpath, RECORDS / vpath.name)
    for d in OTHER_RECORDS:
        _archive(d / f"{bid}.json", RECORDS / d.name / f"{bid}.json")
    if has_draft:
        _archive(real, RECORDS / "saved_blueprints" / f"{bid}.bpt")
        _archive(draft._dir(bid) / "draft.json", RECORDS / "drafts" / bid / "draft.json")
    w_sha0 = h._sha(work)
    _dump(rewrite(bp, ren, ids), work)
    w_sha1 = h._sha(work)
    if has_draft:                                      # the saved blueprint too, and the copy's starting point
        r_bp = _load(real)
        r_ren, r_ids, _ = ({o: v for o, v in given[0].items() if o in (r_bp.get("fields") or {})},
                           {o: v for o, v in given[1].items() if o in (r_bp.get("fields") or {})}, None) if given \
            else plan(bid, r_bp)
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
    return n, ren


def reread(bid: str, bp: dict) -> tuple[dict, dict]:
    """(renames, parts) for the fields the reader now reads with no flag (grid_naming.identify placing a grid cell the
    old grid reading could not, 2026-10-26) whose parts print another name, the same words with the number moved
    (`csl_premium_1_amt` -> `csl_premium_amt_1`); the stored parts of every other field are left (the reader is
    written for the names' old order, so on names already in the standard's it reads worse than what is stored)."""
    import copy
    bare = copy.deepcopy(bp)
    for sp in bare["fields"].values():
        if isinstance(sp, dict):
            sp.pop(KEY, None)
    got = FI.read_form(bid, bare)
    ren, ids = {}, {}
    for name, (ident, flags) in got.items():
        if not ident or any(not f.startswith("no standard suffix") for f in flags):
            continue
        new = naming.print_name(ident)
        if new != name and sorted(new.split("_")) == sorted(name.split("_")):
            ren[name], ids[name] = new, ident
    fields = bp.get("fields") or {}
    taken = collections.Counter(ren.values())
    ok = {o: v for o, v in ren.items() if taken[v] == 1 and not (v in fields and v not in ren)}
    return ok, {o: ids[o] for o in ok}


def context_plan(bid: str, bp: dict) -> tuple[dict, dict]:
    """(renames, parts) from the one parts reader with the form's context (field_identifiers.read_parts, 2026-10-26):
    a field whose reading prints another name is renamed to it (the number after the suffix, the short suffix); a
    field in a block takes its block's parts from the block's record where the stored parts lack them; every other
    stored reading is kept (with no context the reader is no better than what is stored)."""
    from petey.validate import field_identifiers as FIx
    blocks, _ = FIx.context(bid, bp)
    got = FIx.read_parts(bid, bp)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    ren, ids = {}, {}
    for n, sp in fields.items():
        parts, flags = got[n]
        if any(not f.startswith("no standard suffix") for f in flags):
            continue
        stored = {k: v for k, v in (sp.get(KEY) or {}).items() if k != "grid"}
        fresh = {k: v for k, v in parts.items() if k != "grid"}
        if naming.standard(stored) == naming.standard(fresh):
            continue
        new = naming.print_name(fresh)
        b = blocks.get(str(sp.get("x_petey_id")))
        if new != n:
            ren[n], ids[n] = new, parts
        elif b and fresh.get("block_prefix") == b[0] and stored.get("block_prefix") != b[0]:
            ids[n] = parts
    taken = collections.Counter(ren.values())
    ok = {o: v for o, v in ren.items() if taken[v] == 1 and not (v in fields and v not in ren)}
    return ok, {o: v for o, v in ids.items() if o not in ren or o in ok}


def main() -> int:
    do = "--do" in sys.argv
    listing = json.loads(Path(sys.argv[1]).read_text())
    paths = h.blueprint_paths()
    tot, log = collections.Counter(), {}
    again = "--reread" in sys.argv or "--context" in sys.argv
    for bid in kept_copies(listing):
        if again:
            plan_ = context_plan if "--context" in sys.argv else reread
            given = plan_(bid, _load(h.working_path(bid, paths)))
            if not given[0] and not given[1]:
                continue
            n, ren = apply_form(bid, paths, do, given)
        else:
            n, ren = apply_form(bid, paths, do)
        tot.update(n)
        tot["forms"] += 1
        if ren:
            log[bid] = ren
    OUT.mkdir(parents=True, exist_ok=True)
    tag = "_context" if "--context" in sys.argv else "_reread" if again else ""
    (OUT / (f"renames{tag}.json" if do else f"renames{tag}_dry.json")).write_text(json.dumps(log, indent=1))
    print(("" if do else "DRY RUN: ") + json.dumps(dict(tot)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
