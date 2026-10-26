"""Old-page bugs fixed in the React review page (Andrew, 2026-10-26: "let's do all 11"), the two that could mislead or
leave a record behind, in headless Chrome against a mocked API (as test_review_app_typing):

- Grids: a grid's selection and last check do not follow you to another form whose grid has the same id (p1-G1).
- Groups: undoing an ungroup takes back the record of the boxes as not a group (else the finder never suggests them
  again)."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br
from tests.test_review_app_typing import CHROME, PNG, PW

PAGES = [{"page": 1, "w_pt": 612, "h_pt": 792}]


def _entry(bid):
    return {"id": bid, "form": bid, "fields": 4, "accepted": 0, "flagged": 0, "source": "lib"}


def _grids(on_pattern):
    cells = [{"name": f"row_{r}_{c}_txt", "rect": [50 + 60 * c, 50 + 20 * r, 100 + 60 * c, 65 + 20 * r]} for r in (1, 2) for c in (0, 1)]
    return {"path": "blueprints/x.bpt", "pages": PAGES, "tables": [
        {"id": "p1-G1", "page": 1, "bbox": [50, 70, 160, 105], "rows": 2, "cols": 2, "cells": cells, "accepted": 0,
         "on_pattern": on_pattern, "why": "" if on_pattern else "position 2 off", "source": "finder"}]}


def _groups(bid):
    items = {f"{w}_ind": {"id": f"{w}_ind", "field": f"{w}_ind", "key": None, "page": 1, "rect": [50, 50 + 20 * k, 60, 60 + 20 * k],
                          "widget_type": "checkbox"} for k, w in enumerate(("yes", "no"))}
    return {"id": bid, "path": "blueprints/g.bpt", "pages": PAGES, "items": items, "base": [], "other_names": [], "info": {},
            "units": [{"name": "answer", "type": "category", "items": ["yes_ind", "no_ind"], "origin": None, "confirmed": False}]}


RUN = """
import base64, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
dist, chrome = Path(sys.argv[1]), sys.argv[2]
api = json.loads(sys.stdin.read())
sent = []
def route(r):
    path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("#")[0].split("?")[0]
    if path.startswith("next"):
        f = dist / path[len("next/"):]
        return r.fulfill(path=str(f if f.is_file() else dist / "index.html"))
    if r.request.method != "GET":
        sent.append([r.request.method, path, json.loads(r.request.post_data or "{}")])
    if "/png/" in path:
        return r.fulfill(body=base64.b64decode(api["png"]), content_type="image/png")
    if path.endswith("/sha"):
        return r.fulfill(json={"sha": "1"})
    if path.startswith("api/overlay/"):
        return r.fulfill(json={"fields": [], "grids": [], "blocks": []})
    if path in api:
        return r.fulfill(json=api[path])
    if path.endswith("/check"):                       # a check: its result, the grid as it was
        return r.fulfill(json={"status": "validated", "steps": ["on pattern: 4 cells accepted"]})
    if path.endswith("/preview"):
        return r.fulfill(json={"pos_axis": "col", "positions": [], "lines": [], "all": None})
    if path.endswith("/plan"):
        return r.fulfill(json={"changes": [], "errors": []})
    if r.request.method != "GET":
        return r.fulfill(json={})
    return r.fulfill(status=404, body="not mocked: " + path)
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.route("**/*", route)
    # Grids: a check on form a's p1-G1, then form b, whose grid is also p1-G1
    pg.goto("http://review.test/next/#grids/a")
    pg.wait_for_selector(".gtcard")
    pg.click(".gtcard"); pg.click("button:has-text('check & validate')")
    pg.wait_for_selector(".gtres")
    out["a"] = [pg.locator(".gtcard.sel").count(), pg.locator(".gtres").count()]
    pg.evaluate("location.hash = '#grids/b'")
    pg.wait_for_function("document.querySelector('.gtcard') && location.hash === '#grids/b'")
    pg.wait_for_timeout(300)
    out["b"] = [pg.locator(".gtcard.sel").count(), pg.locator(".gtres").count()]
    # Groups: ungroup (u), then undo (z)
    pg.evaluate("location.hash = '#groups/g'")
    pg.wait_for_selector(".gcur")
    pg.click("#stage", position={"x": 2, "y": 2})
    pg.keyboard.press("u"); pg.wait_for_timeout(300)
    pg.keyboard.press("z"); pg.wait_for_timeout(300)
    out["notgroup"] = [s[2] for s in sent if s[1] == "api/groups/g/notgroup"]
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def test_grid_state_stays_with_its_form_and_undo_takes_back_not_a_group():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built      # else the test would run the last build that worked
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    api = {"api/blueprints": [_entry("a"), _entry("b"), _entry("g")], "api/grids/a": _grids(True), "api/grids/b": _grids(False),
           "api/groups/g": _groups("g"), "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["a"] == [1, 1]                       # form a: its grid selected, its check's result shown
    assert out["b"] == [0, 0]                       # form b: neither carried over to its p1-G1
    assert out["notgroup"] == [{"items": ["yes_ind", "no_ind"]}, {"items": ["yes_ind", "no_ind"], "on": False}]
