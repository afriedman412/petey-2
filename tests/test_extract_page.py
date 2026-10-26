"""Extraction reads the page at the blueprint's rects (petey/extract.py; Andrew, 2026-10-19: presume the form is
flattened, never read the form layer). Values are written the usual way (through the form fields) and read back
from the page."""
import pymupdf

from petey.extract import extract
from petey.synth.render import render_case

NAME_RECT = [36.0, 94.0, 453.6, 108.0]
ADDR_RECT = [58.6, 180.0, 200.9, 204.0]
CASE = {"p1:36.0,94.0,453.6,108.0": "Harbor Light Logistics Inc",
        "p1:58.2,180.8,200.8,191.2": "1120 Sycamore Terrace", "p1:58.6,193.4,200.6,203.0": "Fresno, CA 93721"}


def bpt():
    return {"fields": {"taxpayer_name": {"type": "string", "widget": {"page": 1, "rect": NAME_RECT}},
                       "property_address_1": {"type": "string", "widget": {"page": 1, "rect": ADDR_RECT}}}}


def test_reads_what_was_filled(f8825, tmp_path):
    render_case(dict(CASE), f8825, tmp_path / "filled.pdf")
    got = extract(bpt(), tmp_path / "filled.pdf", blank_pdf=f8825)
    assert got["taxpayer_name"] == "Harbor Light Logistics Inc"
    assert "1120 Sycamore Terrace" in got["property_address_1"]


def test_no_path_needed(f8825, tmp_path):
    # the blueprint above carries no widget path: rects alone read the page
    render_case(dict(CASE), f8825, tmp_path / "filled.pdf")
    assert extract(bpt(), tmp_path / "filled.pdf", blank_pdf=f8825)["taxpayer_name"]


def test_flattened_reads_the_same(f8825, tmp_path):
    render_case(dict(CASE), f8825, tmp_path / "filled.pdf")
    with pymupdf.open(str(tmp_path / "filled.pdf")) as d:
        d.bake(annots=True, widgets=True)
        d.save(str(tmp_path / "flat.pdf"))
    a = extract(bpt(), tmp_path / "filled.pdf", blank_pdf=f8825)
    b = extract(bpt(), tmp_path / "flat.pdf", blank_pdf=f8825)
    assert {k: v for k, v in a.items() if not k.startswith("_")} == {k: v for k, v in b.items() if not k.startswith("_")}
