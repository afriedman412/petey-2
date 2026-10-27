"""Grids by geometry (grid_check.geometric, 2026-10-27, tentative; Andrew: "define grids partially by geometry ... it's
also about reasonably uniform spacing"; "consistent across a row/column"; "there doesn't have to be a field in every
single location"): a table whose caption repeats under every row is one; fields lined up with their own labels are not."""
import pymupdf

from petey.validate import grid_check as gc


def _page(tmp_path, rows, cols, caption, skip=()):
    """A blank with `rows` x `cols` underlined blanks and `caption(r, c)` printed under (or beside) each, and the
    blueprint fields and grid cells for them."""
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    fields, cells = {}, []
    for r in range(rows):
        y = 120 + 40 * r
        for c in range(cols):
            if (r, c) in skip:
                continue
            x0 = (60 + 170 * c) if caption(r, c)[1] == "under" else (100 + 240 * c)
            rect = [x0, y, x0 + 150, y + 16]
            text, where = caption(r, c)
            if where == "under":
                pg.insert_text((x0 + 4, y + 25), text, fontsize=7)
            else:                                         # in the gap left of the box (the columns set wider apart)
                pg.insert_text((x0 - 60, y + 12), text, fontsize=8)
            n = f"r{r}c{c}"
            fields[n] = {"type": "string", "x_petey_id": n, "widget": {"page": 1, "rect": rect, "widget_type": "text"}}
            cells.append({"name": n, "page": 1, "row": r, "col": c})
    p = tmp_path / "f.pdf"
    doc.save(p)
    return {"source_pdf": str(p), "fields": fields}, cells


def test_a_caption_repeated_under_every_row_is_a_table(tmp_path):
    heads = ["Child's Name", "Social Security Number", "Date of Birth"]
    bp, g = _page(tmp_path, 4, 3, lambda r, c: (heads[c], "under"))
    assert gc.geometric(bp, g)


def test_a_slot_left_empty_is_still_a_table(tmp_path):
    heads = ["Child's Name", "Social Security Number", "Date of Birth"]
    bp, g = _page(tmp_path, 4, 3, lambda r, c: (heads[c], "under"), skip={(3, 2)})
    assert gc.geometric(bp, g)


def test_fields_lined_up_with_their_own_labels_are_not(tmp_path):
    labels = [["Name", "Phone"], ["Address", "Email"], ["City", "Zip"]]
    bp, g = _page(tmp_path, 3, 2, lambda r, c: (labels[r][c], "left"))
    assert not gc.geometric(bp, g)


def test_uneven_rows_are_not(tmp_path):
    heads = ["Child's Name", "Social Security Number", "Date of Birth"]
    bp, g = _page(tmp_path, 4, 3, lambda r, c: (heads[c], "under"))
    for c in range(3):                                     # the last row far below the others
        w = bp["fields"][f"r3c{c}"]["widget"]
        w["rect"] = [w["rect"][0], w["rect"][1] + 120, w["rect"][2], w["rect"][3] + 120]
    assert not gc.geometric(bp, g)


def test_found_by_says_which_test(tmp_path):
    heads = ["Child's Name", "Social Security Number", "Date of Birth"]
    bp, g = _page(tmp_path, 4, 3, lambda r, c: (heads[c], "under"))
    assert gc.found_by(bp, g) == "geometry"                # names r0c0 .. carry no line numbers


def _rec_and_grid(block_rows, confirmed=False, src="finder (SIA)"):
    """A 4 x 2 geometry-only grid (cells a0..d1) and a block type whose blocks are `block_rows` (rows per block)."""
    rows = "abcd"
    grid = [{"name": f"{r}{c}", "page": 1, "row": i, "col": c} for i, r in enumerate(rows) for c in range(2)]
    code = {c["name"]: c["name"] for c in grid}
    blocks = [[f"{r}{c}" for r in rows[i:i + block_rows] for c in range(2)] for i in range(0, 4, block_rows)]
    t = {"id": "BT1", "blocks": blocks, "from": src}
    if confirmed:
        t["confirmed"] = "2026-10-27"
    rec = {"types": [t], "grids": [{"id": "p1-G1"}]}
    return rec, [{"id": "p1-G1", "status": "active", "by": "geometry", "grid": grid}], code


def test_a_geometry_grid_takes_unconfirmed_finder_blocks_that_cut_across_its_rows():
    # fl__sd_2924580 (2026-10-27): a 23-row entry table read as 2-row blocks; the table wins
    rec, grids, code = _rec_and_grid(2)
    assert gc.superseded(rec, grids, code, tentative=True) == ["BT1-1", "BT1-2"]


def test_and_blocks_that_are_its_rows():
    # bm__sd_1930130 p5 (2026-10-27): a 21-row tenant table read as 21 one-row blocks; "if it's in a grid it can't be
    # in a block", the table wins
    rec, grids, code = _rec_and_grid(1)
    assert gc.superseded(rec, grids, code, tentative=True) == ["BT1-1", "BT1-2", "BT1-3", "BT1-4"]
    assert rec["types"] == []


def test_but_not_confirmed_or_hand_made_blocks():
    rec, grids, code = _rec_and_grid(2, confirmed=True)
    assert gc.superseded(rec, grids, code, tentative=True) == []
    rec, grids, code = _rec_and_grid(1, src="drawn")
    assert gc.superseded(rec, grids, code, tentative=True) == []


def test_jev_scores_are_read_by_the_grid_fields():
    bp = {"fields": {"x": {"x_petey_id": "7"}, "y": {"x_petey_id": "3"}}}
    assert gc.grid_key(bp, [{"name": "x"}, {"name": "y"}]) == "3,7"
