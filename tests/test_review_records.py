"""Review records (petey/validate/hand_review.py): the review server saves verdicts on threads; saves read, change
and write a record under one lock and write it whole. 2026-10-19: two saves of je__cra_t2 in one second wrote over
each other and left the record unreadable; the server would not start on it."""
import json
import threading

import pytest
import yaml

from petey.validate import hand_review as H


@pytest.fixture
def state(tmp_path, monkeypatch):
    bpt = tmp_path / "form.bpt"
    fields = {f"f{i}": {"type": "string", "widget": {"page": 1, "rect": [0, i * 10, 50, i * 10 + 8]}} for i in range(20)}
    bpt.write_text(yaml.safe_dump({"name": "form", "fields": fields}))
    monkeypatch.setattr(H, "OUT", tmp_path / "records")
    monkeypatch.setattr(H, "working_path", lambda bid, paths=None: bpt)
    s = object.__new__(H.State)
    s.paths, s._index = {"t__form": bpt}, {}
    return s


def test_a_save_is_read_back(state):
    state.put_verdicts("t__form", {"verdicts": {"f0": {"verdict": "accept"}}})
    rec = H.load_verdicts("t__form")
    assert rec["verdicts"]["f0"]["verdict"] == "accept"


def test_concurrent_saves_all_kept(state):
    threads = [threading.Thread(target=state.put_verdicts, args=("t__form", {"verdicts": {f"f{i}": {"verdict": "flag",
               "note": f"note {i}"}}})) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rec = json.loads(H.verdict_path("t__form").read_text())          # whole and readable
    assert sorted(rec["verdicts"]) == sorted(f"f{i}" for i in range(20))


def test_clearing_a_verdict(state):
    state.put_verdicts("t__form", {"verdicts": {"f1": {"verdict": "accept"}}})
    state.put_verdicts("t__form", {"verdicts": {"f1": None}})
    assert "f1" not in H.load_verdicts("t__form")["verdicts"]



def test_reset_clears_every_verdict_and_keeps_the_record(tmp_path, monkeypatch):
    """Andrew (2026-10-22): "a button to reset validations? (and a 'are you sure?' screen)"."""
    import json
    from petey.validate import hand_review as h
    monkeypatch.setattr(h, "OUT", tmp_path)
    assert h.reset_verdicts("t__x") == {"cleared": 0, "backup": None}
    h.verdict_path("t__x").write_text(json.dumps({"verdicts": {"a": {"verdict": "accept"}, "b": {"verdict": "flag"}}}))
    out = h.reset_verdicts("t__x")
    assert out["cleared"] == 2 and not h.verdict_path("t__x").exists()
    assert json.loads(open(out["backup"]).read())["verdicts"]["b"]["verdict"] == "flag"


def test_the_groups_tab_gets_each_fields_code(tmp_path, monkeypatch):
    """Andrew (2026-10-24): "group panel needs the full field id too": the Groups data carries every field's code."""
    import yaml
    from petey.validate import group_review as gr
    bpt = tmp_path / "f.bpt"
    bpt.write_text(yaml.safe_dump({"fields": {
        "sex": {"type": "category", "x_petey_id": "1_16", "widgets": {
            "male": {"page": 1, "rect": [0, 0, 10, 10], "widget_type": "checkbox"},
            "female": {"page": 1, "rect": [20, 0, 30, 10], "widget_type": "checkbox"}}},
        "name_nm": {"type": "string", "x_petey_id": "1_2", "widget": {"page": 1, "rect": [0, 20, 90, 30],
                                                                     "widget_type": "text"}}}}))
    monkeypatch.setattr(gr, "blueprint_paths", lambda: {"t__f": bpt})
    monkeypatch.setattr(gr, "working_path", lambda bid, paths=None: bpt)
    monkeypatch.setattr(gr, "resolve_blank", lambda bp: None)
    monkeypatch.setattr(gr, "RECORDS", tmp_path, raising=False)
    out = gr.State().detail("t__f")
    assert out["codes"] == {"sex": "1_16", "name_nm": "1_2"}
