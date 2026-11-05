"""The benchmark key takes only forms STRUCTURE VALIDATED (Andrew, 2026-11-04: "structural is all that matters for the
benchmark!"; validated-only forms "leave them out until they get an S")."""
import sys
from pathlib import Path

import yaml

from petey.validate import hand_review as H
from petey_dataset import verdicts as DV

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import benchmark_key as bk  # noqa: E402


def test_only_the_s_puts_a_form_in_the_key(tmp_path, monkeypatch):
    bpt = tmp_path / "form.bpt"
    fields = {"f0": {"type": "string", "widget": {"page": 1, "rect": [0, 0, 50, 8]}}}
    bpt.write_text(yaml.safe_dump({"name": "form", "fields": fields}))
    monkeypatch.setattr(DV, "OUT", tmp_path / "records")
    monkeypatch.setattr(H, "working_path", lambda bid, paths=None: bpt)
    s = object.__new__(H.State)
    s.paths, s._index = {"t__form": bpt}, {}
    s.put_verdicts("t__form", {"verdicts": {"f0": {"verdict": "accept"}}})
    v = H.load_verdicts("t__form")
    assert H.checked(v, bpt, H._load(bpt))["validated"]               # every name accepted, no S
    assert not bk.in_key(v, bpt)
    H.stamp_structure("t__form", bpt, bpt)
    assert bk.in_key(H.load_verdicts("t__form"), bpt)
    bpt.write_text(bpt.read_text() + "\n# edited\n")                   # changed since: the S is stale
    assert not bk.in_key(H.load_verdicts("t__form"), bpt)
