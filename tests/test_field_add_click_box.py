"""Add / remove: a click inside a printed box that neither the form layer nor the finder has proposes that box
(field_add.enclosed_box; Andrew, 2026-10-27: "click inside a small box and it automatically selects that box as a field
to add")."""
import pymupdf

from petey.validate.field_add import enclosed_box


def _page(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    pg.draw_rect(pymupdf.Rect(100, 100, 300, 120), color=(0, 0, 0), width=0.8)       # a boxed text field
    pg.insert_text((104, 113), "Name", fontsize=8)                                    # a caption inside it
    for a, b in (((400, 300), (410, 300)), ((410, 300), (410, 310)), ((410, 310), (400, 310)), ((400, 310), (400, 300))):
        pg.draw_line(a, b, color=(0, 0, 0), width=0.8)                                # a checkbox of four lines
    pg.draw_line((100, 500), (300, 500), color=(0, 0, 0), width=0.8)                  # an open blank on a line
    p = tmp_path / "f.pdf"
    doc.save(p)
    return p


def _near(r, want, tol=1.5):
    return all(abs(a - b) <= tol for a, b in zip(r, want))


def test_a_caption_left_of_the_click_is_left_out(tmp_path):
    r = enclosed_box(_page(tmp_path), 1, 200, 110)          # "Name" is printed at the cell's left
    assert r is not None and r[0] > 120 and _near([r[1], r[2], r[3]], [100, 300, 120])


def test_a_click_on_the_caption_itself_gives_the_whole_cell(tmp_path):
    r = enclosed_box(_page(tmp_path), 1, 110, 111)          # the caption is not left of the click: nothing trimmed
    assert r is not None and _near(r, [100, 100, 300, 120])


def test_a_checkbox_drawn_as_four_lines(tmp_path):
    r = enclosed_box(_page(tmp_path), 1, 405, 305)
    assert r is not None and _near(r, [400, 300, 410, 310])


def test_an_open_underline_is_not_a_box(tmp_path):
    assert enclosed_box(_page(tmp_path), 1, 200, 495) is None
