"""Add / remove: the underlines no field covers are lines to click, and a click on one (or just above an underline no
printed box encloses) proposes a text field over the band above it, named from its caption (Andrew, 2026-10-28: "the
underlines are highlighted and you can click on one to create a field above it"; "there are other fields to find
besides signatures")."""
import pymupdf
import yaml

from petey.validate import field_add


def _ctx(tmp_path, monkeypatch, fields=None):
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((72, 200), "Owner Signature:", fontsize=9)
    pg.draw_line((150, 200), (350, 200), color=(0, 0, 0), width=0.8)             # caption left of the line
    pg.draw_line((72, 300), (300, 300), color=(0, 0, 0), width=0.8)              # caption printed under the line
    pg.insert_text((72, 310), "Notary Public Signature", fontsize=8)
    pg.draw_line((72, 400), (300, 400), color=(0, 0, 0), width=0.8)              # a line the blueprint has
    blank = tmp_path / "f.pdf"
    doc.save(blank)
    bpt = tmp_path / "f.bpt"
    bpt.write_text(yaml.safe_dump({"source_pdf": "f.pdf", "fields": fields or {}}))
    monkeypatch.setattr(field_add, "resolve_blank", lambda bp: blank)
    return field_add.Context("t__f", bpt)


HAVE = {"p1_f1": {"type": "string", "widget": {"page": 1, "rect": [72, 388, 300, 400], "widget_type": "text",
                                               "path": None}}}


def _line(ctx, y):
    return next(u for u in ctx.lines() if abs(u["rect"][3] - y) < 1.5)


def test_lines_are_the_underlines_no_field_covers(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, HAVE)
    ys = sorted(round(u["rect"][3]) for u in ctx.lines())
    assert ys == [200, 300]                                    # the line at 400 is field p1_f1
    assert all(u["source"] == "underline" and u["sid"].startswith("u1_") for u in ctx.lines())


def test_a_line_clicked_is_a_text_field_named_from_its_caption(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch)
    left = field_add.propose(ctx, 1, sid=_line(ctx, 200)["sid"])["proposals"]
    assert [(p["kind"], p["geometry"], p["caption"]) for p in left] == [("text", "underline", "Owner Signature")]
    under = field_add.propose(ctx, 1, sid=_line(ctx, 300)["sid"])["proposals"]
    assert [(p["geometry"], p["caption"], p["name"]) for p in under] == [
        ("underline", "Notary Public Signature", "notary_public_signature")]


def test_a_click_just_above_an_open_underline_takes_the_line(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, HAVE)
    r = field_add.propose(ctx, 1, rect=[199, 279, 201, 281])  # above the band of the line at 300
    assert r["notes"] == ["the band above the underline at the click"]
    (p,) = r["proposals"]
    assert p["geometry"] == "underline" and abs(p["rect"][3] - 300) < 1.5 and p["rect"][0] <= 73
    taken = field_add.propose(ctx, 1, rect=[199, 394, 201, 396])
    assert taken == {"proposals": [], "notes": ["the underline here is already field p1_f1"]}


def test_a_box_drawn_over_fields_is_a_field_anyway(tmp_path, monkeypatch):
    """Andrew, 2026-10-31: "in general you should just let a box be drawn anywhere and become a field. overlapping
    boxes are common" (je__f4506t p1: a box on the signature line was refused, the finder's row box under it being
    the phone field's)."""
    ctx = _ctx(tmp_path, monkeypatch, HAVE)
    r = field_add.propose(ctx, 1, rect=[60, 380, 320, 404])           # right over field p1_f1
    (p,) = r["proposals"]
    assert p["rect"] == [60.0, 380.0, 320.0, 404.0] and p["geometry"] == "selection"


def test_saving_keeps_an_added_field_that_overlaps_and_skips_the_same_box_again(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, HAVE)
    (over,) = field_add.propose(ctx, 1, rect=[60, 380, 200, 404])["proposals"]
    (again,) = field_add.propose(ctx, 1, rect=[72, 388, 300, 400])["proposals"]
    over, again = {**over, "name": "signature"}, {**again, "name": "line_again"}
    out = field_add.plan({"fields": dict(HAVE)}, [over, again])
    assert "signature" in out["fields"] and "line_again" not in out["fields"]
    assert any("overlaps field p1_f1" in c for c in out["changes"])
    assert out["skipped"] == ["line_again: the same box is field p1_f1"]


def test_free_name_adds_or_raises_the_iteration():
    """Andrew, 2026-10-31: "any suggested duplicate name should just be converted to a non-clashing name, either by
    increasing the iteration value or by adding one"."""
    assert field_add.free_name("sort_code", {"sort_code"}) == "sort_code_2"
    assert field_add.free_name("sort_code", {"sort_code", "sort_code_2"}) == "sort_code_3"
    assert field_add.free_name("x_line_2", {"x_line_2", "x_line_3"}) == "x_line_4"
    assert field_add.free_name("line_12_amt", {"line_12_amt"}) == "line_12_amt_2"     # a number inside stays
    assert field_add.free_name("free", set()) == "free"


def test_saving_renames_a_clash_instead_of_refusing(tmp_path, monkeypatch):
    ctx = _ctx(tmp_path, monkeypatch, HAVE)
    (a,) = field_add.propose(ctx, 1, rect=[60, 150, 200, 170])["proposals"]
    (b,) = field_add.propose(ctx, 1, rect=[60, 500, 200, 520])["proposals"]
    out = field_add.plan({"fields": dict(HAVE)}, [{**a, "name": "p1_f1"}, {**b, "name": "p1_f1"}])
    assert not out["errors"]
    assert {"p1_f1", "p1_f1_2", "p1_f1_3"} <= set(out["fields"])
    assert "p1_f1 is taken: added as p1_f1_2" in out["changes"] and "p1_f1 is taken: added as p1_f1_3" in out["changes"]


def test_fields_say_which_are_choices():
    bp = {"fields": {"nm": {"type": "string", "widget": {"page": 1, "rect": [0, 0, 50, 10], "widget_type": "text"}},
                     "yes": {"type": "boolean", "widget": {"page": 1, "rect": [0, 20, 8, 28], "widget_type": "checkbox"}},
                     "work": {"type": "category", "widget": {"page": 1, "rect": [0, 40, 50, 50], "widget_type": "combobox"}}}}
    assert {f["name"]: f["choice"] for f in field_add.field_rects(bp)} == {"nm": False, "yes": True, "work": True}


def test_fields_say_which_are_printed():
    # signatures, initials, printed names: their own colour on Add / remove (2026-10-31)
    bp = {"fields": {"nm": {"type": "string", "widget": {"page": 1, "rect": [0, 0, 50, 10], "widget_type": "text"}},
                     "sig": {"type": "string", "widget": {"page": 1, "rect": [0, 20, 90, 30], "widget_type": "text"},
                             "x_petey_printed": {"source": "review", "when": "2026-10-31 20:00:00"}}}}
    assert {f["name"]: f["printed"] for f in field_add.field_rects(bp)} == {"nm": False, "sig": True}


def test_a_box_drawn_over_a_suggestion_set_aside_is_the_area_drawn(tmp_path, monkeypatch):
    """Andrew, 2026-10-31: "I want to be able to un-suggest boxes so they don't get selected when I draw over them":
    a finder box set aside as not a field (sent by the page, or in the record) is not there for a box drawn."""
    import json
    monkeypatch.setattr(field_add, "OUT", tmp_path / "rec")
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.boxes = [{"id": 7, "sid": "b7", "page": 1, "rect": [100, 600, 300, 614], "kind": "text", "claimed_by": None}]
    draw = [90, 590, 320, 620]
    (p,) = field_add.propose(ctx, 1, rect=draw)["proposals"]
    assert p["rect"] == [100, 600, 300, 614]                          # the suggestion, as before
    (p,) = field_add.propose(ctx, 1, rect=draw, dismissed={"b7"})["proposals"]
    assert p["rect"] == [90.0, 590.0, 320.0, 620.0] and p["geometry"] == "selection"
    (tmp_path / "rec").mkdir()
    (tmp_path / "rec" / "t__f.json").write_text(json.dumps({"dismissed": [{"sid": "b7"}]}))
    (p,) = field_add.propose(ctx, 1, rect=draw)["proposals"]          # set aside in the record: the same
    assert p["geometry"] == "selection"


def test_a_click_on_a_box_set_aside_proposes_nothing(tmp_path, monkeypatch):
    """Andrew, 2026-11-01: "'not a field' removes the outline from the add/remove layout. z brings it back": a click
    on a printed box or underline set aside proposes nothing; a box drawn there is still the field."""
    monkeypatch.setattr(field_add, "OUT", tmp_path / "rec")
    ctx = _ctx(tmp_path, monkeypatch)
    ctx.boxes = []
    band = _line(ctx, 200)["rect"]
    x, y = (band[0] + band[2]) / 2, (band[1] + band[3]) / 2
    click = [x - 1, y - 1, x + 1, y + 1]
    assert field_add.propose(ctx, 1, rect=click)["proposals"]
    aside = [{"sid": _line(ctx, 200)["sid"], "page": 1, "rect": band, "source": "underline"}]
    r = field_add.propose(ctx, 1, rect=click, dismissed=aside)
    assert r["proposals"] == [] and r["notes"] == ["set aside as not a field (z brings it back)"]
    (p,) = field_add.propose(ctx, 1, rect=[band[0], band[1] - 2, band[2], band[3] + 2], dismissed=aside)["proposals"]
    assert p["geometry"] == "selection"                                   # drawn: the field


def test_a_removed_fields_box_keeps_its_id():
    # the id names the box, not its place in the list, so setting one aside does not move to another
    rec = {"removed_applied": [{"name": "a", "page": 1, "rect": [10, 20, 60, 30]}, {"name": "b", "page": 2, "rect": [5, 5, 9, 9]}]}
    out = field_add.with_removed([], [], rec)
    assert [x["sid"] for x in out] == ["r1_10_20", "r2_5_5"]
