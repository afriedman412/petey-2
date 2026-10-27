"""The light flat path and the corpus collection for the flat-structure benchmark (2026-10-26): publisher groups kept
apart when joins are added, the fetcher's sector and rehosted-government rules, and widget boxes for staging."""
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "acquisition"))

import flat_light as FL  # noqa: E402
import safedocs_fetch as SF  # noqa: E402
import safedocs_stage as SS  # noqa: E402


def test_publisher_groups_never_merge():
    # two publisher yes / no groups and a code or Jev join between them: the pregnancy intake pack lost 6 groups so
    marks = ["f1", "f2", "f3", "f4", "f5"]
    got = FL._union_keeping([{"f1", "f2"}, {"f3", "f4"}], [("f2", "f3")], marks)
    assert sorted(map(sorted, got)) == [["f1", "f2"], ["f3", "f4"]]


def test_loose_box_may_join_a_publisher_group():
    marks = ["f1", "f2", "f3", "f4"]
    got = FL._union_keeping([{"f1", "f2"}], [("f2", "f3"), ("f3", "f4")], marks)
    assert sorted(map(sorted, got)) == [["f1", "f2", "f3", "f4"]]


def test_loose_box_cannot_bridge_two_publisher_groups():
    marks = ["f1", "f2", "f3", "f4", "f5"]
    got = FL._union_keeping([{"f1", "f2"}, {"f4", "f5"}], [("f2", "f3"), ("f3", "f4")], marks)
    assert sorted(map(sorted, got)) == [["f1", "f2", "f3"], ["f4", "f5"]]


def test_sector_from_the_url_path_not_the_host():
    assert SF.sector_of("https://example.com/forms/new-patient-intake.pdf") == "health"
    assert SF.sector_of("https://healthclinic.com/files/a1.pdf") is None         # the host's words do not count
    assert SF.sector_of("https://x.org/docs/employment-application.pdf") == "employment"


def test_rehosted_government_forms_by_url():
    assert SF.GOV_URL.search("https://acme.com/hr/fw9.pdf")
    assert SF.GOV_URL.search("https://acme.com/hr/I-9_form.pdf")
    assert not SF.GOV_URL.search("https://acme.com/hr/review-form.pdf")


def test_zip_url_is_arithmetic():
    assert SF.zip_url("0000123.pdf").endswith("/zipfiles/0000-0999/0000.zip")
    assert SF.zip_url("1659642.pdf").endswith("/zipfiles/1000-1999/1659.zip")


def _add(page, kind, name, rect):
    w = pymupdf.Widget()
    w.field_type = kind
    w.field_name = name
    w.rect = pymupdf.Rect(*rect)
    if kind == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
        w.field_value = False
    page.add_widget(w)


def test_widget_boxes_skip_buttons_and_keep_radio_groups(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=600, height=400)
    _add(pg, pymupdf.PDF_WIDGET_TYPE_TEXT, "name", (50, 50, 300, 66))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "smoker", (50, 100, 60, 110))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON, "smoker", (100, 100, 110, 110))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "agree", (50, 150, 60, 160))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_BUTTON, "print", (400, 300, 480, 320))
    p = tmp_path / "f.pdf"
    doc.save(p)
    boxes, groups = SS.widget_boxes(p)
    assert [b["kind"] for b in boxes] == ["text", "radio", "radio", "checkbox"]
    assert [b["id"] for b in boxes] == ["1", "2", "3", "4"]
    assert groups == [{"f2", "f3"}]
