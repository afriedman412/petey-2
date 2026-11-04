"""`compound_values.find` reports dates, phones and ID numbers only (Andrew, 2026-11-04: "change the detector to only
find those types of text groups"); the other kinds are still read, and come back with `kinds=None`."""
import pytest

from petey.validate import compound_values as cv, split_model as sm


@pytest.fixture(autouse=True)
def _rules_only(monkeypatch):
    """These tests are about the caption rules: the fitted split model, when pasted in, is set aside."""
    monkeypatch.setattr(sm, "WEIGHTS", None)


def _field(code: str, rect: list) -> dict:
    return {"x_petey_id": code, "type": "string", "widget": {"page": 1, "rect": rect, "widget_type": "text"}}


def _word(x0, y0, x1, y1, text) -> tuple:
    return (x0, y0, x1, y1, text, 0, 0, 0)


class _Words:
    def __init__(self, words):
        self._w = words

    def words(self, page):
        return self._w if page == 1 else []


def _page():
    """One line: a name in two boxes captioned First / Last, then a date in three boxes under one (MM/DD/YYYY)."""
    bp = {"fields": {
        "first": _field("1", [10, 100, 80, 112]), "last": _field("2", [90, 100, 160, 112]),
        "d1": _field("3", [220, 100, 250, 112]), "d2": _field("4", [255, 100, 285, 112]),
        "d3": _field("5", [290, 100, 330, 112])}}
    words = [_word(10, 88, 30, 96, "First"), _word(90, 88, 108, 96, "Last"),
             _word(220, 88, 240, 96, "Date"), _word(243, 88, 300, 96, "(MM/DD/YYYY)")]
    return bp, _Words(words)


def test_only_dates_phones_and_ids_are_reported():
    bp, pw = _page()
    got = cv.find(bp, pw)
    assert [(v["kind"], v["fields"]) for v in got] == [("date", ["3", "4", "5"])]


def test_every_kind_on_request():
    bp, pw = _page()
    got = cv.find(bp, pw, kinds=None)
    assert sorted((v["kind"], v["fields"]) for v in got) == [("date", ["3", "4", "5"]), ("name", ["1", "2"])]


def test_a_run_ends_where_the_next_box_has_its_own_caption():
    """Andrew, 2026-11-04: "each has their own caption". A ZIP box and a phone box side by side, captioned above, are
    not one phone; an FEIN box and an SSN box with their labels printed before them are not one ID number."""
    bp = {"fields": {
        "zip": _field("1", [10, 100, 35, 112]), "phone": _field("2", [40, 100, 100, 112]),
        "fein": _field("3", [40, 140, 100, 152]), "ssn": _field("4", [130, 140, 190, 152])}}
    words = [_word(10, 88, 30, 96, "ZIP"), _word(40, 88, 70, 96, "Phone"),      # captions 10 pt apart: one line of text
             _word(10, 142, 36, 150, "FEIN:"), _word(104, 142, 126, 150, "SSN:")]
    assert cv.find(bp, _Words(words)) == []


def test_a_caption_spanning_the_run_does_not_cut_it():
    """One caption over three boxes ("Social Security Number") is the run's, not the later boxes' own."""
    bp = {"fields": {"a": _field("1", [10, 100, 40, 112]), "b": _field("2", [45, 100, 75, 112]),
                     "c": _field("3", [80, 100, 120, 112])}}
    words = [_word(10, 88, 40, 96, "Social"), _word(43, 88, 75, 96, "Security"), _word(78, 88, 110, 96, "Number")]
    assert [(v["kind"], v["fields"]) for v in cv.find(bp, _Words(words))] == [("id_number", ["1", "2", "3"])]


def test_the_split_model_chains_pairs_when_it_is_there(monkeypatch):
    """A toy model: join when nothing but separators sit between the boxes; the kind from the slashes."""
    monkeypatch.setattr(sm, "WEIGHTS", {"between_word": -6.0, "bias": 2.0})
    monkeypatch.setattr(sm, "MEAN", {}); monkeypatch.setattr(sm, "STD", {}); monkeypatch.setattr(sm, "CUT", 0.5)
    bp = {"fields": {"a": _field("1", [10, 100, 40, 112]), "b": _field("2", [48, 100, 78, 112]),
                     "c": _field("3", [86, 100, 126, 112]), "d": _field("4", [160, 100, 220, 112])}}
    words = [_word(41, 102, 47, 110, "/"), _word(79, 102, 85, 110, "/"), _word(130, 102, 156, 110, "Fax:")]
    got = cv.find(bp, _Words(words))
    assert [(v["kind"], v["fields"], v["parts"]) for v in got] == [("date", ["1", "2", "3"], ["month", "day", "yr"])]
