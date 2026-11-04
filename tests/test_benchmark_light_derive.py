"""The light_splits arm re-derived from the light arm and the page PDF, no Jev (Andrew, 2026-11-04)."""
import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))

import benchmark_light as L   # noqa: E402
from petey.validate import type_model as tm   # noqa: E402


def _page_pdf(path: Path) -> None:
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((220, 96), "Date (MM/DD/YYYY)", fontsize=8)
    pg.insert_text((10, 96), "Name", fontsize=8)
    pg.insert_text((40, 180), "Signature", fontsize=8)          # under the line at y 160-172
    doc.save(str(path))
    doc.close()


def test_splits_arm_from_the_light_arm(tmp_path, monkeypatch):
    monkeypatch.setattr(tm, "WEIGHTS", None)          # the fitted type model, when pasted in, is set aside here
    key, out = tmp_path / "key", tmp_path / "pred"
    (key / "pages").mkdir(parents=True)
    (out / "light").mkdir(parents=True)
    _page_pdf(key / "pages" / "f__p1.pdf")
    (key / "index.json").write_text(json.dumps([{"page_id": "f__p1", "set": "t"}]))
    light = {"fields": [{"id": "n", "rect": [40, 100, 160, 112], "kind": "text"},
                        {"id": "d1", "rect": [220, 100, 250, 112], "kind": "text"},
                        {"id": "d2", "rect": [255, 100, 285, 112], "kind": "text"},
                        {"id": "d3", "rect": [290, 100, 330, 112], "kind": "text"},
                        {"id": "sig", "rect": [40, 160, 240, 172], "kind": "text"},
                        {"id": "o.a", "rect": [40, 130, 48, 138], "kind": "choice"},
                        {"id": "o.b", "rect": [60, 130, 68, 138], "kind": "choice"}],
             "groups": [["o.a", "o.b"]]}
    (out / "light" / "f__p1.json").write_text(json.dumps(light))
    assert L.derive_splits(key, out) == 1
    got = json.loads((out / "light" / "f__p1.json").read_text())           # the one arm, rewritten in place
    kinds = {f["id"]: f["kind"] for f in got["fields"]}
    assert kinds["sig"] == "printed" and kinds["n"] == "text" and kinds["o.a"] == "choice"
    assert got["groups"] == [["o.a", "o.b"], ["d1", "d2", "d3"]]


def test_retype_flips_a_box_and_drops_it_from_its_group(tmp_path, monkeypatch):
    """A toy type model: a box is a choice only when a word sits right beside it."""
    monkeypatch.setattr(tm, "WEIGHTS", {"word_right": 6.0, "bias": -3.0})
    monkeypatch.setattr(tm, "MEAN", {}); monkeypatch.setattr(tm, "STD", {}); monkeypatch.setattr(tm, "CUT", 0.5)
    pdf = tmp_path / "p.pdf"
    doc = pymupdf.open(); pg = doc.new_page(width=612, height=792)
    pg.insert_text((52, 138), "Yes", fontsize=8)          # beside box a only
    doc.save(str(pdf)); doc.close()
    pred = {"fields": [{"id": "a", "rect": [40, 130, 48, 138], "kind": "choice"},
                       {"id": "b", "rect": [40, 150, 48, 158], "kind": "choice"},
                       {"id": "c", "rect": [100, 130, 108, 138], "kind": "text"}],
            "groups": [["a", "b"]]}
    assert L.retype(pred, pdf) == 1
    assert {f["id"]: f["kind"] for f in pred["fields"]} == {"a": "choice", "b": "text", "c": "text"}
    assert pred["groups"] == []
