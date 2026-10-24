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
    assert bt.validate_block("t5", bp, "1_1")["ok"]          # alone with its prefix: no number (the standard, 2026-10-24)
    for c in ("1_1", "1_4", "1_7"):
        bt.set_parts("t5", c, None, "-")                                   # '-': no iteration
    assert bt.validate_block("t5", bp, "1_1")["ok"]
    res = bt.validate_block("t5", bp, "1_4")
    assert not res["ok"] and res["differs"] == [{"pos": 1, "name": "physical_street_number_txt", "want": "physical_street_txt",
                                            "ident": {"block_prefix": "physical", "subject": "street", "suffix": "txt"}}]


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
    assert moved == {"type": "BT1", "block": 4, "of": 4, "was": "BT2", "code": "1_10", "missing": [], "extra": []}
    assert [t["id"] for t in gc.load_set("t8")["types"]] == ["BT1"]      # BT2 left with no blocks: dropped


def test_a_block_type_has_a_label(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["d_1_month", "d_1_day", "d_1_ind"]])
    bt.draw("t9", bp, 1, area(0))
    bt.set_label("t9", "BT1", "  a date  ")
    assert bt.listing(bp, gc.load_set("t9"))[0]["label"] == "a date"
    bt.set_label("t9", "BT1", "")
    assert bt.listing(bp, gc.load_set("t9"))[0]["label"] == ""


def test_names_are_printed_from_parts_as_every_field(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "for each block type [field_name]_[block iteration] and for each block: [prefix]"; since
    2026-10-22 ("set up block labels to work like the rest of the field names") the parts are a field's: the block's
    prefix and the position's subject, the position's suffix, the block's iteration, printed iteration last."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["prior_spouse_1_first_nm", "prior_spouse_1_last_nm", "prior_spouse_1_ind"],
                    ["prior_spouse_first_nm", "prior_spouse_last_nm", "prior_spouse_ind"]])
    for b in range(2):
        bt.draw("t10", bp, 1, area(b))
    bt.confirm("t10", bp, "BT1", ["first_nm", "last_nm", "ind"])
    res = bt.validate_block("t10", bp, "1_4")             # the second block: no number, shares the prefix -> 2
    assert res["prefix"] == "prior_spouse" and res["iteration"] == "2"
    assert res["differs"][0] == {"pos": 1, "name": "prior_spouse_first_nm", "want": "prior_spouse_2_first_nm",
                                 "ident": {"block_prefix": "prior_spouse", "block_iteration": "2", "subject": "first",
                                           "suffix": "nm"}}
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


def test_block_name_clashes(monkeypatch, tmp_path):
    """VA 21-686c BT7-5 / BT7-6 (2026-10-21): blocks whose names are swapped rename together; two blocks coming to one
    name get no renames until settled; a rename onto a name a field outside keeps is held."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["child_first_nm_2", "child_last_nm_2", "child_ind_2"],      # the first block carries the 2nd's
                    ["child_first_nm_1", "child_last_nm_1", "child_ind_1"]])     # names, and the 2nd the 1st's
    for b in range(2):
        bt.draw("t14", bp, 1, area(b))
    bt.confirm("t14", bp, "BT1", ["first_nm", "last_nm", "ind"])
    bt.set_label("t14", "BT1", "child")
    bt.set_auto("t14", "BT1", True)
    r = bt.block_renames("t14", bp, "1_1")
    assert ("child_first_nm_2", "child_1_first_nm") in {(d["name"], d["want"]) for d in r["renames"]}
    t = bt.type_renames("t14", bp, "BT1")             # the standard's order: the old swap is no longer one
    assert {(d["name"], d["want"]) for d in t["renames"]} >= {("child_first_nm_2", "child_1_first_nm"),
                                                               ("child_first_nm_1", "child_2_first_nm")}
    bt.set_parts("t14", "1_4", None, "1")                                       # both now come to child_1
    t = bt.type_renames("t14", bp, "BT1")
    assert t["same"] == ["BT1-1", "BT1-2"] and t["renames"] == []
    bt.set_parts("t14", "1_4", None, "3")
    bp["fields"]["child_3_ind"] = {"type": "boolean", "x_petey_id": "1_99", "widget": {"page": 1, "widget_type": "checkbox",
                                                                                     "rect": [500, 700, 510, 710]}}
    held = bt.type_renames("t14", bp, "BT1")["held"]
    assert [(d["name"], d["want"], d["held"]) for d in held] == [("child_ind_1", "child_3_ind", "no block")]


def test_a_block_told_apart_by_its_prefix(monkeypatch, tmp_path):
    """Andrew (2026-10-21): "provide a prefix instead of an iteration ... you want preparer_address and preparer is the
    defining aspect (not iteration)"; "we do want preparer_address_1 and _2 available"; "this should be a block-level
    decision". A block told apart by its prefix has no number while it is alone with the prefix; blocks sharing it
    are numbered; a block by number keeps its number; two blocks both set to none clash."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["preparer_nm", "preparer_signature_dt", "preparer_ind"],
                    ["interpreter_nm", "interpreter_signature_dt", "interpreter_ind"],
                    ["child_nm", "child_signature_dt", "child_ind"]])
    for b in range(3):
        bt.draw("t20", bp, 1, area(b))
    bt.confirm("t20", bp, "BT1", ["nm", "signature_dt", "ind"])
    res = bt.validate_block("t20", bp, "1_4")             # by number, alone with its prefix: no number (2026-10-24)
    assert res["iteration"] is None and res["ok"]
    for code in ("1_1", "1_4"):
        bt.set_parts("t20", code, None, None, "prefix")
        res = bt.validate_block("t20", bp, code)
        assert res["ok"] and res["iteration"] is None
    assert bt.validate_block("t20", bp, "1_7")["ok"]                                       # by number, alone
    bt.set_parts("t20", "1_4", "preparer", "", "prefix")   # two blocks on one prefix: numbered, in the type's order
    assert bt.validate_block("t20", bp, "1_1")["differs"][0]["want"] == "preparer_1_nm"
    assert bt.validate_block("t20", bp, "1_4")["differs"][0]["want"] == "preparer_2_nm"
    bt.set_parts("t20", "1_4", "preparer", "-", "prefix")  # ... both set to none: they clash, flagged
    bt.set_parts("t20", "1_1", None, "-", "prefix")
    rec = gc.load_set("t20")
    assert bt.type_checks(bp, rec["types"][0], rec)["1_4"]["same_as"]
    bt.set_parts("t20", "1_1", None, None, None)          # back to the default: by number
    assert bt.validate_block("t20", bp, "1_1")["iteration"] == "1"
    lst = bt.listing(bp, gc.load_set("t20"))[0]["blocks"]
    assert [b["by"] for b in lst] == ["number", "prefix", "number"]


def test_names_that_say_nothing_leave_place_and_size_to_decide(monkeypatch, tmp_path):
    """VA 21-686c BT35 (2026-10-21): a date's three boxes named school_3_dt, school_2_dt, school_1_dt (the labeler
    numbered the parts as dates), spaced a little wider than the date type's, became a type of their own and could
    not be assigned to the date type (month, day, yr): the names share no word with any wording, so they say
    nothing, and the boxes pair by place and size."""
    use_tmp_records(monkeypatch, tmp_path)
    def date(codes, y, names, xs):
        return {n: {"type": "string", "x_petey_id": c, "widget": {"page": 1, "widget_type": "text",
                "rect": [x, y, x + w, y + 16]}} for n, c, x, w in zip(names, codes, xs, (33, 33, 67))}
    bp = {"fields": {**date(["1_1", "1_2", "1_3"], 100, ["dob_month", "dob_day", "dob_yr"], (50, 99, 145)),
                     **date(["1_4", "1_5", "1_6"], 300, ["school_3_dt", "school_2_dt", "school_1_dt"], (50, 113, 164))}}
    bt.draw("t21", bp, 1, [45, 95, 215, 120])
    bt.confirm("t21", bp, "BT1", ["month", "day", "yr"])
    assert bt.draw("t21", bp, 1, [45, 295, 235, 320])["new"]           # a type of its own, as on the form
    out = bt.assign("t21", bp, "1_4", "BT1")
    assert out["missing"] == [] and out["extra"] == []
    t = next(x for x in gc.load_set("t21")["types"] if x["id"] == "BT1")
    assert t["blocks"][1] == ["1_4", "1_5", "1_6"]                      # month, day, yr: left to right


def test_assign_pairs_by_location_not_by_name(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "assigning a block to a type should just overwrite the labels using the type info, by
    location". A block whose day and month boxes carry each other's names pairs by where they sit: the left box is
    the month, whatever it is called."""
    use_tmp_records(monkeypatch, tmp_path)
    def date(codes, y, names, xs):
        return {n: {"type": "string", "x_petey_id": c, "widget": {"page": 1, "widget_type": "text",
                "rect": [x, y, x + w, y + 16]}} for n, c, x, w in zip(names, codes, xs, (33, 33, 67))}
    bp = {"fields": {**date(["1_1", "1_2", "1_3"], 100, ["dob_month", "dob_day", "dob_yr"], (50, 99, 145)),
                     **date(["1_4", "1_5", "1_6"], 300, ["hired_day", "hired_month", "hired_yr"], (50, 113, 164))}}
    bt.draw("t22", bp, 1, [45, 95, 215, 120])
    bt.confirm("t22", bp, "BT1", ["month", "day", "yr"])
    bt.draw("t22", bp, 1, [45, 295, 235, 320])
    bt.assign("t22", bp, "1_4", "BT1")
    t = next(x for x in gc.load_set("t22")["types"] if x["id"] == "BT1")
    assert t["blocks"][1] == ["1_4", "1_5", "1_6"]
    res = bt.validate_block("t22", bp, "1_4")
    assert [d["want"] for d in res["differs"]] == ["hired_month", "hired_day"]      # alone: no number


def test_a_block_reads_the_same_in_either_print_order():
    """2026-10-22: block names were printed [prefix]_[iteration]_[wording] (child_2_city_nm); they are now printed as
    every field's, the iteration last (child_city_nm_2). Either reads to one prefix, iteration and wordings, and a
    number inside a wording (address_line_1) is not the block's."""
    old = bt._read_block(["child_2_address_line_1_txt", "child_2_city_nm", "child_2_ind"])
    new = bt._read_block(["child_address_line_1_txt_2", "child_city_nm_2", "child_ind_2"])
    assert old == new == ("child", "2", ["address_line_1_txt", "city_nm", "ind"])
    assert bt._read_block(["preparer_nm", "preparer_signature_dt"]) == ("preparer", None, ["nm", "signature_dt"])


def test_a_type_is_confirmed_with_a_fields_parts(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "we just need to have the same inputs that go into the standalone fields for the block
    fields": each position a subject, a suffix and a part; the block gives the iteration; names print as a field's."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([["dob_1_month", "dob_1_day", "dob_1_ind"], ["dob_2_month", "dob_2_day", "dob_2_ind"]])
    for b in range(2):
        bt.draw("t23", bp, 1, area(b))
    assert bt.slot("birth_dt_month") == {"subject": "birth", "suffix": "dt", "part": "month"}
    try:
        bt.confirm("t23", bp, "BT1", [{"part": "month"}, {"subject": "birth"}, {"suffix": "ind"}])
        raise AssertionError("a position with only a part")
    except ValueError as e:
        assert "subject or a suffix" in str(e)
    out = bt.confirm("t23", bp, "BT1", [{"subject": "birth", "suffix": "dt", "part": "month"},
                                        {"subject": "birth", "suffix": "dt", "part": "day"}, {"suffix": "ind"}])
    assert out["wordings"] == ["birth_dt_month", "birth_dt_day", "ind"]
    res = bt.validate_block("t23", bp, "1_4")
    assert [d["want"] for d in res["differs"]] == ["dob_2_birth_dt_month", "dob_2_birth_dt_day"]   # dob_2_ind as is
    assert res["differs"][0]["ident"] == {"block_prefix": "dob", "block_iteration": "2", "subject": "birth", "suffix": "dt",
                                          "part": "month"}


def test_a_field_dropped_on_a_block_fills_its_empty_position(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "selected fields sometimes don't show up in a block ... can we drag fields on to a block to
    add them?" A field dropped on a block takes the empty position of its kind nearest it, leaving the block it was in;
    with no such position, the type grows a position only when asked."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)]
    other = {"child_1_note_txt": {"type": "string", "x_petey_id": "1_99",
                                  "widget": {"page": 1, "widget_type": "text", "rect": [50, 130, 120, 144]}}}
    bp = blueprint(rows, other)
    for b in range(3):
        bt.draw("t1", bp, 1, area(b))
    rec = gc.load_set("t1")
    (t,) = rec["types"]
    t["blocks"][1][1] = None                          # block 2's date left out, as a drifted box is
    gc._save_set("t1", rec)

    out = bt.add_field("t1", bp, "1_4", "1_5")
    assert out["pos"] == 2 and not out["grew"]
    assert gc.load_set("t1")["types"][0]["blocks"][1] == ["1_4", "1_5", "1_6"]

    # block 3's date dropped on block 1, which has no empty date: nothing changes until the type may grow
    out = bt.add_field("t1", bp, "1_1", "1_8")
    assert out["grow_needed"] and "every position is filled" in out["why"]

    # a checkbox dropped on a block whose only empty position is a text box: the kinds differ
    rec = gc.load_set("t1")
    rec["types"][0]["blocks"][2][1] = None
    gc._save_set("t1", rec)
    out = bt.add_field("t1", bp, "1_7", "1_3")
    assert out["grow_needed"] and "other kinds" in out["why"]

    # block 1's date into block 3's empty position: it leaves block 1
    out = bt.add_field("t1", bp, "1_7", "1_2")
    assert out["pos"] == 2 and any(s.startswith("out of BT1-1") for s in out["said"])
    assert gc.load_set("t1")["types"][0]["blocks"][0] == ["1_1", None, "1_3"]


def test_a_dropped_field_can_grow_its_type(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2)]
    other = {"child_1_note_txt": {"type": "string", "x_petey_id": "1_99",
                                  "widget": {"page": 1, "widget_type": "text", "rect": [50, 130, 120, 144]}}}
    bp = blueprint(rows, other)
    bt.draw("t2", bp, 1, area(0))
    bt.draw("t2", bp, 1, area(1))
    out = bt.add_field("t2", bp, "1_1", "1_99", grow=True)
    assert out["grew"] and out["pos"] == 4
    (t,) = gc.load_set("t2")["types"]
    assert len(t["boxes"]) == 4 and t["boxes"][3]["dy"] == 30
    assert t["blocks"] == [["1_1", "1_2", "1_3", "1_99"], ["1_4", "1_5", "1_6", None]]
    assert bt.wordings(bp, t)[3] == "note_txt"
    (y,) = bt.listing(bp, gc.load_set("t2"))
    assert y["blocks"][1]["names"][3] is None


def test_a_copy_drawn_off_its_layout_is_found_by_its_printed_labels(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "block detection logic could be/should be using printed labels ... the relative location
    of labels is more important than the actual intended content of the field". The second block's date box is
    drawn 11 pt off, so layout alone misses it; its printed labels sit where the first block's do."""
    import pymupdf
    from petey.validate import retype
    use_tmp_records(monkeypatch, tmp_path)
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    for y in (100, 160):
        pg.insert_text((50, y - 4), "Child 1 full name", fontsize=8)
        pg.insert_text((250, y - 4), "Date of birth", fontsize=8)
        pg.insert_text((450, y - 4), "Disabled", fontsize=8)
    doc.save(str(pdf))
    doc.close()
    monkeypatch.setattr(retype, "resolve_blank", lambda bp: pdf)
    bp = blueprint([[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2)])
    r = bp["fields"]["child_2_birth_dt"]["widget"]["rect"]
    r[0] += 11
    r[2] += 11
    bt.draw("t3", bp, 1, [45, 85, 470, 118])                  # the template, its labels inside the area
    out = bt.detect("t3", bp, 1)
    assert out["by_labels"] == {"BT1": [2]} and not out["empty"]
    assert gc.load_set("t3")["types"][0]["blocks"][1] == ["1_4", "1_5", "1_6"]


def test_labels_of_different_subjects_still_match(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "we need some tolerance on the label matching (spouse first name and child first name are
    congruent)". The second block prints Child's where the first prints Spouse's (so its words after that sit
    elsewhere on the line); its date box is drawn off, so only the labels find it. A block whose lines say something
    else is no copy."""
    import pymupdf
    from petey.validate import retype
    use_tmp_records(monkeypatch, tmp_path)
    pdf = tmp_path / "blank.pdf"
    doc = pymupdf.open()
    pg = doc.new_page(width=612, height=792)
    for y, who in ((100, "Spouse's"), (160, "Child's")):
        pg.insert_text((50, y - 4), f"{who} first name", fontsize=8)
        pg.insert_text((250, y - 4), f"{who} date of birth", fontsize=8)
        pg.insert_text((450, y - 4), "Disabled", fontsize=8)
    pg.insert_text((50, 216), "Employer telephone", fontsize=8)
    pg.insert_text((250, 216), "Gross wages", fontsize=8)
    pg.insert_text((450, 216), "Union member", fontsize=8)
    doc.save(str(pdf))
    doc.close()
    monkeypatch.setattr(retype, "resolve_blank", lambda bp: pdf)
    bp = blueprint([["spouse_first_nm", "spouse_birth_dt", "spouse_ind"], ["child_first_nm", "child_birth_dt", "child_ind"],
                    ["employer_phone_nbr", "wages_amt", "union_ind"]])
    for n in ("child_birth_dt", "wages_amt"):
        r = bp["fields"][n]["widget"]["rect"]
        r[0] += 11
        r[2] += 11
    bt.draw("t4", bp, 1, [45, 85, 470, 118])
    out = bt.detect("t4", bp, 1)
    assert out["by_labels"] == {"BT1": [2]}
    assert [b for b in gc.load_set("t4")["types"][0]["blocks"]] == [["1_1", "1_2", "1_3"], ["1_4", "1_5", "1_6"]]


# rescan (Andrew, 2026-10-22: "we should be able to rescan a page to allow blocks to reform")

def test_a_rescan_grows_a_type_to_the_fields_repeating_in_every_block(monkeypatch, tmp_path):
    """VA 21P-534EZ p13: each child's block held 4 of its boxes, the rest in grids since cancelled. A free field at
    one place in every block joins the type, in reading order; one with no copy in a block does not."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)]
    extra = {f"child_{b}_ssn": {"type": "string", "x_petey_id": f"1_{50 + b}",                # right of the drawn area
                                "widget": {"page": 1, "widget_type": "text", "rect": [480, 40 + 60 * b, 540, 54 + 60 * b]}}
             for b in (1, 2, 3)}
    extra["lone_txt"] = {"type": "string", "x_petey_id": "1_90",                               # only by the first block
                         "widget": {"page": 1, "widget_type": "text", "rect": [300, 120, 380, 130]}}
    bp = blueprint(rows, extra)
    for b in range(3):
        bt.draw("t0", bp, 1, area(b))
    rec = gc.load_set("t0")
    rec["types"][0].setdefault("parts", {})["1_1"] = {"prefix": "kid", "iteration": "1"}
    gc._save_set("t0", rec)
    out = bt.rescan("t0", bp, 1)
    assert out["grew"] == {"BT1": ["child_1_ssn"]}
    t = gc.load_set("t0")["types"][0]
    names = bt._names(bp)
    assert [[names[c] for c in b] for b in t["blocks"]] == [r + [f"child_{b}_ssn"] for b, r in zip((1, 2, 3), rows)]
    assert t["parts"] == {"1_1": {"prefix": "kid", "iteration": "1"}}


def test_a_grid_split_between_blocks_is_set_aside_unless_regular(monkeypatch, tmp_path):
    """Andrew, 2026-10-22: "grids that are split between blocks are probably not correct, unless they are very
    uniformly shaped" ("both rows and columns can be inconsistently sized"): set aside when another field sits inside
    it (VA 21P-534EZ p13: SSN boxes lined up through the children's blocks), the blocks kept; restored by hand, it
    stays. A grid that stays supersedes the blocks inside it (2026-10-23: "form_1095_b_check_p3-G2 should supersede
    the blocks, we don't need both!")."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)]
    bp = blueprint(rows)
    for b in range(3):
        bt.draw("t0", bp, 1, area(b))
    g = [{"name": n, "page": 1, "row": r, "col": c} for r, row in enumerate(rows) for c, n in enumerate(row)]
    bp["fields"]["child_3_nm"]["widget"]["rect"][3] += 6                      # sizes may differ
    assert gc.uniform(bp, g)
    bp["fields"]["note_txt"] = {"type": "string", "x_petey_id": "1_77",       # another field inside the grid
                                "widget": {"page": 1, "widget_type": "text", "rect": [260, 140, 300, 150]}}
    assert not gc.uniform(bp, g)
    split = [t for t in gc.listing("t0", bp) if t["status"] == "split"]
    assert split and "BT1-1" in split[0]["aside_why"]
    assert len(gc.load_set("t0")["types"][0]["blocks"]) == 3                 # set aside: the blocks stay
    gc.set_status("t0", split[0]["id"], False)                                # restored: a grid after all
    assert next(t for t in gc.listing("t0", bp) if t["id"] == split[0]["id"])["status"] == "active"
    rec = gc.load_set("t0")
    assert not rec["types"] and rec["grids"][0]["supersedes"] == ["BT1-1", "BT1-2", "BT1-3"]


def test_a_regular_grid_supersedes_the_blocks_inside_it_and_run_finders_leaves_them(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)]
    bp = blueprint(rows)
    for b in range(3):
        bt.draw("t1", bp, 1, area(b))
    assert [t["status"] for t in gc.listing("t1", bp)] == ["active"]
    assert not gc.load_set("t1")["types"]
    out = bt.discover("t1", bp)
    assert out["types"] == [] and out["grids"] == ["p1-G1"]                 # SIA does not rebuild them


def test_an_empty_prefix_is_an_error_only_when_the_prefix_tells_the_block_apart(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "only raise an error when the prefix field is empty if prefix is selected"."""
    import pytest
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2)])
    bt.draw("t5", bp, 1, area(0))
    bt.draw("t5", bp, 1, area(1))
    assert bt.set_parts("t5", "1_1", "", "1", "number")["prefix"] == ""
    (t,) = gc.load_set("t5")["types"]
    assert bt.check_block(bp, t, t["blocks"][0])["start"] == "1"
    with pytest.raises(ValueError, match="needs one"):
        bt.set_parts("t5", "1_1", "", None, "prefix")
    with pytest.raises(ValueError, match="lower case"):
        bt.set_parts("t5", "1_1", "Child One", None, "number")


def test_a_new_prefix_takes_the_next_number_free(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "updating the prefix doesn't automatically populate the iteration". Block 3 (child_3)
    given the prefix spouse, its iteration left empty: spouse 1, not the 3 its names carried."""
    use_tmp_records(monkeypatch, tmp_path)
    bp = blueprint([[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)])
    for b in range(3):
        bt.draw("t6", bp, 1, area(b))
    bt.set_parts("t6", "1_7", "spouse", "", "number")
    (t,) = gc.load_set("t6")["types"]
    parts = bt.block_parts(bp, t)
    assert parts["1_7"]["prefix"] == "spouse" and parts["1_7"]["iteration"] is None     # alone: no number
    assert parts["1_1"]["iteration"] == "1" and parts["1_4"]["iteration"] == "2"


def test_no_field_is_in_two_blocks_the_larger_keeps_it(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "make sure no field can be in two blocks. larger blocks get precedence"."""
    use_tmp_records(monkeypatch, tmp_path)
    rec = {"types": [{"id": "BT1", "boxes": [{}] * 4, "blocks": [["1_1", "1_2", "1_3", "1_4"]]},
                     {"id": "BT2", "boxes": [{}] * 2, "blocks": [["1_3", "1_9"], ["1_4", "1_2"]],
                      "parts": {"1_3": {"prefix": "x"}}}]}
    gc._save_set("t7", rec)
    got = gc.load_set("t7")
    assert got["types"][0]["blocks"] == [["1_1", "1_2", "1_3", "1_4"]]
    assert got["types"][1]["blocks"] == [[None, "1_9"]]                 # the block left with nothing went
    assert got["types"][1]["parts"] == {"1_9": {"prefix": "x"}}         # its settings follow its new first box


def test_grouping_fields_keeps_them_in_their_block(monkeypatch, tmp_path):
    """Andrew (2026-10-22): "groups should act independently from the block logic ... creating a group shouldn't pull
    those fields out of the block". Block 2's two checkboxes grouped into a new field (a new id): its positions point
    at the group, and the block does not rename it."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind", f"child_{b}_other_ind"] for b in (1, 2)]
    bp = blueprint(rows)
    for b, row in enumerate(rows):                           # a second checkbox beside each block's first
        y = 100 + 60 * b
        bp["fields"][row[3]]["widget"] = {"page": 1, "widget_type": "checkbox", "rect": [470, y, 480, y + 14]}
    bt.draw("t8", bp, 1, [45, 95, 490, 118])
    bt.draw("t8", bp, 1, [45, 155, 490, 178])
    (t,) = gc.load_set("t8")["types"]
    assert t["blocks"][1] == ["1_5", "1_6", "1_7", "1_8"]
    w1 = bp["fields"].pop("child_2_ind")["widget"]
    w2 = bp["fields"].pop("child_2_other_ind")["widget"]
    bp["fields"]["child_2_status"] = {"type": "category", "x_petey_id": "1_9", "widgets": {"a": w1, "b": w2}}
    assert bt.reattach("t8", bp) == {"moved": 2, "left": 0, "merged": 0}      # only block 2 grouped: no merge
    (t,) = gc.load_set("t8")["types"]
    assert t["blocks"][1] == ["1_5", "1_6", "1_9", "1_9"]
    assert all(d["name"] != "child_2_status" for d in bt.check_block(bp, t, t["blocks"][1])["differs"])


def test_a_group_in_every_block_becomes_one_position(monkeypatch, tmp_path):
    """Andrew (2026-10-23): "field names persist from group to block and v/v". Both blocks' two checkboxes grouped:
    the type's two positions become one, the group's; the block names the group like any field."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind", f"child_{b}_other_ind"] for b in (1, 2)]
    bp = blueprint(rows)
    for b, row in enumerate(rows):
        y = 100 + 60 * b
        bp["fields"][row[3]]["widget"] = {"page": 1, "widget_type": "checkbox", "rect": [470, y, 480, y + 14]}
    bt.draw("t9", bp, 1, [45, 95, 490, 118])
    bt.draw("t9", bp, 1, [45, 155, 490, 178])
    for b, code in ((1, "1_9"), (2, "1_10")):
        w1 = bp["fields"].pop(f"child_{b}_ind")["widget"]
        w2 = bp["fields"].pop(f"child_{b}_other_ind")["widget"]
        bp["fields"][f"child_{b}_status"] = {"type": "category", "x_petey_id": code, "widgets": {"a": w1, "b": w2}}
    assert bt.reattach("t9", bp) == {"moved": 4, "left": 0, "merged": 1}
    (t,) = gc.load_set("t9")["types"]
    assert len(t["boxes"]) == 3 and t["boxes"][2]["kind"] == "checkboxx2"
    assert t["blocks"] == [["1_1", "1_2", "1_9"], ["1_5", "1_6", "1_10"]]
    assert bt.wordings(bp, t)[2] == "status"
    bp["fields"]["child_2_state"] = bp["fields"].pop("child_2_status")      # renamed in Groups: the block sees it
    assert [(d["name"], d["want"]) for d in bt.check_block(bp, t, t["blocks"][1])["differs"]] == [("child_2_state", "child_2_status")]


def test_a_grid_row_is_relabeled_in_each_of_its_cells(monkeypatch, tmp_path):
    """Andrew (2026-10-23): "can we add the ability to edit grid labels ... from the grid page": a row's number (or
    label) put to what was typed in each of its cells' names; a name another field holds is left."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2, 3)]
    bp = blueprint(rows, {"child_7_ind": {"type": "boolean", "widget": {"page": 2, "widget_type": "checkbox",
                                                                      "rect": [0, 0, 10, 10]}}})
    monkeypatch.setattr(gc.h, "working_path", lambda bid, *a: tmp_path / "x.bpt")
    monkeypatch.setattr(gc.h, "_load", lambda p: bp)
    (g,) = [t for t in gc.listing("t2", bp) if t["status"] == "active"]
    got = []
    out = gc.relabel_line("t2", g["id"], 2, "7", apply=lambda edits: got.extend(edits) or {"changes": edits})
    assert {e["field"]: e["edit"]["name"] for e in got} == {"child_2_nm": "child_7_nm", "child_2_birth_dt": "child_7_birth_dt"}
    assert out["left"] == ["child_2_ind: child_7_ind is already another field's name"]


def test_run_finders_is_primed_by_a_block_drawn_and_a_grid_inside_blocks_gives_way(monkeypatch, tmp_path):
    """Andrew (2026-10-23, B 106D check): "priming 'run finders' with the existing blocks, so that creating one
    iteration of the intended block will push it to find other ones like it"; p2-G2, three claims' city / state /
    zip read as a grid, gives way to the claims' blocks ("we want 3 blocks that fill each row")."""
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"claim_{b}_nm", f"claim_{b}_dt", f"claim_{b}_ind"] for b in (1, 2, 3)]
    extra = {}
    for b in range(3):                       # each claim's city / state / zip line, 30 pt under its first line
        for k, part in enumerate(("city", "state", "zip")):
            extra[f"claim_{b + 1}_{part}"] = {"type": "string", "x_petey_id": f"1_{50 + 3 * b + k}",
                                              "widget": {"page": 1, "widget_type": "text",
                                                         "rect": [50 + 70 * k, 130 + 60 * b, 110 + 70 * k, 144 + 60 * b]}}
    bp = blueprint(rows, extra)
    bt.draw("t3", bp, 1, [45, 95, 470, 148])                   # one claim drawn, with its address line
    out = bt.discover("t3", bp)
    (t,) = gc.load_set("t3")["types"]
    assert len(t["blocks"]) == 3 and all(len([c for c in b if c]) == 6 for b in t["blocks"])
    assert out["primed"]["found"] == {"BT1": [2, 3]} or sum(len(v) for v in out["primed"]["found"].values()) == 2
    g = [x for x in gc.listing("t3", bp) if x["source"] == "finder"]
    assert g and all(x["status"] != "active" for x in g)                  # the city / state / zip grid gives way


def test_fill_blocks_puts_the_field_at_an_empty_position(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2)]
    bp = blueprint(rows)
    bt.draw("t4", bp, 1, area(0))
    bt.draw("t4", bp, 1, area(1))
    rec = gc.load_set("t4")
    rec["types"][0]["blocks"][1][1] = None                    # the second block lost its date
    assert bt.fill_blocks(bp, rec) == {"BT1-2": ["child_2_birth_dt"]}
