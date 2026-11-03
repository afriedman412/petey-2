"""The finder's minor-2 rules (2026-10-27): hollow glyph squares, small drawn squares and underlines read off the PDF's
own drawings and characters, added on top of the finder's boxes without moving them."""
import pymupdf

from petey.synth import finder_addons as FA
from petey.synth.boxes import _rect_key


def _page():
    return pymupdf.open().new_page(width=612, height=792)


def test_hollow_glyph_squares_whatever_their_code_point():
    # ZapfDingbats 'o' (shadowed box) and 'q' (box) are found; its filled square 'n', a check mark '4' and a
    # Helvetica letter o are not
    p = _page()
    for x, c, font in ((100, "o", "zadb"), (150, "n", "zadb"), (200, "4", "zadb"), (250, "q", "zadb"), (300, "o", "helv")):
        p.insert_text((x, 100), c, fontname=font, fontsize=12)
    got = FA.glyph_square_rects(p)
    assert sorted(round(r.x0) for r in got) == [101, 251]
    assert all(7 <= r.width <= 10 and 7 <= r.height <= 10 for r in got)


def test_small_drawn_squares_but_not_bullets_or_big_boxes():
    p = _page()
    p.draw_rect((100, 100, 105.9, 105.4), color=(0, 0, 0), width=0.5)        # 1698411's 5.9 x 5.4 checkbox
    p.draw_rect((150, 100, 156, 106), color=None, fill=(0, 0, 0))           # a bullet
    p.draw_rect((200, 100, 240, 140), color=(0, 0, 0))                      # a cell, not a checkbox
    got = FA.square_rects(p)
    assert [round(r.x0) for r in got] == [100]


def test_underline_band_above_a_line_split_by_a_word_on_it():
    p = _page()
    p.insert_text((72, 200), "Name", fontname="helv", fontsize=10)
    p.draw_line((100, 200), (300, 200), color=(0, 0, 0), width=0.5)
    p.insert_text((310, 200), "Date", fontname="helv", fontsize=10)
    p.draw_line((300, 200), (450, 200), color=(0, 0, 0), width=0.5)       # one stroke under both, "Date" printed on it
    got = sorted(FA.underline_rects(p), key=lambda r: r.x0)
    assert len(got) == 2
    assert round(got[0].x0) == 100 and got[0].x1 < 310 and round(got[1].x0) >= 330 and round(got[1].x1) == 450
    assert all(round(r.y1) == 200 and r.height == FA.LINE_BAND for r in got)


def test_typed_underscore_run_fused_to_its_label():
    p = _page()
    p.insert_text((72, 300), "Name:____________________", fontname="helv", fontsize=10)
    got = FA.underline_rects(p)
    assert len(got) == 1
    assert got[0].x0 > 100 and got[0].width > 80                            # the run, not the label


def test_stacked_rules_are_a_table_not_underlines():
    p = _page()
    for y in (400, 404):                                                    # a double rule
        p.draw_line((72, y), (500, y), color=(0, 0, 0), width=0.5)
    assert all(r.y1 != 404 for r in FA.underline_rects(p))


def test_added_boxes_leave_the_finders_boxes_alone(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    p.draw_rect((100, 100, 105.9, 105.4), color=(0, 0, 0), width=0.5)
    p.insert_text((72, 200), "Name", fontname="helv", fontsize=10)
    p.draw_line((100, 200), (300, 200), color=(0, 0, 0), width=0.5)
    pdf = tmp_path / "blank.pdf"
    doc.save(str(pdf))
    base = [{"id": "1", "page": 1, "rect": [100, 186, 300, 200], "kind": "text"}]      # the finder has the line
    got = FA.added_boxes(pdf, base, _rect_key)
    assert [(b["id"], b["kind"], b["addon"]) for b in got] == [("2", "checkbox", "squares")]


# minor 3 (2026-10-27): bm__sd_394533 p1's 17 pt beveled radios, bm__sd_395088 p7's squares

def _ring(p, x, y, r=8.5, dot=False):
    p.draw_circle((x, y), r, color=(0, 0, 0), width=1)
    if dot:
        p.draw_circle((x, y), 3.5, color=None, fill=(0, 0, 0))


def test_circles_up_to_20_pt_and_a_printed_default_beside_its_row():
    p = _page()
    for i, x in enumerate((100, 123, 146, 169, 192)):         # a row of 17 pt options, the first printed marked
        _ring(p, x, 100, dot=i == 0)
    _ring(p, 100, 200, r=4.5, dot=True)                          # a lone dotted marker (CA 540's line markers)
    _ring(p, 180, 200, r=4.5)                                    # an empty one far along the line is no row-mate
    got = sorted(round(r.x0) for r in FA.circle_rects(p))
    assert got == [92, 114, 138, 160, 176, 184]                  # the row with its marked first, the empty far ring


def test_squares_up_to_20_pt_once_as_the_outer_square():
    p = _page()
    p.draw_rect((100, 100, 117, 117), color=(0, 0, 0), width=1)              # a beveled box: outer edge
    p.draw_rect((102.5, 102.5, 114.5, 114.5), color=(0, 0, 0), width=1)      # and its inner edge
    got = FA.square_rects(p)
    assert [(round(r.x0), round(r.width)) for r in got] == [(100, 17)]


def test_the_finders_comb_keeps_its_cells_out_but_touching_checkboxes_stay(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    for i in range(6):                                                       # six digit cells, 2 pt apart
        p.draw_rect((100 + 17 * i, 100, 115 + 17 * i, 115), color=(0, 0, 0), width=0.5)
    for y in (200, 213):                                                     # two checkboxes stacked, touching
        p.draw_rect((100, y, 113, y + 13), color=(0, 0, 0), width=0.5)
    pdf = tmp_path / "blank.pdf"
    doc.save(str(pdf))
    base = [{"id": "1", "page": 1, "rect": [100, 100, 200, 115], "kind": "comb"}]
    got = FA.added_boxes(pdf, base, _rect_key)
    assert [(b["kind"], round(b["rect"][1])) for b in got] == [("checkbox", 200), ("checkbox", 213)]


def test_a_mark_is_kept_out_only_by_an_option_box_of_its_size(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page(width=612, height=792)
    for x in (100, 123, 146):
        _ring(p, x, 100)
    p.draw_rect((300, 100, 312, 112), color=(0, 0, 0), width=0.5)
    pdf = tmp_path / "blank.pdf"
    doc.save(str(pdf))
    base = [{"id": "1", "page": 1, "rect": [90, 90, 157, 110], "kind": "text"},        # one strip over the row
            {"id": "2", "page": 1, "rect": [117, 94, 129, 106], "kind": "text"},       # a ring's middle read as text
            {"id": "3", "page": 1, "rect": [140, 91.5, 152, 108.5], "kind": "checkbox"},  # the finder had this one
            {"id": "4", "page": 1, "rect": [303, 103, 309, 109], "kind": "checkbox"}]   # a bit inside the square
    got = FA.added_boxes(pdf, base, _rect_key)
    assert [(b["kind"], round(b["rect"][0])) for b in got] == [("radio", 92), ("radio", 114), ("checkbox", 300)]


def test_a_run_of_close_squares_is_a_comb_but_a_touching_pair_is_two_checkboxes():
    p = _page()
    for i in range(5):                                                       # five 15 x 16.7 cells, touching
        p.draw_rect((100 + 15 * i, 100, 115 + 15 * i, 116.7), color=(0, 0, 0), width=0.5)
    for x in (100, 106.6):                                                   # 2044009's touching pair of 6 pt boxes
        p.draw_rect((x, 200, x + 6.3, 208.3), color=(0, 0, 0), width=0.5)
    for x in (100, 122, 144):                                                # a row of 17 pt options 5 pt apart
        p.draw_rect((x, 300, x + 17, 317), color=(0, 0, 0), width=0.5)
    got = FA.square_rects(p)
    assert sorted((round(r.y0), round(r.x0)) for r in got) == [(200, 100), (200, 107), (300, 100), (300, 122), (300, 144)]
