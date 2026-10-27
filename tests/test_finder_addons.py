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
