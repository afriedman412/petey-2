"""The React review page keeps what you type (Andrew, 2026-10-26: "the 'edit parts' button in the block window doesn't
let you type more than a couple letters into the fields"; the reason for the React page): every letter typed into a
field's part stays, and the tab reading its data again in the middle of the typing (the file changed on disk) leaves
the box, its text and the cursor where they were. The built page (petey/validate/review_app/dist) runs in headless
Chrome against a mocked API. Playwright is not in the project venv: the test runs in ~/.venvs/petey-playwright and is
skipped where that, Chrome or node is missing."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br

PW = Path.home() / ".venvs" / "petey-playwright" / "bin" / "python"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

ENTRY = {"id": "t0", "form": "t0", "fields": 2, "accepted": 0, "flagged": 0, "source": "lib"}
FIELD = {"page": 1, "options": [], "type": "string", "tier": "single", "why": [], "witnesses": {}}
REVIEW = {
    "path": "blueprints/t0.bpt", "pages": [{"page": 1, "w_pt": 612, "h_pt": 792}], "verdicts": {}, "semantic_types": [],
    "fields": [
        {**FIELD, "name": "owner_nm", "id": "1_1", "rects": [{"page": 1, "rect": [50, 50, 200, 70]}],
         "identifiers": {"subject": "owner", "suffix": "nm"}},
        {**FIELD, "name": "owner_ssn_nbr", "id": "1_2", "rects": [{"page": 1, "rect": [50, 90, 200, 110]}],
         "identifiers": {"subject": "owner_ssn", "suffix": "nbr"}},
    ],
}

RUN = """
import base64, json, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
dist, chrome = Path(sys.argv[1]), sys.argv[2]
api = json.loads(sys.stdin.read())
sha = {"n": 0}
def route(r):
    path = r.request.url.split("://", 1)[1].split("/", 1)[1].split("#")[0].split("?")[0]
    if path.startswith("next"):
        f = dist / path[len("next/"):]
        if f.is_file():
            return r.fulfill(path=str(f))
        return r.fulfill(path=str(dist / "index.html"))
    if path == "api/blueprints/t0/sha":
        sha["n"] += 1
        return r.fulfill(json={"sha": str(sha["n"])})
    if path.startswith("api/blueprints/t0/png/"):
        return r.fulfill(body=base64.b64decode(api["png"]), content_type="image/png")
    if path in api:
        return r.fulfill(json=api[path])
    return r.fulfill(status=404, body="not mocked: " + path)
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", route)
    pg.goto("http://review.test/next/#review/t0")
    pg.wait_for_selector(".rlist div")
    pg.click(".rlist div[data-n=owner_nm]")
    pg.click("#i_subject"); pg.keyboard.press("End"); pg.keyboard.type("abcdef", delay=30)
    out["typed"] = [pg.input_value("#i_subject"), pg.input_value("#eName")]
    # the file changed on disk in the middle of the typing: the tab reads its data again
    pg.evaluate("window.dispatchEvent(new Event('focus'))")
    pg.wait_for_timeout(500)
    pg.keyboard.type("q")
    out["after_reload"] = [pg.evaluate("document.activeElement.id"), pg.input_value("#i_subject")]
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def test_typing_in_a_part_keeps_every_letter_through_a_reload():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built      # else the test would run the last build that worked
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    api = {"api/blueprints": [ENTRY], "api/review/t0": REVIEW, "api/review/t0/removals": {"removed": []},
           "api/overlay/t0": {"fields": [], "grids": [], "blocks": []}, "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["typed"] == ["ownerabcdef", "ownerabcdef_nm"]
    assert out["after_reload"] == ["i_subject", "ownerabcdefq"]
