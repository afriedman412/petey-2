"""Corrections made on the review page (hand_review.clean_edit, 2026-10-07 on) and the whole-dollar rule
(money_retype.keep_reason, 2026-10-07): only what differs is kept, and every part is validated."""
import pytest

from petey.validate.hand_review import clean_edit
from petey.validate.money_retype import keep_reason

SPEC = {"type": "string", "x_petey_identifiers": {"subject": "parent_first", "suffix": "nm", "iteration": "1"}}


class TestCleanEdit:
    def test_nothing_changed_is_nothing(self):
        assert clean_edit("parent_first_nm_1", SPEC, {"name": "parent_first_nm_1", "type": "string"}) is None

    def test_a_rename_and_a_type(self):
        assert clean_edit("x", {"type": "string"}, {"name": "gross_rents", "type": "number"}) == \
            {"name": "gross_rents", "type": "number"}

    def test_the_name_is_printed_from_its_parts(self):
        out = clean_edit("parent_first_nm_1", SPEC, {"identifiers": {"subject": "parent_first", "suffix": "nm",
                                                                      "iteration": "2"}})
        assert out["name"] == "parent_first_nm_2" and out["identifiers"]["iteration"] == "2"

    @pytest.mark.parametrize("edit, msg", [({"name": "Bad Name"}, "lower-case"), ({"type": "money"}, "one of"),
                                           ({"semantic_type": "shoe_size"}, "not in the registry"),
                                           ({"pattern": "(["}, "regular expression"),
                                           ({"identifiers": {"iteration": "2"}}, "subject")])
    def test_bad_edits_are_refused(self, edit, msg):
        with pytest.raises(ValueError, match=msg):
            clean_edit("x", {"type": "string"}, edit)

    def test_semantic_type_none_clears(self):
        assert clean_edit("x", {"type": "string", "semantic_type": "text"}, {"semantic_type": "none"}) == \
            {"semantic_type": "none"}

    def test_a_group_must_stay_a_choice(self):
        grp = {"type": "category", "widgets": {"a": {}, "b": {}}}
        with pytest.raises(ValueError, match="option group"):
            clean_edit("g", grp, {"type": "string"})


class TestWholeDollars:
    def test_the_fields_own_text(self):
        spec = {"description": "Enter amounts rounded to whole dollars", "widget": {}}
        assert keep_reason("x_amt", spec, {}, {}, lambda pg: "").startswith("field text")

    def test_may_round_does_not_count(self):
        spec = {"widget": {"page": 1, "rect": [0, 0, 50, 10]}}
        assert keep_reason("x_amt", spec, {}, {}, lambda pg: "You may round off cents to whole dollars.") == ""

    def test_the_page_asks_for_whole_dollars(self):
        spec = {"widget": {"page": 1, "rect": [0, 0, 50, 10]}}
        assert keep_reason("x_amt", spec, {}, {}, lambda pg: "Round to the nearest whole dollar.").startswith("page")

    def test_a_cents_box_beside_it(self):
        fields = {"x_amt": {"widget": {"page": 1, "rect": [0, 0, 50, 10], "widget_type": "text"}},
                  "x_cents": {"widget": {"page": 1, "rect": [52, 0, 70, 10], "widget_type": "text"}}}
        assert keep_reason("x_amt", fields["x_amt"], fields, {}, lambda pg: "") == "cents box: x_cents"

    def test_otherwise_plain_money(self):
        spec = {"widget": {"page": 1, "rect": [0, 0, 50, 10]}}
        assert keep_reason("x_amt", spec, {}, {}, lambda pg: "Total income") == ""
