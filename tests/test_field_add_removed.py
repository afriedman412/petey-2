"""A removed field's box is a suggestion again once the removal is in the working copy (Andrew, 2026-10-28: "when you
remove a field, it should revert to orange instead of disappearing entirely")."""
from petey.validate.field_add import with_removed

W = {"sid": "w1", "source": "widget", "page": 1, "rect": [10, 10, 100, 20]}


def test_a_widget_freed_by_a_removal_stays_a_suggestion_of_itself():
    rec = {"removed_applied": [{"name": "old", "page": 1, "rect": [10, 10, 100, 20]}]}
    assert [x["sid"] for x in with_removed([W], [], rec)] == ["w1"]


def test_a_removed_box_with_nothing_behind_it_comes_back_as_its_own_suggestion():
    rec = {"removed_applied": [{"name": "old", "page": 2, "rect": [50, 50, 90, 60]}]}
    got = with_removed([W], [], rec)
    assert [(x["sid"], x["source"], x["page"]) for x in got] == [("w1", "widget", 1), ("r0", "removed_box", 2)]


def test_not_while_the_removal_waits_nor_where_a_field_is_again():
    pending = {"removed": [{"name": "old", "page": 1, "rect": [10, 10, 100, 20]}]}
    assert with_removed([W], [], pending) == []                       # still a field, drawn to be removed
    rec = {"removed_applied": [{"name": "old", "page": 2, "rect": [50, 50, 90, 60]}]}
    readded = [{"name": "new", "page": 2, "rect": [50, 50, 90, 60]}]
    assert [x["sid"] for x in with_removed([W], readded, rec)] == ["w1"]
