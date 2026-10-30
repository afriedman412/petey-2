"""Text fields made checkboxes in Groups (Andrew, 2026-10-27: "convert fields from text to bool/ind in groups";
"change the suffix and add it if it isn't there"): the field becomes a boolean indicator on its own text widget, named
with _ind, alone or grouped with other boxes."""
from petey.validate import group_review as gr


def _bp():
    def text(x, **k):
        return {"type": "string", **k, "widget": {"page": 1, "rect": [x, 100, x + 12, 110], "widget_type": "text",
                                                  "path": None}}
    return {"fields": {
        "day_txt": text(100, pattern="^.*$"),
        "evening": text(150),
        "other_ind": {"type": "boolean", "semantic_type": "indicator",
                      "widget": {"page": 1, "rect": [200, 100, 210, 110], "widget_type": "checkbox", "path": None}},
        "notes_txt": text(300),
    }}


def test_the_suffix_becomes_ind_or_is_added():
    assert gr.ind_name("day_txt") == "day_ind"
    assert gr.ind_name("evening") == "evening_ind"
    assert gr.ind_name("phone_nbr_2") == "phone_ind_2"
    assert gr.ind_name("p1_f12") == "p1_f12_ind"
    assert gr.ind_name("smoker_ind") == "smoker_ind"


def test_a_text_field_made_a_checkbox_on_its_own():
    bp = _bp()
    units = [{"name": "day_ind", "type": "boolean", "items": ["day_txt"], "origin": "day_txt"},
             {"name": "other_ind", "type": "boolean", "items": ["other_ind"], "origin": "other_ind"}]
    pl = gr.plan(bp, units, page_captions=False)
    assert not pl["errors"]
    f = pl["fields"]
    assert "day_txt" not in f and list(f) == ["day_ind", "evening", "other_ind", "notes_txt"]      # its place kept
    assert f["day_ind"]["type"] == "boolean" and f["day_ind"]["semantic_type"] == "indicator"
    assert "pattern" not in f["day_ind"] and f["day_ind"]["widget"]["widget_type"] == "text"         # its own box
    assert f["day_ind"]["x_petey_converted"]["from"] == {"type": "string", "pattern": "^.*$"}
    assert any("day_txt: text field made a checkbox" in c for c in pl["changes"])
    assert bp["fields"]["day_txt"]["type"] == "string"                                            # the input untouched


def test_text_fields_made_checkboxes_and_grouped_with_a_checkbox():
    units = [{"name": "shift", "type": "category", "items": ["day_txt", "evening", "other_ind"], "origin": None}]
    pl = gr.plan(_bp(), units, page_captions=False)
    assert not pl["errors"]
    g = pl["fields"]["shift"]
    assert g["type"] == "category" and list(g["widgets"]) == ["day_ind", "evening_ind", "other_ind"]   # keys as checkboxes
    assert g["widgets"]["day_ind"]["widget_type"] == "text"
    assert "notes_txt" in pl["fields"] and "evening" not in pl["fields"]


def test_a_text_field_in_an_entity_is_not_converted():
    units = [{"name": "other_ind", "type": "boolean", "items": ["other_ind"], "origin": "other_ind"},
             {"kind": "text", "name": "day_evening", "type": "string", "items": ["day_txt", "evening"]}]
    pl = gr.plan(_bp(), units, page_captions=False)
    assert not pl["errors"]
    assert pl["fields"]["day_txt"]["type"] == "string" and pl["fields"]["evening"][gr.ENTITY_KEY]["name"] == "day_evening"
    assert not any("made a checkbox" in c for c in pl["changes"])
