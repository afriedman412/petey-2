"""Whole forms ignored (Andrew, 2026-11-03: an "ignored" status, "a little button next to the 'reset validation'
button"; "this is for whole forms. ignored should be another status that can be hidden or shown by the filter")."""
from pathlib import Path

import pytest

from petey_dataset import ignored_forms

SRC = Path(__file__).resolve().parents[1] / "petey" / "validate" / "review_app" / "src"


def test_ignore_needs_a_reason_and_can_be_taken_back(tmp_path):
    rec = tmp_path / "ignored_forms.json"
    with pytest.raises(ValueError):
        ignored_forms.put("lib__x", True, "  ", record=rec)
    assert ignored_forms.put("lib__x", True, "too   messy", record=rec)["lib__x"]["reason"] == "too messy"
    assert ignored_forms.load(rec)["lib__x"]["reason"] == "too messy"
    assert ignored_forms.put("lib__x", False, record=rec) == {} and ignored_forms.load(rec) == {}


def test_a_key_page_belongs_to_its_form():
    assert ignored_forms.page_form("bm__sd_12__p3") == "bm__sd_12"


def test_the_header_button_sits_next_to_reset_validation():
    header = (SRC / "components" / "Header.tsx").read_text()
    i = header.index('id="resetV"')
    assert header.index("</span>", i) < header.index('id="ignoreForm"') < header.index('id="notesBtn"')
    assert "/api/ignored-forms/" in header


def test_the_benchmark_leaves_ignored_forms_out():
    root = Path(__file__).resolve().parents[1]
    assert 'skipped["form ignored"] += 1' in (root / "eval" / "benchmark_key.py").read_text()
    assert "ignored_forms.page_form(pid) in ignored_f" in (root / "eval" / "benchmark_score.py").read_text()
