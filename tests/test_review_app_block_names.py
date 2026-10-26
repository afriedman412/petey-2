"""A field's name edited from the block window in the React review page (Andrew, 2026-10-26: "can we make it so field
names within a block can be edited from the individual block window? ... parts, two steps (but only if there is
another block of the same type)"): the position's parts saved as the type's, then its blocks renamed, asked first
when the type has other blocks; a hovered name lights its field on the page. Headless Chrome against a mocked API
(as test_review_app_typing)."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br
from tests.test_review_app_typing import CHROME, PNG, PW

PAGES = [{"page": 1, "w_pt": 612, "h_pt": 792}]


def _block(n, y):
    names = [f"child_{n}_nm", f"child_{n}_birth_dt"]
    return {"n": n, "code": f"1_{n}", "page": 1, "bbox": [50, y, 300, y + 40], "template": n == 1, "names": names,
            "cells": [{"name": names[0], "rect": [50, y, 150, y + 15], "accepted": False},
                      {"name": names[1], "rect": [160, y, 300, y + 15], "accepted": False}],
            "prefix": "child", "iteration": str(n), "by": "number", "parts_set": False,
            "differs": [{"pos": 1, "name": names[0], "want": f"kid_{n}_nm"}], "kept": [], "same_as": [], "validated": False}


def _blocks(bid, n):
    return {"id": bid, "path": f"blueprints/{bid}.bpt", "pages": PAGES, "loose": [], "types": [{
        "id": "BT1", "label": "child", "auto": False, "page": 1, "boxes": 2, "confirmed": True, "wordings": ["nm", "birth_dt"],
        "slots": [{"suffix": "nm"}, {"subject": "birth", "suffix": "dt"}], "blocks": [_block(k, 60 * k) for k in range(1, n + 1)]}]}


RUN = """
import base64, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
dist, chrome = Path(sys.argv[1]), sys.argv[2]
api = json.loads(sys.stdin.read())
sent, dialogs = [], []
def route(r):
    path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("#")[0].split("?")[0]
    if path.startswith("next"):
        f = dist / path[len("next/"):]
        return r.fulfill(path=str(f if f.is_file() else dist / "index.html"))
    if r.request.method != "GET":
        sent.append([path, json.loads(r.request.post_data or "{}")])
    if "/png/" in path:
        return r.fulfill(body=base64.b64decode(api["png"]), content_type="image/png")
    if path.endswith("/sha"):
        return r.fulfill(json={"sha": "1"})
    if path.startswith("api/overlay/"):
        return r.fulfill(json={"fields": [], "grids": [], "blocks": []})
    if path in api:
        return r.fulfill(json=api[path])
    if path.endswith("/confirm"):
        return r.fulfill(json={"wordings": ["kid_nm", "birth_dt"], "numbered": []})
    if path.endswith("/tfix"):
        return r.fulfill(json={"renamed": 1, "same": [], "held": [], "errors": []})
    return r.fulfill(status=404, body="not mocked: " + path)
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("dialog", lambda d: (dialogs.append(d.message[:40]), d.accept()))
    pg.route("**/*", route)
    for form in ("two", "one"):
        sent.clear(); dialogs.clear()
        pg.goto(f"http://review.test/next/#blocks/{form}/BT1-1")
        pg.wait_for_selector(".btopen .btnames code.ed")
        pg.locator(".btopen .btnames tr").first.hover()
        lit = pg.locator("#canvas .gcell.hl").count()
        pg.locator(".btopen .btnames code.ed").first.click()
        warn = pg.locator(".btpe .warn").count()
        pg.locator(".btpe input").first.fill("kid")
        preview = pg.inner_text(".btpe > div:nth-child(2)")
        pg.keyboard.press("Enter")
        pg.wait_for_function("!document.querySelector('.btpe')")
        pg.wait_for_timeout(800)
        out[form] = {"lit": lit, "warn": warn, "preview": preview, "dialogs": len(dialogs),
                     "sent": [[s[0].rsplit("/", 1)[1], s[1]] for s in sent]}
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def test_a_name_edited_in_the_block_window_saves_its_parts_then_renames():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    api = {"api/blueprints": [{"id": f, "form": f, "fields": 4, "accepted": 0, "flagged": 0, "source": "lib"} for f in ("two", "one")],
           "api/blocks/two": _blocks("two", 2), "api/blocks/one": _blocks("one", 1), "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    slots = [{"subject": "kid", "suffix": "nm"}, {"subject": "birth", "suffix": "dt"}]
    # two blocks: the warning, the name as it will print, the type's parts saved, then asked, then renamed
    assert out["two"] == {"lit": 1, "warn": 1, "preview": "→ child_1_kid_nm", "dialogs": 1,
                          "sent": [["confirm", {"type": "BT1", "slots": slots}], ["tfix", {"type": "BT1"}]]}
    # one block: no warning, renamed without asking
    assert out["one"] == {"lit": 1, "warn": 0, "preview": "→ child_1_kid_nm", "dialogs": 0,
                          "sent": [["confirm", {"type": "BT1", "slots": slots}], ["tfix", {"type": "BT1"}]]}


CLASH_RUN = """
import base64, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
dist, chrome = Path(sys.argv[1]), sys.argv[2]
api = json.loads(sys.stdin.read())
def route(r):
    path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("#")[0].split("?")[0]
    if path.startswith("next"):
        f = dist / path[len("next/"):]
        return r.fulfill(path=str(f if f.is_file() else dist / "index.html"))
    if "/png/" in path:
        return r.fulfill(body=base64.b64decode(api["png"]), content_type="image/png")
    if path.endswith("/sha"):
        return r.fulfill(json={"sha": "1"})
    if path.startswith("api/overlay/"):
        return r.fulfill(json={"fields": [], "grids": [], "blocks": []})
    if path in api:
        return r.fulfill(json=api[path])
    return r.fulfill(status=404, body="not mocked: " + path)
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", route)
    pg.goto("http://review.test/next/#blocks/two/BT1-1")
    pg.wait_for_selector(".btopen")
    lines = pg.locator(".btopen .warn > div").all_inner_texts()
    links = pg.locator(".btopen .warn a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
    b.close()
print(json.dumps({"lines": lines, "links": links, "errors": errs}))
"""


def test_names_held_by_another_field_are_said_under_the_validate_button():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built
    data = _blocks("two", 2)
    first = data["types"][0]["blocks"][0]
    first["differs"] = [{"pos": 1, "name": "child_1_nm", "want": "kid_1_nm", "held": "BT2-1"},
                        {"pos": 2, "name": "child_1_birth_dt", "want": "kid_1_birth_dt"}]          # not held: no line
    data["codes"] = {"child_1_nm": "1_7", "kid_1_nm": "2_3"}
    api = {"api/blueprints": [{"id": "two", "form": "two", "fields": 4, "accepted": 0, "flagged": 0, "source": "lib"}],
           "api/blocks/two": data, "png": PNG}
    res = subprocess.run([str(PW), "-c", CLASH_RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["lines"] == ["two_1_7 and two_2_3 would both be kid_1_nm"]
    assert out["links"] == ["#review/two/1_7", "#review/two/2_3"]
