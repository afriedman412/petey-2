"""New fields to check (Andrew, 2026-11-02: "is there a way for me to know what needs to be revisited?"): a form once
fully checked that has since gained fields without a verdict (a sweep, an edit) says how many, and remembers it was
checked through later saves."""
import pytest
import yaml

from petey.validate import hand_review as H


@pytest.fixture
def state(tmp_path, monkeypatch):
    bpt = tmp_path / "form.bpt"
    fields = {f"f{i}": {"type": "string", "widget": {"page": 1, "rect": [0, i * 10, 50, i * 10 + 8]}} for i in range(3)}
    bpt.write_text(yaml.safe_dump({"name": "form", "fields": fields}))
    monkeypatch.setattr(H, "OUT", tmp_path / "records")
    monkeypatch.setattr(H, "working_path", lambda bid, paths=None: bpt)
    s = object.__new__(H.State)
    s.paths, s._index = {"t__form": bpt}, {}
    return s, bpt


def _new(bpt):
    return H.new_to_check(H.load_verdicts("t__form"), bpt, H._load(bpt))


def _add_fields(bpt, n):
    bp = yaml.safe_load(bpt.read_text())
    for i in range(n):
        bp["fields"][f"swept{i}"] = {"type": "string", "widget": {"page": 1, "rect": [100, i * 10, 150, i * 10 + 8]},
                                     "x_petey_added": {"source": "missing_sweep"}}
    bpt.write_text(yaml.safe_dump(bp))


def test_never_checked_is_not_new_fields(state):
    st, bpt = state
    st.put_verdicts("t__form", {"verdicts": {"f0": {"verdict": "accept"}}})
    _add_fields(bpt, 2)
    assert _new(bpt) is None


def test_checked_then_swept_counts_the_new_fields_and_remembers_through_saves(state):
    st, bpt = state
    st.put_verdicts("t__form", {"verdicts": {f"f{i}": {"verdict": "accept"} for i in range(3)}})
    assert _new(bpt) is None                                     # fully checked
    _add_fields(bpt, 2)
    assert _new(bpt) == 2
    st.put_verdicts("t__form", {"verdicts": {"swept0": {"verdict": "accept"}}})
    assert H.load_verdicts("t__form").get("was_checked")         # the save keeps the memory
    assert _new(bpt) == 1
    st.put_verdicts("t__form", {"verdicts": {"swept1": {"verdict": "accept"}}})
    assert _new(bpt) is None                                     # checked again
