"""Filling a test case into the blank through its form fields (petey/synth/render.py) and the expected values the
scorer reads from it (petey/validate/rect_join.py, petey/validate/validate._bank_case).

The case is keyed by the page finder's cells; the blank's widgets are the form layer's. Where the finder splits one
widget into several cells (Form 8825's two-line address box, a comb), the filler writes one string into the widget
and the expected value is that string. 2026-10-20: frozen cases held that joined string, so every reuse joined it
again ("Omar Fischer, 1120" x2, x4) on 27 forms since 2026-09-30."""
import json

import pymupdf
import pytest

from petey.synth import render
from petey.synth.render import _join_cells, render_case
from petey.validate import validate
from petey.validate.rect_join import case_to_paths

ADDR = "topmostSubform[0].Page1[0].Table_Line1[0].RowA[0].Col_a[0].f1_3[0]"   # two lines tall, one widget
LINE1, LINE2 = "p1:58.2,180.8,200.8,191.2", "p1:58.6,193.4,200.6,203.0"     # the finder's two cells inside it
NAME = "topmostSubform[0].Page1[0].f1_1[0]"
NAME_CELL = "p1:36.0,94.0,453.6,108.0"


def widget_value(pdf, name):
    with pymupdf.open(str(pdf)) as d:
        for page in d:
            for w in page.widgets():
                if w.field_name == name:
                    return w.field_value
    raise KeyError(name)


# ---------------------------------------------------------------------------
# _join_cells: one widget's string from its cells
# ---------------------------------------------------------------------------

class TestJoinCells:
    def test_comb_cells_on_one_line_run_together(self):
        assert _join_cells([(100, "1"), (100, "2"), (100, "3")]) == "123"

    def test_repeated_digits_in_a_comb_are_kept(self):
        assert _join_cells([(100, "1"), (100, "1")]) == "11"

    def test_lines_of_one_answer_get_a_space(self):
        assert _join_cells([(100, "1120 Sycamore Terrace"), (112, "Fresno, CA 93721")]) == \
            "1120 Sycamore Terrace Fresno, CA 93721"

    def test_a_line_repeating_the_line_above_is_written_once(self):
        assert _join_cells([(181, "Omar Fischer, 1120"), (193, "Omar Fischer, 1120")]) == "Omar Fischer, 1120"

    def test_empty_lines_are_skipped(self):
        assert _join_cells([(100, "a"), (112, ""), (124, "b")]) == "a b"


# ---------------------------------------------------------------------------
# render_case on the real blank
# ---------------------------------------------------------------------------

class TestRenderCase:
    def test_two_lines_into_one_widget(self, f8825, tmp_path):
        eff, rep = render_case({LINE1: "1120 Sycamore Terrace", LINE2: "Fresno, CA 93721"}, f8825, tmp_path / "f.pdf")
        want = "1120 Sycamore Terrace Fresno, CA 93721"
        assert widget_value(tmp_path / "f.pdf", ADDR) == want
        assert eff[LINE1] == eff[LINE2] == want

    def test_same_value_on_both_lines_is_written_once(self, f8825, tmp_path):
        eff, _ = render_case({LINE1: "Omar Fischer, 1120", LINE2: "Omar Fischer, 1120"}, f8825, tmp_path / "f.pdf")
        assert widget_value(tmp_path / "f.pdf", ADDR) == "Omar Fischer, 1120"

    def test_a_cell_that_is_its_widget_is_written_as_is(self, f8825, tmp_path):
        eff, _ = render_case({NAME_CELL: "Harbor Light Logistics Inc"}, f8825, tmp_path / "f.pdf")
        assert widget_value(tmp_path / "f.pdf", NAME) == "Harbor Light Logistics Inc"
        assert eff[NAME_CELL] == "Harbor Light Logistics Inc"

    def test_filling_the_same_draw_twice_gives_the_same_case(self, f8825, tmp_path):
        drawn = {LINE1: "1120 Sycamore Terrace", LINE2: "Fresno, CA 93721", NAME_CELL: "Harbor Light Logistics Inc"}
        a, _ = render_case(dict(drawn), f8825, tmp_path / "a.pdf")
        b, _ = render_case(dict(drawn), f8825, tmp_path / "b.pdf")
        assert a == b


# ---------------------------------------------------------------------------
# _bank_case: what is frozen, and what a reuse fills
# ---------------------------------------------------------------------------

class TestFrozenCase:
    DRAWN = {LINE1: "1120 Sycamore Terrace", LINE2: "Fresno, CA 93721", NAME_CELL: "Harbor Light Logistics Inc"}

    @pytest.fixture
    def draws(self, monkeypatch):
        n = {"drawn": 0}

        def fake_draw(cmap, seed=0):
            n["drawn"] += 1
            return dict(self.DRAWN)
        monkeypatch.setattr(validate, "generate_from_bank", fake_draw)
        return n

    def test_the_draw_is_frozen_not_the_fill(self, f8825, tmp_path, draws):
        cp = tmp_path / "frozen.json"
        eff, _ = validate._bank_case({"boxes": {}}, f8825, tmp_path / "f.pdf", cp, "k")
        assert json.loads(cp.read_text()) == self.DRAWN            # the drawn lines, not the joined string
        assert eff[LINE1] == "1120 Sycamore Terrace Fresno, CA 93721"

    def test_reuse_gives_the_same_expected_values(self, f8825, tmp_path, draws):
        # the regression: a reused case must not join the joined string again
        cp = tmp_path / "frozen.json"
        first, _ = validate._bank_case({"boxes": {}}, f8825, tmp_path / "1.pdf", cp, "k")
        again, _ = validate._bank_case({"boxes": {}}, f8825, tmp_path / "2.pdf", cp, "k")
        third, _ = validate._bank_case({"boxes": {}}, f8825, tmp_path / "3.pdf", cp, "k")
        assert first == again == third
        assert draws["drawn"] == 1                                   # drawn once, then read back

    def test_no_cache_dir_draws_every_time(self, f8825, tmp_path, draws):
        validate._bank_case({"boxes": {}}, f8825, tmp_path / "1.pdf", None, "k")
        validate._bank_case({"boxes": {}}, f8825, tmp_path / "2.pdf", None, "k")
        assert draws["drawn"] == 2


# ---------------------------------------------------------------------------
# case_to_paths: the expected value of each blueprint field
# ---------------------------------------------------------------------------

class TestExpectedValues:
    def bpt(self):
        return {"fields": {
            "property_address_1": {"type": "string", "widget": {"page": 1, "rect": [58.6, 180.0, 200.9, 204.0],
                                                              "path": ADDR}},
            "taxpayer_name": {"type": "string", "widget": {"page": 1, "rect": [36.0, 94.0, 453.6, 108.0],
                                                           "path": NAME}},
        }}

    def test_a_field_over_two_cells_expects_the_widget_string_once(self, f8825, tmp_path):
        eff, rep = render_case({LINE1: "1120 Sycamore Terrace", LINE2: "Fresno, CA 93721",
                                NAME_CELL: "Harbor Light Logistics Inc"}, f8825, tmp_path / "f.pdf")
        gt, unclaimed = case_to_paths(self.bpt(), eff, rep.get("targets"))
        assert gt[ADDR] == "1120 Sycamore Terrace Fresno, CA 93721"
        assert gt[NAME] == "Harbor Light Logistics Inc"
        assert unclaimed == {}


# ---------------------------------------------------------------------------
# fit_widget: a value fits the widget it is typed into
# ---------------------------------------------------------------------------

from petey.extract import extract                       # noqa: E402
from petey.synth.render import fit_widget               # noqa: E402

TYPE_CELL, TYPE_RECT = "p1:201.6,180.0,295.2,204.0", [201.6, 180.0, 295.2, 204.0]     # multi-line, 93.6 pt, 8 pt font


class TestFitWidget:
    def test_a_long_value_in_a_narrow_box_is_cut_to_what_shows(self):
        # ACORD 90 NY's 22 pt state box: "REF97533" read back "EF975" and was scored as the blueprint's miss
        assert fit_widget("REF97533", (428, 318, 450, 330), 8) == "REF"

    def test_a_value_that_fits_is_unchanged(self):
        assert fit_widget("VA", (428, 318, 450, 330), 8) == "VA"
        assert fit_widget("Harbor Light Logistics Inc", (36, 94, 453.6, 108), 8) == "Harbor Light Logistics Inc"

    def test_multiline_wraps_words_over_its_lines(self):
        s = "Rental real estate with several units on two parcels near the river"
        assert fit_widget(s, TYPE_RECT, 8, multiline=True) == "Rental real estate with several units on two"

    def test_a_word_longer_than_a_line_is_cut_not_broken(self):
        assert fit_widget("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 Second", TYPE_RECT, 8, multiline=True) == \
            "ABCDEFGHIJKLMNOP"

    def test_comb_is_left_to_its_maxlen(self):
        assert fit_widget("123456789", (0, 0, 20, 12), 8, comb=True) == "123456789"

    @pytest.mark.parametrize("value", ["ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 Second",
                                       "Rental real estate with several units on two parcels near the river", "Duplex"])
    def test_what_is_expected_is_what_is_read(self, f8825, tmp_path, value):
        eff, _ = render_case({TYPE_CELL: value}, f8825, tmp_path / "f.pdf")
        got = extract({"fields": {"t": {"type": "string", "widget": {"page": 1, "rect": TYPE_RECT}}}},
                      tmp_path / "f.pdf", blank_pdf=f8825)["t"]
        assert eff[TYPE_CELL] == got


class TestOverlaidBoxes:
    def test_the_written_value_wins_over_an_empty_box_over_the_same_widget(self):
        # ACORD 90 NY p2: a wide box treated as a mark (False, nothing written) and the small box that wrote 'H'
        # both landed at the marital-status widget; the field expected '' while the widget held 'H'
        rect = [497.0, 72.0, 511.0, 84.0]
        targets = {"p2:482.9,72.5,532.3,83.5": [{"page": 2, "rect": rect, "value": False}],
                   "p2:497.5,72.8,510.5,83.5": [{"page": 2, "rect": rect, "value": "H"}]}
        bpt = {"fields": {"marital_status": {"type": "string", "widget": {"page": 2, "rect": rect, "path": "MS"}}}}
        gt, unclaimed = case_to_paths(bpt, {}, targets)
        assert gt == {"MS": "H"} and unclaimed == {}


def test_a_date_too_wide_is_written_shorter_not_cut():
    # ACORD 90 NY's reinstatement date: '2017-03-0' cut by width read back as no date
    out = fit_widget("2017-03-05", (0, 0, 40, 12), 8)
    assert out in ("03/05/2017", "03/05/17", "3/5/17", "030517") and fit_widget("2017-03-05", (0, 0, 200, 12), 8) == "2017-03-05"


def test_a_written_string_wins_over_a_mark_on_the_same_text_widget():
    rect = [497.0, 72.0, 511.0, 84.0]
    targets = {"p2:482.9,72.5,532.3,83.5": [{"page": 2, "rect": rect, "value": True}],
               "p2:497.5,72.8,510.5,83.5": [{"page": 2, "rect": rect, "value": "F"}]}
    bpt = {"fields": {"marital_status": {"type": "string", "widget": {"page": 2, "rect": rect, "path": "MS"}}}}
    assert case_to_paths(bpt, {}, targets)[0] == {"MS": "F"}
