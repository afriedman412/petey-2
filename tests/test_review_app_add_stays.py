"""Add / remove: adding a field leaves the page where it is (Andrew, 2026-10-28: "make it so added a field doesn't
automatically move to the next suggested field"): no next suggestion is proposed after the add, none is current, and n
still goes on to the next one; in headless Chrome against a mocked API (as test_review_app_fixes)."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br
from tests.test_review_app_fixes import PAGES, RUN as FIXES, _entry
from tests.test_review_app_typing import CHROME, PNG, PW

RUN = FIXES.split("out = {}")[0] + """
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", route)
    pg.goto("http://review.test/next/#add/a")
    pg.wait_for_selector(".ov.sug")
    pg.keyboard.press("n"); pg.wait_for_selector("text=add this field")
    pg.click("text=add this field"); pg.wait_for_timeout(500)
    proposed = lambda: [s[2].get("sid") for s in sent if s[1] == "api/add/a/propose"]
    out["after_add"] = [proposed(), pg.eval_on_selector_all(".ov.sug.cur", "els => els.length")]
    pg.keyboard.press("n"); pg.wait_for_timeout(400)
    out["after_n"] = proposed()
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def _add():
    sug = [{"sid": f"s{k}", "page": 1, "rect": [50, 50 + 40 * k, 150, 65 + 40 * k], "source": "finder"} for k in (1, 2)]
    return {"path": "blueprints/a.bpt", "finder": "f", "classifier": "c", "label_model": "m", "pages": PAGES,
            "suggestions": sug, "fields": [], "field_specs": {}, "semantic_types": [], "added": [], "dismissed": [],
            "removed": []}


def _proposal():
    return {"proposals": [{"kind": "text", "page": 1, "rect": [50, 90, 150, 105], "geometry": "finder", "options": [],
                           "name": "owner_nm", "name_options": [], "evidence": [], "type": "string",
                           "widget": {"page": 1, "rect": [50, 90, 150, 105], "widget_type": "text"}}]}


def test_adding_a_field_does_not_move_on():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    api = {"api/blueprints": [_entry("a")], "api/add/a": _add(), "api/add/a/propose": _proposal(),
           "api/add/a/record": {"changes": [], "errors": []}, "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["after_add"] == [["s1"], 0]          # the add proposed nothing more, and no suggestion is current
    assert out["after_n"] == ["s1", "s2"]           # n goes on to the next one
