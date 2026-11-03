"""Add / remove: a field of the blueprint made text, printed or a choice in place (field_add.flip_kind, 2026-11-01)."""
import pytest

from petey.validate.field_add import KIND_EDIT, flip_kind, kind_of
from petey.validate.printed_fields import TAG

NOW = "2026-11-01 12:00:00"


def checkbox(**kw):
    s = {"type": "boolean", "semantic_type": "indicator", "x_petey_id": "1_7",
         "widget": {"page": 1, "rect": [10, 10, 20, 20], "widget_type": "checkbox", "path": "f.Box7",
                    "on_state": "Yes"}}
    s.update(kw)
    return s


def test_a_checkbox_made_text_keeps_its_id_and_box_and_sets_its_path_aside():
    s = checkbox()
    assert flip_kind(s, "mail_ind", "text", NOW) == "mail_ind: choice -> text"
    assert kind_of(s) == "text" and s["type"] == "string" and "semantic_type" not in s
    assert s["x_petey_id"] == "1_7" and s["widget"] == {"page": 1, "rect": [10, 10, 20, 20], "widget_type": "text",
                                                         "path": None}
    assert s[KIND_EDIT]["from"] == "choice" and s[KIND_EDIT]["path"] == "f.Box7"


def test_flipped_back_it_is_the_checkbox_it_was():
    s = checkbox()
    flip_kind(s, "mail_ind", "text", NOW)
    assert flip_kind(s, "mail_ind", "choice", NOW) == "mail_ind: text -> choice"
    assert s["widget"] == checkbox()["widget"] and (s["type"], s["semantic_type"]) == ("boolean", "indicator")


def test_a_text_box_made_a_choice_drops_its_text_path_and_printed_tag():
    s = {"type": "string", "pattern": r"^\d+$", TAG: {"source": "review"},
         "widget": {"page": 2, "rect": [0, 0, 9, 9], "widget_type": "text", "path": "f.T1"}}
    assert flip_kind(s, "box", "choice", NOW) == "box: printed -> choice"
    assert s["widget"]["widget_type"] == "checkbox" and s["widget"]["path"] is None
    assert TAG not in s and "pattern" not in s and s["type"] == "boolean"
    flip_kind(s, "box", "text", NOW)
    assert s["widget"]["path"] == "f.T1" and s["widget"]["widget_type"] == "text"


def test_printed_is_text_with_the_tag():
    s = checkbox()
    assert flip_kind(s, "sig", "printed", NOW) == "sig: choice -> printed"
    assert kind_of(s) == "printed" and s[TAG]["source"] == "field_add"
    assert flip_kind(s, "sig", "text", NOW) == "sig: printed -> text" and TAG not in s
    assert flip_kind(s, "sig", "text", NOW) is None


def test_a_group_of_several_boxes_does_not_change_kind():
    s = {"type": "string", "values": ["a", "b"], "widgets": {"a": {"page": 1, "rect": [0, 0, 1, 1]},
                                                             "b": {"page": 1, "rect": [2, 0, 3, 1]}}}
    with pytest.raises(ValueError):
        flip_kind(s, "g", "text", NOW)
