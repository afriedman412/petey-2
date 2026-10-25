"""Grids are named on one pattern (eval/grid_naming.py, 2026-10-15): tables found by layout, each column one
wording, each row one number (or the transpose)."""
import grid_naming as G


def blueprint(name_of, rows=4, cols=("vehicle_make", "vehicle_year", "vehicle_vin")):
    fields = {}
    for r in range(rows):
        for c, col in enumerate(cols):
            fields[name_of(r, c, col)] = {"type": "string", "widget": {
                "page": 1, "widget_type": "text", "rect": [50 + c * 120, 100 + r * 20, 160 + c * 120, 116 + r * 20]}}
    return {"fields": fields}


def test_a_table_is_found_by_layout():
    gs = G.grids(blueprint(lambda r, c, col: f"{col}_{r + 1}_txt"))
    assert len(gs) == 1 and G.iterated(gs[0]) and len(gs[0]) == 12


def test_on_pattern():
    g = G.grids(blueprint(lambda r, c, col: f"{col}_{r + 1}_txt"))[0]
    assert G.on_pattern(g) == (True, "columns")


def test_a_cell_off_its_column_breaks_the_pattern():
    off = lambda r, c, col: "model_year_9_txt" if (r, c) == (3, 1) else f"{col}_{r + 1}_txt"   # noqa: E731
    ok, why = G.on_pattern(G.grids(blueprint(off))[0])
    assert not ok and "model_year_N_txt" in why


def test_simple_scheme_names_are_on_pattern_too():
    g = G.grids(blueprint(lambda r, c, col: f"{col}_{r + 1}"))[0]
    assert G.on_pattern(g)[0]


def test_one_row_of_boxes_out_of_order_is_renumbered_by_position():
    """UK MR01 p1 (2026-10-20): the company number's eight boxes named company_3_nbr, company_5_nbr, ... left to right.
    One row of one wording is one position numbered across; the resolver renumbers it in code, swaps included."""
    order = [3, 5, 6, 1, 4, 7, 8, 2]
    bp = {"fields": {f"company_{n}_nbr": {"type": "string", "widget": {
        "page": 1, "widget_type": "text", "rect": [50 + i * 20, 100, 66 + i * 20, 116]}} for i, n in enumerate(order)}}
    g = [{"name": f"company_{n}_nbr", "page": 1, "row": 0, "col": i} for i, n in enumerate(order)]
    assert G.breaks(g)[0] == "rows"
    r = G.resolve(bp, g, {})
    assert r["status"] == "fixed"
    assert r["renames"] == {f"company_{n}_nbr": f"company_{i + 1}_nbr" for i, n in enumerate(order) if n != i + 1}


def test_a_swap_in_one_row_is_renumbered_too():
    order = [1, 3, 2, 4]
    bp = {"fields": {f"char_{n}_txt": {"type": "string", "widget": {
        "page": 1, "widget_type": "text", "rect": [50 + i * 20, 100, 66 + i * 20, 116]}} for i, n in enumerate(order)}}
    g = [{"name": f"char_{n}_txt", "page": 1, "row": 0, "col": i} for i, n in enumerate(order)]
    assert G.resolve(bp, g, {})["renames"] == {"char_3_txt": "char_2_txt", "char_2_txt": "char_3_txt"}


def test_a_number_the_same_along_a_line_is_wording():
    """1065-X Part II (2026-10-20): columns (a) (b) (c), lines by the form's wording; line 10 is
    col_a_net_section_1231_gain_loss_amt, col_b_..., col_c_...: the letter changes along the line, 1231 does not."""
    lines = ["ordinary_business_income_loss", "net_section_1231_gain_loss", "collectibles_28_gain_loss", "royalties"]
    g = [{"name": f"col_{l}_{w}_amt", "page": 2, "row": r, "col": c}
         for r, w in enumerate(lines) for c, l in enumerate("abc")]
    assert G.on_pattern(g) == (True, "rows")


def test_a_table_labelled_with_the_column_first_is_on_pattern():
    """GSE 1076 p3 (2026-10-20): unit counts down the side, entire project / subject legal phase across, named
    [column]_[line]_cnt."""
    kinds = ["total_units", "units_sold_and_closed", "investor_units", "hoa_owned_units"]
    g = [{"name": f"{col}_{k}_cnt", "page": 3, "row": r, "col": c}
         for r, k in enumerate(kinds) for c, col in enumerate(["entire_project", "subject_legal_phase"])]
    assert G.on_pattern(g) == (True, "columns named by role or kind")
    assert G.resolve({"fields": {c["name"]: {} for c in g}}, g, {})["status"] == "ok"


def test_labelled_rows_with_a_numbered_run_are_on_pattern():
    """IRS 433-F p2-T4 (2026-10-21): expense rows named by their printed labels, three blank "Other" rows numbered
    1-3 and a totals row; ACORD 125's first_named_insured beside other_named_insured_1, _2; VA 21P-534EZ's item
    letters. A run that does not count from 1, or every row numbered (the number check's), is not labelled."""
    def grid(keys, cols=("actual", "irs_allowed")):
        return [{"name": f"{k}_{col}_amt", "page": 2, "row": r, "col": c}
                for r, k in enumerate(keys) for c, col in enumerate(cols)]
    labels = ["health_insurance", "union_dues", "student_loans"]
    assert G.on_pattern(grid(labels + ["other_expenses_1", "other_expenses_2", "other_expenses_3", "other_total"])) \
        == (True, "rows named by role or kind")
    assert G.keyed(grid(["first_named_insured", "other_named_insured_1", "other_named_insured_2"]))
    assert G.keyed(grid(["veteran", "care_10c", "care_10d"]))
    assert not G.keyed(grid(labels + ["other_expenses_2", "other_expenses_3"]))
    assert not G.keyed(grid([f"other_expenses_{i}" for i in range(1, 4)]))


def test_a_labelled_table_needs_one_wording_per_column():
    """I-730 p5-T1 (2026-10-21): prior_spouse_1_middle_2_nm beside prior_spouse_2_middle_nm shares only its last word
    with its column. Still a table to the finder (loose), off pattern to the naming check (strict)."""
    g = [{"name": n, "page": 5, "row": r, "col": c} for r, row in enumerate([
        ["prior_spouse_1_last_nm", "prior_spouse_1_first_nm", "prior_spouse_1_middle_2_nm"],
        ["prior_spouse_2_last_nm", "prior_spouse_2_first_nm", "prior_spouse_2_middle_nm"],
        ["beneficiary_last_nm", "beneficiary_first_nm", "beneficiary_middle_nm"]]) for c, n in enumerate(row)]
    assert G.keyed(g) and not G.keyed(g, strict=True) and not G.on_pattern(g)[0]


# standardize (the Grids card's buttons, reworked 2026-10-22: "it often doesn't work and never says why clearly")

def _grid(names_by_row, page=1):
    """A blueprint and its grid: rows of cells, each row's names left to right."""
    fields, g = {}, []
    for r, row in enumerate(names_by_row):
        for c, n in enumerate(row):
            fields[n] = {"type": "string", "widget": {"page": page, "widget_type": "text",
                                                      "rect": [50 + c * 120, 100 + r * 20, 160 + c * 120, 116 + r * 20]}}
            g.append({"name": n, "page": page, "row": r, "col": c})
    return {"fields": fields}, g


def test_a_shifted_row_takes_the_row_holding_its_name_along():
    """ACORD 126 p1-T1: the premium columns numbered one ahead (rows 1-3 carry 2-4); renumbering row 2 alone ran onto
    row 3's names and did nothing. The cells holding the names are renamed with it."""
    bp, g = _grid([[f"make_{r}_txt", f"premium_{r + 1}_amt"] for r in (1, 2, 3)])
    r = G.standardize(bp, g, {}, lines_=[1])
    assert r["renames"]["premium_3_amt"] == "premium_2_amt"
    assert r["renames"]["premium_2_amt"] == "premium_1_amt" and "premium_2_amt" in r["pulled"]
    assert not r["left"]


def test_a_rename_onto_a_field_outside_the_grid_says_where_it_is():
    bp, g = _grid([[f"make_{r}_txt", f"premium_{r + 1}_amt"] for r in (1, 2, 3)])
    bp["fields"]["premium_1_amt"] = {"type": "string", "widget": {"page": 2, "widget_type": "text", "rect": [0, 0, 9, 9]}}
    r = G.standardize(bp, g, {}, positions=[1])
    assert any("a field outside this grid, p2" in x for x in r["left"])


def test_an_even_split_asks_for_a_pick_and_the_pick_is_used():
    bp, g = _grid([["guns_1_amt", "note_1_txt"], ["silver_2_amt", "note_2_txt"]])
    r = G.standardize(bp, g, {}, positions=[0])
    assert not r["renames"] and "pick one" in r["left"][0]
    r = G.standardize(bp, g, {}, positions=[0], forced={0: "valuables_N_amt"})
    assert r["renames"] == {"guns_1_amt": "valuables_1_amt", "silver_2_amt": "valuables_2_amt"}


def test_lettered_rows_take_the_letter_most_of_the_row_has():
    """ACORD 24 p1-T2: a lettered grid whose row d has one cell numbered 1; renumbering the row did nothing."""
    bp, g = _grid([[f"line_{x}_txt", f"amount_{x}_amt", f"note_{x}_txt"] for x in "abc"]
                  + [["line_d_txt", "amount_1_amt", "note_d_txt"]])
    r = G.standardize(bp, g, {}, lines_=[3])
    assert r["renames"] == {"amount_1_amt": "amount_d_amt"}


def test_the_off_count_and_the_button_agree_on_a_continued_series():
    """ACORD 90 NY p1-T15 (2026-10-22): vehicles 3-4, continuing vehicles 1-2 in another grid, were counted off their
    rows (as if from 1) while the button kept them: both read the series from the same basis now."""
    bp, g = _grid([[f"vehicle_{n}_make_txt", f"vehicle_{n}_year_txt"] for n in (3, 4)])
    for n in (1, 2):
        bp["fields"][f"vehicle_{n}_make_txt"] = {"type": "string"}
    F = G._Frame(g)
    assert F.numbers(bp, g, {}, F.basis())[0] == {0: 3, 1: 4}
    assert G.standardize(bp, g, {})["renames"] == {}


def test_halves_side_by_side_read_as_one():
    """ACORD 140's blanket list (Andrew, 2026-10-24: "this needs a systematic fix because it's not a unique
    situation"): blankets 1-2 on the left, 3-4 on the right, read as four rows, on pattern as named."""
    import grid_naming as G
    words = ["blanket_{}_nbr", "blanket_{}_amt", "blanket_type_{}_txt"]
    grid = [{"name": w.format(r + 1 + 2 * half), "page": 1, "row": r, "col": 3 * half + k}
            for half in range(2) for r in range(2) for k, w in enumerate(words)]
    flat = G.unfold(grid)
    assert sorted((c["row"], c["col"], c["name"]) for c in flat)[:4] == [
        (0, 0, "blanket_1_nbr"), (0, 1, "blanket_1_amt"), (0, 2, "blanket_type_1_txt"), (1, 0, "blanket_2_nbr")]
    assert {c["name"]: c["row"] for c in flat}["blanket_4_nbr"] == 3
    assert G.on_pattern(grid)[0] and "halves" in G.on_pattern(grid)[1]
    assert G.unfold([dict(c, col=c["col"] % 3) for c in grid if c["col"] < 3]) is None      # one half: nothing to do


def test_a_grid_continuing_an_earlier_pages_series_numbers_on_from_it():
    """ACORD 140 p2-G2 (Andrew, 2026-10-24): subjects of insurance 6-10 under page 1's 1-5; one column ran 6-10, the
    rest 1-5. The rows are 6-10: the others are renumbered."""
    bp, g = _grid([[f"item_{r}_txt", f"item_{r + 5}_amt"] for r in (1, 2, 3)])
    for c in g:
        bp["fields"][c["name"]]["widget"]["page"] = 2
        c["page"] = 2
    for r in range(1, 6):
        bp["fields"][f"item_{r}_amt"] = {"type": "string", "widget": {"page": 1, "widget_type": "text", "rect": [0, 9 * r, 9, 9 * r + 9]}}
    r = G.standardize(bp, g, {})
    assert r["renames"] == {"item_1_txt": "item_6_txt", "item_2_txt": "item_7_txt", "item_3_txt": "item_8_txt"}


def test_one_list_across_pages_is_numbered_on_with_one_wording(monkeypatch, tmp_path):
    """CBP 7501 (Andrew, 2026-10-24: "if its the same data with the same labels they should continue automatically!"):
    page 1's lines under mixed names, page 2's under one wording each numbered 2-4, the same printed headings."""
    from petey.validate import grid_check as gc
    monkeypatch.setattr(gc, "SETS", tmp_path)
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / f"{bid}.json")
    f = {}
    def box(n, page, x, y):
        f[n] = {"type": "string", "widget": {"page": page, "widget_type": "text", "rect": [x, y, x + 60, y + 12]}}
    for r, (a, b) in enumerate([("line_no", "amount_dollars_amt"), ("line_no_row2", "amt_row2_cents")]):
        box(a, 1, 50, 200 + 30 * r); box(b, 1, 200, 200 + 30 * r)
    for r in range(3):
        box(f"line_no_{r + 2}", 2, 50, 200 + 30 * r); box(f"line_amt_{r + 2}", 2, 200, 200 + 30 * r)
    bp = {"fields": f}
    monkeypatch.setattr(G, "position_caption", lambda bp, cells, how, lines: "No." if cells[0]["col"] == 0 else "Amount")
    g1 = [{"name": n, "page": 1, "row": r, "col": c} for r, row in enumerate([["line_no", "amount_dollars_amt"], ["line_no_row2", "amt_row2_cents"]]) for c, n in enumerate(row)]
    g2 = [{"name": n, "page": 2, "row": r, "col": c} for r in range(3) for c, n in enumerate([f"line_no_{r + 2}", f"line_amt_{r + 2}"])]
    monkeypatch.setattr(gc, "listing", lambda bid, bp: [{"id": "p1-G1", "status": "active", "grid": g1},
                                                       {"id": "p2-G1", "status": "active", "grid": g2}])
    monkeypatch.setattr(gc, "grid_title", lambda bp, g, lines: "OWNERS" if g[0]["page"] == 1 else "MANAGERS")
    assert gc.series("t", bp, "p1-G1", g1, {}) is None       # same headings, other subjects: not one list (Andrew:
                                                              # "the same data about different subjects")
    monkeypatch.setattr(gc, "grid_title", lambda bp, g, lines: "LINE ITEMS" if g[0]["page"] == 1 else "CONTINUATION SHEET")
    se = gc.series("t", bp, "p1-G1", g1, {})
    assert se["start"] == 1 and se["parts"] == ["p1-G1", "p2-G1"] and se["wordings"] == {0: "line_no_N", 1: "line_amt_N"}
    r = gc.series_renames("t", bp, se, {})
    assert r["left"] == [] and r["renames"] == {
        "line_no": "line_no_1", "amount_dollars_amt": "line_amt_1", "line_no_row2": "line_no_2", "amt_row2_cents": "line_amt_2",
        "line_no_2": "line_no_3", "line_amt_2": "line_amt_3", "line_no_3": "line_no_4", "line_amt_3": "line_amt_4",
        "line_no_4": "line_no_5", "line_amt_4": "line_amt_5"}


def test_grids_with_the_same_headings_under_other_titles_keep_apart(monkeypatch):
    """Andrew (2026-10-24): "grids that aren't connected that have the same labels are likely to carry the same data
    about different subjects, so their labels shouldn't clash": the second grid, numbered on to dodge the first's
    names, takes its own title as its subject."""
    from petey.validate import grid_check as gc
    bp, g = _grid([[f"name_{r + 3}_nm", f"phone_{r}_nbr"] for r in (1, 2, 3)])      # names numbered on to dodge
    for r in (1, 2, 3):                                  # the first grid's names, on another page
        for w in ("name_{}_nm", "phone_{}_nbr"):
            bp["fields"][w.format(r)] = {"type": "string", "widget": {"page": 2, "widget_type": "text", "rect": [0, 9 * r, 9, 9 * r + 9]}}
    monkeypatch.setattr(gc, "grid_title", lambda bp, g, lines: "PART III - MANAGERS")
    alts = gc.row_subject_wordings(bp, g, {}, None)
    assert alts == {0: "managers_name_N_nm"}


def test_lines_of_two_printed_rows_read_as_one():
    """CMS-1500 p1-G8 (Andrew, 2026-10-25: "manually selecting a wording doesn't override 'no majority'"): each
    service line's shaded strip above it; one column held supplemental info and charges in turn."""
    rows = []
    for n in (1, 2, 3):
        rows.append([f"service_line_{n}_supplemental_info_txt", f"service_line_{n}_epsdt_cd"])
        rows.append([f"service_line_{n}_charges_amt", f"service_line_{n}_family_plan_cd"])
    bp, g = _grid(rows)
    assert not G._on_pattern(g)[0]
    folded = G.fold_rows(g)
    assert len({c["row"] for c in folded}) == 3 and len({c["col"] for c in folded}) == 4
    assert G.on_pattern(g) == (True, "lines of two rows read as one (columns)")
