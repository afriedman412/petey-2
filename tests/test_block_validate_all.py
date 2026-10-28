"""The block type's "validate all" (blueprint_review.Blocks.type_validate): each block asked for by its first box that
is there (lib__i864 BT1-2, lib__i9 BT4-2, 2026-10-27: a block whose first position is empty raised "no such block
(drawn again since?)")."""
from types import SimpleNamespace

from petey.validate import block_types, blueprint_review as br, grid_check, hand_review


def test_validate_all_names_a_block_by_its_first_box_there(monkeypatch):
    rec = {"types": [{"id": "BT1", "blocks": [["1_1", "1_2"], [None, "1_4"]]}]}
    monkeypatch.setattr(grid_check, "load_set", lambda bid: rec)
    monkeypatch.setattr(hand_review, "_load", lambda p: {"fields": {}})
    monkeypatch.setattr(hand_review, "load_verdicts", lambda bid: {})
    asked = []

    def validate_block(bid, bp, code):
        asked.append(code)
        return {"ok": True, "names": [], "differs": []}
    monkeypatch.setattr(block_types, "validate_block", validate_block)
    app = SimpleNamespace(working=lambda bid: "x.bpt", put_verdicts=lambda *a: None, refresh=lambda: None,
                          entry=lambda bid: None)
    out = br.Blocks(app).type_validate("f", "BT1")
    assert asked == ["1_1", "1_4"] and out["validated"] == ["BT1-1", "BT1-2"]
