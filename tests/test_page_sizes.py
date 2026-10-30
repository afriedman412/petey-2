"""Every tab shows every page; the page list says how many fields have a box on each page, so a page with none is
drawn apart (Andrew, 2026-10-27)."""
import pymupdf

from petey.validate.hand_review import page_sizes


def test_every_page_with_its_field_count(tmp_path):
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page(width=612, height=792)
    blank = tmp_path / "blank.pdf"
    doc.save(str(blank))
    bp = {"fields": {
        "name": {"widget": {"page": 1, "rect": [10, 10, 100, 20]}},
        "date": {"widget": {"page": 1, "rect": [10, 30, 100, 40]}},
        "answer": {"widgets": {"yes": {"page": 3, "rect": [10, 10, 20, 20]}, "no": {"page": 3, "rect": [30, 10, 40, 20]}}},
        "lost": {"widget": {"page": 2}},                      # no box: not on the page
    }}
    got = page_sizes(bp, blank)
    assert [(p["page"], p["fields"]) for p in got] == [(1, 2), (2, 0), (3, 1)]
    assert got[0]["w_pt"] == 612 and got[0]["h_pt"] == 792


def test_no_blank_no_pages(tmp_path):
    assert page_sizes({"fields": {}}, tmp_path / "missing.pdf") == []
