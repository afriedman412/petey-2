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
    out = bt.discover("t1", bp)
    assert {k: v for k, v in out.items() if k != "primed"} == {"grids": [], "superseded": [], "types": ["BT1"], "blocks": 3,
                                                              "fields": 9}
    (t,) = gc.load_set("t1")["types"]
    assert t["from"] == "finder (SIA)" and t["blocks"] == [["1_1", "1_2", "1_3"], ["1_4", "1_5", "1_6"], ["1_7", "1_8", "1_9"]]
    assert bt.discover("t1", bp)["types"] == []                       # nothing left in no block
