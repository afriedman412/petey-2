"""Duplicate labels (petey/label/dedup.py) and field names printed from their parts (field identifiers,
docs/PLAN_FIELD_IDENTIFIERS.md; decided order: subject, suffix, iteration, part)."""
import pytest

from petey.validate import field_identifiers as FI
from petey.label import structure as S
from petey.label.dedup import DedupState


class TestDedup:
    def test_first_in_reading_order_keeps_the_name(self):
        d = DedupState()
        assert [d.assign("phone", 1, [0, 0, 1, 1]) for _ in range(3)] == ["phone", "phone_2", "phone_3"]
        assert d.summary()["duplicate_labels_reassigned"] == 2

    def test_a_number_already_taken_is_skipped(self):
        d = DedupState()
        d.assign("phone_2", 1, [0, 0, 1, 1])
        d.assign("phone", 1, [0, 0, 1, 1])
        assert d.assign("phone", 1, [0, 0, 1, 1]) == "phone_3"

    def test_collision_log_names_both(self):
        d = DedupState()
        d.assign("x", 1, [0, 0, 1, 1]); d.assign("x", 2, [5, 5, 6, 6])
        c = d.summary()["collisions"][0]
        assert c["original_label"] == "x" and c["assigned_label"] == "x_2" and c["page"] == 2


class TestPrintName:
    @pytest.mark.parametrize("ident, want", [
        ({"subject": "parent_first", "suffix": "nm", "iteration": "2"}, "parent_first_nm_2"),
        ({"subject": "veteran", "suffix": "ssn", "part": "1"}, "veteran_ssn_1"),
        ({"subject": "gross_rents", "iteration": "3"}, "gross_rents_3"),          # simple scheme: no suffix
        ({"subject": "sibling_name", "iteration": "1", "suffix": ""}, "sibling_nm_1"),   # the short suffix (2026-10-24)
        ({"block_prefix": "child", "block_iteration": "2", "subject": "ssn", "part": "part_1"}, "child_2_ssn_part1"),
        ({"subject": "phone", "suffix": "number", "iteration": "2", "part": "area"}, "phone_nbr_2_area"),
    ])
    def test_order_and_absent_parts(self, ident, want):
        assert FI.print_name(ident) == want
        assert S.print_name(ident) == want           # bulk printing uses the same order

    def test_old_order_kept_for_comparison(self):
        assert FI.print_name({"subject": "loss", "suffix": "dt", "iteration": "2"}, "old") == "loss_2_dt"


class TestReadIdentifiers:
    """The one parts reader (petey/naming.read_name, 2026-10-26), with the context the form gives: a compound
    value's part, a series' varying number (`line`), a block."""
    def test_suffix_and_part(self):
        from petey import naming
        ident, flags = naming.read_name("veteran_ssn_1", {"type": "string"}, part="1")
        assert ident == {"subject": "veteran", "suffix": "ssn", "part": "1"} and flags == []

    def test_a_number_before_field_words_is_the_blocks(self):
        """The naming standard (2026-10-24): parent_2_first_nm is the second parent's first name."""
        from petey import naming
        ident, _ = naming.read_name("parent_2_first_nm", {"type": "string"}, line="2")
        assert ident == {"block_prefix": "parent", "block_iteration": "2", "subject": "first", "suffix": "nm"}

    def test_a_number_before_the_suffix_is_the_fields(self):
        from petey import naming
        ident, _ = naming.read_name("procedure_2_cd", {"type": "string"}, line="2")
        assert ident == {"subject": "procedure", "suffix": "cd", "iteration": "2"}
        assert FI.print_name(ident) == "procedure_cd_2"

    def test_a_line_label_stays_with_its_word(self):
        from petey import naming
        ident, _ = naming.read_name("liabilities_row_14_amt", {"type": "number"}, line="14")
        assert FI.print_name(ident) == "liabilities_row_14_amt"

    def test_no_suffix_is_flagged_under_the_standard(self):
        from petey import naming
        _, flags = naming.read_name("gross_rents", {"type": "number"})
        assert "no standard suffix" in flags
