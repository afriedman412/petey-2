"""Duplicate labels (petey/label/dedup.py) and field names printed from their parts (field identifiers,
docs/PLAN_FIELD_IDENTIFIERS.md; decided order: subject, suffix, iteration, part)."""
import pytest

import field_identifiers as FI
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
        ({"subject": "sibling_name", "iteration": "1", "suffix": ""}, "sibling_name_1"),
    ])
    def test_order_and_absent_parts(self, ident, want):
        assert FI.print_name(ident) == want
        assert S.print_name(ident) == want           # bulk printing uses the same order

    def test_old_order_kept_for_comparison(self):
        assert FI.print_name({"subject": "loss", "suffix": "dt", "iteration": "2"}, "old") == "loss_2_dt"


class TestReadIdentifiers:
    def test_suffix_and_part(self):
        ident, flags = FI.read("veteran_ssn_1", {"type": "string"}, {"veteran_ssn_1": "ssn"}, None, FI._series_index([]))
        assert ident == {"subject": "veteran", "suffix": "ssn", "part": "1"} and flags == []

    def test_the_varying_number_is_the_iteration(self):
        names = ["parent_1_first_nm", "parent_2_first_nm"]
        ident, _ = FI.read("parent_2_first_nm", {"type": "string"}, {}, None, FI._series_index(names))
        assert ident == {"subject": "parent_first", "suffix": "nm", "iteration": "2"}

    def test_no_suffix_is_flagged_under_the_standard(self):
        _, flags = FI.read("gross_rents", {"type": "number"}, {}, None, FI._series_index([]))
        assert "no standard suffix" in flags
