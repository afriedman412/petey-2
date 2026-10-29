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


def test_stacked_widgets_become_one_field():
    # bm__sd_1474805 p2 (2026-10-27): two widgets on one printed box; the one a saved block type uses stays
    w = lambda r: {"page": 2, "rect": r, "widget_type": "text", "path": None}
    bp = {"fields": {"a": {"type": "string", "x_petey_id": "5", "widget": w([32, 247, 431, 263])},
                     "b": {"type": "string", "x_petey_id": "9", "widget": w([32, 247, 431, 263])},
                     "c": {"type": "string", "x_petey_id": "6", "widget": w([438, 247, 585, 263])}}}
    gone = FL.collapse_stacked(bp, keep={"9"})
    assert [d["name"] for d in gone] == ["a"] and sorted(bp["fields"]) == ["b", "c"]
    assert bp["x_petey_dropped_widgets"]["count"] == 1 and "stacked on b" in bp["x_petey_dropped_widgets"]["widgets"][0]["reason"]


def test_a_checkbox_on_a_text_box_is_not_merged():
    bp = {"fields": {"a": {"x_petey_id": "1", "widget": {"page": 1, "rect": [0, 0, 10, 10], "widget_type": "text"}},
                     "b": {"x_petey_id": "2", "widget": {"page": 1, "rect": [0, 0, 10, 10], "widget_type": "checkbox"}}}}
    assert FL.collapse_stacked(bp) == [] and len(bp["fields"]) == 2


def test_stacked_widgets_left_out_at_staging(tmp_path):
    # 2026-10-27, handoff item 4: staging collapses two widgets of one kind on one printed box, and logs the one left out
    doc = pymupdf.open()
    pg = doc.new_page(width=600, height=400)
    _add(pg, pymupdf.PDF_WIDGET_TYPE_TEXT, "employer", (50, 50, 300, 66))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_TEXT, "employer_copy", (50, 50, 300, 66))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_CHECKBOX, "on_top", (50, 50, 60, 60))     # another kind: not merged
    p = tmp_path / "f.pdf"
    doc.save(p)
    dropped = []
    boxes, _ = SS.widget_boxes(p, dropped)
    assert [b["kind"] for b in boxes] == ["text", "checkbox"]
    assert [d["widget_name"] for d in dropped] == ["employer_copy"]


def test_government_hosts_and_tiers():
    # Andrew, 2026-10-27: "more government forms from a variety of sources"; school districts stay out
    import safedocs_candidates as SC
    assert SC.is_gov("www.co.lake.il.us") and SC.is_gov("townofcary.org") and SC.is_gov("www2.gov.bc.ca")
    assert SC.is_gov("acme.com", "https://acme.com/DocumentCenter/View/12")
    assert not SC.is_gov("countyline-realty.com") and not SC.is_gov("lakeschools.k12.mi.us")
    assert SF.tier_of("www.fema.gov") == "federal" and SF.tier_of("tax.ny.gov") == "state"
    assert SF.tier_of("www.dmv.state.va.us") == "state" and SF.tier_of("www.nycourts.gov") == "courts"
    assert SF.tier_of("kingcounty.gov") == "local" and SF.tier_of("www.canada.ca") == "intl"
    assert SF.LIBRARY_HOSTS.search("www.irs.gov") and SF.LIBRARY_HOSTS.search("www.courts.ca.gov")
    assert not SF.LIBRARY_HOSTS.search("www.cdtfa.ca.gov")


def test_signature_widgets_are_text_fields(tmp_path):
    # 2026-10-28: signatures count as text (the benchmark's kinds); staging had left them out with the buttons
    doc = pymupdf.open()
    pg = doc.new_page(width=600, height=400)
    _add(pg, pymupdf.PDF_WIDGET_TYPE_TEXT, "name", (50, 50, 300, 66))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_SIGNATURE, "sign_here", (50, 300, 300, 320))
    _add(pg, pymupdf.PDF_WIDGET_TYPE_BUTTON, "print", (400, 350, 480, 370))
    p = tmp_path / "f.pdf"
    doc.save(p)
    boxes, _ = SS.widget_boxes(p)
    assert [b["kind"] for b in boxes] == ["text", "text"]


def test_two_groups_in_one_block_copy_both_kept(tmp_path, monkeypatch):
    # bm__mu_0d8e9867024f p3 (2026-10-29): YES / NO pairs in one block copy were all named p3_b1_c1, each written over
    # the one before (14 of the page's 20 boxes lost); now the second takes the next plain group name
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    doc.save(str(pdf))
    boxes = [{"id": str(i), "page": 1, "rect": [100 + 40 * (i % 2), 100 + 30 * (i // 2), 110 + 40 * (i % 2), 110 + 30 * (i // 2)],
              "kind": "checkbox"} for i in range(4)]
    monkeypatch.setattr(FL, "groups", lambda raw, stub, workers, preset=(): ([{"f0", "f1"}, {"f2", "f3"}], 0))
    block = {"cells": [{"id": i, "block": 0, "slot": i} for i in range(4)]}
    monkeypatch.setattr(FL.S, "find", lambda raw, entries: {1: {"tables": [], "blocks": [block]}})
    bp, _ = FL.build(pdf, "t", boxes=boxes)
    got = {n: sorted(w["rect"][1] for w in s["widgets"].values()) for n, s in bp["fields"].items()}
    assert sum(len(s["widgets"]) for s in bp["fields"].values()) == 4
    assert sorted(got.values()) == [[100, 100], [130, 130]] and "p1_b1_c1" in got
