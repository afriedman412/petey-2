"""Names and their parts in step (Andrew, 2026-10-26: names built from parts; "block and groups need to consider parts
as well"): a name changed by a path that sends no parts gets parts read from it, printing exactly that name; a number
inside a name read alone stays with the subject (line_29_covered_all_12_months_ind: not block 12)."""
from petey import naming
from petey.validate import hand_review as h


def test_parts_for_prints_the_name_and_keeps_inner_numbers_in_the_subject():
    assert naming.parts_for("tooth_nbr_1") == {"subject": "tooth", "suffix": "nbr", "iteration": "1"}
    assert naming.parts_for("line_29_covered_all_12_months_ind") == {"subject": "line_29_covered_all_12_months",
                                                                       "suffix": "ind"}
    assert naming.parts_for("plan_name") == {"subject": "plan_name"}          # a typed name is not changed
    assert naming.parts_for("tax_status", {"widgets": {"a": {}, "b": {}}}) == {"subject": "tax_status"}


def test_sync_parts_keeps_matching_parts_and_the_grid():
    fields = {"a_nm": {"x_petey_identifiers": {"subject": "a", "suffix": "nm"}},
              "b_amt_2": {"x_petey_identifiers": {"subject": "old", "grid": "p1-G1"}}, "c_txt": {}}
    assert naming.sync_parts(fields) == ["b_amt_2", "c_txt"]
    assert fields["b_amt_2"]["x_petey_identifiers"] == {"subject": "b", "suffix": "amt", "iteration": "2", "grid": "p1-G1"}


def test_a_typed_rename_stores_its_parts():
    fields = {"old_nm": {"type": "string", "x_petey_identifiers": {"subject": "old", "suffix": "nm"}}}
    e = h.clean_edit("old_nm", fields["old_nm"], {"name": "insured_nm_2"})
    out = h.edit_fields(fields, {"old_nm": e}, {"old_nm": "insured_nm_2"}, "now", "rec")
    assert out["insured_nm_2"]["x_petey_identifiers"] == {"subject": "insured", "suffix": "nm", "iteration": "2"}


def test_read_name_with_the_forms_context():
    """One parts reader (2026-10-26): the standard's order; a block's start from its record; a grid line's number
    where it belongs (x_1_amt -> x_amt_1); a number after a line word, or one the line does not carry, stays put."""
    r = naming.read_name
    assert r("csl_premium_1_amt", line="1")[0] == {"subject": "csl_premium", "suffix": "amt", "iteration": "1"}
    assert r("line_29_covered_all_12_months_ind", line="29")[0] == {"subject": "line_29_covered_all_12_months",
                                                                    "suffix": "ind"}
    assert r("line_2_first_nm", line="39")[1] == ["number 2 is not its line's (39)"]
    assert r("child_2_first_nm", block=("child", "2"))[0] == {"block_prefix": "child", "block_iteration": "2",
                                                              "subject": "first", "suffix": "nm"}
    assert r("child_2_first_nm", block=("kid", "2"))[1]
    assert r("dependent_child_1_nm_2", block=("dependent_child", "1"))[0]["suffix"] == "nm"
    assert r("wiring_improvement_yr")[0] == {"subject": "wiring_improvement", "suffix": "yr"}
    assert r("signature_2_day")[0] == {"suffix": "signature", "iteration": "2", "part": "day"}    # a date's day
    assert r("item_5a_page", line="5") == ({"subject": "item_5a_page"}, ["no standard suffix"])     # the letter is the column's
