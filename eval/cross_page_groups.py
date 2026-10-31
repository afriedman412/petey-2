"""Option groups that cross a page, taken apart (Andrew, 2026-10-31, ATF Form 4 mg__pb_7da4739a276d p12: "it was
ungrouping paired Y/N boxes on the same row. but the cross-page grouping is a problem too"; "I know it's a problem
across ATF forms").

Staging a fillable PDF groups its checkboxes by the publisher's field name (`safedocs_stage.widget_boxes`), page or
no page. A form printed as several copies of its pages names each box the same on every copy, so Q1's Yes on pages 2,
9 and 12 became one group, and the Yes / No pairing, which never joins two publisher groups, left each row's Yes and
No apart (291 groups on 17 blueprints, 2026-10-31). Other forms reuse a name for another box on another page (204
groups on 83). Staging now keeps a publisher's group on one page; this takes the ones already staged apart:

  * a COPY PAGE is a page whose option boxes all sit where a lower page's do (2026-10-31, Andrew: "let's do a, because
    we haven't decided how to deal with duplicate pages yet"): its boxes are grouped as the first copy's are, whatever
    the first copy holds now (hand edits included), named after it (p2_o4 -> p9_o4);
  * any other group that crosses a page is split by page; a box left on its own is paired by the code rules (the
    Yes / No labels, rows and columns: `yes_no_groups`, `cell_groups`) with the loose boxes of its page.

Only blueprints staged from a fillable PDF's widgets (authoring flat_light / widgets): a hand-made group may be a
question continuing onto the next page. The result goes through the Groups tab's own writer (`group_review.apply`: the record, then the blueprint), into the
working copy while one is open (`draft.py`), the file backed up first.

    PYTHONPATH=. venv/bin/python eval/cross_page_groups.py            # what it would change
    PYTHONPATH=. venv/bin/python eval/cross_page_groups.py --apply [--forms ID ...]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_groups  # noqa: E402
import yes_no_groups  # noqa: E402

from petey.paths import RUNS  # noqa: E402
from petey.validate import group_review as G  # noqa: E402
from petey.validate.hand_review import _load, _sha, blueprint_paths, working_path  # noqa: E402
from petey.validate.retype import resolve_blank  # noqa: E402

BACKUP = RUNS / "cross_page_backup_2026-10-31"
SAME = 3.0               # pt: a box on a copy page sits where the first copy's does


def _same(a, b) -> bool:
    return all(abs(x - y) < SAME for x, y in zip(a, b))


def copy_pages(items: dict) -> dict[int, tuple[int, dict[str, str]]]:
    """{copy page: (first copy page, {item on the copy: the item at its place on the first copy})}: a page with 2+
    option boxes, every one at the place of a box on a lower page."""
    by_page = collections.defaultdict(list)
    for i, it in items.items():
        if it.get("widget_type") in G.OPTION_TYPES:
            by_page[it["page"]].append(i)
    out: dict[int, tuple[int, dict[str, str]]] = {}
    pages = sorted(by_page)
    for q in pages:
        if len(by_page[q]) < 2:
            continue
        for p in pages:
            if p >= q or p in out or len(by_page[p]) != len(by_page[q]):
                continue
            m = {}
            for i in by_page[q]:
                j = next((j for j in by_page[p] if _same(items[i]["rect"], items[j]["rect"])), None)
                if j is None:
                    break
                m[i] = j
            if len(m) == len(by_page[q]) and len(set(m.values())) == len(m):
                out[q] = (p, m)
                break
    return out


def _rename(name: str, p: int, q: int) -> str:
    return re.sub(rf"^p{p}_", f"p{q}_", name) if name.startswith(f"p{p}_") else f"{name}_p{q}"


def regroup(bp: dict, items: dict, units: list[dict], blank) -> tuple[list[dict], list[str]]:
    """(units with no option group crossing a page, what changed in words). `units` as `current_units` gives them."""
    opt = [u for u in units if u.get("kind") != "text"]
    if not any(len({items[i]["page"] for i in u["items"]}) > 1 for u in opt):
        return units, []
    copies = copy_pages(items)
    taken = set((bp.get("fields") or {})) | {u["name"] for u in units}
    notes: list[str] = []

    def fresh(name: str) -> str:
        n, k = name, 2
        while n in taken:
            n, k = f"{name}_{k}", k + 1
        taken.add(n)
        return n

    out: list[dict] = []
    freed: list[str] = []                         # boxes split off on their own, not on a copy page
    for u in units:
        if u.get("kind") == "text":
            out.append(u)
            continue
        keep = [i for i in u["items"] if items[i]["page"] not in copies]
        pages = sorted({items[i]["page"] for i in keep})
        if len(pages) <= 1 and len(keep) == len(u["items"]):
            out.append(u)
            continue
        for k, pg in enumerate(pages):
            ids = [i for i in keep if items[i]["page"] == pg]
            if k == 0:
                part = dict(u, items=ids)
            else:
                name = fresh(_rename(u["name"], pages[0], pg))
                part = {"name": name, "type": u.get("type"), "items": ids, "origin": items[ids[0]]["field"],
                        "description": None, "confirmed": False}
            if len(ids) == 1:
                part["type"] = "boolean"
                if k == 0 or items[ids[0]]["key"] is not None:
                    freed.append(ids[0])
            out.append(part)
        if len(pages) > 1:
            notes.append(f"{u['name']}: split by page ({', '.join(f'p{p}' for p in pages)})")
    # boxes left on their own: paired by the code rules with the loose boxes of their page
    if freed and blank:
        loose = {u["items"][0]: u for u in out if u.get("kind") != "text" and len(u["items"]) == 1}
        stub = {"fields": {f"b{n}": {"type": "boolean", "widget": {"page": items[i]["page"], "rect": items[i]["rect"],
                                                                  "widget_type": items[i].get("widget_type") or "checkbox"}}
                           for n, i in enumerate(loose)}}
        name_of = {f"b{n}": i for n, i in enumerate(loose)}
        pairs = [(name_of[a], name_of[b]) for g in cell_groups.groups(stub, blank)
                 for a, b in zip(sorted(g), sorted(g)[1:])]
        pairs += [(stub_i, stub_j) for _n, yi, ni in yes_no_groups.pairs(stub, blank)
                  for stub_i, stub_j in [(name_of[yi], name_of[ni])]]
        parent = {i: i for i in loose}

        def find(x):
            while parent[x] != x:
                x = parent[x]
            return x
        for a, b in pairs:
            parent[find(a)] = find(b)
        comps = collections.defaultdict(list)
        for i in loose:
            comps[find(i)].append(i)
        fset = set(freed)
        for ids in comps.values():
            if len(ids) < 2 or not fset & set(ids):
                continue
            ids.sort(key=lambda i: (items[i]["rect"][1], items[i]["rect"][0]))
            for i in ids:
                out.remove(loose[i])
            first = loose[ids[0]]
            out.append({"name": fresh(f"{first['name']}_group" if not first["name"].endswith("_ind") else
                                      first["name"][:-4]), "type": "category", "items": ids,
                        "origin": items[ids[0]]["field"], "description": None, "confirmed": False})
            notes.append(f"p{items[ids[0]]['page']}: {len(ids)} boxes paired by the code rules")
    # the copy pages: the first copy's units, mapped
    for q, (p, m) in sorted(copies.items()):
        back = {j: i for i, j in m.items()}
        made = 0
        for u in list(out):
            if u.get("kind") == "text" or not u["items"] or items[u["items"][0]]["page"] != p:
                continue
            ids = [back[i] for i in u["items"] if i in back]
            if not ids:
                continue
            name = fresh(_rename(u["name"], p, q))
            out.append({"name": name, "type": u.get("type") if len(ids) > 1 else "boolean", "items": ids,
                        "origin": items[ids[0]]["field"], "description": None, "confirmed": False})
            made += 1
        notes.append(f"p{q}: a copy of p{p}, grouped as p{p} is ({made} units)")
    return out, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", nargs="*")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    paths = blueprint_paths()
    todo = args.forms or sorted(paths)
    done = 0
    for bid in todo:
        p = working_path(bid, paths)
        if p is None or not p.exists():
            continue
        try:
            bp = _load(p)
        except Exception:
            continue
        au = bp.get("authoring") or {}
        if (au.get("method"), au.get("geometry")) != ("flat_light", "widgets"):
            continue                              # hand-made groups may continue onto the next page
        if not any(isinstance(s, dict) and s.get("widgets") and len({w.get("page") for w in s["widgets"].values()}) > 1
                   for s in (bp.get("fields") or {}).values()):
            continue
        sha = _sha(p)
        items, units, info = G.current_units(bid, bp, sha)
        if info["stale"] and not G.load_record(bid).get("boxes"):     # as `group_review.apply`: boxes rebase safely
            print(f"{bid}: its Groups record is stale; open it in the page first, skipped")
            continue
        new, notes = regroup(bp, items, units, resolve_blank(bp))
        if not notes:
            continue
        done += 1
        print(f"{bid}  ({p})")
        for n in notes:
            print(f"   {n}")
        if not args.apply:
            continue
        BACKUP.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, BACKUP / f"{bid}.bpt")
        rec = G.load_record(bid)
        rec_path = G.record_path(bid)
        if rec_path.exists():
            shutil.copyfile(rec_path, BACKUP / f"{bid}.group_review.json")
        rec.update({"blueprint": str(paths[bid]), "form": paths[bid].stem, "blueprint_sha": sha,
                    "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "units": new,
                    "boxes": G.item_boxes(items, new)})
        rec_path.parent.mkdir(parents=True, exist_ok=True)
        rec_path.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        G.apply(bid)
    print(f"\n{done} blueprint(s) {'changed' if args.apply else 'to change'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
