"""The mechanical pass (eval/mechanical_pass.py): a box whose line reads "Reserved for future use" is not a field
(2026-10-17). Form 8825 prints lines 15 and 16 that way on both pages, one box per property column."""
import pytest

import mechanical_pass as M
from petey.label.auto_label import enumerate_geometry


@pytest.fixture(scope="module")
def form():
    from tests.conftest import F8825
    widgets, _, _ = enumerate_geometry(F8825, "auto")
    bp = {"fields": {f"f{w['id']}": {"type": "string", "widget": {"page": w["page"], "rect": w["rect"],
                                                                  "path": w["path"]}} for w in widgets}}
    return bp, F8825


def test_reserved_lines_are_removed(form):
    bp, blank = form
    out = M.reserved(bp, blank)
    # lines 15 and 16 x four property columns, on each of the two pages
    assert len(out) == 16
    assert {o["page"] for o in out} == {1, 2}
    assert all("reserved for future use" in o["why"] for o in out)      # its own line, or a line-mate's


def test_no_blank_no_page_reading(form):
    bp, _ = form
    assert M.reserved(bp, None) == []
