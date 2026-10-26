"""The labeler's pages go out at once (Andrew, 2026-10-26: "is there any downside to running the pages in
parallel?" ... "yeah definitely"): each page's call is its own, so the form takes its slowest page's time, and every
page's labels land on that page's widgets."""
import threading
import time

from petey.label import auto_label


def test_pages_are_labeled_at_once_and_each_keeps_its_labels(monkeypatch, f8825):
    at_once, now, lock = [0], [0], threading.Lock()

    def fake(widgets, words, model=None, think=True, structure=None, bulk=False, parts_out=None, page=None):
        with lock:
            now[0] += 1
            at_once[0] = max(at_once[0], now[0])
        time.sleep(0.3)
        with lock:
            now[0] -= 1
        return {w["id"]: f"page_{w['page']}_box_{w['id']}" for w in widgets}

    monkeypatch.setattr(auto_label, "label_page_via_llm", fake)
    bp = auto_label.build_blueprint(f8825, "f8825", use_retrieval=False)
    pages = {sp["widget"]["page"] for sp in bp["fields"].values() if sp.get("widget")}
    assert len(pages) >= 2 and at_once[0] == min(len(pages), auto_label.LABEL_PAGES_AT_ONCE)
    for name, sp in bp["fields"].items():
        if sp.get("widget") and name.startswith("page_"):
            assert name.startswith(f"page_{sp['widget']['page']}_")      # each page's labels on its own widgets
