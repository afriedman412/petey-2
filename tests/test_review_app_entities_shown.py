"""Entities shown wherever groups are (Andrew, 2026-10-28: "lets make the entities visible everywhere the groups are"):
the overlay carries each entity's boxes from the fields' tags, Review outlines them as it outlines option groups (a
click selecting its first field), and the other tabs' "show groups" layer draws them; in headless Chrome against a
mocked API (as test_review_app_typing)."""
import json
import subprocess
from pathlib import Path

import pytest

from petey.validate import blueprint_review as br
from petey.validate import group_review as gr
from tests.test_review_app_block_names import _blocks
from tests.test_review_app_typing import CHROME, ENTRY, PNG, PW, REVIEW, RUN as TYPING


def test_the_overlay_carries_the_entities():
    def text(x):
        return {"type": "string", "x_petey_id": f"1_{x}", "widget": {"page": 1, "rect": [x, 100, x + 30, 112],
                                                                      "widget_type": "text", "path": None}}
    fields = {"dob_month": text(100), "dob_day": text(140), "notes_txt": text(300)}
    fields = gr.plan({"fields": fields}, [{"kind": "text", "name": "dob", "type": "string", "entity_type": "date",
                                           "items": ["dob_month", "dob_day"]}], page_captions=False)["fields"]
    o = br.overlay({"fields": fields}, "nowhere", {})
    assert o["entities"] == [{"name": "dob", "entity_type": "date", "page": 1, "fields": ["dob_month", "dob_day"],
                              "rects": [{"page": 1, "rect": [100, 100, 130, 112]}, {"page": 1, "rect": [140, 100, 170, 112]}]}]


RUN = TYPING.split("out = {}")[0] + """
out = {}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=chrome)
    pg = b.new_page(viewport={"width": 1400, "height": 900})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/*", route)
    pg.goto("http://review.test/next/#review/t0")
    pg.wait_for_selector(".rlist div")
    pg.wait_for_selector(".gh.rvg.entity")
    out["review"] = pg.eval_on_selector_all(".gh.rvg.entity", "els => els.map(e => e.title)")
    pg.click(".gh.rvg.entity", position={"x": 2, "y": 2}); pg.wait_for_timeout(200)
    out["selected"] = pg.eval_on_selector_all(".rlist div.sel", "els => els.map(e => e.dataset.n)")
    pg.goto("http://review.test/next/#blocks/t0")
    pg.wait_for_selector(".ovl.entity")
    out["blocks"] = pg.eval_on_selector_all(".ovl.entity", "els => els.map(e => e.title)")
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def test_entities_are_drawn_on_review_and_the_other_tabs():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    built = br.build_app()
    assert not built.startswith("build failed"), built
    if not (br.APP_DIST / "index.html").exists():
        pytest.skip(f"the React page is not built: {built}")
    ent = {"name": "owner", "entity_type": "name", "page": 1, "fields": ["owner_nm", "owner_ssn_nbr"],
           "rects": [{"page": 1, "rect": [50, 50, 200, 70]}, {"page": 1, "rect": [50, 90, 200, 110]}]}
    api = {"api/blueprints": [ENTRY], "api/review/t0": REVIEW, "api/review/t0/removals": {"removed": []},
           "api/overlay/t0": {"fields": [], "grids": [], "blocks": [], "entities": [ent]},
           "api/blocks/t0": _blocks("t0", 1), "png": PNG}
    res = subprocess.run([str(PW), "-c", RUN, str(br.APP_DIST), CHROME], input=json.dumps(api),
                         capture_output=True, text=True, timeout=120)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["review"] == ["owner (entity: name, 2 fields)"]
    assert out["selected"] == ["owner_nm"]
    assert out["blocks"] == ["owner (entity: name, 2 fields)"]
