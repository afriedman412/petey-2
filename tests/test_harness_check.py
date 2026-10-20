"""The harness check (petey/validate/harness_check.py): the same cases filled in two rounds must expect the same
values at every widget; anything else is the test drifting, not the blueprint."""
import json

from petey.validate.harness_check import expected_drift


def run(tmp_path, name, cases):
    d = tmp_path / name
    for case, gt in cases.items():
        (d / case).mkdir(parents=True)
        (d / case / "ground_truth.json").write_text(json.dumps(gt))
    return d


def test_same_values_no_drift(tmp_path):
    a = run(tmp_path, "r1", {"case_001_intact": {"w1": "Omar Fischer, 1120", "w2": True}})
    b = run(tmp_path, "r2", {"case_001_intact": {"w1": "Omar Fischer, 1120", "w2": True}})
    assert expected_drift(a, b) == []


def test_a_doubled_value_is_drift(tmp_path):
    a = run(tmp_path, "r1", {"case_001_intact": {"w1": "Omar Fischer, 1120"}})
    b = run(tmp_path, "r2", {"case_001_intact": {"w1": "Omar Fischer, 1120Omar Fischer, 1120"}})
    assert expected_drift(a, b) == [{"case": "case_001_intact", "path": "w1", "before": "Omar Fischer, 1120",
                                     "after": "Omar Fischer, 1120Omar Fischer, 1120"}]


def test_a_field_gained_or_lost_is_not_drift(tmp_path):
    # the blueprint decides which widgets are read; a path in one run only is a blueprint change
    a = run(tmp_path, "r1", {"case_001_intact": {"w1": "x"}})
    b = run(tmp_path, "r2", {"case_001_intact": {"w1": "x", "w2": "y"}, "case_002_intact": {"w1": "z"}})
    assert expected_drift(a, b) == []


import pytest                                                    # noqa: E402

from petey.validate.harness_check import repeated, repeated_values   # noqa: E402


@pytest.mark.parametrize("v, want", [("5C5C", True), ("Omar Fischer, 1120Omar Fischer, 1120", True),
                                     ("234.12699234.12699", True), ("1212", False), ("0000", False),
                                     ("Omar Fischer, 1120", False), ("ABAB C", False), (True, False), ("", False)])
def test_repeated(v, want):
    assert repeated(v) is want


def test_repeated_values_in_a_run(tmp_path):
    d = run(tmp_path, "r1", {"case_001_intact": {"w1": "5C5C", "w2": "5C"}})
    assert repeated_values(d) == [{"case": "case_001_intact", "path": "w1", "value": "5C5C"}]
