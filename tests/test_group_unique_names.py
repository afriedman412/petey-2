"""No two groups under one name in the Groups tab (Andrew, 2026-11-01, bm__mu_009291445aab p3_o4: "no field or group
should ever be given a name that is already in use"): boxes of a group the record never saw join the unit holding the
rest of it; a name still used twice takes the next free one; a unit under its field's name follows a Review rename."""
import json

import yaml

from petey.validate import group_review as gr


def _w(x, key):
    return {"page": 1, "rect": [x, 100, x + 12, 110], "widget_type": "checkbox", "path": None, "on_state": key}


def _group(keys, x0=100):
    return {"type": "category", "values": list(keys), "widgets": {k: _w(x0 + 20 * i, k) for i, k in enumerate(keys)}}


def _write(tmp_path, monkeypatch, bp, units, sha=None):
    p = tmp_path / "f.bpt"
    p.write_text(yaml.safe_dump(bp), encoding="utf-8")
    monkeypatch.setattr(gr, "OUT", tmp_path / "rec")
    (tmp_path / "rec").mkdir(exist_ok=True)
    rec = {"blueprint": str(p), "form": "f", "blueprint_sha": sha or gr._sha(p), "updated": "2026-11-01 10:00:00",
           "units": units}
    gr.record_path("x").write_text(json.dumps(rec), encoding="utf-8")
    return p


def _names(units):
    return [u["name"] for u in units if u.get("kind") != "text"]


def test_boxes_the_record_never_saw_join_their_group(tmp_path, monkeypatch):
    """lib__acord25 group_p1_2: an option renamed after the record came back as a second group_p1_2."""
    bp = {"fields": {"wc": _group(["per_statute", "above_limits"])}}
    p = _write(tmp_path, monkeypatch, bp, [{"name": "wc", "type": "category", "origin": "wc",
                                            "items": ["wc::per_statute", "wc::other"]}], sha="old")
    _, units, info = gr.current_units("x", bp, gr._sha(p))
    assert info["stale"]
    assert [(u["name"], sorted(u["items"])) for u in units] == [("wc", ["wc::above_limits", "wc::per_statute"])]
    assert not gr.plan(bp, units, page_captions=False)["errors"]


def test_a_name_used_twice_takes_the_next_free_one(tmp_path, monkeypatch):
    """bm__mu_009291445aab: the record held p3_o4's options and its five added checkboxes as two units, both p3_o4."""
    bp = {"fields": {"p3_o4": _group(["opt1", "opt2", "f7", "f8"])}}
    p = _write(tmp_path, monkeypatch, bp, [
        {"name": "p3_o4", "type": "category", "origin": "p3_o4", "items": ["p3_o4::opt1", "p3_o4::opt2"]},
        {"name": "p3_o4", "type": "category", "origin": "p3_o4", "items": ["p3_o4::f7", "p3_o4::f8"]}])
    _, units, _ = gr.current_units("x", bp, gr._sha(p))
    assert sorted(_names(units)) == ["p3_o4", "p3_o4_2"]
    assert next(u for u in units if u["name"] == "p3_o4_2")["origin"] is None       # a new group, not p3_o4 renamed
    pl = gr.plan(bp, units, page_captions=False)
    assert not pl["errors"] and set(pl["fields"]) == {"p3_o4", "p3_o4_2"}


def test_a_group_does_not_take_a_text_fields_name(tmp_path, monkeypatch):
    bp = {"fields": {"g": _group(["a", "b"]),
                     "notes": {"type": "string", "widget": {"page": 1, "rect": [0, 0, 50, 10], "widget_type": "text"}}}}
    p = _write(tmp_path, monkeypatch, bp, [{"name": "notes", "type": "category", "origin": None,
                                            "items": ["g::a", "g::b"]}])
    _, units, _ = gr.current_units("x", bp, gr._sha(p))
    assert _names(units) == ["notes_2"]


def test_a_unit_under_its_fields_name_follows_a_review_rename(tmp_path, monkeypatch):
    """p3_o3 renamed p3_o9 in Review after the record: saving Groups renamed it back."""
    v1 = {"fields": {"p3_o3": _group(["opt1", "opt2"]), "p3_o4": _group(["opt1", "opt2"], 300)}}
    p = _write(tmp_path, monkeypatch, v1, [{"name": "p3_o3", "type": "category", "origin": "p3_o3",
                                            "items": ["p3_o3::opt1", "p3_o4::opt1", "p3_o3::opt2", "p3_o4::opt2"]}])
    rec = gr.load_record("x")
    rec["boxes"] = gr.item_boxes(gr.option_items(v1)[0], rec["units"])
    gr.record_path("x").write_text(json.dumps(rec), encoding="utf-8")
    v2 = {"fields": {"p3_o9": v1["fields"]["p3_o3"], "p3_o4": v1["fields"]["p3_o4"]}}
    p.write_text(yaml.safe_dump(v2), encoding="utf-8")
    _, units, _ = gr.current_units("x", v2, gr._sha(p))
    assert _names(units) == ["p3_o9"]


def test_a_checkbox_made_text_after_the_record_stays_text(tmp_path, monkeypatch):
    """bm__pb_d985db100931: cents cells made text in Add / remove came back as checkboxes on leaving Groups."""
    from petey.validate.field_add import flip_kind
    chk = {"type": "boolean", "semantic_type": "indicator",
           "widget": {"page": 1, "rect": [0, 0, 9, 9], "widget_type": "checkbox", "path": None}}
    bp = {"fields": {"cents": dict(chk, widget=dict(chk["widget"]))}}
    p = _write(tmp_path, monkeypatch, bp, [{"name": "cents", "type": "boolean", "origin": "cents", "items": ["cents"]}])
    flip_kind(bp["fields"]["cents"], "cents", "text", "2026-11-01 11:00:00")      # after the record (10:00)
    p.write_text(yaml.safe_dump(bp), encoding="utf-8")
    _, units, _ = gr.current_units("x", bp, gr._sha(p))
    pl = gr.plan(bp, units, page_captions=False)
    assert not pl["changes"] and pl["fields"]["cents"]["type"] == "string"
