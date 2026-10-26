"""Groups' "rescan page": the labeler names a page's groups in one call per page (field_add.labeler_names, 2026-10-25)."""
import types
from pathlib import Path

from petey.validate import field_add


class FakeDoc:
    def __getitem__(self, i):
        return i
    def close(self):
        pass


def setup(monkeypatch, answer):
    calls = []
    monkeypatch.setattr(field_add.pymupdf, "open", lambda *_: FakeDoc())
    monkeypatch.setattr(field_add.auto_label, "_words_from_page", lambda pg: [f"words of page index {pg}"])
    def label(entries, words, model=None, think=True):
        calls.append({"entries": entries, "words": words, "think": think})
        return answer(entries)
    monkeypatch.setattr(field_add.auto_label, "label_page_via_llm", label)
    ctx = types.SimpleNamespace(widgets=[], blank=Path("blank.pdf"), path=Path("x.bpt"))
    return ctx, calls


def group(page, key_caps):
    return {"kind": "group", "page": page, "rect": [0, 0, 10, 10],
            "options": [{"key": k, "caption": c} for k, c in key_caps]}


def test_one_call_per_page_and_names_back_in_order(monkeypatch):
    ctx, calls = setup(monkeypatch, lambda es: {e["id"]: f"name.{e['options'][0]}" for e in es})
    ps = [group(2, [("a", "Single"), ("b", None)]), group(3, [("c", "Owner")]), group(2, [("d", None)])]
    assert field_add.labeler_names(ctx, ps, think=False) == ["name_single", "name_owner", "name_d"]
    assert [len(c["entries"]) for c in calls] == [2, 1]
    assert calls[0]["words"] == ["words of page index 1"] and not calls[0]["think"]
    assert calls[0]["entries"][0]["options"] == ["Single", "b"]       # a box without a caption goes by its key


def test_a_box_the_labeler_skips_gets_no_name(monkeypatch):
    ctx, _ = setup(monkeypatch, lambda es: {1: "marital_status"})
    ps = [group(1, [("a", "Single")]), group(1, [("b", "Yes")])]
    assert field_add.labeler_names(ctx, ps) == ["marital_status", None]
    assert field_add.labeler_name(ctx, ps[0]) == "marital_status"
