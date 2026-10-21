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


def test_a_drawn_block_is_a_new_type_or_a_copy_of_one(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "drag to create a block type from a new set of fields (it should auto-detect existing block
    types though)"; a near copy says which type it nearly is and what differs."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)])
    bp["fields"]["child_3_birth_dt"]["widget"]["rect"][2] += 40                  # the third block's date is wider
    one = bt.draw("t0", bp, 1, area(0))
    assert one["new"] and one["type"] == "BT1" and one["block"] == 1
    two = bt.draw("t0", bp, 1, area(1))
    assert not two["new"] and two["type"] == "BT1" and two["of"] == 2
    three = bt.draw("t0", bp, 1, area(2))
    assert three["new"] and three["type"] == "BT2" and three["closest"]["type"] == "BT1"
    assert "child_3_birth_dt" in three["closest"]["differs"]
    assert bt.draw("t0", bp, 1, area(1)).get("already")
    assert not [e for e in gc.load_set("t0")["grids"] if e.get("type")]          # no block group yet


def test_blocks_take_the_template_names_with_their_own_key(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    rows = [["child_1_nm", "child_1_birth_dt", "child_1_ind"],
            ["child_2_name", "child_2_dob", "child_2_ind"],             # spelled otherwise: takes the template's
            ["child_3_nm", "child_3_birth_dt", "child_3_ind"]]
    bp = blueprint(rows)
    for b in range(3):
        bt.draw("t2", bp, 1, area(b))
    ren, notes = bt.names_from_type("t2", bp, "BT1")
    assert ren == {"child_2_name": "child_2_nm", "child_2_dob": "child_2_birth_dt"} and not notes


def test_printed_keys_out_of_order_are_never_renumbered(monkeypatch, tmp_path):
    """I-130 (2026-10-21): item numbers printed in two columns run 5, 3, 6 top then left; renumbering them broke
    the names."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"item_{n}_nm", f"item_{n}_dt", f"item_{n}_ind"] for n in (5, 3, 6)]
    bp = blueprint(rows)
    for b in range(3):
        bt.draw("t3", bp, 1, area(b))
    ren, notes = bt.names_from_type("t3", bp, "BT1")
    assert ren == {} and any("not counting by one" in x for x in notes)


def test_a_lone_block_is_checked_against_its_confirmed_type(monkeypatch, tmp_path):
    """I-134 BT3 (2026-10-21): one address block for the supporter, one for the physical address, one for the
    beneficiary, in no block group. Each position's wording is what follows each block's own start; a block passes
    when every name is its start and the wording."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["supporter_mailing_street_txt", "supporter_mailing_city_nm", "supporter_mailing_ind"],
                    ["physical_street_number_txt", "physical_city_nm", "physical_ind"],
                    ["beneficiary_mailing_street_txt", "beneficiary_mailing_city_nm", "beneficiary_mailing_ind"]])
    for b in range(3):
        bt.draw("t5", bp, 1, area(b))
    t = gc.load_set("t5")["types"][0]
    assert bt.wordings(bp, t) == ["street_txt", "city_nm", "ind"]
    try:
        bt.validate_block("t5", bp, "1_4")
        raise AssertionError("validated before the type was confirmed")
    except ValueError as e:
        assert "confirm" in str(e)
    bt.confirm("t5", bp, "BT1", ["street_txt", "city_nm", "ind"])
    assert bt.validate_block("t5", bp, "1_1")["differs"][0]["want"] == "supporter_mailing_1_street_txt"   # empty: next free
    for c in ("1_1", "1_4", "1_7"):
        bt.set_parts("t5", c, None, "-")                                   # '-': no iteration
    assert bt.validate_block("t5", bp, "1_1")["ok"]
    res = bt.validate_block("t5", bp, "1_4")
    assert not res["ok"] and res["differs"] == [{"pos": 1, "name": "physical_street_number_txt", "want": "physical_street_txt"}]


def test_a_cancelled_rename_keeps_the_name(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "the suggested name changes should be cancelable": a cancelled one no longer counts as off
    the type, so the block can validate; undone, it counts again."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["a_street_txt", "a_city_nm", "a_ind"], ["b_street_number_txt", "b_city_nm", "b_ind"]])
    for b in range(2):
        bt.draw("t6", bp, 1, area(b))
    bt.confirm("t6", bp, "BT1", ["street_txt", "city_nm", "ind"])
    for c in ("1_1", "1_4"):
        bt.set_parts("t6", c, None, "-")
    assert not bt.validate_block("t6", bp, "1_4")["ok"]
    bt.keep_name("t6", "1_4", 1)
    res = bt.validate_block("t6", bp, "1_4")
    assert res["ok"] and res["kept"] == [1]
    bt.keep_name("t6", "1_4", 1, on=False)
    assert not bt.validate_block("t6", bp, "1_4")["ok"]


def test_an_area_of_several_copies_is_several_blocks(monkeypatch, tmp_path):
    """VA 21P-527EZ p8 (2026-10-21): "selecting an area that contains several iterations of existing block type should
    identify them"; an area with other boxes too is a new type."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"d_{b}_month", f"d_{b}_day", f"d_{b}_ind"] for b in (1, 2, 3, 4)])
    bt.draw("t7", bp, 1, area(0))
    out = bt.draw("t7", bp, 1, [45, 155, 470, 298])              # blocks 2-4 in one area
    assert out["found"] == 3 and out["fresh"] == 3 and out["of"] == 4
    assert bt.draw("t7", bp, 1, [45, 95, 470, 238])["found"] == 3   # 1-3 again: found, none new


def test_a_page_is_searched_for_block_types_and_a_block_reassigned(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "can we detect existing block types on a page? and can we assign a block type to a
    block?"."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"d_{b}_month", f"d_{b}_day", f"d_{b}_ind"] for b in (1, 2, 3, 4)])
    bp["fields"]["d_4_day"]["widget"]["rect"][2] += 20                  # the fourth a near copy
    bt.draw("t8", bp, 1, area(0))
    out = bt.detect("t8", bp, 1)
    assert out["found"] == {"BT1": [2, 3]}                             # blocks 2 and 3; 4 is not a copy
    near = bt.draw("t8", bp, 1, area(3))
    assert near["new"] and near["type"] == "BT2"
    moved = bt.assign("t8", bp, "1_10", "BT1")
    assert moved == {"type": "BT1", "block": 4, "of": 4, "was": "BT2", "missing": [], "extra": []}
    assert [t["id"] for t in gc.load_set("t8")["types"]] == ["BT1"]      # BT2 left with no blocks: dropped


def test_a_block_type_has_a_label(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["d_1_month", "d_1_day", "d_1_ind"]])
    bt.draw("t9", bp, 1, area(0))
    bt.set_label("t9", "BT1", "  a date  ")
    assert bt.listing(bp, gc.load_set("t9"))[0]["label"] == "a date"
    bt.set_label("t9", "BT1", "")
    assert bt.listing(bp, gc.load_set("t9"))[0]["label"] == ""


def test_names_are_prefix_iteration_wording(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "for each block type [field_name]_[block iteration] and for each block: [prefix] ... so
    you can have beneficiary_prior_spouse_1_first_nm"."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["prior_spouse_1_first_nm", "prior_spouse_1_last_nm", "prior_spouse_1_ind"],
                    ["prior_spouse_first_nm", "prior_spouse_last_nm", "prior_spouse_ind"]])
    for b in range(2):
        bt.draw("t10", bp, 1, area(b))
    bt.confirm("t10", bp, "BT1", ["first_nm", "last_nm", "ind"])
    res = bt.validate_block("t10", bp, "1_4")             # the second block: no number, shares the prefix -> 2
    assert res["prefix"] == "prior_spouse" and res["iteration"] == "2"
    assert res["differs"][0] == {"pos": 1, "name": "prior_spouse_first_nm", "want": "prior_spouse_2_first_nm"}
    bt.set_parts("t10", "1_1", "beneficiary_prior_spouse", "1")
    res = bt.validate_block("t10", bp, "1_1")
    assert res["differs"][0]["want"] == "beneficiary_prior_spouse_1_first_nm"


def test_a_block_with_fewer_boxes_is_fitted_to_a_type(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "cross-check box sizes or locations or labels to find a best fit": ACORD 80's co-applicant
    block has fewer boxes than the applicant's. Assigned, its boxes pair by place, size and label; the one it lacks
    stays empty, its own extra box stays out."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["applicant_first_nm", "applicant_birth_dt", "applicant_ind"],
                    ["co_applicant_first_nm", "co_applicant_birth_dt", "co_applicant_ind"]])
    del bp["fields"]["co_applicant_birth_dt"]                       # the second block lacks the date ...
    bp["fields"]["co_applicant_email_txt"] = {"type": "string", "x_petey_id": "1_9", "widget": {     # ... and has a box
        "page": 1, "widget_type": "text", "rect": [50, 175, 120, 189]}}                             # the type has not
    bt.draw("t11", bp, 1, area(0))
    bt.confirm("t11", bp, "BT1", ["first_nm", "birth_dt", "ind"])
    near = bt.draw("t11", bp, 1, [45, 155, 470, 192])
    assert near["new"]
    out = bt.assign("t11", bp, "1_4", "BT1")
    assert out["missing"] == [2] and out["extra"] == ["co_applicant_email_txt"]
    bt.set_parts("t11", "1_4", None, "-")
    res = bt.validate_block("t11", bp, "1_4")
    assert res["ok"]                                               # the missing box is not counted as off


def test_blocks_named_from_the_type_label_and_numbered(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "set the blocks to automatically iterate and populate the prefix with the block name"."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["spouse_a_first_nm", "spouse_a_last_nm", "spouse_a_ind"],
                    ["former_first_nm", "former_last_nm", "former_ind"]])
    for b in range(2):
        bt.draw("t12", bp, 1, area(b))
    bt.confirm("t12", bp, "BT1", ["first_nm", "last_nm", "ind"])
    try:
        bt.set_auto("t12", "BT1", True)
        raise AssertionError("auto without a label")
    except ValueError as e:
        assert "label" in str(e)
    bt.set_label("t12", "BT1", "Prior Spouse")
    bt.set_auto("t12", "BT1", True)
    wants = [d["want"] for d in bt.validate_block("t12", bp, "1_4")["differs"]]
    assert wants == ["prior_spouse_2_first_nm", "prior_spouse_2_last_nm", "prior_spouse_2_ind"]


def test_word_variants_still_pair(monkeypatch, tmp_path):
    """VA 21-686c BT7-3 (2026-10-21): page 11 named its boxes residence_city_nm where the type has
    resides_address_city_nm; resides / residence is one word, and the box is the city box."""
    assert bt._same_word("resides", "residence") and bt._same_word("ended", "end") and not bt._same_word("years", "yr")


def test_a_block_that_is_no_longer_one(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"d_{b}_month", f"d_{b}_day", f"d_{b}_ind"] for b in (1, 2)])
    for b in range(2):
        bt.draw("t13", bp, 1, area(b))
    assert bt.remove_block("t13", bp, "1_4")["said"] == ["no longer a block of BT1"]
    assert "dropped" in bt.remove_block("t13", bp, "1_1")["said"][-1]
    assert gc.load_set("t13")["types"] == []
