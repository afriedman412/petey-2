"""Fields left out of the benchmark (Andrew, 2026-11-03: stacked in one open area with no printed line between them):
the record, the key leaving them out, the scorer leaving a system's boxes in those areas out too."""
import sys

import pytest

from petey.validate import ignored_fields as ifl

sys.path.insert(0, "eval")
import benchmark_key as K  # noqa: E402
import benchmark_score as S  # noqa: E402


def test_needs_a_reason_and_a_page_id(tmp_path):
    rec = tmp_path / "f.json"
    with pytest.raises(ValueError):
        ifl.put("lib__fl_160__p2", ["2_1"], "  ", record=rec)
    with pytest.raises(ValueError):
        ifl.put("lib__fl_160", ["2_1"], "no lines", record=rec)
    assert not rec.exists()


def test_put_take_back_and_drop_a_batch(tmp_path):
    rec = tmp_path / "f.json"
    ifl.put("a__p1", ["1", "2"], "no lines between", source="unruled_stack", record=rec)
    ifl.put("b__p2", ["7"], "no lines between", source="unruled_stack", record=rec)
    out = ifl.put("b__p2", ["8"], "by hand", record=rec)
    assert set(out) == {"a__p1", "b__p2"} and out["a__p1"]["1"]["source"] == "unruled_stack"
    assert set(ifl.take_back("a__p1", ["1"], record=rec)["a__p1"]) == {"2"}
    assert ifl.drop_source("unruled_stack", record=rec) == 2
    assert ifl.load(rec) == {"b__p2": {"8": ifl.load(rec)["b__p2"]["8"]}}


def _stack():
    """Three lines stacked in an open cell (no rule between), a name field elsewhere, the lines grouped with nothing."""
    return {"fields": [{"id": "l1", "rect": [100, 100, 300, 112], "kind": "text"},
                       {"id": "l2", "rect": [100, 112, 300, 124], "kind": "text"},
                       {"id": "l3", "rect": [100, 124, 300, 136], "kind": "text"},
                       {"id": "nm", "rect": [100, 200, 300, 212], "kind": "text"},
                       {"id": "y", "rect": [100, 240, 108, 248], "kind": "choice"},
                       {"id": "n", "rect": [120, 240, 128, 248], "kind": "choice"}],
            "groups": [["y", "n"], ["l1", "l2"]]}


def test_key_leaves_ignored_fields_out_and_keeps_their_boxes():
    k = _stack()
    assert K.drop_ignored(k, {"l1", "l2", "l3"}) == 3
    assert [f["id"] for f in k["fields"]] == ["nm", "y", "n"]
    assert k["groups"] == [["y", "n"]]                                   # a group left with no fields goes
    assert k["ignored"] == [[100, 100, 300, 112], [100, 112, 300, 124], [100, 124, 300, 136]]
    assert K.drop_ignored(k, {"zz"}) == 0


def test_scorer_leaves_boxes_in_ignored_areas_out():
    k = _stack()
    K.drop_ignored(k, {"l1", "l2", "l3"})
    pred = {"fields": [{"id": "strip", "rect": [100, 98, 300, 138], "kind": "text"},      # one box over the whole cell
                       {"id": "nm", "rect": [100, 200, 300, 212], "kind": "text"},
                       {"id": "y", "rect": [100, 240, 108, 248], "kind": "choice"},
                       {"id": "n", "rect": [120, 240, 128, 248], "kind": "choice"}],
            "groups": [["y", "n"]]}
    c = S.score_page(k, pred)
    assert c["found_key"] == c["found_found"] == c["found_hit"] == 3              # the strip neither hits nor costs
    half = {"fields": pred["fields"] + [{"id": "wide", "rect": [100, 130, 300, 190], "kind": "text"}],
            "groups": [["y", "n"]]}
    assert S.score_page(k, half)["found_found"] == 4                     # mostly outside the area: still scored
