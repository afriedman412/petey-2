"""Model calls: a stream that stalls or drops mid-answer is retried (generate.final_message). The SDK retries only
the opening request; on 2026-10-19 three form runs died of an httpx ReadTimeout raised from inside a stream."""
import anthropic
import httpx2
import pytest

from petey.synth import generate


class FakeStream:
    def __init__(self, outcome):
        self.outcome = outcome

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(generate.time, "sleep", lambda s: None)


def opener(*outcomes):
    calls = iter(outcomes)
    n = {"opened": 0}

    def open_stream():
        n["opened"] += 1
        return FakeStream(next(calls))
    return open_stream, n


class TestFinalMessage:
    def test_returns_the_message(self):
        open_stream, n = opener("final")
        assert generate.final_message(open_stream) == "final" and n["opened"] == 1

    @pytest.mark.parametrize("err", [httpx2.ReadTimeout("stalled"), httpx2.RemoteProtocolError("dropped"),
                                     anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))])
    def test_a_stall_or_drop_is_retried(self, err):
        open_stream, n = opener(err, "final")
        assert generate.final_message(open_stream, "t") == "final" and n["opened"] == 2

    def test_gives_up_after_its_tries(self):
        open_stream, n = opener(*[httpx2.ReadTimeout("stalled")] * 3)
        with pytest.raises(httpx2.ReadTimeout):
            generate.final_message(open_stream, "t", tries=3)
        assert n["opened"] == 3

    def test_other_errors_are_not_retried(self):
        open_stream, n = opener(ValueError("a bug"), "final")
        with pytest.raises(ValueError):
            generate.final_message(open_stream)
        assert n["opened"] == 1
