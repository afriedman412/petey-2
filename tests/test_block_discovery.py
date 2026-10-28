"""Block discovery (petey/validate/block_discovery.py, SIA, 2026-10-22): repeated blocks found with no template, kept
when each copy has 3+ fields, not all tick boxes, and each slot's printed caption repeats."""
import pymupdf

from petey.validate import block_discovery as D


def _form(tmp_path, blocks, kinds, captions, step=80, x0=50):
    """A blank with `blocks` copies, `step` pt apart down page 1, each a row of boxes of `kinds` captioned by
    `captions` (a caption per block per box, so copies can print different ones), and its blueprint."""
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    fields, i = {}, 0
    for b in range(blocks):
        y = 100 + step * b
        for k, kind in enumerate(kinds):
            i += 1
            x = x0 + 170 * k
            w = 10 if kind == "checkbox" else 150
            pg.insert_text((x, y - 4), captions[b][k], fontsize=8)
            fields[f"f{i}"] = {"type": "string", "x_petey_id": f"1_{i}",
                               "widget": {"page": 1, "widget_type": kind, "rect": [x, y, x + w, y + 14]}}
    doc.save(str(pdf))
    doc.close()
    return {"source_pdf": str(pdf), "fields": fields}


def test_repeated_blocks_are_found(tmp_path):
    caps = [[f"Child {b + 1} name", "Date of birth", "City of birth"] for b in range(3)]
    bp = _form(tmp_path, 3, ["text", "text", "text"], caps)
    (p,) = D.find(bp)
    assert p["boxes"] == 3 and p["slots"] == [["1_1", "1_2", "1_3"], ["1_4", "1_5", "1_6"], ["1_7", "1_8", "1_9"]]


def test_two_fields_are_no_block(tmp_path):
    caps = [[f"Child {b + 1} name", "Date of birth"] for b in range(3)]
    assert D.find(_form(tmp_path, 3, ["text", "text"], caps)) == []


def test_a_list_of_different_questions_is_no_block(tmp_path):
    """Andrew (2026-10-22): lists of Yes / No questions laid out alike (I-360) are no block."""
    caps = [["Yes", "No", "Unknown"] for _ in range(3)]
    assert D.find(_form(tmp_path, 3, ["checkbox", "checkbox", "checkbox"], caps)) == []


def test_copies_whose_captions_differ_are_no_block(tmp_path):
    """Same boxes, different things (IRS line items sharing boxes): the captions do not repeat."""
    caps = [["Gross receipts", "Returns", "Cost of goods"], ["Wages", "Rents", "Taxes"],
            ["Interest", "Depletion", "Repairs"]]
    assert D.find(_form(tmp_path, 3, ["text", "text", "text"], caps)) == []


def test_no_blank_no_blocks(tmp_path):
    bp = _form(tmp_path, 3, ["text", "text", "text"], [["a b", "c d", "e f"]] * 3)
    bp["source_pdf"] = str(tmp_path / "missing.pdf")
    assert D.find(bp) == []


def test_run_finders_saves_the_blocks_found_as_a_type(tmp_path, monkeypatch):
    """The review page's "run finders" (Andrew, 2026-10-23): SIA's pattern saved as a block type, its copies its
    blocks, marked as the finder's; fields already in a block stay where they are."""
    from petey.validate import block_types as bt, grid_check as gc
    monkeypatch.setattr(gc, "SETS", tmp_path / "sets")
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / "sets" / f"{bid}.json")
    caps = [[f"Child {b + 1} name", "Date of birth", "City of birth"] for b in range(3)]
    bp = _form(tmp_path, 3, ["text", "text", "text"], caps)
    monkeypatch.setattr(gc, "geometric", lambda *a, **k: False)       # no grid here: see the next test
    out = bt.discover("t1", bp)
    assert {k: v for k, v in out.items() if k != "primed"} == {"grids": [], "superseded": [], "types": ["BT1"], "blocks": 3,
                                                              "fields": 9}
    (t,) = gc.load_set("t1")["types"]
    assert t["from"] == "finder (SIA)" and t["blocks"] == [["1_1", "1_2", "1_3"], ["1_4", "1_5", "1_6"], ["1_7", "1_8", "1_9"]]
    assert bt.discover("t1", bp)["types"] == []                       # nothing left in no block


def test_page_sized_copies_give_way_to_the_wines_they_are_made_of():
    # fl__sd_252381 pp. 3-8 (2026-10-27): three wines of 7 fields a page; the page as one copy, a field or two of its
    # third wine left out (a vintage line whose caption differs), still gives way to the 18 wines
    wine = lambda p, w: {f"p{p}w{w}f{k}" for k in range(7)}
    wines = [wine(p, w) for p in range(6) for w in range(3)]
    pages = [wine(p, 0) | wine(p, 1) | (wine(p, 2) - {f"p{p}w2f5", f"p{p}w2f6"}) for p in range(6)]
    sets = [pages, wines]
    assert D._glued(0, sets) and not D._glued(1, sets)


def test_a_big_block_holding_one_small_copy_stays():
    small = [{f"s{i}a", f"s{i}b", f"s{i}c"} for i in range(4)]
    big = [small[0] | {f"x{k}" for k in range(10)}, small[1] | {f"y{k}" for k in range(10)}]
    assert not D._glued(0, [big, small])


def test_run_finders_makes_no_blocks_inside_a_grid(tmp_path, monkeypatch):
    """Andrew (2026-10-27): "if it's in a grid it can't be in a block and v/v ... especially when re-running the finder";
    one-line rows under the same captions are a table ("wouldn't 'child 1/2/3' just be the row labels?"): no type made,
    the grid stays, and running it again changes nothing."""
    from petey.validate import block_types as bt, grid_check as gc
    monkeypatch.setattr(gc, "SETS", tmp_path / "sets")
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / "sets" / f"{bid}.json")
    caps = [[f"Child {b + 1} name", "Date of birth", "City of birth"] for b in range(3)]
    bp = _form(tmp_path, 3, ["text", "text", "text"], caps)
    for _ in range(2):
        out = bt.discover("t2", bp)
        assert out["types"] == [] and out["superseded"] == [] and len(out["grids"]) == 1
    assert not gc.load_set("t2").get("types")


def _columns(tmp_path, right_x, step):
    """Two parties down page 1, `step` pt apart, each three stacked boxes on the left (Name / Address / Email) and three
    at `right_x` (Company / Phone / Date), narrower, captions over each box (bm__sd_3867602 p2, 2026-10-27)."""
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    fields, i = {}, 0
    for b in range(2):
        for x, w, caps in ((50, 150, ("Name", "Address", "Email")), (right_x, 110, ("Company", "Phone", "Date"))):
            for r, cap in enumerate(caps):
                i += 1
                y = 100 + step * b + 22 * r
                pg.insert_text((x, y - 4), cap, fontsize=8)
                fields[f"f{i}"] = {"type": "string", "x_petey_id": f"1_{i}",
                                   "widget": {"page": 1, "widget_type": "text", "rect": [x, y, x + w, y + 14]}}
    doc.save(str(pdf))
    doc.close()
    return {"source_pdf": str(pdf), "fields": fields}


def test_two_columns_that_move_together_are_one_block(tmp_path):
    """bm__sd_3867602 p2 (Andrew, 2026-10-27): each party's two columns 40 pt apart, past GAP, were two block types;
    each copy's columns sit at the same shift, nearer each other than the next party: one block of six."""
    (p,) = D.find(_columns(tmp_path, 240, 120))
    assert p["boxes"] == 6 and sorted(map(sorted, p["slots"])) == [["1_1", "1_2", "1_3", "1_4", "1_5", "1_6"],
                                                                  ["1_10", "1_11", "1_12", "1_7", "1_8", "1_9"]]


def test_two_lists_side_by_side_stay_apart(tmp_path):
    """The same columns 200 pt apart, the parties 90 pt apart: each column nearer its own next copy than the other
    column, two lists that repeat alike, not one block."""
    found = D.find(_columns(tmp_path, 400, 90))
    assert len(found) == 2 and all(p["boxes"] == 3 for p in found)
