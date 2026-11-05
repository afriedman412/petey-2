"""The split-value taxonomy (petey_dataset/split_types.py, Andrew 2026-11-04: "a taxonomy of defined types that can be
added and removed"): one list read by the Groups tab, the detector and the benchmark key; a flag per kind says
whether it counts as a split value."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

from petey.validate import compound_values as cv, group_review
from petey_dataset import split_types as st   # noqa: E402


def test_dates_phones_and_ids_count():
    assert st.counted() == ("date", "phone", "id_number")
    assert st.counts("date") and not st.counts("name") and not st.counts(None) and not st.counts("nothing")


def test_the_groups_tab_and_the_detector_read_the_same_list():
    assert group_review.ENTITY_TYPES == tuple(st.TYPES)
    assert cv.TYPES == group_review.ENTITY_TYPES
    assert cv.FOUND == st.counted()
    assert cv.PARTS["date"] == ("month", "day", "yr") and "other" not in cv.PARTS


def test_the_key_keeps_counted_kinds_only():
    import benchmark_key as K
    bp = {"fields": {
        "m": {"x_petey_id": "1", "type": "string", "widget": {"page": 1, "rect": [10, 10, 30, 20], "widget_type": "text"}},
        "d": {"x_petey_id": "2", "type": "string", "widget": {"page": 1, "rect": [32, 10, 52, 20], "widget_type": "text"}},
        "f": {"x_petey_id": "3", "type": "string", "widget": {"page": 1, "rect": [10, 40, 60, 50], "widget_type": "text"}},
        "l": {"x_petey_id": "4", "type": "string", "widget": {"page": 1, "rect": [62, 40, 112, 50], "widget_type": "text"}}}}
    tagged = [{"kind": "date", "fields": ["1", "2"]}, {"kind": "name", "fields": ["3", "4"]}]
    keys = K.page_keys(bp, [e for e in tagged if st.counts(e["kind"])])
    assert keys[1]["groups"] == [["1", "2"]]
