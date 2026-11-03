"""The "same kind of box" model in the finder (petey/validate/same_box.py, 2026-10-27; Andrew: "are these two boxes the
same type"): after SIA picks its blocks, a copy's box a few points shorter still takes its position; an empty position
takes a box set further along its line when its caption is alike; another kind or a far box with another caption never."""
import pymupdf

from petey.validate import block_discovery as D
from petey.validate import block_types as bt
from petey.validate import grid_check as gc
from petey.validate import same_box as sb


def _box(code, x0, y0, w, kind="textx1", h=14):
    return {"code": code, "page": 1, "rect": [x0, y0, x0 + w, y0 + h], "kind": kind}


def test_kind_distance_and_caption():
    a = _box("a", 100, 100, 150)
    near = _box("b", 104, 300, 140)
    assert sb.score(a, near, 0, 200, 60, 400, {"reason", "leaving"}, {"reason", "leaving"}) >= sb.KEEP
    assert sb.score(a, _box("c", 104, 300, 10, "checkboxx1"), 0, 200, 60, 400, set(), set()) == 0.0   # another kind
    far = _box("d", 130, 300, 150)                                                                     # 30 pt along
    assert sb.score(a, far, 0, 200, 60, 400, {"date", "birth"}, {"telephone", "number"}) == 0.0
    assert sb.score(a, far, 0, 200, 60, 400, {"rent", "up", "date"}, {"present", "rent", "up", "date"}) >= sb.KEEP


def _blank(tmp_path, rows):
    """A blank with `rows` [(caption, x, y, w)] printed and boxed; the blueprint with a text field per row."""
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    fields = {}
    for i, (cap, x, y, w) in enumerate(rows, 1):
        pg.insert_text((x, y - 3), cap, fontsize=7)
        fields[f"f{i}"] = {"type": "string", "x_petey_id": f"1_{i}",
                           "widget": {"page": 1, "widget_type": "text", "rect": [x, y, x + w, y + 14]}}
    doc.save(str(pdf))
    doc.close()
    return {"source_pdf": str(pdf), "fields": fields}


def _employment(step):
    """Three copies of a four-line employment section (bm__sd_2218681's flat copy): the last box `step` pt shorter in
    each copy than in the one before, so no two are alike (SIA's 3 pt) and plain SIA leaves the position out."""
    rows = []
    for b in range(3):
        y = 100 + 170 * b
        rows += [("Company", 50, y, 300), ("Job title", 50, y + 28, 300), ("Supervisor", 50, y + 56, 300),
                 ("Reason for leaving", 50, y + 84, 300 - step * b)]
    return rows


def test_a_copys_shorter_box_still_takes_its_position(tmp_path, monkeypatch):
    bp = _blank(tmp_path, _employment(6))
    (p,) = D.find(bp)
    assert p["slots"] == [["1_1", "1_2", "1_3", "1_4"], ["1_5", "1_6", "1_7", "1_8"], ["1_9", "1_10", "1_11", "1_12"]]
    monkeypatch.setattr(D, "grow_more", lambda occ, *a, **k: occ)          # plain SIA: the position left out
    (p,) = D.find(bp)
    assert [len(o) for o in p["slots"]] == [3, 3, 3]


def test_neighbouring_copies_are_not_glued(tmp_path):
    bp = _blank(tmp_path, _employment(0))
    pats = D.find(bp)
    assert [len(p["slots"]) for p in pats] == [3] and all(len(o) == 4 for o in pats[0]["slots"])


def test_an_empty_position_takes_a_box_further_along_its_line_with_its_caption(monkeypatch, tmp_path):
    monkeypatch.setattr(gc, "SETS", tmp_path)
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / f"{bid}.json")
    rows = [("Lived from", 50, 100, 80), ("Is present rent up to date?", 200, 100, 120), ("Phone", 400, 100, 120),
            ("Lived from", 50, 200, 80), ("Was rent up to date?", 222, 200, 120), ("Phone", 400, 200, 120)]
    bp = _blank(tmp_path, rows)
    bt.draw("t5", bp, 1, [45, 90, 530, 118])
    rec = gc.load_set("t5")
    t = rec["types"][0]
    t["blocks"].append(["1_4", None, "1_6"])                 # copy 2, its rent question 22 pt along its line
    assert bt.fill_blocks(bp, rec) == {"BT1-2": ["f5"]}
    rec2 = gc.load_set("t5")
    rec2["types"][0]["blocks"].append(["1_4", None, "1_6"])
    bp["fields"]["f5"]["widget"]["rect"] = [262, 200, 382, 214]      # 62 pt along: beyond the window, not taken
    assert bt.fill_blocks(bp, rec2) == {}
