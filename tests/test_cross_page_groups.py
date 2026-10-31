"""Option groups that cross a page taken apart (eval/cross_page_groups.py, 2026-10-31, ATF Form 4: Q1's Yes on three
copies of a page was one group, and each row's Yes and No stayed apart)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import cross_page_groups as X  # noqa: E402


def _item(field, key, page, x, y):
    iid = f"{field}::{key}" if key else field
    return iid, {"id": iid, "field": field, "key": key, "page": page, "rect": [x, y, x + 10, y + 10],
                 "widget_type": "checkbox"}


def _units(groups):
    return [{"name": n, "type": "category", "items": ids, "origin": n} for n, ids in groups.items()]


def test_copy_pages_are_grouped_as_the_first_copy():
    # pages 2 and 9 are copies; the publisher's names made "all Yes" and "all No" groups across them
    items = dict([_item("yes", "a", 2, 500, 100), _item("yes", "b", 9, 500, 100),
                  _item("no", "a", 2, 530, 100), _item("no", "b", 9, 530, 100)])
    # as staged and partly hand-fixed: p2's Yes / No paired, the copy's No still in that group, its Yes on its own
    units = _units({"q1": ["yes::a", "no::a", "no::b"], "yes": ["yes::b"]})
    out, notes = X.regroup({"fields": {}}, items, units, None)
    by_page = sorted(sorted(u["items"]) for u in out if u["items"])
    assert by_page == [["no::a", "yes::a"], ["no::b", "yes::b"]]
    assert any("copy of p2" in n for n in notes)


def test_other_groups_crossing_a_page_are_split_by_page():
    items = dict([_item("g", "a", 1, 50, 100), _item("g", "b", 1, 90, 100), _item("g", "c", 3, 300, 500),
                  _item("g", "d", 3, 340, 500), _item("g", "e", 3, 380, 500)])
    out, notes = X.regroup({"fields": {}}, items, _units({"p1_o1": list(items)}), None)
    assert sorted(sorted(u["items"]) for u in out) == [["g::a", "g::b"], ["g::c", "g::d", "g::e"]]
    assert {u["name"] for u in out} == {"p1_o1", "p3_o1"}
