"""Printed fields from a field's own caption (petey/validate/printed_caption.py, Andrew 2026-11-04)."""
import pytest

from petey.validate import printed_caption as pc, printed_fields as pf, printed_model as pm


@pytest.fixture(autouse=True)
def _rule_only(monkeypatch):
    """These tests are about the caption rule: the fitted model, when pasted in, is set aside."""
    monkeypatch.setattr(pm, "WEIGHTS", None)


def _field(code, rect, **extra):
    return {"x_petey_id": code, "type": "string", "widget": {"page": 1, "rect": rect, "widget_type": "text"}, **extra}


def _word(x0, y0, x1, y1, text):
    return (x0, y0, x1, y1, text, 0, 0, 0)


def _page():
    """A signature line with "Signature" under it and a date box beside it with "Date" under it; a second signature
    line captioned "Signature Date" as one phrase; a print-name box captioned above (text); a box on the next row under
    the first signature's caption."""
    bp = {"fields": {
        "sig": _field("1", [40, 100, 240, 112]), "date": _field("2", [260, 100, 340, 112]),
        "sigdate": _field("3", [40, 160, 240, 172]),
        "pname": _field("4", [40, 220, 240, 232]),
        "next": _field("5", [40, 130, 240, 142]),
        "opts": {"x_petey_id": "6", "type": "category", "widgets": {
            "a": {"page": 1, "rect": [300, 160, 308, 168], "widget_type": "checkbox"},
            "b": {"page": 1, "rect": [320, 160, 328, 168], "widget_type": "checkbox"}}}}}
    words = [_word(40, 114, 80, 122, "Signature"), _word(260, 114, 280, 122, "Date"),
             _word(40, 174, 80, 182, "Signature"), _word(83, 174, 100, 182, "Date"),
             _word(40, 208, 60, 216, "Print"), _word(63, 208, 85, 216, "Name"),
             _word(300, 170, 330, 178, "Sign")]
    return bp, (lambda pg: words if pg == 1 else [])


def test_the_caption_under_a_line_is_that_lines_own():
    bp, words_of = _page()
    assert pc.find(bp, words_of) == ["sig"]          # the print-name box is text


def test_mark_writes_the_tag_and_clears_its_own_stale_ones():
    bp, words_of = _page()
    bp["fields"]["date"][pf.TAG] = {"source": pc.SOURCE, "when": "2026-11-03 00:00:00"}   # stale, this source's
    bp["fields"]["next"][pf.TAG] = {"source": "review", "when": "2026-11-03 00:00:00"}    # someone else's: kept
    assert pc.mark(bp, words_of) == 1
    assert bp["fields"]["sig"][pf.TAG]["source"] == pc.SOURCE
    assert pf.TAG not in bp["fields"]["date"]
    assert bp["fields"]["next"][pf.TAG]["source"] == "review"
    assert pf.is_printed(bp["fields"]["sig"]) and not pf.is_printed(bp["fields"]["pname"])


def test_says():
    assert pc.says("signature of applicant") and pc.says("initials") and pc.says("signed:")
    assert not pc.says("date of signature") and not pc.says("title") and not pc.says("significant")
    assert not pc.says("type or print name")      # a printed name is typed or hand-written: text (Andrew, 2026-11-04)


def test_the_fitted_model_decides_when_it_is_there(monkeypatch):
    """A toy model: one weight on the own-caption cue; the cut decides."""
    bp, words_of = _page()
    monkeypatch.setattr(pm, "WEIGHTS", {"own_says": 4.0, "bias": -2.0})
    monkeypatch.setattr(pm, "MEAN", {}); monkeypatch.setattr(pm, "STD", {}); monkeypatch.setattr(pm, "CUT", 0.5)
    assert pc.find(bp, words_of, size_of=lambda pg: (612.0, 792.0)) == ["sig"]
    monkeypatch.setattr(pm, "CUT", 0.99)
    assert pc.find(bp, words_of, size_of=lambda pg: (612.0, 792.0)) == []
