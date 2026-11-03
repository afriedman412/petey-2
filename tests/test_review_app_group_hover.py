"""Groups: an option hovered anywhere in the sidebar lights its box on the page (Andrew, 2026-10-27: "rolling over a
group option anywhere in the groups tab highlights the corresponding field"), in headless Chrome against a mocked API
(as test_review_app_fixes): a group card's chip and the selected group's option row each light their own box, and
the light goes when the mouse leaves."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br
from tests.test_review_app_fixes import RUN as FIXES, _entry, _groups
from tests.test_review_app_typing import CHROME, PNG, PW

RUN = FIXES.split("out = {}")[0] + """
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", route)
    pg.goto("http://review.test/next/#groups/g")
    pg.wait_for_selector(".gcard .gchip")
    lit = lambda: pg.eval_on_selector_all(".gi.hl", "els => els.map(e => e.dataset.item)")
    pg.hover(".gcard .gchip >> nth=1"); pg.wait_for_timeout(150)
    out["chip"] = lit()
    pg.mouse.move(1, 1); pg.wait_for_timeout(150)
    out["left"] = lit()
    pg.click(".gcard h3"); pg.wait_for_selector(".orow")
    pg.hover(".orow >> nth=0"); pg.wait_for_timeout(150)
    out["row"] = lit()
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def test_a_hovered_option_lights_its_box():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    api = {"api/blueprints": [_entry("g")], "api/groups/g": _groups("g"), "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["chip"] == ["no_ind"]                # the card's second chip: its box alone
    assert out["left"] == []                        # gone when the mouse leaves
    assert out["row"] == ["yes_ind"]                # the selected group's first option row
