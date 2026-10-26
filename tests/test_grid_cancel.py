"""The cancel button on a grid check (petey/validate/blueprint_review.py, Andrew 2026-10-21: "can the cancel
button cancel the validation query"): nothing written after it, a call to Opus under way given up."""
import threading
import time
import types

import pytest

from petey.validate import blueprint_review as br, grid_check


def test_until_returns_the_answer():
    assert br.until(lambda: 7, lambda: False) == 7


def test_until_gives_up_a_call_under_way():
    flag = threading.Event()
    threading.Timer(0.2, flag.set).start()
    t0 = time.time()
    with pytest.raises(br.Cancelled):
        br.until(lambda: time.sleep(3), flag.is_set, every=0.05)
    assert time.time() - t0 < 1


def test_a_cancelled_check_writes_nothing_after_the_cancel(monkeypatch):
    wrote = []
    app = types.SimpleNamespace(refresh=lambda: None, entry=lambda bid: {}, accept_grid=lambda *a: wrote.append(a))
    tab = br.Grids(app)
    monkeypatch.setattr(br.Grids, "_apply", lambda self, bid: lambda edits: wrote.append(edits) or {"changes": edits})

    def slow_check(bid, tid, *, accept, apply, ask_opus):      # Jev for a while, then the renames
        time.sleep(0.4)
        apply([{"field": "a", "edit": {"name": "b"}}])
        accept(1, ["b"])
        return {"status": "fixed", "steps": []}
    monkeypatch.setattr(grid_check, "check", slow_check)
    threading.Timer(0.1, lambda: tab.cancel("je__x", "p1-T1")).start()
    out = tab.check("je__x", "p1-T1")
    assert out["status"] == "cancelled" and wrote == []
    assert not tab.running and not tab.stop


def test_cancel_with_no_check_under_way_leaves_no_flag():
    tab = br.Grids(types.SimpleNamespace())
    assert tab.cancel("je__x", "p1-T1") == {"cancelled": False} and not tab.stop


def test_small_finder_grids_are_set_aside_and_ids_say_grid(tmp_path, monkeypatch):
    """Andrew (2026-10-23): "i_829_check_p4-T1 is a frivolous grid" (3 x 2: two blocks side by side) and "we need to
    rename these G1 G2 etc because they are grids". Under 3 x 3 and under 12 cells: set aside, restorable; 3 x 3
    stays; ids are p1-G1."""
    from petey.validate import grid_check as gc
    monkeypatch.setattr(gc, "SETS", tmp_path)
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / f"{bid}.json")
    monkeypatch.setattr(gc, "not_grids", lambda bid: [])

    def lattice(rows, cols, y0):
        return {f"r{y0}_{r}_{c}": {"type": "string", "x_petey_id": f"1_{y0}{r}{c}",
                                   "widget": {"page": 1, "widget_type": "text",
                                              "rect": [50 + 120 * c, y0 + 30 * r, 150 + 120 * c, y0 + 30 * r + 14]}}
                for r in range(rows) for c in range(cols)}
    bp = {"fields": {**lattice(3, 2, 100), **lattice(3, 3, 400)}}
    out = {(len({c["row"] for c in t["grid"]}), len({c["col"] for c in t["grid"]})): t for t in gc.listing("t1", bp)}
    assert all(t["id"].startswith("p1-G") for t in out.values())
    if (3, 2) in out:
        assert out[(3, 2)]["status"] == "split" and "small" in out[(3, 2)]["aside_why"]
    if (3, 3) in out:
        assert out[(3, 3)]["status"] == "active"


def test_a_grid_over_as_many_other_fields_as_cells_is_set_aside(tmp_path, monkeypatch):
    """Andrew (2026-10-23): a grid may hold a few other fields in its outline, "but if ... it contains 6 fields but
    covers almost twice as many" it is no grid. A 3 x 3 lattice with 10 small boxes scattered between its rows."""
    from petey.validate import grid_check as gc
    monkeypatch.setattr(gc, "SETS", tmp_path)
    monkeypatch.setattr(gc, "_set_path", lambda bid: tmp_path / f"{bid}.json")
    monkeypatch.setattr(gc, "not_grids", lambda bid: [])
    f = {f"a_{r}_{c}": {"type": "string", "x_petey_id": f"1_a{r}{c}",
                        "widget": {"page": 1, "widget_type": "text", "rect": [50 + 160 * c, 100 + 30 * r, 150 + 160 * c, 114 + 30 * r]}}
         for r in range(3) for c in range(3)}
    def lattice_only(extra):
        return [t for t in gc.listing("t2", {"fields": {**f, **extra}})
                if {c["name"] for c in t["grid"]} >= {f"a_{r}_{c}" for r in range(3) for c in range(3)}]
    few = {f"x_{i}": {"type": "boolean", "x_petey_id": f"1_x{i}",
                      "widget": {"page": 1, "widget_type": "checkbox", "rect": [61 + 41 * i, 118 + 30 * (i % 2), 67 + 41 * i, 124 + 30 * (i % 2)]}}
           for i in range(10)}
    got = lattice_only(few)
    assert got and all(t["status"] == "split" and "other fields" in t["aside_why"] for t in got)
    (tmp_path / "t2.json").unlink()
    got = lattice_only({k: few[k] for k in list(few)[:3]})          # 3 others to 9 cells: a grid
    assert got and all(t["status"] == "active" for t in got)


def test_grid_cells_are_accepted_on_the_checks_own_test_and_a_refusal_says_why(monkeypatch):
    """je__acord_131 p3-G2 (Andrew, 2026-10-24: "they aren't getting validated by check and validate"; "what's the
    point of the stricter check, especially if it fails silently?"): rows named by their questions, two of them
    descriptions. Accepting uses the check's test (code check or the resolver's ok); a refusal is said."""
    cells = [('advertising_agency_services_used_explanation_txt', 0, 0),
             ('advertising_agency_services_used_ind', 0, 1),
             ('coverage_provided_under_agency_policy_explanation_txt', 1, 0),
             ('coverage_provided_under_agency_policy_ind', 1, 1),
             ('aircraft_owned_leased_operated_explanation_txt', 2, 0),
             ('aircraft_owned_leased_operated_ind', 2, 1),
             ('dangerous_cargo_hauled_explanation_txt', 3, 0),
             ('dangerous_cargo_hauled_ind', 3, 1),
             ('passengers_carried_for_fee_explanation_txt', 4, 0),
             ('passengers_carried_for_fee_ind', 4, 1),
             ('units_not_insured_by_underlying_policies_explanation_txt', 5, 0),
             ('units_not_insured_by_underlying_policies_ind', 5, 1),
             ('vehicles_leased_rented_to_others_explanation_txt', 6, 0),
             ('vehicles_leased_rented_to_others_ind', 6, 1),
             ('hired_and_non_owned_coverage_provided_explanation_txt', 7, 0),
             ('hired_and_non_owned_coverage_provided_ind', 7, 1),
             ('bridge_dam_marine_work_performed_explanation_txt', 8, 0),
             ('bridge_dam_marine_work_performed_ind', 8, 1),
             ('typical_jobs_performed_desc_txt', 9, 0),
             ('contractual_agreements_desc_txt', 10, 0),
             ('cranes_owned_rented_used_explanation_txt', 11, 0),
             ('cranes_owned_rented_used_ind', 11, 1),
             ('subcontractors_carry_lower_limits_explanation_txt', 12, 0),
             ('subcontractors_carry_lower_limits_ind', 12, 1)]
    grid = [{"name": n, "page": 3, "row": r, "col": c} for n, r, c in cells]
    put = {}
    app = br.App.__new__(br.App)
    monkeypatch.setattr(br.App, "working", lambda self, bid: None, raising=False)
    monkeypatch.setattr(br.App, "put_verdicts", lambda self, bid, body: put.update(body["verdicts"]), raising=False)
    monkeypatch.setattr(br.hand_review, "_load", lambda p: {"fields": {}})
    monkeypatch.setattr(br.hand_review, "load_verdicts", lambda bid: {})
    monkeypatch.setattr(grid_check, "listing", lambda bid, bp: [{"id": "p3-G2", "status": "active", "grid": grid}])
    from petey.validate import grid_naming
    from petey.validate import retype
    monkeypatch.setattr(retype, "resolve_blank", lambda bp: None)
    names = {c["name"] for c in grid}
    assert not grid_naming.on_pattern(grid)[0]                          # off the strict pattern ...
    monkeypatch.setattr(grid_naming, "resolve", lambda *a, **k: {"status": "ok", "why": "lines labelled", "renames": {}})
    refused = []
    assert sorted(app.accept_grid("t", 3, names, refused)) == sorted(names) and refused == []   # ... the resolver's ok
    put.clear()
    monkeypatch.setattr(grid_naming, "resolve", lambda *a, **k: {"status": "unsure", "why": "column 1 split", "renames": {}})
    assert app.accept_grid("t", 3, names, refused) == [] and refused == [{"grid": "p3-G2", "why": "column 1 split"}]
