"""The naming standard (petey/validate/standardize_names.py, docs/NAMING.md): [subject]_[iteration]_[suffix]_[part] as
decided with Andrew 2026-10-14/15, applied on copies by the clearing passes."""
import pytest

from petey.validate.standardize_names import has_suffix, number_firsts, part_sets, standard, zero_based


@pytest.mark.parametrize("name, spec, want", [
    # a number after the suffix is an iteration: it moves before the suffix
    ("loss_occurrence_dt_2", {"type": "date"}, "loss_occurrence_2_dt"),
    # a number glued to a word is split off
    ("parent1_nm", {"type": "string"}, "parent_1_nm"),
    # a percentage is _pct, never _qty / _cnt (2026-10-15)
    ("ownership_qty", {"type": "number", "semantic_type": "percent"}, "ownership_pct"),
    # the type's default suffix, when the name has none
    ("gross_rents", {"type": "number", "semantic_type": "money"}, "gross_rents_amt"),
    ("hours_flown", {"type": "number"}, "hours_flown_qty"),
    ("dependents", {"type": "integer"}, "dependents_cnt"),
    ("signed", {"type": "boolean"}, "signed_ind"),
    ("home_city", {"type": "string"}, "home_city_nm"),
    ("mailing_country", {"type": "string"}, "mailing_country_cd"),
    # numbered lines of one paragraph: one text value, the line a part after the suffix
    ("remarks_line_2", {"type": "string"}, "remarks_txt_2"),
    # an option group keeps its question's name (no suffix)
    ("filing_status", {"type": "category", "values": ["single", "joint"]}, "filing_status"),
    # a phone part word is left for a person
    ("telephone_area", {"type": "string"}, "telephone_area"),
])
def test_standard(name, spec, want):
    assert standard(name, spec)[0] == want


def test_unchanged_name_reports_nothing():
    assert standard("filing_status", {"type": "category", "values": ["a"]}) == ("filing_status", [])


def test_every_occurrence_numbered_the_first_too():
    # parent_nm next to parent_2_nm is parent_1_nm (decided 2026-10-14)
    assert number_firsts(["parent_nm", "parent_2_nm", "parent_3_nm"]) == {"parent_nm": "parent_1_nm"}


def test_number_firsts_never_onto_an_existing_name():
    assert number_firsts(["premium_amt", "premium_1_amt", "premium_2_amt"]) == {}


def test_zero_based_duplicates_shift_up():
    assert zero_based(["auto_dt", "auto_dt_1", "auto_dt_2"]) == {"auto_dt": "auto_dt_1", "auto_dt_1": "auto_dt_2",
                                                                  "auto_dt_2": "auto_dt_3"}


@pytest.mark.parametrize("name, want", [("telephone_nbr_area", True), ("summary_txt_3", True),
                                        ("veteran_ssn_1", True), ("gross_rents", False)])
def test_has_suffix(name, want):
    assert has_suffix(name) is want


def _box(x0, x1, page=1):
    return {"type": "number", "widget": {"page": page, "rect": [x0, 0, x1, 10]}}


def test_dollars_and_cents_need_a_narrow_cents_box():
    # 940 / 941: a 21 pt cents box against the dollars box is one amount
    assert part_sets({"line_3_amt_1": _box(480, 552), "line_3_amt_2": _box(554, 575)}) == {
        "line_3_amt_1": ("line_3_amt", "money", "dollars"), "line_3_amt_2": ("line_3_amt", "money", "cents")}


def test_two_amount_boxes_alike_are_two_amounts():
    # T2 p6 (2026-10-20): a subtotal carried right to amount J, two 77 pt boxes 22 pt apart, not dollars / cents
    assert part_sets({"amount_j_amt_1": _box(264, 341), "amount_j_amt_2": _box(363, 440)}) == {}
