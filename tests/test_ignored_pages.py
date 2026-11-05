"""Pages ignored on the review page, with a reason (Andrew, 2026-10-31): the record, and the scorer leaving them out."""
import json
import sys

import pytest

from petey_dataset import ignored_pages as ip


def test_ignore_needs_a_reason_and_a_page_id(tmp_path):
    rec = tmp_path / "ignored.json"
    with pytest.raises(ValueError):
        ip.put("bm__sd_1__p2", True, "  ", record=rec)
    with pytest.raises(ValueError):
        ip.put("bm__sd_1", True, "checklist", record=rec)
    with pytest.raises(ValueError):
        ip.put("bm__sd_1__p0", True, "checklist", record=rec)
    assert not rec.exists()


def test_ignore_then_take_back(tmp_path):
    rec = tmp_path / "ignored.json"
    out = ip.put("bm__sd_1__p2", True, "  checklist   of documents ", record=rec)
    assert out["bm__sd_1__p2"]["reason"] == "checklist of documents" and out["bm__sd_1__p2"]["when"]
    ip.put("lib__fw9__p4", True, "instructions", record=rec)
    assert set(ip.load(rec)) == {"bm__sd_1__p2", "lib__fw9__p4"}
    assert set(ip.put("bm__sd_1__p2", False, record=rec)) == {"lib__fw9__p4"}
    assert set(ip.put("bm__sd_9__p1", False, record=rec)) == {"lib__fw9__p4"}       # not there: nothing to take back


def test_the_scorer_leaves_ignored_pages_out(tmp_path, monkeypatch, capsys):
    sys.path.insert(0, "eval")
    import benchmark_score as bs
    key, pred = tmp_path / "key", tmp_path / "pred"
    key.mkdir(); pred.mkdir()
    for pid in ("a__p1", "b__p1"):
        (key / f"{pid}.json").write_text(json.dumps({"page_id": pid, "fields": [], "groups": []}))
    (key / "index.json").write_text(json.dumps([{"page_id": "a__p1", "set": "s"}, {"page_id": "b__p1", "set": "s"}]))
    rec = tmp_path / "ignored.json"
    ip.put("b__p1", True, "few fields", record=rec)
    monkeypatch.setattr(ip, "RECORD", rec)
    monkeypatch.setattr(sys, "argv", ["benchmark_score.py", str(pred), "--key", str(key)])
    assert bs.main() == 0
    out = capsys.readouterr().out
    assert "1 key pages ignored" in out and out.splitlines()[1].startswith("1 pages")
