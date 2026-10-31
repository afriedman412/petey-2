"""A group of one option is no group (Andrew, 2026-10-31: "the ability to group one field is confusing and not really
useful"): it loads as a loose box and is written back as a checkbox, the same field (name, id) on the same box."""
from petey.validate import group_review as gr


def _bp():
    box = {"page": 1, "rect": [100, 100, 110, 110], "widget_type": "checkbox", "path": "f.cb", "on_state": "Yes",
           "caption": "Occurrence", "x_petey_caption_source": "page_text"}
    return {"fields": {
        "liability_type": {"x_petey_id": "1_4", "type": "category", "values": ["occurrence"],
                           "widgets": {"occurrence": box}},
        "smoker_ind": {"x_petey_id": "1_5", "type": "boolean", "semantic_type": "indicator",
                       "widget": {**box, "rect": [200, 100, 210, 110], "caption": None}},
    }}


def test_a_group_of_one_loads_as_a_loose_box(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "OUT", tmp_path)
    _, units, _ = gr.current_units("x", _bp(), "sha")
    one = next(u for u in units if u["origin"] == "liability_type")
    assert one["type"] == "boolean" and one["items"] == ["liability_type::occurrence"]


def test_a_group_of_one_written_as_a_checkbox_keeping_its_name_and_id(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "OUT", tmp_path)
    bp = _bp()
    _, units, _ = gr.current_units("x", bp, "sha")
    pl = gr.plan(bp, units, page_captions=False)
    assert not pl["errors"]
    f = pl["fields"]["liability_type"]
    assert list(pl["fields"]) == ["liability_type", "smoker_ind"]
    assert f["x_petey_id"] == "1_4" and f["type"] == "boolean" and f["semantic_type"] == "indicator"
    assert "widgets" not in f and "values" not in f
    assert f["widget"]["path"] == "f.cb" and f["widget"]["on_state"] == "Yes" and "caption" not in f["widget"]
    assert f["description"] == "Occurrence"
    assert pl["changes"] == ["liability_type: a group of one option made a checkbox"]
    assert pl["fields"]["smoker_ind"] == bp["fields"]["smoker_ind"]


def test_a_group_of_two_is_left_alone(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "OUT", tmp_path)
    bp = _bp()
    bp["fields"]["liability_type"]["widgets"]["claims"] = {**bp["fields"]["liability_type"]["widgets"]["occurrence"],
                                                           "rect": [120, 100, 130, 110]}
    _, units, _ = gr.current_units("x", bp, "sha")
    assert next(u for u in units if u["origin"] == "liability_type")["type"] == "category"
    assert not gr.plan(bp, units, page_captions=False)["changes"]


def test_a_group_of_loose_boxes_left_with_one_gives_it_back_as_it_was(tmp_path, monkeypatch):
    monkeypatch.setattr(gr, "OUT", tmp_path)
    bp = _bp()
    units = [{"name": "pick", "type": "category", "items": ["smoker_ind"], "origin": None, "confirmed": False}]
    (tmp_path / "x.json").write_text(gr.json.dumps({"blueprint_sha": "sha", "units": units}))
    _, units, _ = gr.current_units("x", bp, "sha")
    u = next(u for u in units if u["items"] == ["smoker_ind"])
    assert (u["name"], u["origin"], u["type"]) == ("smoker_ind", "smoker_ind", "boolean")
    assert gr.plan(bp, units, page_captions=False)["fields"]["smoker_ind"] == bp["fields"]["smoker_ind"]
