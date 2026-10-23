"""What every tab of the review page draws besides its own (blueprint_review.overlay, Andrew 2026-10-22: "add block
and grid overlays and validated fields to all views, so it's clear what is and isn't already accounted for"), and
the Grids finder holding back grids that sit in a block type's blocks (in place of the block-group finder)."""
from petey.validate import block_types as bt, blueprint_review as br, grid_check as gc
from tests.test_block_types import area, blueprint, use_tmp_records


def test_the_overlay_has_accepted_fields_grids_and_blocks(monkeypatch, tmp_path):
    use_tmp_records(monkeypatch, tmp_path)
    rows = [[f"child_{b}_nm", f"child_{b}_birth_dt", f"child_{b}_ind"] for b in (1, 2)]
    bp = blueprint(rows)
    bt.draw("t0", bp, 1, area(0))
    bt.draw("t0", bp, 1, area(1))
    out = br.overlay(bp, "t0", {"child_1_nm": {"verdict": "accept"}, "child_2_nm": {"verdict": "flag"}})
    assert {f["name"] for f in out["fields"] if f["accepted"]} == {"child_1_nm"}
    assert [b["id"] for b in out["blocks"]] == ["BT1-1", "BT1-2"] and not any(b["validated"] for b in out["blocks"])
    assert out["blocks"][0]["bbox"][1] == 100
    # the two rows read as a grid by the finder: 2 x 3, small, set aside, so the blocks stay (an active grid over
    # them would supersede them: test_block_types)
    assert all(g["page"] == 1 for g in out["grids"])


def test_a_grid_inside_one_block_is_not_listed():
    from tests.test_grid_naming import blueprint as rows_of
    bp = rows_of(lambda r, c, col: f"{col}_{r + 1}_txt")
    grids = gc.found(bp)
    assert len(grids) == 1
    assert not gc.found(bp, [{c["name"] for c in grids[0]}])                 # all of it in one block
    assert gc.found(bp, [{grids[0][0]["name"]}])                             # one cell in a block: still a grid


def test_a_row_renumber_says_once_per_column_why_it_waits():
    """2026-10-22: a reason per cell (707 of them over the kept grids) said one thing per column."""
    import grid_naming as G
    from tests.test_grid_naming import _grid
    bp, g = _grid([["guns_1_amt", "note_1_txt"], ["silver_2_amt", "note_2_txt"], ["cash_3_amt", "note_5_txt"],
                   ["coin_4_amt", "note_4_txt"]])
    r = G.standardize(bp, g, {}, lines_=[0, 1, 2, 3])
    assert sum("position 1" in x for x in r["left"]) == 1
    assert r["renames"] == {"note_5_txt": "note_3_txt"}
