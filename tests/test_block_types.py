"""Block types (petey/validate/block_types.py, 2026-10-21): a template drawn once, its exact copies on the form found,
every block named from the template block's names with its own key."""
from petey.validate import block_types as bt, grid_check as gc


def blueprint(names, extra=None):
    """Blocks of three boxes (a name, a date, a checkbox) 60 pt apart down page 1, named by `names`."""
    fields, i = {}, 0
    for b, row in enumerate(names):
        y = 100 + 60 * b
        for k, n in enumerate(row):
            i += 1
            kind = "checkbox" if k == 2 else "text"
            w = 10 if k == 2 else 150
            fields[n] = {"type": "boolean" if k == 2 else "string", "x_petey_id": f"1_{i}",
                         "widget": {"page": 1, "widget_type": kind, "rect": [50 + 200 * k, y, 50 + 200 * k + w, y + 14]}}
    fields.update(extra or {})
    return {"fields": fields}


def use_tmp_records(monkeypatch, tmp_path):
    monkeypatch.setattr(gc, "SETS", tmp_path)
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / f"{bid}.json")


def test_exact_copies_are_found_and_a_box_of_another_size_is_not():
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)]
    odd = {"other_nm": {"type": "string", "x_petey_id": "1_99",
                        "widget": {"page": 1, "widget_type": "text", "rect": [50, 400, 120, 414]}}}
    bp = blueprint(rows, odd)
    tpl = bt.template(bp, 1, [45, 95, 470, 118])
    found = bt.find(bp, tpl)
    assert [[c[0] for c in b["cells"]] for b in found] == rows


def area(b):
    """The box around block `b` of `blueprint`."""
    return [45, 95 + 60 * b, 470, 118 + 60 * b]


def test_a_type_is_its_selection_and_blocks_are_designated(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "select the selection and interpret that as a type, don't automatically find other
    versions ... define and designate manually is fine"."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)])
    out = bt.define("t0", bp, 1, area(0))
    assert out["boxes"] == 3 and gc.load_set("t0")["types"][0]["blocks"] == [["1_1", "1_2", "1_3"]]
    assert not [e for e in gc.load_set("t0")["grids"] if e.get("type")]           # nothing else selected
    d = bt.designate("t0", bp, out["id"], 1, area(2))
    assert d["of"] == 2 and d["group"]
    g = next(e for e in gc.load_set("t0")["grids"] if e["id"] == d["group"])
    assert sorted({c[1] for c in g["cells"]}) == [0, 1]


def test_an_area_that_is_not_a_copy_is_refused(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["a_1_nm", "a_1_dt", "a_1_ind"], ["b_nm", "b_dt", "b_ind"]])
    bp["fields"]["b_dt"]["widget"]["rect"][2] += 40                          # a wider box
    out = bt.define("t3", bp, 1, area(0))
    try:
        bt.designate("t3", bp, out["id"], 1, area(1))
        raise AssertionError("designated")
    except ValueError as e:
        assert "not an exact copy" in str(e) and "b_dt" in str(e)


def test_blocks_take_the_template_names_with_their_own_key(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    rows = [["child_1_nm", "child_1_birth_dt", "child_1_ind"],
            ["child_2_name", "child_2_dob", "child_2_ind"],             # spelled otherwise: takes the template's
            ["child_3_nm", "child_3_birth_dt", "child_3_ind"]]
    bp = blueprint(rows)
    out = bt.define("t1", bp, 1, area(0))
    for b in (1, 2):
        bt.designate("t1", bp, out["id"], 1, area(b))
    ren, notes = bt.names_from_type("t1", bp, out["id"])
    assert ren == {"child_2_name": "child_2_nm", "child_2_dob": "child_2_birth_dt"} and not notes


def test_printed_keys_out_of_order_are_never_renumbered(monkeypatch, tmp_path):
    """I-130 (2026-10-21): item numbers printed in two columns run 5, 3, 6 top then left; renumbering them broke
    the names."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"item_{n}_nm", f"item_{n}_dt", f"item_{n}_ind"] for n in (5, 3, 6)]
    bp = blueprint(rows)
    out = bt.define("t2", bp, 1, area(0))
    for b in (1, 2):
        bt.designate("t2", bp, out["id"], 1, area(b))
    ren, notes = bt.names_from_type("t2", bp, out["id"])
    assert ren == {} and any("not counting by one" in x for x in notes)
