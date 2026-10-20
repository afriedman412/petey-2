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
