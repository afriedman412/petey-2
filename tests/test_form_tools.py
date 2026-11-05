"""The header's form tools (Andrew, 2026-11-04: "take the 'run finders' button and make it a dropdown and then add
'split multiline blocks', 'add signatures' and 'add text groups'"): multi-line boxes cut only at printed lines,
signature places found from their captions, Claude's text groups kept only when they are clean."""
from pathlib import Path

import pymupdf

from petey.validate import form_tools as ft
from petey.validate import split_types

SRC = Path(__file__).resolve().parents[1] / "petey" / "validate" / "review_app" / "src"


def _pdf(tmp_path, draw) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    draw(page)
    p = tmp_path / "blank.pdf"
    doc.save(p)
    return p


def _text(x0, y0, x1, y1, page=1):
    return {"type": "string", "widget": {"page": page, "rect": [x0, y0, x1, y1], "widget_type": "text", "path": None}}


def test_a_box_over_drawn_lines_is_cut_at_each_line(tmp_path):
    def draw(pg):
        for y in (120, 140, 160):
            pg.draw_line((50, y), (550, y), width=0.5)
    blank = _pdf(tmp_path, draw)
    bp = {"fields": {"notes": _text(50, 100, 550, 180), "short": _text(50, 300, 550, 315)}}
    added, removed, notes = ft.split_proposals(bp, blank, now="t")
    assert [r["name"] for r in removed] == ["notes"]
    assert [a["name"] for a in added] == ["notes_line_1", "notes_line_2", "notes_line_3", "notes_line_4"]
    assert [a["rect"][1] for a in added] == [100, 120, 140, 160] and added[-1]["rect"][3] == 180
    assert notes == ["notes: 4 lines"]


def test_rows_of_printed_dots_are_lines_and_the_last_row_ends_the_box(tmp_path):
    def draw(pg):
        for y in (125, 150, 175):
            pg.insert_text((55, y), "." * 210, fontsize=9)
    blank = _pdf(tmp_path, draw)
    cuts = ft.line_cuts(pymupdf.open(blank)[0], [50, 105, 560, 178])
    assert len(cuts) == 2 and 120 < cuts[0] < 130 and 145 < cuts[1] < 155


def test_no_printed_lines_or_printed_words_inside_leave_the_box_whole(tmp_path):
    def draw(pg):
        pg.draw_line((50, 140), (550, 140), width=0.5)
        pg.insert_text((60, 160), "Total income", fontsize=9)      # words under the first line: a table cell
    blank = _pdf(tmp_path, draw)
    page = pymupdf.open(blank)[0]
    assert ft.line_cuts(page, [50, 120, 550, 180]) == []
    assert ft.line_cuts(page, [50, 300, 550, 380]) == []           # nothing printed there at all


def test_a_signature_line_with_its_caption_under_it_gets_a_field(tmp_path):
    def draw(pg):
        pg.draw_line((300, 200), (520, 200), width=0.8)
        pg.insert_text((300, 212), "Signature", fontsize=10)
        pg.draw_line((300, 260), (520, 260), width=0.8)
        pg.insert_text((300, 272), "Signature", fontsize=10)
    blank = _pdf(tmp_path, draw)
    added, notes = ft.signature_proposals({"fields": {"other": _text(300, 244, 520, 260)}}, blank, now="t")
    assert [a["name"] for a in added] == ["signature"]              # the second line already has a field
    a = added[0]
    assert a["rect"] == [300, 182, 520, 200] and a["printed"] and a["kind"] == "text"


def test_a_box_with_its_caption_inside_gets_a_field_but_a_heading_bar_does_not(tmp_path):
    def draw(pg):
        pg.draw_rect(pymupdf.Rect(40, 100, 560, 118), color=None, fill=(0.1, 0.1, 0.1))   # a dark heading bar
        pg.insert_text((50, 113), "Signature and acknowledgement", fontsize=11, color=(1, 1, 1))
        pg.draw_rect(pymupdf.Rect(340, 400, 540, 480), color=(0, 0, 0), width=0.7)
        pg.insert_text((346, 412), "Signature", fontsize=9)
    blank = _pdf(tmp_path, draw)
    added, _ = ft.signature_proposals({"fields": {}}, blank, now="t")
    assert [(a["name"], a["rect"]) for a in added] == [("signature", [340.0, 400.0, 540.0, 480.0])]


def test_signatures_sharing_a_caption_are_numbered_in_reading_order(tmp_path):
    def draw(pg):
        for y in (300, 200):
            pg.draw_line((300, y), (520, y), width=0.8)
            pg.insert_text((300, y + 12), "Signature", fontsize=10)
    added, _ = ft.signature_proposals({"fields": {}}, _pdf(tmp_path, draw), now="t")
    assert [(a["name"], a["rect"][3]) for a in added] == [("signature_1", 200), ("signature_2", 300)]


def test_clean_groups_keeps_two_or_more_free_fields_on_one_page():
    texts = {n: _text(x, 100, x + 30, 112) for n, x in (("mm", 100), ("dd", 140), ("yyyy", 180), ("taken", 220))}
    texts["p2"] = _text(260, 100, 290, 112, page=2)
    proposed = [{"name": "Date of birth", "entity_type": "date", "fields": ["yyyy", "mm", "dd", "mm"]},
                {"name": "x", "entity_type": "phone", "fields": ["taken", "dd"]},          # dd used, taken grouped
                {"name": "y", "entity_type": "nonsense", "fields": ["yyyy", "p2"]},        # two pages
                {"name": "z", "entity_type": "name", "fields": ["ghost", "p2"]},          # one real field
                {"name": "w", "entity_type": "name", "fields": ["taken", "p2", "dd"]}]     # a kind not offered
    out = ft.clean_groups(proposed, texts, {"taken"}, {"date_of_birth"})
    assert len(out) == 1
    u = out[0]
    assert (u["kind"], u["name"], u["entity_type"], u["items"]) == ("text", "date_of_birth_2", "date", ["mm", "dd", "yyyy"])


def test_the_quick_fix_menu_holds_the_five_tools():
    """Andrew, 2026-11-05: "add a 'rightsize check boxes' button", "change that dropdown menu to 'quick fix'"."""
    header = (SRC / "components" / "Header.tsx").read_text()
    assert "<FormTools bid={bid} />" in header and "'quick fix ▾'" in header and "'run finders ▾'" not in header
    for k, label in (("finders", "run finders"), ("split", "split multi-line boxes"), ("signatures", "add signatures"),
                     ("textgroups", "add text groups"), ("rightsize", "rightsize checkboxes")):
        assert f"k: '{k}', label: '{label}'" in header
    assert "mapi('tools', bid, '/' + t.k)" in header
    server = (Path(__file__).resolve().parents[1] / "petey" / "validate" / "blueprint_review.py").read_text()
    assert '("tools", "split"), ("tools", "signatures")' in server and '("tools", "textgroups")' in server
    assert '("tools", "rightsize")' in server


def test_text_groups_are_asked_for_the_counted_kinds_only():
    """Andrew, 2026-11-04: "pare this down to the ones we care about": the prompt and the schema offer the taxonomy's
    counted kinds (dates, phones, ID numbers) and name the others as not text groups."""
    kinds = split_types.counted()
    assert ft.TEXT_KINDS == kinds == ("date", "phone", "id_number")
    enum = ft.TEXT_SCHEMA["properties"]["groups"]["items"]["properties"]["entity_type"]["enum"]
    assert tuple(enum) == kinds
    for k in kinds:
        assert f"- {k}: " in ft.TEXT_SYSTEM
    for k in set(split_types.names()) - set(kinds):
        assert f"- {k}: " not in ft.TEXT_SYSTEM
    assert "Not text groups: name parts" in ft.TEXT_SYSTEM


def _check(x0, y0, x1, y1, page=1):
    return {"type": "boolean", "widget": {"page": page, "rect": [x0, y0, x1, y1], "widget_type": "checkbox", "path": None}}


def test_a_checkbox_bigger_than_its_printed_square_shrinks_to_it(tmp_path):
    blank = _pdf(tmp_path, lambda pg: pg.draw_rect(pymupdf.Rect(100, 100, 110, 110), width=0.6))
    bp = {"fields": {"agree": _check(96, 97, 140, 114)}}
    changes, notes = ft.rightsize_proposals(bp, blank)
    assert changes == [("agree", None, [100.0, 100.0, 110.0, 110.0])]
    assert ft.rightsize(bp, changes) and bp["fields"]["agree"]["widget"]["rect"] == [100.0, 100.0, 110.0, 110.0]


def test_a_checkbox_smaller_than_its_printed_circle_grows_to_it(tmp_path):
    blank = _pdf(tmp_path, lambda pg: pg.draw_circle((205, 205), 6, width=0.6))
    opts = {"yes": {"page": 1, "rect": [202, 202, 208, 208], "widget_type": "radiobutton", "on_state": "yes"}}
    bp = {"fields": {"answer": {"type": "string", "widgets": opts}}}
    (n, k, r), = ft.rightsize_proposals(bp, blank)[0]
    assert (n, k) == ("answer", "yes") and all(abs(a - b) < 0.6 for a, b in zip(r, [199, 199, 211, 211]))


def test_a_checkbox_a_little_off_its_square_still_snaps_to_it(tmp_path):
    """Leniency: most of the printed square inside the field is enough."""
    blank = _pdf(tmp_path, lambda pg: pg.draw_rect(pymupdf.Rect(100, 100, 110, 110), width=0.6))
    bp = {"fields": {"agree": _check(98, 98, 108.5, 112)}}
    assert ft.rightsize_proposals(bp, blank)[0] == [("agree", None, [100.0, 100.0, 110.0, 110.0])]


def test_a_checkbox_over_two_squares_or_already_right_is_left_alone(tmp_path):
    def draw(pg):
        for x in (100, 130, 300):
            pg.draw_rect(pymupdf.Rect(x, 100, x + 10, 110), width=0.6)
    blank = _pdf(tmp_path, draw)
    bp = {"fields": {"both": _check(95, 95, 145, 115), "fine": _check(299.6, 99.6, 310.4, 110.4),
                     "text": _text(290, 95, 320, 115)}}
    changes, notes = ft.rightsize_proposals(bp, blank)
    assert changes == [] and notes == ["p1 both: over 2 printed boxes, left as it is"]


def test_a_square_drawn_white_is_no_printed_box(tmp_path):
    """bm__sd_7908813 p1: an unstroked white square behind each printed one (a typed box character there)."""
    def draw(pg):
        pg.draw_rect(pymupdf.Rect(95, 95, 113, 113), color=None, fill=(1, 1, 1))
        pg.draw_rect(pymupdf.Rect(200, 100, 208, 108), width=0.6)
    blank = _pdf(tmp_path, draw)
    doc = pymupdf.open(blank)
    assert ft.printed_marks(doc[0]) == [[200.0, 100.0, 208.0, 108.0]]


def test_a_checkbox_in_a_table_cell_is_not_grown_to_the_cell(tmp_path):
    """lib__gsa_sf_26 p1: an "(X)" column's cells hold no printed box."""
    def draw(pg):
        for y in (100, 114, 128):
            pg.draw_line((50, y), (400, y), width=0.6)
        for x in (50, 200, 217, 400):
            pg.draw_line((x, 100), (x, 128), width=0.6)
    blank = _pdf(tmp_path, draw)
    bp = {"fields": {"included": _check(203, 102, 213, 112)}}
    assert ft.rightsize_proposals(bp, blank) == ([], [])


def test_a_radio_printed_already_marked_is_not_shrunk_to_the_ring_round_its_dot(tmp_path):
    """bm__sd_4920315 p1: no drawn circle the finder takes (a dotted ring alone is a printed marker), and the white
    between the dot and the outline is no box."""
    def draw(pg):
        pg.draw_circle((105, 105), 6, width=1.5)
        pg.draw_circle((105, 105), 2.5, color=None, fill=(0, 0, 0))
    blank = _pdf(tmp_path, draw)
    bp = {"fields": {"full_time": _check(98, 96, 112, 113)}}
    assert ft.rightsize_proposals(bp, blank) == ([], [])
