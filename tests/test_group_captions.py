"""'re-read captions' in Groups asks the review agent for a group with a box added in Add / remove, even when every
caption is printed beside its box (Andrew, 2026-10-27: "re-reading captions doesn't seem to work on fields added
with add/remove"): Add / remove reads a box's caption off the words beside it, so the page check always confirmed
it and the agent was never asked (I-864 p7: the header's "For", "Household", "Size" kept for the printed 1-9). A
group with no added box still stands on the page check, no call."""
from pathlib import Path

from petey.synth import generate
from petey.validate import flag_agent
from petey.validate import group_review as gr


def _bp(added: bool):
    def box(x, cap):
        spec = {"type": "boolean", "description": cap,
                "widget": {"page": 1, "rect": [x, 100, x + 7, 107], "widget_type": "checkbox", "path": None}}
        if added:
            spec["x_petey_added"] = {"source": "field_add", "name_from": "option caption", "caption": cap}
        return spec
    return {"fields": {"for_ind": box(80, "For"), "household_ind": box(110, "Household")}}


def _read(monkeypatch, added: bool):
    calls = []
    monkeypatch.setattr(gr, "page_confirms", lambda blank, ws: True)
    monkeypatch.setattr(generate, "make_client", lambda model: None)

    def propose(client, blank, name, spec, ask, *a):
        calls.append(sorted(spec["widgets"]))
        return {"options": {"for_ind": {"caption": "1"}, "household_ind": {"caption": "2"}}}
    monkeypatch.setattr(flag_agent, "propose", propose)
    out = gr.suggest_captions(_bp(added), Path("blank.pdf"), "household_size", ["for_ind", "household_ind"])
    return out, calls


def test_a_group_with_an_added_box_goes_to_the_agent(monkeypatch):
    out, calls = _read(monkeypatch, added=True)
    assert calls == [["for_ind", "household_ind"]]
    assert {i: c["caption"] for i, c in out.items()} == {"for_ind": "1", "household_ind": "2"}
    assert {c["source"] for c in out.values()} == {flag_agent.MODEL}


def test_a_group_with_no_added_box_stands_on_the_page_check(monkeypatch):
    out, calls = _read(monkeypatch, added=False)
    assert calls == []
    assert {i: c["caption"] for i, c in out.items()} == {"for_ind": "For", "household_ind": "Household"}
    assert {c["source"] for c in out.values()} == {"page text"}
