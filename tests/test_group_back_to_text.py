"""A text field made a checkbox in Groups and applied goes back to text from the card's "back to text" (Andrew,
2026-10-29, fin__pb_358ecead701f's sort-code fields: "having a nightmare trying to recode ... to text"): shown as a
conversion not yet applied, and a converted box no unit holds is a text field again, its type and pattern back."""
import json

from petey.validate import group_review as gr


def _bp():
    return {"fields": {
        "day_txt": {"type": "string", "pattern": "^.*$",
                    "widget": {"page": 1, "rect": [100, 100, 112, 110], "widget_type": "text", "path": None}},
        "other_ind": {"type": "boolean", "semantic_type": "indicator",
                      "widget": {"page": 1, "rect": [200, 100, 210, 110], "widget_type": "checkbox", "path": None}},
    }}


def _applied():
    units = [{"name": "day_ind", "type": "boolean", "items": ["day_txt"], "origin": "day_txt"},
             {"name": "other_ind", "type": "boolean", "items": ["other_ind"], "origin": "other_ind"}]
    pl = gr.plan(_bp(), units, page_captions=False)
    assert not pl["errors"]
    return {"fields": pl["fields"]}


def test_an_applied_conversion_is_shown_as_one_not_applied():
    bp = _applied()
    items, _ = gr.option_items(bp)
    shown = gr.as_converted_items(bp, items)
    assert shown["day_ind"]["kind"] == "text" and shown["day_ind"]["converted"] and shown["day_ind"]["ind_name"] == "day_ind"
    assert "kind" not in shown["other_ind"]                                  # a checkbox of its own stays one


def test_a_converted_box_no_unit_holds_is_text_again():
    bp = _applied()
    pl = gr.plan(bp, [{"name": "other_ind", "type": "boolean", "items": ["other_ind"], "origin": "other_ind"}],
                 page_captions=False)
    assert not pl["errors"]
    f = pl["fields"]["day_ind"]
    assert f["type"] == "string" and f["pattern"] == "^.*$" and "semantic_type" not in f
    assert "x_petey_converted" not in f and f["x_petey_back_to_text"]["converted"]["from"]["type"] == "string"
    assert f["widget"]["widget_type"] == "text"
    assert "day_ind: checkbox made a text field again" in pl["changes"]
    assert pl["fields"]["other_ind"]["type"] == "boolean"


def test_a_converted_box_still_in_a_unit_stays_a_checkbox():
    bp = _applied()
    _, units = gr.option_items(bp)
    pl = gr.plan(bp, units, page_captions=False)
    assert not pl["errors"] and not pl["changes"]


def test_the_record_keeps_it_out_of_its_unit_until_applied(tmp_path, monkeypatch):
    import yaml
    bp = _applied()
    p = tmp_path / "f.bpt"
    p.write_text(yaml.safe_dump(bp), encoding="utf-8")
    monkeypatch.setattr(gr, "OUT", tmp_path / "rec")
    st = gr.State.__new__(gr.State)
    st.paths, st._index = {"x": p}, {}
    monkeypatch.setattr(st, "path", lambda bid: p, raising=False)
    monkeypatch.setattr(st, "_entry", lambda bid: None, raising=False)
    units = [{"name": "other_ind", "type": "boolean", "items": ["other_ind"], "origin": "other_ind"}]
    st.put_units("x", {"units": units, "to_text": ["day_ind", "other_ind"]})
    rec = json.loads(gr.record_path("x").read_text())
    assert rec["to_text"] == ["day_ind"]                                      # only a converted box in no unit
    st.put_units("x", {"units": units})                                       # a save without the list keeps it
    assert json.loads(gr.record_path("x").read_text())["to_text"] == ["day_ind"]
    items, cur, _ = gr.current_units("x", bp, gr._sha(p))
    assert [u["items"] for u in cur] == [["other_ind"]] and items["day_ind"]["converted"]
    pl = gr.plan(bp, cur, page_captions=False)
    assert pl["fields"]["day_ind"]["type"] == "string"
