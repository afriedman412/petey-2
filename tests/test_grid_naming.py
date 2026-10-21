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


def test_a_drawn_block_group_with_an_uneven_last_gap_keeps_its_blocks():
    """I-526 p18 (2026-10-20): page / part / item on one line, additional information under it, five times; the fifth
    block sits 6 pt lower than the step. Each block is one row of four positions, not two rows."""
    from petey.validate.grid_check import arrange
    fields, names = {}, []
    for b, top in enumerate((204, 306, 408, 510, 618), start=1):
        for n, r in ((f"page_{b}_nbr", [78, top, 138, top + 18]), (f"part_{b}_nbr", [174, top, 234, top + 18]),
                     (f"item_{b}_nbr", [270, top, 330, top + 18]),
                     (f"additional_information_{b}_txt", [78, top + 24, 576, top + 78 - (0.00001 if b == 1 else 0)])):
            fields[n] = {"type": "string", "widget": {"page": 18, "widget_type": "text", "rect": r}}
            names.append(n)
    cells = arrange({"fields": fields}, names, "block")
    assert {(c["row"], c["col"]) for c in cells} == {(r, k) for r in range(5) for k in range(4)}
    assert all(c["row"] == int(c["name"].split("_")[-2]) - 1 for c in cells)


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


def test_item_lettered_blocks_with_different_box_heights():
    """N-600 p14 (2026-10-20): items 3-6, each page / part / item on one line and additional information under it,
    lettered a-d by the form (part_11_3a_page_nbr .. part_11_3d_additional_information_txt); the text box is 72 pt in
    two items and 90 in two, and overlaps the page, part and item columns alike. Four blocks of four, on pattern."""
    from petey.validate.grid_check import arrange
    fields, names = {}, []
    for b, (top, h) in enumerate(((210, 72), (330, 72), (450, 90), (588, 90)), start=3):
        for n, r in ((f"part_11_{b}a_page_nbr", [78, top, 138, top + 18]),
                     (f"part_11_{b}b_part_nbr", [168, top, 228, top + 18]),
                     (f"part_11_{b}c_item_nbr", [258, top, 318, top + 18]),
                     (f"part_11_{b}d_additional_information_txt", [78 - (0.001 if b % 2 else 0), top + 24, 576, top + 24 + h])):
            fields[n] = {"type": "string", "widget": {"page": 14, "widget_type": "text", "rect": r}}
            names.append(n)
    cells = arrange({"fields": fields}, names, "block")
    assert {(c["row"], c["col"]) for c in cells} == {(r, k) for r in range(4) for k in range(4)}
    assert G.on_pattern(cells)[0]


def test_a_table_labelled_with_the_column_first_is_on_pattern():
    """GSE 1076 p3 (2026-10-20): unit counts down the side, entire project / subject legal phase across, named
    [column]_[line]_cnt."""
    kinds = ["total_units", "units_sold_and_closed", "investor_units", "hoa_owned_units"]
    g = [{"name": f"{col}_{k}_cnt", "page": 3, "row": r, "col": c}
         for r, k in enumerate(kinds) for c, col in enumerate(["entire_project", "subject_legal_phase"])]
    assert G.on_pattern(g) == (True, "columns named by role or kind")
    assert G.resolve({"fields": {c["name"]: {} for c in g}}, g, {})["status"] == "ok"


def test_blocks_side_by_side():
    """CBP 7512 p2 (2026-10-20): two certificates of transfer side by side, each box of the second 225 pt right of
    its twin; two blocks of the same fields, not lines down the page."""
    from petey.validate.grid_check import arrange
    left = {"reason_txt": [100, 352, 233, 364], "to_nm": [36, 371, 234, 384], "dt": [34, 389, 146, 402],
            "at_txt": [169, 389, 234, 402], "sealed_with_txt": [87, 407, 196, 420], "seal_nbr": [44, 425, 189, 438]}
    fields = {}
    for b in (1, 2):
        for k, r in left.items():
            d = 225 * (b - 1) + (0.6 if b == 2 else 0)
            fields[f"transfer_{b}_{k}"] = {"type": "string", "widget": {
                "page": 2, "widget_type": "text", "rect": [r[0] + d, r[1] + 0.3, r[2] + d, r[3] + 0.3]}}
    cells = arrange({"fields": fields}, list(fields), "block")
    assert {c["row"] for c in cells} == {0, 1} and len({c["col"] for c in cells}) == 6
    assert all(c["name"].startswith(f"transfer_{c['row'] + 1}_") for c in cells)
    assert G.on_pattern(cells)[0]


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
