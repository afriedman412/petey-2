"""Suggested option groups among loose boxes (petey/validate/group_finder.py; Andrew, 2026-10-25: "anything more
complicated that doesn't get picked up automatically is probably worth of a human look anyways")."""
import pymupdf

from petey.validate import group_finder as gf


def _pdf(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=600, height=400)
    pg.insert_text((50, 60), "Do you smoke?", fontsize=10)
    pg.insert_text((222, 60), "Yes", fontsize=10)
    pg.insert_text((282, 60), "No", fontsize=10)
    pg.insert_text((50, 140), "Marital status (check one):", fontsize=10)
    for k, w in enumerate(("Single", "Married", "Widowed")):
        pg.insert_text((222, 165 + 20 * k), w, fontsize=10)
    pg.insert_text((50, 300), "Hobbies:", fontsize=10)
    for k, w in enumerate(("Golf", "Tennis")):
        pg.insert_text((222 + 80 * k, 300), w, fontsize=10)
    p = tmp_path / "f.pdf"
    doc.save(p)
    return p


def _box(field, x, y):
    return {"field": field, "page": 1, "rect": [x, y - 9, x + 10, y + 1], "widget_type": "checkbox"}


def test_yes_no_and_check_one_are_suggested_and_a_plain_run_is_not(tmp_path, monkeypatch):
    monkeypatch.setattr(gf, "NOT_GROUPS", tmp_path / "ng")
    loose = {"smoker_yes_ind": _box("smoker_yes_ind", 210, 60), "smoker_no_ind": _box("smoker_no_ind", 270, 60),
             **{f"marital_{w}_ind": _box(f"marital_{w}_ind", 210, 165 + 20 * k) for k, w in enumerate(("single", "married", "widowed"))},
             "golf_ind": _box("golf_ind", 210, 300), "tennis_ind": _box("tennis_ind", 290, 300)}
    got = gf.find({}, _pdf(tmp_path), loose, "t")
    by = {frozenset(s["items"]): s for s in got}
    assert by[frozenset({"smoker_yes_ind", "smoker_no_ind"})]["name"] == "smoker"
    assert frozenset({"marital_single_ind", "marital_married_ind", "marital_widowed_ind"}) in by
    assert not any("golf_ind" in s["items"] for s in got)          # no printed "one": left for a person
    gf.dismiss("t", ["smoker_yes_ind", "smoker_no_ind"])
    assert not any("smoker_yes_ind" in s["items"] for s in gf.find({}, _pdf(tmp_path), loose, "t"))


def _pdf2(tmp_path):
    doc = pymupdf.open()
    pg = doc.new_page(width=600, height=400)
    pg.insert_text((50, 40), "If you are changing information, check the applicable box.", fontsize=10)
    for k, w in enumerate(("Change", "Add", "Remove")):
        pg.insert_text((62 + 80 * k, 60), w, fontsize=10)
    pg.insert_text((50, 140), "Type of entity. Check the applicable box:", fontsize=10)
    for row, ws in enumerate((("General", "LLC", "Foreign"), ("Limited", "LLP", "Other"))):
        for k, w in enumerate(ws):
            pg.insert_text((62 + 100 * k, 160 + 20 * row), w, fontsize=10)
    pg.insert_text((50, 280), "Check at least one box.", fontsize=10)
    for k, w in enumerate(("Records", "Benefits")):
        pg.insert_text((62 + 100 * k, 300), w, fontsize=10)
    p = tmp_path / "g.pdf"
    doc.save(p)
    return p


def test_the_applicable_box_and_its_lines_are_one_group_and_at_least_one_is_not(tmp_path, monkeypatch):
    # 2026-10-25: CMS-855B's Change / Add / Remove under "check the applicable box"; f1065 p2's six entity types on
    # two lines under one "check the applicable box"; SSA-3288's "check at least one box" is a list to check any of
    monkeypatch.setattr(gf, "NOT_GROUPS", tmp_path / "ng")
    loose = {**{f"tech_{w}_ind": _box(f"tech_{w}_ind", 50 + 80 * k, 60) for k, w in enumerate(("change", "add", "remove"))},
             **{f"entity_{w}_ind": _box(f"entity_{w}_ind", 50 + 100 * k, 160 + 20 * r)
                for r, ws in enumerate((("general", "llc", "foreign"), ("limited", "llp", "other"))) for k, w in enumerate(ws)},
             **{f"{w}_ind": _box(f"{w}_ind", 50 + 100 * k, 300) for k, w in enumerate(("records", "benefits"))}}
    got = {frozenset(s["items"]): s for s in gf.find({}, _pdf2(tmp_path), loose, "t")}
    assert got[frozenset(f"tech_{w}_ind" for w in ("change", "add", "remove"))]["name"] == "tech"
    assert frozenset(i for i in loose if i.startswith("entity_")) in got
    assert not any("records_ind" in s for s in got)
    gf.dismiss("t", [i for i in loose if i.startswith("entity_")])      # ungrouped: neither line comes back alone
    assert not any("entity_llc_ind" in s["items"] for s in gf.find({}, _pdf2(tmp_path), loose, "t"))


def test_the_finder_s_groups_are_made(monkeypatch):
    # 2026-10-25, Andrew: "make sure the finder groups related ind fields instead of putting them in a single block";
    # "let's have the finder groups group automatically, easy to ungroup them"
    from petey.validate import group_review as gr
    st = gr.State.__new__(gr.State)
    items = {f"i{k}": {"field": f"tech_{w}_ind"} for k, w in enumerate(("change", "add", "remove"))}
    units = [{"name": it["field"], "type": "boolean", "items": [i]} for i, it in items.items()] + \
            [{"name": "tech", "type": "category", "items": ["j0", "j1"]}]
    put = {}
    monkeypatch.setattr(st, "put_units", lambda bid, inc: put.update(inc), raising=False)
    bp = {"fields": {"tech": {}, "tech_change_ind": {}, "other": {}}}
    made = st._group("t", bp, items, units, [{"items": ["i0", "i1", "i2"], "page": 3, "why": "x", "name": "tech"}])
    assert made == [{"name": "tech_2", "page": 3, "items": 3, "why": "x"}]      # "tech" is taken: numbered
    assert [u["name"] for u in put["units"]] == ["tech", "tech_2"]
    assert put["units"][1]["items"] == ["i0", "i1", "i2"] and put["units"][1]["confirmed"] is False


def test_a_suggested_groups_name_keeps_the_number_its_boxes_share():
    """Andrew (2026-10-26): "block and groups need to consider parts as well": phone 2's type boxes are phone_type_2,
    not phone 1's phone_type."""
    from petey.validate.group_finder import _name
    assert _name(["phone_type_home_ind_2", "phone_type_cell_ind_2"]) == "phone_type_2"
    assert _name(["smoker_yes_ind", "smoker_no_ind"]) == "smoker"
