"""Structure-first labeling (petey/label/structure.py): a table's cells printed from its columns' and rows' labels,
a block group's from its fields' labels, and the prompts that ask for them, in both naming schemes."""
import re

import pytest

from petey.label import auto_label, structure as S


def table(tid="T1", rows=3, cols=2, start=0):
    """A page structure with one table of rows x cols cells, ids numbered row by row from `start`."""
    cells = [{"id": start + r * cols + c, "row": r, "col": c} for r in range(rows) for c in range(cols)]
    return {"tables": [{"id": tid, "cells": cells}], "blocks": []}


def ids_of(ps):
    return {c["id"] for t in ps.get("tables", []) for c in t["cells"]} | \
           {c["id"] for b in ps.get("blocks", []) for c in b["cells"]}


# ---------------------------------------------------------------------------
# print_cells: tables
# ---------------------------------------------------------------------------

class TestTables:
    def test_columns_named_rows_numbered(self):
        ps = table(rows=2, cols=2)
        ans = {"tables": [{"id": "T1", "columns": [{"col": 1, "label": "vehicle_make_txt"},
                                                    {"col": 2, "label": "vehicle_year"}], "rows": "numbered"}]}
        names, parts, left = S.print_cells(ps, ans, ids_of(ps))
        assert names == {0: "vehicle_make_txt_1", 1: "vehicle_year_1", 2: "vehicle_make_txt_2", 3: "vehicle_year_2"}
        assert parts[0] == {"subject": "vehicle_make", "suffix": "txt", "iteration": "1"}
        assert left == []

    def test_rows_named_columns_lettered(self):
        # printed column letters (a) .. (d) number 1 .. 4 (docs/NAMING.md)
        ps = table(rows=1, cols=3)
        ans = {"tables": [{"id": "T1", "rows": [{"row": 1, "label": "gross_rents_amt"}], "columns": ["a", "b", "c"]}]}
        names, _, _ = S.print_cells(ps, ans, ids_of(ps))
        assert names == {0: "gross_rents_amt_1", 1: "gross_rents_amt_2", 2: "gross_rents_amt_3"}

    def test_both_axes_named(self):
        ps = table(rows=1, cols=1)
        ans = {"tables": [{"id": "T1", "rows": [{"row": 1, "label": "applicant"}],
                           "columns": [{"col": 1, "label": "first_nm"}]}]}
        names, parts, _ = S.print_cells(ps, ans, ids_of(ps))
        assert names[0] == "applicant_first_nm" and parts[0] == {"subject": "applicant_first", "suffix": "nm"}

    def test_simple_scheme_kind_goes_into_parts(self):
        ps = table(rows=1, cols=1)
        ans = {"tables": [{"id": "T1", "columns": [{"col": 1, "label": "gross_rents", "kind": "money"}],
                           "rows": "numbered"}]}
        names, parts, _ = S.print_cells(ps, ans, ids_of(ps))
        assert names[0] == "gross_rents_1" and parts[0]["kind"] == "money"

    def test_unlike_or_unanswered_tables_are_left_for_one_by_one(self):
        ps = table(rows=2, cols=2)
        for ans in ({"tables": [{"id": "T1", "rows": "unlike", "columns": "numbered"}]}, {"tables": []}):
            names, _, left = S.print_cells(ps, ans, ids_of(ps))
            assert names == {} and sorted(left) == [0, 1, 2, 3]

    def test_aside_row_is_left(self):
        # ACORD 90 NY: a header line of driver numbers over the vehicle rows
        ps = table(rows=3, cols=1)
        ans = {"tables": [{"id": "T1", "columns": [{"col": 1, "label": "driver_use_pct"}], "rows": "numbered",
                           "aside": [1]}]}
        names, _, left = S.print_cells(ps, ans, ids_of(ps))
        assert left == [0] and set(names) == {1, 2}

    def test_duplicate_column_labels_are_left(self):
        # two panes side by side read as one table: the printed names would collide
        ps = table(rows=1, cols=2)
        ans = {"tables": [{"id": "T1", "columns": [{"col": 1, "label": "rate_class"}, {"col": 2, "label": "rate_class"}],
                           "rows": "numbered"}]}
        names, _, left = S.print_cells(ps, ans, ids_of(ps))
        assert names == {} and sorted(left) == [0, 1]

    def test_empty_label_drops_the_line(self):
        ps = table(rows=1, cols=2)
        ans = {"tables": [{"id": "T1", "columns": [{"col": 1, "label": "amount_amt"}, {"col": 2, "label": ""}],
                           "rows": "numbered"}]}
        names, _, _ = S.print_cells(ps, ans, ids_of(ps))
        assert names == {0: "amount_amt_1", 1: ""}


# ---------------------------------------------------------------------------
# print_cells: block groups
# ---------------------------------------------------------------------------

class TestBlocks:
    def blocks(self):
        # two blocks of three slots: name, marital status, a Yes / No pair counted as two slots
        cells = [{"id": b * 4 + s, "block": b, "slot": s} for b in range(2) for s in range(4)]
        return {"tables": [], "blocks": [{"id": "B1", "cells": cells}]}

    def answer(self):
        return {"blocks": [{"id": "B1", "entity": "sibling", "fields": [
            {"slot": 1, "label": "name"}, {"slot": 2, "label": "marital_status"},
            {"slot": 3, "label": "will_accompany.yes"}, {"slot": 4, "label": "will_accompany.no"}]}]}

    def test_entity_leads_with_its_number(self):
        # IMM 5645: the entity and its number lead (the naming standard, 2026-10-24), the short suffix
        ps = self.blocks()
        names, parts, left = S.print_cells(ps, self.answer(), ids_of(ps))
        assert names[0] == "sibling_1_nm" and names[5] == "sibling_2_marital_status"
        assert parts[0] == {"block_prefix": "sibling", "block_iteration": "1", "subject": "name"}
        assert left == []

    def test_a_choice_pair_prints_the_group_and_keeps_the_value(self):
        ps = self.blocks()
        names, parts, _ = S.print_cells(ps, self.answer(), ids_of(ps))
        assert names[2] == "sibling_1_will_accompany.yes" and names[7] == "sibling_2_will_accompany.no"
        assert 2 not in parts                                 # a choice carries no parts (yet)

    def test_unanswered_block_is_left(self):
        ps = self.blocks()
        _, _, left = S.print_cells(ps, {"blocks": []}, ids_of(ps))
        assert sorted(left) == list(range(8))


# ---------------------------------------------------------------------------
# The prompts, per naming scheme
# ---------------------------------------------------------------------------

SUFFIXED = re.compile(r"\b[a-z0-9]+_(?:ind|nm|txt|amt|dt|cd|nbr|pct|qty|cnt)\b")


@pytest.fixture
def simple(monkeypatch):
    monkeypatch.setattr(auto_label, "NAMES", "simple")
    monkeypatch.setattr(S, "SIMPLE", True)


class TestPrompts:
    def test_simple_prompts_show_no_suffixed_example(self, simple):
        # 2026-10-19: one suffix-free twin never matched and the radio rule kept is_amended_return_ind; the labeler
        # wrote 23-46 _ind names on ACORD 90 NY in simple mode. "no _txt, _nm ..." in the rule itself is not a slug.
        labeler = auto_label._system().replace("(no _txt, _nm, _nbr, _cd, _dt, _amt, _ind, _qty, _ssn)", "")
        assert SUFFIXED.findall(labeler) == []
        assert SUFFIXED.findall(S._rules()) == []

    def test_simple_labeler_asks_for_a_kind(self, simple):
        p = auto_label._system()
        assert '"kind": "<kind>"' in p and '"identifier"' in p and '"name" for any name' in p

    def test_say_whose_rule_numbers_last_and_spares_parts(self, simple):
        # IMM 5645: the lone box the block finder missed (sibling_marital_status_7, number last as printing writes
        # it); a table or block answered by its parts takes no number, or the labeler drops the bulk answer
        p = auto_label._system()
        assert "`sibling_marital_status_7`" in p and "takes no number" in p
        assert "sibling_marital_status_7" in S._rules()

    def test_standard_prompts_unchanged(self, monkeypatch):
        monkeypatch.setattr(auto_label, "NAMES", "standard")
        monkeypatch.setattr(S, "SIMPLE", False)
        assert auto_label._system() == auto_label.LABEL_SYSTEM
        assert "vehicle_make_txt" in S._rules() and '"kind"' not in S._rules()


def test_page_check_lets_numbered_lines_of_one_answer_be():
    # Andrew, 2026-10-20: "multiple text lines split into many similarly labeled fields is common" (CBP 7512's
    # "Entered or withdrawn by" over five lines was flagged `continues` in every run)
    from petey.validate.page_check import SYSTEM
    assert "Do not flag lines that are already named as numbered lines of one answer" in SYSTEM


def test_simple_is_the_default():
    # Andrew, 2026-10-20: "simple defaults from here"
    import inspect
    assert inspect.signature(auto_label.build_blueprint).parameters["names"].default == "simple"
    assert 'default="simple"' in inspect.getsource(auto_label.main)


def test_simple_prompt_names_the_non_us_kinds(simple):
    p = auto_label._system()
    assert '"ca_postal_code"' in p and '"uk_postcode"' in p and '"intl_phone"' in p
