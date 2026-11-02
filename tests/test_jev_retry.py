"""Jev requests: a brief outage (503 "Image processing is unavailable", 2026-11-01) is asked again with growing
waits, like busy (429 / 529); other errors still raise at once, and a success is cached."""
import pytest

from petey.validate import jev_page


class Resp:
    def __init__(self, status, body=None):
        self.status_code, self.text, self.headers = status, str(body), {}
        self._body = body

    def json(self):
        return self._body


class Client:
    def __init__(self, *outcomes):
        self.outcomes, self.posts = list(outcomes), 0

    def post(self, *a, **k):
        self.posts += 1
        return self.outcomes.pop(0)


@pytest.fixture
def waits(monkeypatch, tmp_path):
    monkeypatch.setattr(jev_page, "CACHE", tmp_path)
    slept = []
    monkeypatch.setattr(jev_page.time, "sleep", slept.append)
    return slept


def test_unavailable_then_answer(waits):
    ok = {"answers": {"b1": {"noul": 0.9}}, "usage": {"input_tokens": 10}}
    c = Client(Resp(503, {"detail": "Image processing is unavailable."}), Resp(503), Resp(200, ok))
    assert jev_page.ask(c, "k", {"q": 1}, {}) == ok
    assert c.posts == 3 and waits == [2, 4]
    assert jev_page.ask(Client(), "k", {"q": 1}, {}) == ok           # cached: no request


def test_still_down_raises_after_five_waits(waits):
    c = Client(*[Resp(503)] * 6)
    with pytest.raises(RuntimeError, match="503"):
        jev_page.ask(c, "k", {"q": 2}, {})
    assert c.posts == 6 and waits == [2, 4, 8, 16, 32]


def test_other_errors_raise_at_once(waits):
    c = Client(Resp(400, "max_tokens_exceeded"))
    with pytest.raises(RuntimeError, match="400"):
        jev_page.ask(c, "k", {"q": 3}, {})
    assert c.posts == 1 and waits == []
