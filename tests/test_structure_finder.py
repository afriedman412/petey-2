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
