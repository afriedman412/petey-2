"""Add / remove: a proposal made a checkbox or a text box by hand (field_add.switch_kind, 2026-10-20)."""
import types

from petey.validate.field_add import _named, switch_kind


def text_proposal(**kw):
    p = {"kind": "text", "page": 1, "rect": [10, 10, 20, 20], "geometry": "selection",
         "widget": {"page": 1, "rect": [10, 10, 20, 20], "widget_type": "text", "path": None},
         "name": "delivery_fob_origin", "name_source": "page text",
         "name_options": [{"name": "delivery_fob_origin", "source": "page text", "types": {"type": "string"}},
                          {"name": "fob_origin", "source": "tooltip", "types": {"type": "string"}}],
         "type": "string", "evidence": []}
    p.update(kw)
    return p


def test_a_text_box_made_a_checkbox_is_a_boolean_indicator():
    q = switch_kind(text_proposal(), "option")
    assert q["kind"] == "option" and q["widget"]["widget_type"] == "checkbox"
    assert (q["type"], q["semantic_type"]) == ("boolean", "indicator")
    assert q["name"] == "delivery_fob_origin_ind"
    assert [o["name"] for o in q["name_options"]] == ["delivery_fob_origin_ind", "fob_origin_ind"]


def test_a_form_text_widget_made_a_checkbox_drops_its_path_and_gets_it_back():
    p = text_proposal(geometry="widget", widget={"page": 1, "rect": [10, 10, 20, 20], "widget_type": "text",
                                                 "path": "form1.Page1.FOB"})
    q = switch_kind(p, "option")
    assert q["widget"]["path"] is None and p["widget"]["path"] == "form1.Page1.FOB"
    back = switch_kind(q, "text")
    assert back["widget"] == {"page": 1, "rect": [10, 10, 20, 20], "widget_type": "text", "path": "form1.Page1.FOB"}
    assert back["name"] == "delivery_fob_origin" and back["type"] == "string"


def test_a_hand_typed_name_stays_and_a_taken_name_is_not_reused():
    q = switch_kind(text_proposal(name="fob", name_source="hand"), "option")
    assert q["name"] == "fob" and q["type"] == "boolean"
    q = switch_kind(text_proposal(), "option", taken={"delivery_fob_origin_ind"})
    assert q["name"] == "delivery_fob_origin_ind_2"


def test_a_group_is_left_alone():
    g = {"kind": "group", "options": []}
    assert switch_kind(g, "text") is g


def test_a_placeholder_name_says_its_kind():
    p = text_proposal(name="p1_text_30_1000", name_source="placeholder",
                      name_options=[{"name": "p1_text_30_1000", "source": "placeholder"}])
    q = switch_kind(p, "option")
    assert q["name"] == "p1_option_30_1000_ind"
    assert switch_kind(q, "text")["name"] == "p1_text_30_1000"


def test_one_box_beside_an_option_group_is_one_option_not_the_group():
    # HUD 92800-5B p5 (2026-10-21): Existing-1 beside p3's group property_type (Existing-0 / Proposed-0) came in as
    # the group's category, and the Groups tab showed it neither as a group nor as a loose option
    bp = {"fields": {"property_type": {"type": "category", "widgets": {
        "existing": {"page": 3, "rect": [306, 321, 320, 336], "path": "Existing-0"},
        "proposed": {"page": 3, "rect": [361, 321, 376, 336], "path": "Proposed-0"}}}}}
    p = {"kind": "option", "page": 5, "rect": [308, 340, 323, 355],
         "widget": {"page": 5, "rect": [308, 340, 323, 355], "widget_type": "checkbox", "path": "Proposed-1"}}
    _named(p, [("property_type", "twin: sibling path")], "option", set(bp["fields"]), types.SimpleNamespace(bp=bp))
    assert (p["name"], p["type"], p["semantic_type"]) == ("property_type_proposed_ind", "boolean", "indicator")
