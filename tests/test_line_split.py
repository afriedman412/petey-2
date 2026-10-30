"""One ruled line holding several fields (2026-10-27, eval/line_split.py): cut at printed column rules, or at the
captions of a header row / under the line when Jev agrees; captions that belong to another row are not used."""
import pymupdf

import line_split as LS


def _page():
    return pymupdf.open().new_page(width=612, height=792)


def _line(p, x0, x1, y):
    p.draw_line((x0, y), (x1, y), color=(0, 0, 0), width=0.5)


def test_column_rules_cut_a_box_combs_stay_whole():
    vs = [(200, 90, 110), (300, 90, 110)]
    assert [round(r[0]) for r in LS.vertical_parts([100, 95, 400, 108], vs)] == [100, 200, 300]
    comb = [(100 + 12 * k, 90, 110) for k in range(1, 6)]                     # 12 pt cells: a comb
    assert LS.vertical_parts([100, 95, 172, 108], comb) == []
    assert LS.vertical_parts([100, 95, 400, 108], [(250, 50, 60)]) == []     # a rule elsewhere on the page


def test_a_box_hanging_into_the_next_cell_is_trimmed_not_split():
    # fl__sd_3363802: the box starts 8 pt inside the green label cell; a double rule at the cell's edge
    assert LS.vertical_parts([100, 95, 400, 108], [(107, 90, 110), (109, 90, 110)]) == [[109, 95, 400, 108]]


def test_a_part_on_a_tinted_label_cell_is_dropped():
    p = _page()
    p.draw_rect((20, 100, 110, 114), color=None, fill=(0.8, 1, 0.8))        # the green label cell
    p.draw_line((110, 100), (110, 114), color=(0, 0, 0), width=0.5)
    pg = LS.Page(p, [])
    assert pg.off_labels(LS.vertical_parts([60, 101, 400, 113], pg.verticals)) == [[110, 101, 400, 113]]


def test_header_over_a_stack_cuts_every_line_midway_between_headings():
    # fl__sd_1443547's pick-up table: headings over five equal lines; the first line cut like the rest
    p = _page()
    for x, t in ((90, "Name"), (230, "Address"), (380, "Phone")):
        p.insert_text((x, 300), t, fontname="helv", fontsize=10)
    for y in (320, 342, 364):
        _line(p, 60, 520, y)
    pg = LS.Page(p, [])
    cuts = []
    for y in (320, 342, 364):
        cl, how = pg.captions([60, y - 14, 520, y])
        assert how == "stack"
        cuts.append([round(r[2]) for r in LS.caption_parts([60, y - 14, 520, y], cl, how)][:-1])
    assert cuts[0] == cuts[1] == cuts[2] and len(cuts[0]) == 2


def test_cell_captions_over_a_stack_cut_where_each_starts():
    # bm__sd_1698411: ADDRESS | CITY | STATE printed at the top-left of cells under a rule; the column starts there
    p = _page()
    _line(p, 60, 520, 290)
    for x, t in ((62, "ADDRESS"), (300, "CITY"), (420, "STATE")):
        p.insert_text((x, 298), t, fontname="helv", fontsize=6)
    for y in (312, 340):
        _line(p, 60, 520, y)
    cl, how = LS.Page(p, []).captions([60, 300, 520, 312])
    assert how == "header"
    assert [round(r[0]) for r in LS.caption_parts([60, 300, 520, 312], cl, how)] == [60, 298, 418]


def test_captions_under_a_line():
    p = _page()
    _line(p, 72, 500, 400)
    for x, t in ((72, "City"), (300, "State"), (400, "ZIP")):
        p.insert_text((x, 410), t, fontname="helv", fontsize=7)
    cl, how = LS.Page(p, []).captions([72, 386, 500, 400])
    assert how == "below" and [round(c.x0) for c in cl] == [72, 300, 400]


def test_a_captioned_cell_does_not_take_the_next_rows_captions():
    # bm__sd_1698411: NAME OF SCHOOL at the cell's top-left; CITY / STATE under its bottom rule head the next row
    p = _page()
    p.insert_text((72, 388), "NAME OF SCHOOL", fontname="helv", fontsize=6)
    _line(p, 72, 500, 400)
    for x, t in ((72, "ADDRESS"), (300, "CITY"), (400, "STATE")):
        p.insert_text((x, 408), t, fontname="helv", fontsize=6)
    assert LS.Page(p, []).captions([72, 390, 500, 400]) == ([], None)


def test_a_box_labelled_at_its_left_takes_the_captions_under_it():
    # fl__sd_7919716: LAST / FIRST / MIDDLE under the NAME line sit over PRESENT ADDRESS's left end; its own captions
    # are STREET / CITY / STATE under its line
    p = _page()
    _line(p, 66, 450, 139)
    for x, t in ((120, "LAST"), (220, "FIRST"), (390, "MIDDLE")):
        p.insert_text((x, 146), t, fontname="helv", fontsize=6)
    p.insert_text((37, 170), "PRESENT ADDRESS", fontname="helv", fontsize=7)
    _line(p, 110, 450, 170)
    for x, t in ((150, "STREET"), (260, "CITY"), (360, "STATE")):
        p.insert_text((x, 177), t, fontname="helv", fontsize=6)
    pg = LS.Page(p, [])
    cl, how = pg.captions([110, 156, 450, 170])
    assert how == "below" and [pg.text(c) for c in cl] == ["STREET", "CITY", "STATE"]


def test_a_diagonal_watermark_is_not_a_caption():
    p = _page()
    _line(p, 72, 500, 400)
    for x, t in ((72, "City"), (300, "State")):
        p.insert_text((x, 410), t, fontname="helv", fontsize=7)
    p.insert_text((200, 412), "BOSSLADY", fontname="helv", fontsize=30, morph=(pymupdf.Point(200, 412), pymupdf.Matrix(-30)))
    pg = LS.Page(p, [])
    cl, how = pg.captions([72, 386, 500, 400])
    assert how == "below" and [pg.text(c) for c in cl] == ["City", "State"]


def test_checkbox_labels_are_not_column_captions():
    p = _page()
    _line(p, 72, 500, 400)
    for x, t in ((90, "Married"), (250, "Single"), (400, "Widowed")):
        p.draw_rect((x - 12, 402, x - 4, 410), color=(0, 0, 0), width=0.5)
        p.insert_text((x, 410), t, fontname="helv", fontsize=8)
    assert LS.Page(p, []).captions([72, 386, 500, 400]) == ([], None)


def test_a_stack_is_not_climbed_past_a_row_with_its_own_caption():
    # bm__sd_7180896: NAME: LAST FIRST INITIAL heads the first row only; the STATE row below has its own caption
    p = _page()
    for x, t in ((72, "LAST"), (200, "FIRST"), (330, "INITIAL")):
        p.insert_text((x, 300), t, fontname="helv", fontsize=7)
    for y in (320, 350):
        _line(p, 60, 520, y)
    p.insert_text((62, 330), "STATE", fontname="helv", fontsize=6)
    _line(p, 60, 520, 380)
    pg = LS.Page(p, [])
    assert pg.captions([60, 306, 520, 320])[1] == "stack"
    assert pg.captions([60, 366, 520, 380]) == ([], None)


def test_captions_with_symbol_font_boxes_are_option_labels():
    p = _page()
    _line(p, 72, 500, 400)
    for x, t in ((90, "Single"), (250, "Married"), (400, "Other")):
        p.insert_text((x - 10, 410), "q", fontname="zadb", fontsize=8)
        p.insert_text((x, 410), t, fontname="helv", fontsize=8)
    assert LS.Page(p, []).captions([72, 386, 500, 400]) == ([], None)


def test_apply_replaces_the_box_with_numbered_parts():
    boxes = [{"id": "1", "page": 1, "rect": [60, 306, 520, 320], "kind": "text"},
             {"id": "2", "page": 1, "rect": [60, 330, 520, 342], "kind": "text"}]
    plans = [{"box": boxes[0], "how": "stack", "parts": [[60, 306, 200, 320], [200, 306, 520, 320]], "captions": ["a", "b"]},
             {"box": boxes[1], "how": "below", "parts": [[60, 330, 200, 342], [200, 330, 520, 342]], "captions": ["a", "b"]}]
    kept, made = LS.apply(boxes, boxes, plans, {"1": 0.82, "2": 0.4})       # Jev says one answer on line 2
    assert [(b["id"], b.get("split_from")) for b in kept] == [("3", "1"), ("4", "1"), ("2", None)]
    assert made == [{"box": "1", "page": 1, "how": "stack", "parts": ["3", "4"], "jev": 0.82, "captions": ["a", "b"]}]
