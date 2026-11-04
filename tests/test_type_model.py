"""The type model (petey/validate/type_model.py): choice or text for a kept box."""
from petey.validate import type_model as tm


def _w(x0, y0, x1, y1, t):
    return (x0, y0, x1, y1, t, 0, 0, 0)


def test_features_tell_a_cell_row_from_an_option_column():
    cells = [{"rect": [10 + 18 * i, 100, 24 + 18 * i, 114], "kind": "checkbox"} for i in range(8)]
    opts = [{"rect": [300, 100 + 20 * i, 310, 110 + 20 * i], "kind": "checkbox"} for i in range(3)]
    words = [_w(314, 100 + 20 * i, 330, 110 + 20 * i, "Yes") for i in range(3)]
    fc, fo = tm.features(cells[2], cells + opts, words), tm.features(opts[1], cells + opts, words)
    assert fc["row_many"] == 1 and fc["word_beside"] == 0 and fc["row_even"] == 1
    assert fo["col_many"] == 1 and fo["word_right"] == 1 and fo["row_many"] == 0


def test_without_weights_the_finder_kind_stands(monkeypatch):
    monkeypatch.setattr(tm, "WEIGHTS", None)
    b = {"rect": [10, 10, 20, 20], "kind": "radio"}
    assert tm.kind(b, [b], []) == "choice" and tm.kind({"rect": [10, 10, 90, 20], "kind": "text"}, [], []) == "text"
