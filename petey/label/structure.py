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
    path_of = {w["id"]: (w.get("path") or "") for w in entries}
    for g in tables:
        page = g[0]["page"]
        cells = [{"id": int(c["name"][1:]), "row": c["row"], "col": c["col"]} for c in g]
        out.setdefault(page, {"tables": [], "blocks": []})["tables"].append(
            {"rows": max(c["row"] for c in g) + 1, "cols": max(c["col"] for c in g) + 1, "cells": cells,
             "hint": axis_hint(cells, path_of)})
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


def _path_tokens(path: str) -> list[str]:
    """The publisher's field name as tokens: the last path part, split on _ . [ ] and case changes
    (Vehicle_PIP_PremiumAmount_A[0] -> vehicle, pip, premium, amount, a, 0)."""
    import re
    last = (path or "").split(".")[-1]
    return [t.lower() for t in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+", last)]


def _one_token_apart(a: list[str], b: list[str]) -> bool:
    """Two publisher names that differ in exactly one token, that token a letter or a number: the same field in
    another row or column (..._A, ..._B; ..._1, ..._2)."""
    if len(a) != len(b) or a == b:
        return False
    if sum(len(t) >= 3 and t.isalpha() for t in a) < 2:      # f1_01 / f1_02: a generated id, not a name
        return False
    diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
    if len(diff) != 1:
        return False
    x, y = a[diff[0]], b[diff[0]]
    return (len(x) == 1 and len(y) == 1 and x.isalpha() and y.isalpha()) or (x.isdigit() and y.isdigit())


def axis_hint(cells: list[dict], path_of: dict[int, str]) -> dict:
    """Which axis the publisher's own field names say repeats: {"axis": "rows" | "columns" | None, "rows": share,
    "columns": share}. Down a column, cells whose paths are one letter or number apart say the ROWS repeat
    (ACORD 90 NY: Vehicle_SeatBeltCode_A / _B); along a row they say the COLUMNS repeat (PIP_PremiumAmount_A .. _D
    across the vehicles). The share is of adjacent pairs so related; the axis with the larger share wins when it is
    at least half and clearly ahead."""
    toks = {c["id"]: _path_tokens(path_of.get(c["id"], "")) for c in cells}
    if not any(toks.values()):
        return {"axis": None, "rows": 0.0, "columns": 0.0}

    def share(axis_key, other_key):
        lines: dict[int, list] = {}
        for c in cells:
            lines.setdefault(c[axis_key], []).append(c)
        pairs = hits = 0
        for cs in lines.values():
            cs = sorted(cs, key=lambda c: c[other_key])
            for a, b in zip(cs, cs[1:]):
                pairs += 1
                hits += _one_token_apart(toks[a["id"]], toks[b["id"]])
        return hits / pairs if pairs else 0.0
    down = share("col", "row")           # pairs down a column alike -> rows repeat
    across = share("row", "col")         # pairs along a row alike -> columns repeat
    axis = "rows" if down >= 0.5 and down >= across + 0.2 else "columns" if across >= 0.5 and across >= down + 0.2 else None
    both = 0.0
    if axis is None:
        both = _both_named(cells, toks)
        if both >= 0.5:
            axis = "both"
    return {"axis": axis, "rows": round(down, 2), "columns": round(across, 2), "both": round(both, 2)}


def _both_named(cells: list[dict], toks: dict[int, list[str]]) -> float:
    """A ledger: rows are line items and columns are kinds, and the publisher's names say so (AO 40B:
    AttendFeesOffTrans / AttendFeesPrivateReport along a row share the leading stem, AttendFeesOffTrans /
    SalaryOfficalTrans down a column share the trailing one). The share of cells whose name shares a leading token
    with a row-mate and a trailing token with a column-mate."""
    rows: dict[int, list] = {}
    cols: dict[int, list] = {}
    for c in cells:
        rows.setdefault(c["row"], []).append(c)
        cols.setdefault(c["col"], []).append(c)
    hits = n = 0
    for c in cells:
        t = toks.get(c["id"]) or []
        if len(t) < 2 or sum(len(x) >= 3 and x.isalpha() for x in t) < 2:
            continue
        n += 1
        lead = any(toks.get(o["id"]) and toks[o["id"]][0] == t[0] and toks[o["id"]] != t for o in rows[c["row"]] if o is not c)
        words = [x for x in t if x.isalpha() and len(x) >= 3]
        trail = any(toks.get(o["id"]) and [x for x in toks[o["id"]] if x.isalpha() and len(x) >= 3][-1:] == words[-1:]
                    and toks[o["id"]] != t for o in cols[c["col"]] if o is not c) if words else False
        hits += lead and trail
    return hits / n if n else 0.0


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
        h = t.get("hint") or {}
        ev = ("" if not h.get("axis") else
              " (evidence: the publisher's own field names share a stem along each row and a kind down each column, "
              "so the rows are line items and the columns kinds: name both)" if h["axis"] == "both" else
              f" (evidence: the publisher's own field names repeat {'down the rows' if h['axis'] == 'rows' else 'across the columns'}"
              f", one letter or number apart, so the {h['axis']} are the repetitions)")
        parts.append(f"Table {t['id']}: {t['rows']} rows x {t['cols']} columns{ev}" + "".join(
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
            "WHICH boxes belong together; what they hold still comes from the captions, tooltips and paths. A cell "
            "no filer writes in (shaded, hatched, \"reserved for future use\") still gets \"\" as always.")


# ----------------------------------------------------------------- bulk: a column named once, its cells printed

from standardize_names import SUFFIXES  # noqa: E402

BULK_RULES = (
    "Name the structures by their parts, not cell by cell. A table repeats along one axis: say which.\n"
    "- Rows are the repetitions (vehicle 1, 2, 3 down the page; line items): give each COLUMN one label, the wording "
    "every cell of the column shares, with NO row number in it (vehicle_make_txt, parent_first_nm), and "
    "\"rows\": \"numbered\" (or the printed line numbers / letters as a list of strings when the page prints them).\n"
    "- Columns are the repetitions (vehicle 1 .. 4 across the page; year 1, year 2; columns (a), (b), (c)): give each "
    "ROW one label, the wording every cell of the row shares (bodily_injury_limit_amt, net_income_amt), as "
    "\"rows\": [{\"row\": 1, \"label\": ...}, ...] and \"columns\": \"numbered\" (or the printed column "
    "letters / numbers as a list of strings).\n"
    "- Both named (rows are things, columns are kinds: applicant / spouse by first / last name): \"rows\" and "
    "\"columns\" both as label lists; the cell's name joins them.\n"
    "- Neither (the layout code was wrong, the rows are unalike): \"rows\": \"unlike\" and label its widgets one "
    "by one in \"labels\". Where the table comes with evidence that one axis repeats, it does: name the other axis.\n"
    "- A row or column no filer writes in (shaded, \"reserved for future use\", a heading line): label it \"\" "
    "(empty) and its cells are dropped.\n"
    "- A repeated block: say what repeats as \"entity\" (child, sibling, employer, property) and give each FIELD of "
    "the block one label (the same field in every block: name, birth_dt, present_address), with no block number; "
    "the blocks are numbered in order and the entity leads every name (child_name_1, child_birth_dt_1).\n"
    "- A pair or cluster of tick boxes answering one question inside a table or block (Yes / No: will accompany you "
    "to Canada?) is one choice per block: label each box <question>.<value> (will_accompany.yes, "
    "will_accompany.no) and they become one field per block.\n"
    "- Every other widget: one label in \"labels\" as usual. Do not repeat a table's or block's widgets there.\n"
    "Return JSON only:\n"
    '{"labels": [{"id": <int>, "label": "<slug>"}, ...],\n'
    ' "tables": [{"id": "T1", "columns": [{"col": 1, "label": "<slug>"}, ...] | "numbered" | ["<printed>", ...],\n'
    '             "rows": "numbered" | ["<printed>", ...] | [{"row": 1, "label": "<slug>"}, ...] | "unlike"}, ...],\n'
    ' "blocks": [{"id": "B1", "entity": "<slug>", "fields": [{"slot": 1, "label": "<slug>"}, ...]}, ...]}'
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
    toks = [t for t in label.strip().strip("_").split("_") if t and t != "."]
    if len(toks) >= 2 and toks[-1] in SUFFIXES:
        return "_".join(toks[:-1]), toks[-1]
    return "_".join(toks), None


def print_name(ident: dict) -> str:
    """[subject]_[suffix]_[iteration]_[part], absent parts skipped (docs/NAMING.md "Identifiers")."""
    return "_".join(str(ident[k]) for k in ("subject", "suffix", "iteration", "part") if ident.get(k) not in (None, ""))


def _slug(s) -> str:
    """A label as a slug; a dot (one choice of a question, <group>.<value>) is kept."""
    import re
    s = str(s or "").strip().lower()
    if "." in s:
        g, v = s.split(".", 1)
        return _slug(g) + "." + re.sub(r"[^a-z0-9_]+", "_", v).strip("_")
    return re.sub(r"[^a-z0-9_]+", "_", s).strip("_")


def _emit(ident: dict, label: str) -> tuple[str, dict | None]:
    """The printed name for a cell, and its parts; a <group>.<value> label prints the group from the parts and keeps
    the value (will_accompany_1.yes): the labeler's grouping makes one field per block, with no parts stored."""
    if "." in label:
        return print_name(ident) + "." + label.split(".", 1)[1], None
    return print_name(ident), ident


def print_cells(page_struct: dict | None, parsed: dict, ids: set[int]) -> tuple[dict[int, str], dict[int, dict], list[int]]:
    """({widget id: printed name}, {widget id: identifiers}, [ids left for one-by-one labels]) from a bulk answer:
    each table's cells from its columns' labels and its rows' numbers or labels, each block group's from its
    fields' labels and the block number."""
    names: dict[int, str] = {}
    parts: dict[int, dict] = {}
    left: list[int] = []

    def entries(lst, key):
        """{index: slug}; an empty label is kept as "" (the line is dropped), a missing one is absent."""
        if isinstance(lst, dict):
            return {int(k): _slug(v) for k, v in lst.items() if str(k).lstrip("-").isdigit()}
        out = {}
        for e in lst or []:
            if isinstance(e, dict) and isinstance(e.get(key), int):
                out[e[key]] = _slug(e.get("label"))
        return out
    def axis(v, key):
        """('labels', {index: slug}) for a list of {row/col, label}; ('printed', [str]) for printed numbers or
        letters; ('numbered', None); ('unlike', None); (None, None) when absent."""
        if v is None:
            return None, None
        if isinstance(v, str):
            return (v if v in ("numbered", "unlike") else None), None
        if isinstance(v, dict):
            return "labels", {int(k): _slug(x) for k, x in v.items() if str(k).isdigit()}
        if isinstance(v, list):
            if all(isinstance(x, dict) for x in v):
                return "labels", entries(v, key)
            printed = [_slug(x) for x in v]
            if printed and all(len(x) == 1 and x.isalpha() for x in printed):
                printed = [str(i + 1) for i in range(len(printed))]     # columns (a) .. (d): numbered 1 .. 4 (docs/NAMING.md)
            return "printed", printed
        return None, None
    tables = {t.get("id"): t for t in (parsed.get("tables") or []) if isinstance(t, dict)}
    for t in (page_struct or {}).get("tables") or []:
        cells = [c for c in t["cells"] if c["id"] in ids]
        if not cells:
            continue
        ans = tables.get(t["id"]) or {}
        ckind, cval = axis(ans.get("columns"), "col")
        rkind, rval = axis(ans.get("rows"), "row")
        if not ans or rkind == "unlike" or ckind == "unlike" or (ckind != "labels" and rkind != "labels"):
            left += [c["id"] for c in cells]
            continue
        # two boxes at one position: the finder gave two different boxes one column; a label cannot name both
        at: dict[tuple, int] = {}
        for c in cells:
            at[(c["row"], c["col"])] = at.get((c["row"], c["col"]), 0) + 1

        def tag(kind, val, i):           # a line's number or label along one axis, 0-based index i
            if kind == "labels":
                return "label", (val or {}).get(i + 1)      # "" when the line is not fillable, None when unanswered
            if kind == "printed":
                return "iter", (val[i] if i < len(val) else None)
            return "iter", str(i + 1)
        for c in cells:
            if at.get((c["row"], c["col"]), 0) > 1:
                left.append(c["id"])
                continue
            ck, cv = tag(ckind, cval, c["col"])
            rk, rv = tag(rkind, rval, c["row"])
            if (ck == "label" and cv == "") or (rk == "label" and rv == ""):
                names[c["id"]] = ""                         # a line no filer writes in: its cells are dropped
                continue
            if (ck == "label" and not cv) or (rk == "label" and not rv):
                left.append(c["id"])
                continue
            base = lambda x: str(x).split(".", 1)[0]     # noqa: E731  a <group>.<value> label: the group names the cell
            if ck == "label" and rk == "label":          # both named: [row]_[column]
                subject, suffix = _split(base(cv))
                ident = {"subject": f"{base(rv)}_{subject}", "suffix": suffix}
            elif ck == "label":                          # columns named, rows iterate
                subject, suffix = _split(base(cv))
                ident = {"subject": subject, "suffix": suffix, "iteration": rv}
            else:                                        # rows named, columns iterate
                subject, suffix = _split(base(rv))
                ident = {"subject": subject, "suffix": suffix, "iteration": cv}
            if ident.get("iteration") is None and "iteration" in ident:
                left.append(c["id"])
                continue
            ident = {k: v for k, v in ident.items() if v}
            src = cv if ck == "label" else rv
            names[c["id"]], pt = _emit(ident, src if "." in str(src) else "")
            if pt is not None:
                parts[c["id"]] = pt
    blocks = {b.get("id"): b for b in (parsed.get("blocks") or []) if isinstance(b, dict)}
    for b in (page_struct or {}).get("blocks") or []:
        cells = [c for c in b["cells"] if c["id"] in ids]
        if not cells:
            continue
        ans = blocks.get(b["id"])
        slots = entries((ans or {}).get("fields"), "slot") if ans else {}
        entity = _slug((ans or {}).get("entity")) if ans else ""
        if not slots:
            left += [c["id"] for c in cells]
            continue
        for c in cells:
            lab = slots.get(c["slot"] + 1)
            if lab == "":
                names[c["id"]] = ""
                continue
            if not lab:
                left.append(c["id"])
                continue
            subject, suffix = _split(lab.split(".", 1)[0])
            if entity and not subject.startswith(entity):
                subject = f"{entity}_{subject}" if subject else entity
            ident = {k: v for k, v in {"subject": subject, "suffix": suffix, "iteration": str(c["block"] + 1)}.items() if v}
            names[c["id"]], pt = _emit(ident, lab)
            if pt is not None:
                parts[c["id"]] = pt
    return names, parts, left


def in_structure(page_struct: dict | None) -> set[int]:
    return {c["id"] for t in (page_struct or {}).get("tables") or [] for c in t["cells"]} | \
        {c["id"] for b in (page_struct or {}).get("blocks") or [] for c in b["cells"]}
