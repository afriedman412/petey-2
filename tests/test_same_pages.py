"""Identical pages filled from each other (petey/validate/same_pages.py; Andrew, 2026-10-31: "can you try to leverage
existing pages to fill in the info on identical pages"; "everything should carry over")."""
import json

import pytest
import yaml

from petey.validate import draft
from petey.validate import grid_check as gc
from petey.validate import group_review as G
from petey_review import hand_review as H
from petey.validate import same_pages as S
import petey_dataset
from petey_dataset import verdicts as DV
from petey_dataset import blueprints as DB


def _text(page, code, x, y, w=100, path=None, **kw):
    widget = {"page": page, "rect": [x, y, x + w, y + 12], "widget_type": "text"}
    if path:
        widget["path"] = path
    return {"type": "string", "widget": widget, "x_petey_id": code, **kw}


def _group(page, code, boxes, path=None):
    ws = {k: {"page": page, "rect": [x, y, x + 10, y + 10], "widget_type": "checkbox", "on_state": k,
              **({"path": f"{path}.{k}"} if path else {})} for k, (x, y) in boxes.items()}
    return {"type": "category", "widgets": ws, "x_petey_id": code}


def _form():
    """p1 labeled; p2 its copy as staged (publisher names, paths); p3 a copy with no fields."""
    return {"name": "form", "fields": {
        "employee_nm": _text(1, "1_1", 50, 100, x_petey_printed={"source": "review", "when": "x"}),
        "employee_ssn": _text(1, "1_2", 200, 100),
        "p1_o1": _group(1, "1_3", {"yes": (50, 200), "no": (90, 200)}),
        "f2_1": _text(2, "2_1", 50.5, 100.4, path="CopyB.f1"),
        "f2_2": _text(2, "2_2", 200, 100, path="CopyB.f2"),
        "c2_1": _text(2, "2_3", 50, 200, w=10, path="CopyB.c1"),
        "c2_2": _text(2, "2_4", 90, 200, w=10, path="CopyB.c2"),
        "stray": _text(2, "2_5", 400, 600, path="CopyB.f9"),
    }}


def test_a_copy_page_takes_the_first_copys_fields_on_its_own_boxes():
    bp = _form()
    pl = S.plan(bp, bp, 2, 1, True, "t__form")
    f = pl["fields"]
    assert pl["names"] == {"employee_nm": "employee_nm_p2", "employee_ssn": "employee_ssn_p2", "p1_o1": "p2_o1"}
    assert set(pl["removed"]) == {"f2_1", "f2_2", "c2_1", "c2_2"} and pl["left"] == ["stray"]
    nm = f["employee_nm_p2"]
    assert nm["widget"]["path"] == "CopyB.f1" and nm["widget"]["rect"] == [50.5, 100.4, 150.5, 112.4]   # the box here
    assert nm["x_petey_id"] == "2_1" and nm["x_petey_printed"]                    # its code here, its printed tag
    assert nm["x_petey_same_page"]["field"] == "employee_nm" and nm["x_petey_same_page"]["page"] == 1
    # the checkboxes the publisher made text boxes come out as the first copy's Yes / No group
    g = f["p2_o1"]
    assert g["type"] == "category" and set(g["widgets"]) == {"yes", "no"}
    assert all(w["page"] == 2 for w in g["widgets"].values())
    assert "c2_1" not in f and "c2_2" not in f and "stray" in f
    assert list(f).index("employee_nm_p2") > list(f).index("p1_o1")                # in page order


def test_an_empty_copy_gets_the_fields_added_at_their_places():
    bp = _form()
    pl = S.plan(bp, bp, 3, 1, True, "t__form")
    assert pl["added"] == 3 and pl["replaced"] == 0
    ssn = pl["fields"]["employee_ssn_p3"]
    assert ssn["widget"]["page"] == 3 and ssn["widget"]["rect"] == [200, 100, 300, 112] and "path" not in ssn["widget"]
    assert {s["x_petey_id"] for n, s in pl["fields"].items() if n.endswith("_p3") or n == "p3_o1"} == {"3_1", "3_2", "3_3"}


def test_another_forms_page_keeps_its_names_moved_by_the_offset():
    src = {"fields": {"lender_nm": _text(4, "4_1", 60, 110), "loan_nbr": _text(4, "4_2", 210, 110)}}
    bp = {"fields": {"a": _text(1, "1_1", 50, 100, path="A"), "loan_nbr": _text(5, "5_1", 0, 0)}}
    pl = S.plan(bp, src, 1, 4, False, "t__src")
    assert pl["offset"] == (-10.0, -10.0)
    assert pl["names"] == {"lender_nm": "lender_nm", "loan_nbr": "loan_nbr_2"}    # a name taken on another page
    assert pl["fields"]["lender_nm"]["widget"]["path"] == "A"
    assert pl["fields"]["loan_nbr_2"]["widget"]["rect"] == [200, 100, 300, 112]


@pytest.fixture
def state(tmp_path, monkeypatch):
    bpt = tmp_path / "form.bpt"
    bpt.write_text(yaml.safe_dump(_form(), sort_keys=False))
    monkeypatch.setattr(DV, "OUT", tmp_path / "hand_review")
    monkeypatch.setattr(G, "OUT", tmp_path / "group_review")
    monkeypatch.setattr(gc, "SETS", tmp_path / "grids")
    monkeypatch.setattr(DB, "DRAFTS", tmp_path / "drafts")
    monkeypatch.setattr(petey_dataset, "blueprint_paths", lambda: {"t__form": bpt})
    monkeypatch.setattr(DB, "blueprint_paths", lambda: {"t__form": bpt})
    monkeypatch.setattr(H, "blueprint_paths", lambda: {"t__form": bpt})
    H._write_verdicts("t__form", {"blueprint": str(bpt), "form": "form", "blueprint_sha": H._sha(bpt), "verdicts": {
        "employee_nm": {"verdict": "accept", "when": "x"}, "f2_1": {"verdict": "flag", "note": "?", "when": "x"}}})
    gc.SETS.mkdir()
    gc._save_set("t__form", {"grids": [{"id": "p1-G1", "kind": "table", "page": 1, "source": "person",
                                        "status": "active", "cells": [["1_1", 0, 0], ["1_2", 0, 1]]}],
                             "next": {"1G": 2, "BT": 2},
                             "types": [{"id": "BT1", "page": 1, "rect": [40, 90, 310, 115],
                                        "boxes": [{"code": "1_1", "dx": 0, "dy": 0, "w": 100, "h": 12, "kind": "textx1"},
                                                  {"code": "1_2", "dx": 150, "dy": 0, "w": 100, "h": 12, "kind": "textx1"}],
                                        "blocks": [["1_1", "1_2"]], "parts": {"1_1": {"prefix": "employee"}}}]})
    G.OUT.mkdir()
    sha = H._sha(bpt)
    items, units, _ = G.current_units("t__form", H._load(bpt), sha)
    for u in units:
        u["confirmed"] = u["name"] == "p1_o1"
    (G.OUT / "t__form.json").write_text(json.dumps({"blueprint_sha": sha, "units": units,
                                                     "boxes": G.item_boxes(items, units)}))
    return bpt


def test_fill_carries_verdicts_groups_blocks_and_grids_into_the_working_copy(state):
    out = S.fill("t__form", 2, "t__form", 1, state)
    assert out["left"] == ["stray"]
    assert H._load(state)["fields"]["f2_1"]                                       # the blueprint itself untouched
    p = H.working_path("t__form")
    assert p != state
    bp = H._load(p)
    assert "employee_nm_p2" in bp["fields"] and "f2_1" not in bp["fields"]
    vs = H.load_verdicts("t__form")["verdicts"]
    assert vs["employee_nm_p2"]["verdict"] == "accept" and "f2_1" not in vs
    assert vs["stray"]["verdict"] == "flag" and "p1" in vs["stray"]["note"]
    _items, units, info = G.current_units("t__form", bp, H._sha(p))
    assert not info["stale"]
    p2 = next(u for u in units if u["name"] == "p2_o1")
    assert p2["confirmed"] and len(p2["items"]) == 2
    rec = gc.load_set("t__form")
    assert [b for b in rec["types"][0]["blocks"]] == [["1_1", "1_2"], ["2_1", "2_2"]]
    assert rec["types"][0]["parts"]["2_1"] == {"prefix": "employee"}
    g2 = next(e for e in rec["grids"] if e["page"] == 2)
    assert g2["cells"] == [["2_1", 0, 0], ["2_2", 0, 1]] and g2["id"] == "p2-G1" and g2["source"] == "person"
    assert "same page" in draft.status("t__form", state)["log"][0]


def test_same_page_reads_the_inventory_fingerprints():
    w = [f"w{i}" for i in range(30)]
    page = {"page": 1, "n_words": 30, "words_sha": "abc", "vocab": w, "dhash": "f" * 16 + "0" * 48}
    assert S.same_page(page, dict(page, page=2, dhash="0" * 64))                  # the same words
    assert ("text", "abc") in S.bands(page) and len(S.bands(page)) == 9
