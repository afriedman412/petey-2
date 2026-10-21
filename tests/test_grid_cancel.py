"""The cancel button on a grid / block check (petey/validate/blueprint_review.py, Andrew 2026-10-21: "can the cancel
button cancel the validation query"): nothing written after it, a call to Opus under way given up."""
import threading
import time
import types

import pytest

from petey.validate import blueprint_review as br, grid_check


def test_until_returns_the_answer():
    assert br.until(lambda: 7, lambda: False) == 7


def test_until_gives_up_a_call_under_way():
    flag = threading.Event()
    threading.Timer(0.2, flag.set).start()
    t0 = time.time()
    with pytest.raises(br.Cancelled):
        br.until(lambda: time.sleep(3), flag.is_set, every=0.05)
    assert time.time() - t0 < 1


def test_a_cancelled_check_writes_nothing_after_the_cancel(monkeypatch):
    wrote = []
    app = types.SimpleNamespace(refresh=lambda: None, entry=lambda bid: {}, accept_grid=lambda *a: wrote.append(a))
    tab = br.Grids(app, "block")
    monkeypatch.setattr(br.Grids, "_apply", lambda self, bid: lambda edits: wrote.append(edits) or {"changes": edits})

    def slow_check(bid, tid, *, accept, apply, ask_opus):      # Jev for a while, then the renames
        time.sleep(0.4)
        apply([{"field": "a", "edit": {"name": "b"}}])
        accept(1, ["b"])
        return {"status": "fixed", "steps": []}
    monkeypatch.setattr(grid_check, "check", slow_check)
    threading.Timer(0.1, lambda: tab.cancel("je__x", "p1-BG1")).start()
    out = tab.check("je__x", "p1-BG1")
    assert out["status"] == "cancelled" and wrote == []
    assert not tab.running and not tab.stop


def test_cancel_with_no_check_under_way_leaves_no_flag():
    tab = br.Grids(types.SimpleNamespace(), "table")
    assert tab.cancel("je__x", "p1-T1") == {"cancelled": False} and not tab.stop
