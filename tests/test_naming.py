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
