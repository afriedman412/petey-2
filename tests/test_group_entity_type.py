"""Entities in Groups (Andrew, 2026-10-28: an "entity type" dropdown for fields that go together, "sequential fields
on a single line that can be combined logically"; "the entities shouldn't combine into one field, they should get
grouped"; "lets keep everything separate. (we want them to be as auditable as possible!)"): each field of an entity
keeps its name, box and place and is tagged with the entity's name, type and its place in it; a field taken out loses
the tag; the tags make the entities again when Groups loads."""
import json

import yaml

from petey.validate import group_review as gr


def _bp():
    def text(x):
        return {"type": "string", "widget": {"page": 1, "rect": [x, 100, x + 30, 112], "widget_type": "text",
                                             "path": f"F.p{x}"}}
    return {"fields": {"dob_yr": text(180), "dob_month": text(100), "dob_day": text(140), "notes_txt": text(300)}}


def _entity(**k):
    return {"kind": "text", "name": "dob", "type": "string", "items": ["dob_month", "dob_day", "dob_yr"], **k}


def test_an_entity_tags_its_fields_and_keeps_them():
    bp = _bp()
    pl = gr.plan(bp, [_entity(entity_type="date")], page_captions=False)
    assert not pl["errors"]
    f = pl["fields"]
    assert list(f) == ["dob_yr", "dob_month", "dob_day", "notes_txt"]                  # every field, where it was
    for n, k in (("dob_month", 1), ("dob_day", 2), ("dob_yr", 3)):                      # places in reading order
        tag = f[n][gr.ENTITY_KEY]
        assert (tag["name"], tag["entity_type"], tag["n"]) == ("dob", "date", k)
        assert {x: v for x, v in f[n].items() if x != gr.ENTITY_KEY} == bp["fields"][n]   # nothing else touched
    assert gr.ENTITY_KEY not in f["notes_txt"] and gr.ENTITY_KEY not in bp["fields"]["dob_day"]
    assert any(c.startswith("entity dob (date): dob_month, dob_day, dob_yr") for c in pl["changes"])


def test_no_type_or_one_not_on_the_list_tags_without_one():
    for u in (_entity(), _entity(entity_type="ssn_thing")):
        tag = gr.plan(_bp(), [u], page_captions=False)["fields"]["dob_day"][gr.ENTITY_KEY]
        assert "entity_type" not in tag and tag["name"] == "dob"


def test_a_field_taken_out_loses_its_tag_and_an_unchanged_entity_is_no_change():
    once = gr.plan(_bp(), [_entity(entity_type="date")], page_captions=False)["fields"]
    again = gr.plan({"fields": once}, [_entity(entity_type="date")], page_captions=False)
    assert again["changes"] == [] and again["fields"]["dob_day"] == once["dob_day"]
    out = gr.plan({"fields": once}, [{**_entity(), "items": ["dob_month", "dob_day"]}], page_captions=False)
    assert gr.ENTITY_KEY not in out["fields"]["dob_yr"] and "dob_yr: out of entity 'dob'" in out["changes"]
    gone = gr.plan({"fields": once}, [], page_captions=False)["fields"]
    assert not any(gr.ENTITY_KEY in s for s in gone.values())


def test_the_tags_make_the_entities_again():
    f = gr.plan(_bp(), [_entity(entity_type="date")], page_captions=False)["fields"]
    assert gr.entity_units({"fields": f}) == [{"kind": "text", "name": "dob", "type": "string", "origin": None,
                                               "items": ["dob_month", "dob_day", "dob_yr"], "entity_type": "date"}]


def test_the_types():
    assert "id_number" in gr.ENTITY_TYPES and "ssn" not in gr.ENTITY_TYPES
    assert gr.ENTITY_TYPES[-1] == "other"


def _state(tmp_path, monkeypatch, bp):
    p = tmp_path / "f.bpt"
    p.write_text(yaml.safe_dump(bp))
    monkeypatch.setattr(gr, "OUT", tmp_path / "rec")
    monkeypatch.setattr(gr, "record_path", lambda bid: tmp_path / "rec" / f"{bid}.json")
    st = gr.State.__new__(gr.State)
    st.paths = {"x": p}
    st.path = lambda bid: p
    st._entry = lambda bid: None
    return st, p


def test_the_record_keeps_the_entity_type(tmp_path, monkeypatch):
    st, _ = _state(tmp_path, monkeypatch, _bp())
    st.put_units("x", {"units": [_entity(entity_type="date")]})
    assert gr.load_record("x")["units"][0]["entity_type"] == "date"


def test_a_tagged_blueprint_with_no_record_shows_its_entities(tmp_path, monkeypatch):
    f = gr.plan(_bp(), [_entity(entity_type="date")], page_captions=False)["fields"]
    st, p = _state(tmp_path, monkeypatch, {"fields": f})
    _, units, _ = gr.current_units("x", {"fields": f}, gr._sha(p))
    assert [(u["name"], u.get("entity_type"), u["items"]) for u in units if u.get("kind") == "text"] == \
        [("dob", "date", ["dob_month", "dob_day", "dob_yr"])]
    # a current record without the entity (taken apart on the page, not applied yet) keeps it apart
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "x.json").write_text(json.dumps({"blueprint_sha": gr._sha(p), "units": [
        {"kind": "text", "name": "dob2", "type": "string", "items": ["dob_month", "dob_day"]}]}))
    _, units, _ = gr.current_units("x", {"fields": f}, gr._sha(p))
    assert [u["name"] for u in units if u.get("kind") == "text"] == ["dob2"]
