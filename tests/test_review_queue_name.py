"""The review queue's section is named by its batch (2026-11-03: a batch is not always name-check flags): the listing
gives each queued form focus.json's "why", and no other form."""
from types import SimpleNamespace

from petey.validate import blueprint_review as br
from petey.validate import hand_review


def _app(paths):
    app = object.__new__(br.App)
    app.paths = paths
    app.review = SimpleNamespace(_index={"x": 1})
    app.refresh = lambda: None
    app.entry = lambda bid: {"id": bid}
    return app


def test_queued_forms_carry_the_batch_description(monkeypatch):
    monkeypatch.setattr(hand_review, "_focus", lambda: {"why": "thin topics, batch 1", "forms": {"a": 0}})
    rows = {r["id"]: r for r in _app({"a": None, "b": None}).listing()}
    assert rows["a"] == {"id": "a", "focus": 0, "focus_why": "thin topics, batch 1"}
    assert rows["b"] == {"id": "b", "focus": None}


def test_no_queue_file_no_description(monkeypatch):
    monkeypatch.setattr(hand_review, "_focus", lambda: {})
    assert _app({"a": None}).listing() == [{"id": "a", "focus": None}]
