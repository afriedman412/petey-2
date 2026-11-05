"""The page sweeps sheet (/sweep, Andrew 2026-10-31): what each sweep proposes, and a verdict's records."""
import json

import pytest

from petey.validate import page_sweeps as ps
from petey_dataset import ignored_pages


def _key(n_text, n_choice):
    return {"fields": [{"id": f"t{i}", "kind": "text"} for i in range(n_text)]
            + [{"id": f"c{i}", "kind": "choice"} for i in range(n_choice)]}


def test_few_fields():
    assert ps.why(_key(9, 0), "")["few"] == "9 fields"
    assert ps.why(_key(1, 0), "")["few"] == "1 field"
    assert "few" not in ps.why(_key(10, 0), "")


def test_checklist_needs_mostly_boxes_and_list_words():
    words = "Please attach a copy of your licence. Enclosed: ..."
    assert "checklist" in ps.why(_key(5, 6), words)
    assert "checklist" not in ps.why(_key(20, 6), words)           # mostly text fields
    assert "checklist" not in ps.why(_key(5, 6), "Name Address")    # no list words


@pytest.mark.parametrize("text", ["FOR OFFICE USE ONLY", "For official use", "Internal use only", "DO NOT WRITE BELOW THIS LINE"])
def test_office_sections(text):
    assert "office" in ps.why(_key(20, 0), f"Name ... {text} ...")


def test_ignore_writes_both_records_and_keep_takes_it_back(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DIR", tmp_path / "sweeps")
    monkeypatch.setattr(ignored_pages, "RECORD", tmp_path / "ignored.json")
    out = ps.mark("few", "bm__sd_1__p2", "ignore")
    assert out["ignored"] == "few fields"
    assert ignored_pages.load()["bm__sd_1__p2"]["reason"] == "few fields"
    assert ps.seen()["few"]["bm__sd_1__p2"]["verdict"] == "ignore"
    assert ps.mark("few", "bm__sd_1__p2", "keep")["ignored"] is None
    assert ignored_pages.load() == {}
    ps.mark("checklist", "bm__sd_2__p1", "ignore", "list of documents to bring")
    assert ignored_pages.load()["bm__sd_2__p1"]["reason"] == "list of documents to bring"
    with pytest.raises(ValueError):
        ps.mark("few", "bm__sd_1__p2", "done")                     # "fields added" is the office sweep's only


def test_a_page_ignored_elsewhere_stays_ignored_when_kept(tmp_path, monkeypatch):
    monkeypatch.setattr(ps, "DIR", tmp_path / "sweeps")
    monkeypatch.setattr(ignored_pages, "RECORD", tmp_path / "ignored.json")
    ignored_pages.put("bm__sd_3__p1", True, "instructions")
    ps.mark("office", "bm__sd_3__p1", "keep")
    assert ignored_pages.load()["bm__sd_3__p1"]["reason"] == "instructions"


def test_signature_lines_with_no_field_near():
    key = {"fields": [{"id": "1", "kind": "text", "rect": [150, 100, 400, 112]}]}
    lines = [("Signature of applicant", (40, 102, 140, 112)),          # its field on the line: covered
             ("Printed name", (40, 300, 100, 310)),                    # nothing near
             ("SECTION IV: DECLARATION AND SIGNATURE", (40, 500, 300, 510)),   # a heading
             ("By signing below you agree that your signature is binding on you", (40, 600, 400, 610))]   # a sentence
    assert ps.unsigned(key, lines) == ["Printed name"]
    assert ps.why({"fields": key["fields"] * 20}, "", lines)["signature"] == 'no field near: "Printed name"'
