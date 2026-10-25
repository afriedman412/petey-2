"""The field-name standard (petey/naming.py; Andrew, 2026-10-24):
[block subject]_[block iteration]_[field subject]_[suffix]_[field iteration]_[part], short suffixes, parts as words or
part1, a block alone with no number."""
import pytest

from petey import naming
from petey.validate import block_types as bt


@pytest.mark.parametrize("ident, want", [
    ({"block_prefix": "child", "block_iteration": "2", "subject": "ssn", "part": "part_1"}, "child_2_ssn_part1"),
    ({"subject": "ssn", "iteration": "2", "part": "part1"}, "ssn_2_part1"),
    ({"subject": "phone", "suffix": "number", "iteration": "2", "part": "area"}, "phone_nbr_2_area"),
    ({"subject": "first_name"}, "first_nm"),
    ({"subject": "zip", "suffix": "code"}, "zip_cd"),
    ({"block_prefix": "child", "block_iteration": "2", "subject": "name"}, "child_2_nm"),
    ({"subject": "business", "suffix": "nm", "iteration": "3"}, "business_nm_3"),
])
def test_print_name(ident, want):
    assert naming.print_name(ident) == want


@pytest.mark.parametrize("name, want", [
    ("business_phone_number", "business_phone_nbr"), ("agency_name_2", "agency_nm_2"), ("final_tax_code", "final_tax_cd"),
    ("name", "name"), ("first_nm", "first_nm"), ("zip_code_extension", "zip_code_extension"),
])
def test_short_suffix_on_saved_names(name, want):
    assert naming.short_suffix(name) == want


def test_a_position_wording_never_starts_with_the_blocks_number():
    """B 106D BT4 (2026-10-24): a grown position worded 1_last_4_digits_account_nbr printed notify_others_1_1_..."""
    assert bt.slot_text(bt.slot("1_last_4_digits_account_nbr")) == "last_4_digits_account_nbr"
    assert bt.slot("first_name") == {"subject": "first", "suffix": "nm"}
    assert bt.slot_text(bt.slot("ssn_part1")) == "ssn_part1"


def test_a_positions_own_number_prints_after_the_suffix():
    """ACORD 80 BT4 (Andrew, 2026-10-25): a block's second and third 'other coverage options' boxes."""
    s = bt.slot("other_coverage_opts_2_txt")
    assert s == {"subject": "other_coverage_opts", "suffix": "txt", "iteration": "2"}
    assert bt.slot({"subject": "other_coverage_opts_3", "suffix": "txt"})["iteration"] == "3"
    assert bt.slot("address_line_1_txt") == {"subject": "address_line_1", "suffix": "txt"}       # a line's label stays
    assert naming.print_name(bt.block_ident("coverage_type", "2", s)) == "coverage_type_2_other_coverage_opts_txt_2"


@pytest.mark.parametrize("name, want", [
    ("child_2_first_name", {"block_prefix": "child", "block_iteration": "2", "subject": "first", "suffix": "nm"}),
    ("procedure_cd_2", {"subject": "procedure", "suffix": "cd", "iteration": "2"}),
    ("phone_nbr_2_area", {"subject": "phone", "suffix": "nbr", "iteration": "2", "part": "area"}),
    ("address_line_1_txt", {"subject": "address_line_1", "suffix": "txt"}),
    ("employment_2_to_dt", {"block_prefix": "employment", "block_iteration": "2", "subject": "to", "suffix": "dt"}),
])
def test_a_proposed_name_reads_into_the_standards_parts(name, want):
    """Andrew (2026-10-25): '"improve name" should also change "subject"': the proposal fills the parts."""
    got = naming.parse(name, {"nm", "nbr", "cd", "txt", "dt", "amt", "ind"}, {"area", "line", "month"})
    assert got == want and naming.print_name(got) == naming.print_name(want)
