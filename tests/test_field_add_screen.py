"""Add / remove: finder boxes Jev's is-it-a-field screen scored under the cut are not suggested; boxes it kept, and
boxes it never scored, are (Andrew, 2026-11-01: on publisher-box blueprints ~92,570 uncovered finder boxes, ~1 in 5
real; "1 for everything else": the screened boxes as suggestions)."""
import json

import pymupdf
import yaml

from petey.validate import field_add

BOXES = [{"id": str(i), "page": 1, "rect": [72, y, 300, y + 14], "kind": "text", "key": f"k{i}", "conf": 1.0}
         for i, y in ((1, 100), (2, 200), (3, 300))]


def _ctx(tmp_path, monkeypatch, scores=None):
    doc = pymupdf.open()
    doc.new_page(width=612, height=792)
    blank = tmp_path / "f.pdf"
    doc.save(blank)
    bpt = tmp_path / "f.bpt"
    bpt.write_text(yaml.safe_dump({"source_pdf": "f.pdf", "fields": {}}))
    monkeypatch.setattr(field_add, "resolve_blank", lambda bp: blank)
    monkeypatch.setattr(field_add, "_finder_cached", lambda b: True)
    monkeypatch.setattr(field_add, "find_boxes", lambda b: [dict(x) for x in BOXES])
    monkeypatch.setattr(field_add, "classify_form", lambda b, cache_only=True: None)
    monkeypatch.setattr(field_add, "SCREEN_DIR", tmp_path / "screen")
    if scores is not None:
        p = field_add.screen_path(blank)
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"scores": scores}))
    return field_add.Context("t__f", bpt)


def test_screened_out_boxes_are_not_suggested(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, {"1": 0.9, "2": 0.2})          # box 3 was never scored
    s = {x["sid"]: x["what"] for x in ctx.suggestions()}
    assert set(s) == {"b1", "b3"}
    assert s["b1"].endswith("Jev 0.90") and "Jev" not in s["b3"]


def test_no_screen_record_suggests_every_box(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    assert [x["sid"] for x in ctx.suggestions()] == ["b1", "b2", "b3"]
