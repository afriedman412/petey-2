"""Structure before labeling (petey/label/structure.py, 2026-10-19): tables and block groups found on the raw
widgets, and labeler batches cut at their edges. Form 8825: a properties table and a line-item ledger per page."""
import pytest

from petey.label import structure as S
from petey.label.auto_label import enumerate_geometry


@pytest.fixture(scope="module")
def form(request):
    from tests.conftest import F8825
    widgets, _, how = enumerate_geometry(F8825, "auto")
    return widgets, S.find(F8825, widgets), how


def test_geometry_is_the_form_layer(form):
    widgets, _, how = form
    assert how == "acroform" and len(widgets) == 221


def test_tables_found_per_page(form):
    _, st, _ = form
    shapes = {p: sorted((t["rows"], t["cols"]) for t in st[p]["tables"]) for p in (1, 2)}
    assert shapes == {1: [(4, 5), (20, 4)], 2: [(4, 6), (21, 4)]}
    assert all(not st[p]["blocks"] for p in (1, 2))


def test_a_table_that_fits_stays_in_one_batch(form):
    widgets, st, _ = form
    page1 = [w for w in widgets if w["page"] == 1]
    small = next(t for t in st[1]["tables"] if len(t["cells"]) <= 60)
    ids = {c["id"] for c in small["cells"]}
    holding = [b for b in S.batches(page1, st[1], 60) if ids & {w["id"] for w in b}]
    assert len(holding) == 1


def test_batches_cover_every_widget_once(form):
    widgets, st, _ = form
    page1 = [w for w in widgets if w["page"] == 1]
    got = [w["id"] for b in S.batches(page1, st[1], 60) for w in b]
    assert sorted(got) == sorted(w["id"] for w in page1)


def _rows(n_rows, n_cols, page=1, x0=50, y0=100, step=20, start=1):
    """Widgets in a grid of rows, ids from `start`, and the grid finder's cells for them."""
    entries, cells = [], []
    for r in range(n_rows):
        for c in range(n_cols):
            i = start + r * n_cols + c
            entries.append({"id": i, "page": page, "rect": [x0 + c * 40, y0 + r * step, x0 + c * 40 + 30, y0 + r * step + 12],
                            "widget_type": "text", "path": f"f{i}"})
            cells.append({"name": f"w{i}", "page": page, "row": r, "col": c})
    return entries, cells


def _finders(monkeypatch, grids, blocks):
    import grid_naming
    monkeypatch.setattr(grid_naming, "grids", lambda bp, blocks=False: [list(g) for g in grids])
    monkeypatch.setattr(S, "_blocks", lambda bp: [list(b) for b in blocks])


def test_a_grid_wins_over_the_blocks_inside_it(monkeypatch, tmp_path):
    """1095-B p3 (2026-10-23): SIA read twelve rows as two copies of six; the rows go to the labeler as one grid."""
    entries, cells = _rows(12, 6)
    halves = [dict(c, row=c["row"] // 6, col=(c["row"] % 6) * 6 + c["col"], block=True) for c in cells]
    _finders(monkeypatch, [cells], [halves])
    st = S.find(tmp_path / "x.pdf", entries)
    assert [(t["rows"], t["cols"]) for t in st[1]["tables"]] == [(12, 6)] and st[1]["blocks"] == []


def test_a_set_aside_grid_leaves_the_block(monkeypatch, tmp_path):
    """A grid whose outline holds as many other fields as its cells is not handed over; the block there is."""
    entries, cells = _rows(3, 3, step=40)
    between = _rows(2, 3, y0=115, step=40, start=100)[0] + _rows(2, 3, y0=125, step=40, start=110)[0]   # 12 inside
    block = [dict(c, row=c["row"], col=c["col"], block=True) for c in cells]
    _finders(monkeypatch, [cells], [block])
    st = S.find(tmp_path / "x.pdf", entries + between)
    assert st[1]["tables"] == [] and len(st[1]["blocks"]) == 1


def test_a_grid_half_inside_a_larger_block_leaves_it_to_the_block(monkeypatch, tmp_path):
    """The block holds half the grid but is mostly outside it: the block wins, as before SIA's grids rule."""
    entries, cells = _rows(4, 4)
    more, _ = _rows(3, 4, y0=300, start=200)
    block = ([dict(c, row=0, col=k, block=True) for k, c in enumerate(cells[:4])]
             + [dict(c, row=1, col=k, block=True) for k, c in enumerate(cells[4:8])]
             + [dict(name=f"w{200 + k}", page=1, row=2 + k // 4, col=k % 4, block=True) for k in range(12)])
    _finders(monkeypatch, [cells], [block])
    st = S.find(tmp_path / "x.pdf", entries + more)
    assert st[1]["tables"] == [] and len(st[1]["blocks"]) == 1


def test_option_groups_named_alike_in_block_copies_are_numbered_not_dropped():
    """B 106D (2026-10-23): "who owes the debt" in every claim, named alike; each copy keeps its options."""
    from petey.label.auto_label import _number_copies
    w = lambda y: {"page": 1, "rect": [0, y, 10, y + 10]}                          # noqa: E731
    got = _number_copies({("who_owes_debt", (2, "B1", 1)): {"debtor_1": w(1)},
                          ("who_owes_debt", (1, "B1", 0)): {"debtor_1": w(2)},
                          ("who_owes_debt", (2, "B1", 0)): {"debtor_1": w(3)},
                          ("void", None): {"yes": w(4)}, ("lien", (1, "B1", 0)): {"other": w(5)}})
    assert {k: v["debtor_1"]["rect"][1] for k, v in got.items() if k.startswith("who")} == \
        {"who_owes_debt_1": 2, "who_owes_debt_2": 3, "who_owes_debt_3": 1}
    assert "void" in got and "lien" in got                 # alone: no number


def test_print_cells_says_why_it_left_fields():
    """2026-10-23: 180 of 1095-B's fields went back one by one and nothing said why."""
    st = {"tables": [], "blocks": [{"id": "B1", "cells": [{"id": i, "block": i // 2, "slot": i % 2} for i in range(4)]},
                                   {"id": "B2", "cells": [{"id": 10 + i, "block": i // 2, "slot": i % 2} for i in range(4)]}]}
    parsed = {"blocks": [{"id": "B2", "entity": "child", "fields": [{"slot": 1, "label": "name"}]}]}
    why: dict = {}
    _, _, left = S.print_cells(st, parsed, set(range(4)) | set(range(10, 14)), why)
    assert sorted(left) == [0, 1, 2, 3, 11, 13]
    assert dict(why["B1"]) == {"no answer": 4} and dict(why["B2"]) == {"position unlabeled": 2}
