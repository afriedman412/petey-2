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
