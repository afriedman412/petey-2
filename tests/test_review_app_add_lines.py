"""Add / remove: the underlines no field covers are drawn on the page (cyan), a click on one proposes it by its sid,
"l" turns them off, and n / p step through the suggestions only (Andrew, 2026-10-28: "the underlines are highlighted
and you can click on one to create a field above it"); in headless Chrome against a mocked API (as
test_review_app_fixes)."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br
from tests.test_review_app_add_stays import _add, _proposal
from tests.test_review_app_fixes import RUN as FIXES, _entry
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
    pg.wait_for_selector(".ov.line")
    proposed = lambda: [s[2].get("sid") for s in sent if s[1] == "api/add/a/propose"]
    out["drawn"] = pg.eval_on_selector_all(".ov.line", "els => els.map(e => e.dataset.sid)")
    out["count"] = pg.inner_text("#linesLeft")
    pg.click(".ov.line[data-sid='u1_300_400']"); pg.wait_for_selector("text=add this field")
    out["clicked"] = proposed()
    pg.keyboard.press("Escape"); pg.keyboard.press("n"); pg.wait_for_timeout(400)
    out["after_n"] = proposed()
    pg.keyboard.press("l"); pg.wait_for_timeout(200)
    out["after_l"] = pg.eval_on_selector_all(".ov.line", "els => els.length")
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def test_underlines_are_drawn_and_clicked():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    data = {**_add(), "lines": [{"sid": "u1_300_400", "page": 1, "rect": [300, 386, 500, 400], "source": "underline"}]}
    api = {"api/blueprints": [_entry("a")], "api/add/a": data, "api/add/a/propose": _proposal(),
           "api/add/a/record": {"changes": [], "errors": []}, "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["drawn"] == ["u1_300_400"]
    assert out["count"].startswith("1 underline")
    assert out["clicked"] == ["u1_300_400"]                  # the click sends the line itself
    assert out["after_n"] == ["u1_300_400", "s1"]            # n goes to a suggestion, not to a line
    assert out["after_l"] == 0
