"""STRUCTURE VALIDATED (Andrew, 2026-10-31: "since we are currently only looking at structure, in the service of
building the data set, let's encode that status"; "'accept structure' turns the form to STRUCTURE VALIDATED, which is
superceded by VALIDATED when all the field names are accepted")."""
import json

import pytest
import yaml

from petey.validate import draft
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


def _status(bpt):
    v = H.load_verdicts("t__form")
    bp = H._load(bpt)
    c, s = H.checked(v, bpt, bp), H.structure(v, bpt)
    return ("validated" if c and c["validated"] else "structure" if s and not s["stale"] else "stale" if s else None,
            H.structure_ok(v, bpt, bp))


def test_accept_structure_then_every_name(state):
    st, bpt = state
    assert _status(bpt) == (None, False)
    H.stamp_structure("t__form", bpt, bpt)
    assert _status(bpt) == ("structure", True)
    assert H.load_verdicts("t__form")["verdicts"] == {}          # no name accepted by it
    st.put_verdicts("t__form", {"verdicts": {"f0": {"verdict": "accept"}}})
    assert H.load_verdicts("t__form")["structure"]["by"] == "accept structure"    # kept through a verdict save
    st.put_verdicts("t__form", {"verdicts": {f"f{i}": {"verdict": "accept"} for i in range(3)}})
    assert _status(bpt) == ("validated", True)                   # every name accepted: VALIDATED supersedes it


def test_a_changed_file_makes_it_stale_unless_the_page_made_the_change(state, monkeypatch):
    st, bpt = state
    H.stamp_structure("t__form", bpt, bpt)
    before = H._sha(bpt)
    bpt.write_text(bpt.read_text() + "\n# edited\n")
    assert _status(bpt) == ("stale", False)
    monkeypatch.setattr(draft, "_records", lambda bid: {"hand_review": H.verdict_path(bid)})
    draft.follow("t__form", before, H._sha(bpt))                # the page's own change: carried along
    assert _status(bpt) == ("structure", True)


def test_reset_validation_clears_it(state):
    st, bpt = state
    H.stamp_structure("t__form", bpt, bpt)
    H.reset_verdicts("t__form")
    assert _status(bpt) == (None, False)


def test_clicking_accept_structure_again_takes_it_back(state):
    st, bpt = state
    H.stamp_structure("t__form", bpt, bpt)
    H.unstamp_structure("t__form")
    assert _status(bpt) == (None, False)
    H.unstamp_structure("t__form")                               # nothing to take back: fine
