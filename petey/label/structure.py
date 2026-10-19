"""Tables and repeated blocks found BEFORE labeling, as guidance for the labeler (Andrew, 2026-10-19: "try it with
identifying the grids and blocks first, then using that as guidance for labeling").

The finders need only box positions (eval/grid_naming.grids: columns and rows of alike boxes) and the page's printed
captions (eval/block_groups.find: a set of fields laid out again at one step, each slot's caption repeating), so they
run on the widgets as enumerated, with no names. What the labeler gets from them:

    batches     a table or block group is never split across two calls (ACORD 90 NY, 2026-10-19: the vehicle
                table's rows 3 and 4 fell in the second batch of page 1, which named them without the vehicle
                number; 95 page-check flags). The cells of a structure are made contiguous and a batch is cut at
                its edge; a structure larger than a batch is split by rows (or blocks).
    guidance    each batch's prompt lists the structures its widgets belong to, row by row (block by block), and
                asks for one wording per column (slot) with the row (block) number as its own word.

    find(blank, entries) -> {page: {"tables": [...], "blocks": [...]}}
    batches(page_widgets, page_struct, size) -> [[widget]]
    guidance(page_struct, ids) -> str
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "eval"))

_KIND = {"text": "text", "checkbox": "checkbox", "radiobutton": "radio", "radio": "radio", "combobox": "combobox",
         "listbox": "listbox", "signature": "text"}


def _stub(blank: Path, entries: list[dict]) -> dict:
    """A blueprint with one field per widget (named w<id>), enough for the finders."""
    fields = {}
    for w in entries:
        if not w.get("rect") or not w.get("page"):
            continue
        fields[f"w{w['id']}"] = {"type": "string", "widget": {"page": w["page"], "rect": list(w["rect"]),
                                                               "widget_type": _KIND.get(w.get("widget_type"), "text"),
                                                               "path": w.get("path")}}
    return {"source_pdf": str(Path(blank).resolve()), "fields": fields}


def find(blank: Path, entries: list[dict]) -> dict[int, dict]:
    """{page: {"tables": [{"rows", "cols", "cells": [{"id", "row", "col"}]}],
               "blocks": [{"blocks", "slots", "cells": [{"id", "block", "slot"}]}]}} for the pages with any."""
    import block_groups
    import grid_naming as G
    bp = _stub(blank, entries)
    out: dict[int, dict] = {}
    try:
        groups = block_groups.find(bp)
    except Exception as e:                      # no page text, an odd page: the labeler runs without blocks
        print(f"  [structure] block groups: {e}")
        groups = []
    inside = [{c["name"] for c in g} for g in groups]
    tables = []
    for g in G.grids(bp, blocks=False):
        nrow, ncol = len({c["row"] for c in g}), len({c["col"] for c in g})
        if nrow < 2 or ncol < 2 or len(g) < 4:
            continue
        if any(len({c["name"] for c in g} & ns) >= 0.5 * len(g) for ns in inside):
            continue
        tables.append(g)
    for g in tables:
        page = g[0]["page"]
        out.setdefault(page, {"tables": [], "blocks": []})["tables"].append(
            {"rows": max(c["row"] for c in g) + 1, "cols": max(c["col"] for c in g) + 1,
             "cells": [{"id": int(c["name"][1:]), "row": c["row"], "col": c["col"]} for c in g]})
    for g in groups:
        page = g[0]["page"]
        out.setdefault(page, {"tables": [], "blocks": []})["blocks"].append(
            {"blocks": max(c["row"] for c in g) + 1, "slots": max(c["col"] for c in g) + 1,
             "cells": [{"id": int(c["name"][1:]), "block": c["row"], "slot": c["col"]} for c in g]})
    for page, st in out.items():
        for k, t in enumerate(st["tables"], 1):
            t["id"] = f"T{k}"
        for k, b in enumerate(st["blocks"], 1):
            b["id"] = f"B{k}"
    return out


def _units(page_struct: dict | None) -> list[list[list[int]]]:
    """Each structure as its lines of widget ids (a table's rows, a block group's blocks), in reading order."""
    units = []
    for t in (page_struct or {}).get("tables") or []:
        rows: dict[int, list] = {}
        for c in sorted(t["cells"], key=lambda c: (c["row"], c["col"])):
            rows.setdefault(c["row"], []).append(c["id"])
        units.append([rows[r] for r in sorted(rows)])
    for b in (page_struct or {}).get("blocks") or []:
        blocks: dict[int, list] = {}
        for c in sorted(b["cells"], key=lambda c: (c["block"], c["slot"])):
            blocks.setdefault(c["block"], []).append(c["id"])
        units.append([blocks[k] for k in sorted(blocks)])
    return units


def batches(page_widgets: list[dict], page_struct: dict | None, size: int) -> list[list[dict]]:
    """The page's widgets in batches of at most `size`, a structure's cells contiguous and never split across
    batches unless the structure itself is larger than a batch (then by whole lines). Widgets outside any
    structure keep their order and fill the gaps."""
    by_id = {w["id"]: w for w in page_widgets}
    placed: set[int] = set()
    chunks: list[list[dict]] = []           # units to keep whole
    for lines in _units(page_struct):
        lines = [[i for i in ln if i in by_id and i not in placed] for ln in lines]
        ids = [i for ln in lines for i in ln]
        if not ids:
            continue
        placed.update(ids)
        if len(ids) <= size:
            chunks.append([by_id[i] for i in ids])
        else:                                # larger than a batch: whole lines, as many as fit
            cur: list[dict] = []
            for ln in lines:
                if cur and len(cur) + len(ln) > size:
                    chunks.append(cur)
                    cur = []
                cur += [by_id[i] for i in ln]
            if cur:
                chunks.append(cur)
    loose = [w for w in page_widgets if w["id"] not in placed]
    # order: a unit goes where its first widget was; loose widgets around them
    first = {id(ch): min(page_widgets.index(w) for w in ch) for ch in chunks}
    items: list[tuple[int, list[dict]]] = [(first[id(ch)], ch) for ch in chunks] + [(page_widgets.index(w), [w]) for w in loose]
    items.sort(key=lambda x: x[0])
    out: list[list[dict]] = []
    cur = []
    for _, ch in items:
        if cur and len(cur) + len(ch) > size:
            out.append(cur)
            cur = []
        cur += ch
    if cur:
        out.append(cur)
    return out


def guidance(page_struct: dict | None, ids: set[int]) -> str:
    """The structures a batch's widgets belong to, for its prompt; '' when none."""
    parts = []
    for t in (page_struct or {}).get("tables") or []:
        cells = [c for c in t["cells"] if c["id"] in ids]
        if len(cells) < 2:
            continue
        rows: dict[int, list] = {}
        for c in sorted(cells, key=lambda c: (c["row"], c["col"])):
            rows.setdefault(c["row"], []).append(c["id"])
        parts.append(f"Table {t['id']}: {t['rows']} rows x {t['cols']} columns" + "".join(
            f"\n  row {r + 1}: ids {rows[r]}" for r in sorted(rows)))
    for b in (page_struct or {}).get("blocks") or []:
        cells = [c for c in b["cells"] if c["id"] in ids]
        if len(cells) < 2:
            continue
        blocks: dict[int, list] = {}
        for c in sorted(cells, key=lambda c: (c["block"], c["slot"])):
            blocks.setdefault(c["block"], []).append(c["id"])
        parts.append(f"Repeated block {b['id']}: {b['blocks']} blocks of {b['slots']} fields each (the same fields again)" + "".join(
            f"\n  block {k + 1}: ids {blocks[k]}" for k in sorted(blocks)))
    if not parts:
        return ""
    return ("Structure on this page, found from the layout (rows of alike boxes; a set of fields laid out again):\n"
            + "\n".join(parts) + "\n\n"
            "In a table, every cell of one column holds the same kind of value: give the column ONE wording and "
            "number the rows, the row number as its own word before the type suffix (vehicle_1_make_txt, "
            "vehicle_2_make_txt, ... vehicle_4_make_txt; parent_1_first_nm, parent_2_first_nm). Every row is "
            "numbered, the first one too; use the table's own printed numbers or letters when it prints them. "
            "Where a table's rows are named by role or kind instead (applicant, spouse; subtotal, total), name "
            "them so and skip the number. In a repeated block, the same field in each block gets the same wording "
            "with the block number as its own word (sibling_1_first_nm, sibling_2_first_nm). The structure says "
            "WHICH boxes belong together; what they hold still comes from the captions, tooltips and paths.")


# ----------------------------------------------------------------- bulk: a column named once, its cells printed

from standardize_names import SUFFIXES  # noqa: E402

BULK_RULES = (
    "Name the structures by their parts, not cell by cell:\n"
    "- A table: give each COLUMN one label, the wording every cell of the column shares, with NO row number in it "
    "(vehicle_make_txt, parent_first_nm, gross_rents_amt). Say how its rows are told apart: \"rows\": \"numbered\" "
    "when they are repetitions (row 1, row 2, ...; the printed line numbers or letters when the page prints them, "
    "as a list of strings), or a list of row labels when each row is a thing of its own named on the page "
    "(\"applicant\", \"spouse\"; \"subtotal\", \"total\"). If the rows are NOT alike at all (the layout code was "
    "wrong and this is no table), answer \"rows\": \"unlike\" and label its widgets one by one in \"labels\".\n"
    "- A repeated block: give each FIELD of the block one label (the same field in every block), with no block "
    "number; the blocks are numbered in order.\n"
    "- Every other widget: one label in \"labels\" as usual. Do not repeat a table's or block's widgets there.\n"
    "Return JSON only:\n"
    '{"labels": [{"id": <int>, "label": "<slug>"}, ...],\n'
    ' "tables": [{"id": "T1", "columns": [{"col": 1, "label": "<slug>"}, ...], "rows": "numbered" | ["<row label>", ...] | "unlike"}, ...],\n'
    ' "blocks": [{"id": "B1", "fields": [{"slot": 1, "label": "<slug>"}, ...]}, ...]}'
)


def guidance_bulk(page_struct: dict | None, ids: set[int]) -> str:
    """The structures a batch's widgets belong to, and the bulk answer format; '' when none."""
    g = guidance(page_struct, ids)
    if not g:
        return ""
    head = g.split("\n\nIn a table,")[0]
    return head + "\n\n" + BULK_RULES


def _split(label: str) -> tuple[str, str | None]:
    """(subject, suffix) of a column's label: the last word when it is a standard suffix."""
    toks = [t for t in label.strip().strip("_").split("_") if t]
    if len(toks) >= 2 and toks[-1] in SUFFIXES:
        return "_".join(toks[:-1]), toks[-1]
    return "_".join(toks), None


def print_name(ident: dict) -> str:
    """[subject]_[suffix]_[iteration]_[part], absent parts skipped (docs/NAMING.md "Identifiers")."""
    return "_".join(str(ident[k]) for k in ("subject", "suffix", "iteration", "part") if ident.get(k) not in (None, ""))


def _slug(s) -> str:
    import re
    return re.sub(r"[^a-z0-9_]+", "_", str(s or "").strip().lower()).strip("_")


def print_cells(page_struct: dict | None, parsed: dict, ids: set[int]) -> tuple[dict[int, str], dict[int, dict], list[int]]:
    """({widget id: printed name}, {widget id: identifiers}, [ids left for one-by-one labels]) from a bulk answer:
    each table's cells from its columns' labels and its rows' numbers or labels, each block group's from its
    fields' labels and the block number."""
    names: dict[int, str] = {}
    parts: dict[int, dict] = {}
    left: list[int] = []

    def entries(lst, key):
        if isinstance(lst, dict):
            return {int(k): _slug(v) for k, v in lst.items() if str(k).lstrip("-").isdigit()}
        out = {}
        for e in lst or []:
            if isinstance(e, dict) and isinstance(e.get(key), int):
                out[e[key]] = _slug(e.get("label"))
        return out
    tables = {t.get("id"): t for t in (parsed.get("tables") or []) if isinstance(t, dict)}
    for t in (page_struct or {}).get("tables") or []:
        cells = [c for c in t["cells"] if c["id"] in ids]
        if not cells:
            continue
        ans = tables.get(t["id"])
        cols = entries((ans or {}).get("columns"), "col") if ans else {}
        rows = (ans or {}).get("rows")
        if not ans or rows == "unlike" or not cols:
            left += [c["id"] for c in cells]
            continue
        row_labels = [_slug(x) for x in rows] if isinstance(rows, list) else None
        # two boxes at one position: the finder gave two different boxes one column (ACORD 90 NY's transportation
        # expense limits, 170 pt apart); a column label cannot name both, so they are labeled one by one
        at: dict[tuple, int] = {}
        for c in cells:
            at[(c["row"], c["col"])] = at.get((c["row"], c["col"]), 0) + 1
        keyed = row_labels is not None and not all(x.replace("_", "").isalnum() and (x.isdigit() or (len(x) <= 3 and x[0].isdigit())) for x in row_labels)
        for c in cells:
            lab = cols.get(c["col"] + 1)
            if not lab or at.get((c["row"], c["col"]), 0) > 1:
                left.append(c["id"])
                continue
            subject, suffix = _split(lab)
            if row_labels is not None and c["row"] < len(row_labels) and row_labels[c["row"]]:
                if keyed:
                    ident = {"subject": f"{row_labels[c['row']]}_{subject}", "suffix": suffix}
                else:
                    ident = {"subject": subject, "suffix": suffix, "iteration": row_labels[c["row"]]}
            else:
                ident = {"subject": subject, "suffix": suffix, "iteration": str(c["row"] + 1)}
            if at.get((c["row"], c["col"]), 0) > 1:
                left.append(c["id"])
                continue
            ident = {k: v for k, v in ident.items() if v}
            names[c["id"]] = print_name(ident)
            parts[c["id"]] = ident
    blocks = {b.get("id"): b for b in (parsed.get("blocks") or []) if isinstance(b, dict)}
    for b in (page_struct or {}).get("blocks") or []:
        cells = [c for c in b["cells"] if c["id"] in ids]
        if not cells:
            continue
        ans = blocks.get(b["id"])
        slots = entries((ans or {}).get("fields"), "slot") if ans else {}
        if not slots:
            left += [c["id"] for c in cells]
            continue
        for c in cells:
            lab = slots.get(c["slot"] + 1)
            if not lab:
                left.append(c["id"])
                continue
            subject, suffix = _split(lab)
            ident = {k: v for k, v in {"subject": subject, "suffix": suffix, "iteration": str(c["block"] + 1)}.items() if v}
            names[c["id"]] = print_name(ident)
            parts[c["id"]] = ident
    return names, parts, left


def in_structure(page_struct: dict | None) -> set[int]:
    return {c["id"] for t in (page_struct or {}).get("tables") or [] for c in t["cells"]} | \
        {c["id"] for b in (page_struct or {}).get("blocks") or [] for c in b["cells"]}
