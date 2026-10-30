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
