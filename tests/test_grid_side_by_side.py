"""Tables side by side (grid_check.side_by_side, 2026-10-27; Andrew: "every row is a single data point, and every column
relates to that data point alone"; bm__sd_1034080 p4-G1, two Amount / Begin Date / End Date tables found as one): a set
of row labels printed between two columns, or column headings that start over, cuts the grid there."""
import pymupdf

from petey.validate import grid_check as gc


def _page(tmp_path, rows, heads, gap_text=None, row_labels=True):
    """`rows` rows of boxes under `heads` (one column each); `gap_text(r)` printed between the third and fourth
    columns, which are set wider apart; the left table's row labels at the left edge."""
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    fields, cells = {}, []
    xs = []
    x = 120
    for c in range(len(heads)):
        if c == 3:
            x += 110                                        # the gap where the second table's row labels go
        xs.append(x)
        x += 70
    for c, t in enumerate(heads):
        pg.insert_text((xs[c], 110), t, fontsize=8)
    for r in range(rows):
        y = 120 + 16 * r
        if row_labels:
            pg.insert_text((40, y + 11), LEFT[r], fontsize=8)
        if gap_text and gap_text(r):
            pg.insert_text((xs[2] + 66, y + 11), gap_text(r), fontsize=8)
        for c in range(len(heads)):
            n = f"r{r}c{c}"
            fields[n] = {"type": "string", "x_petey_id": n,
                         "widget": {"page": 1, "rect": [xs[c], y, xs[c] + 60, y + 14], "widget_type": "text"}}
            cells.append({"name": n, "page": 1, "row": r, "col": c})
    p = tmp_path / "f.pdf"
    doc.save(p)
    return {"source_pdf": str(p), "fields": fields}, cells


LEFT = ["Wages", "Pension", "Disability", "Interest"]
HEADS = ["Amount", "Begin Date", "End Date"]
OTHER = ["Unemployment", "Other benefits", "Wage replacement", "Pension"]


def test_row_labels_between_two_columns_make_two_tables(tmp_path):
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"], gap_text=lambda r: OTHER[r])
    pieces = gc.side_by_side(bp, g)
    assert [(len({c["row"] for c in p}), len({c["col"] for c in p})) for p in pieces] == [(4, 3), (4, 3)]
    assert {c["name"] for c in pieces[1]} == {f"r{r}c{c}" for r in range(4) for c in (3, 4, 5)}
    assert {c["col"] for c in pieces[1]} == {0, 1, 2}                 # each piece numbered from 0


def test_repeated_headings_make_two_tables(tmp_path):
    bp, g = _page(tmp_path, 4, HEADS + HEADS, row_labels=False)
    assert list(gc.split_points(bp, g)) == [3]
    assert len(gc.side_by_side(bp, g)) == 2


def test_one_caption_repeated_between_columns_is_not_a_row_label(tmp_path):
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"], gap_text=lambda r: "to")
    assert gc.side_by_side(bp, g) == [g]


def test_one_table_stays_one(tmp_path):
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"])
    assert gc.side_by_side(bp, g) == [g]


def test_the_pieces_keep_the_test_that_found_the_whole(tmp_path):
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"], gap_text=lambda r: OTHER[r])
    import petey.validate.grid_naming as G
    G_grids = G.grids
    try:
        G.grids = lambda bp, blocks=False: [g]
        got = gc.found_pairs(bp)
    finally:
        G.grids = G_grids
    assert len(got) == 2 and {by for _g, by in got} == {gc.found_by(bp, g)}


def test_a_label_mid_row_with_none_at_the_left_is_one_data_point(tmp_path):
    # je__ircc_imm_5645 p1: Name, then Applicant / Spouse / Mother / Father, then that person's other fields
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"], gap_text=lambda r: OTHER[r], row_labels=False)
    assert gc.side_by_side(bp, g) == [g]


def test_repeated_headings_under_labelled_rows_are_columns_of_one_row(tmp_path):
    # lib__ao044 p1: Pages / Price under Original and again under 1st Copy, the categories at the left
    bp, g = _page(tmp_path, 4, HEADS + HEADS)
    assert gc.side_by_side(bp, g) == [g]


def test_pieces_of_a_cancelled_grid_start_cancelled(tmp_path, monkeypatch):
    import json
    import petey.validate.grid_naming as G
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"], gap_text=lambda r: OTHER[r])
    monkeypatch.setattr(G, "grids", lambda bp, blocks=False: [g])
    monkeypatch.setattr(gc, "found_by", lambda bp, g: "geometry")
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / f"{bid}.json")
    monkeypatch.setattr(gc, "not_grids", lambda bid: [])
    whole = {"id": "p1-G1", "kind": "table", "page": 1, "source": "finder", "status": "cancelled",
             "cells": [[c["name"], c["row"], c["col"]] for c in g]}
    (tmp_path / "x.json").write_text(json.dumps({"grids": [whole], "next": {"1G": 2}, "types": []}))
    got = gc.listing("x", bp)
    assert [t["id"] for t in got] == ["p1-G2", "p1-G3"] and {t["status"] for t in got} == {"cancelled"}


def test_the_light_path_finder_cuts_them_too(tmp_path):
    from petey.label import structure as S
    bp, g = _page(tmp_path, 4, HEADS + ["Paid", "From", "To"], gap_text=lambda r: OTHER[r])
    entries = [{"id": i, "page": 1, "rect": bp["fields"][c["name"]]["widget"]["rect"], "widget_type": "text"}
               for i, c in enumerate(g, 1)]
    tables = S.find(tmp_path / "f.pdf", entries)[1]["tables"]
    assert sorted((t["rows"], t["cols"]) for t in tables) == [(4, 3), (4, 3)]
