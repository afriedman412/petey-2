"""Groups: a combined text field's entity type picked from a dropdown on its card (Andrew, 2026-10-28: "let's add a
'entity type' dropdown for combined fields"), in headless Chrome against a mocked API (as test_review_app_fixes): the
card shows the saved type, a new pick is saved with the units, and (none) takes it off; and several text fields picked
at once made one entity with one button (2026-10-28: "combine 9 fields at once instead of doing them one click at a
time")."""
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
    pg.goto("http://review.test/next/#groups/g")
    pg.wait_for_selector(".gcard h3")
    pg.click(".gcard h3 >> text=dob_dt"); pg.wait_for_selector("#gEntityType")
    out["shown"] = pg.eval_on_selector("#gEntityType", "e => e.value")
    out["choices"] = pg.eval_on_selector_all("#gEntityType option", "els => els.map(e => e.value)")
    pg.select_option("#gEntityType", "id_number"); pg.wait_for_timeout(300)
    pg.select_option("#gEntityType", ""); pg.wait_for_timeout(300)
    puts = [s[2] for s in sent if s[0] == "PUT" and s[1].endswith("/units")]
    out["saved"] = [[u.get("entity_type") for u in body["units"] if u.get("kind") == "text"] for body in puts]
    # several loose text fields picked at once (a click, then Shift-clicks) made one entity with one button
    pg.click('[data-item="a_1"]')
    for i in (2, 3, 4):
        pg.click(f'[data-item="a_{i}"]', modifiers=["Shift"])
    pg.wait_for_selector("#gEntity")
    out["button"] = pg.inner_text("#gEntity")
    pg.click("#gEntity"); pg.wait_for_timeout(300)
    last = [s[2] for s in sent if s[0] == "PUT" and s[1].endswith("/units")][-1]
    out["made"] = [u["items"] for u in last["units"] if u.get("kind") == "text" and u["name"] != "dob_dt"]
    # ... or with its type in the same step, from the card's dropdown
    pg.click("text=separate again"); pg.wait_for_timeout(200)
    pg.click('[data-item="a_1"]')
    for i in (2, 3):
        pg.click(f'[data-item="a_{i}"]', modifiers=["Shift"])
    pg.select_option("#gEntityPick", "date"); pg.wait_for_timeout(300)
    last = [s[2] for s in sent if s[0] == "PUT" and s[1].endswith("/units")][-1]
    out["typed"] = [(u["items"], u.get("entity_type")) for u in last["units"] if u.get("kind") == "text" and u["name"] != "dob_dt"]
    # each entity in its own colour, as option groups are (2026-10-28: "make entities show up highlighted by color")
    col = lambda i: pg.eval_on_selector(f'[data-item="{i}"]', "e => getComputedStyle(e).getPropertyValue('--c').trim()")
    out["colors"] = [col("dob_month"), col("dob_yr"), col("a_1"), col("a_4")]
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def _groups(bid):
    items = {f"dob_{w}": {"id": f"dob_{w}", "field": f"dob_{w}", "key": None, "kind": "text", "page": 1,
                          "rect": [50 + 40 * k, 50, 80 + 40 * k, 62], "widget_type": "text", "type": "string"}
             for k, w in enumerate(("month", "day", "yr"))}
    items.update({f"a_{i}": {"id": f"a_{i}", "field": f"a_{i}", "key": None, "kind": "text", "page": 1,
                             "rect": [50 + 40 * i, 200, 80 + 40 * i, 212], "widget_type": "text", "type": "string"}
                  for i in range(1, 5)})
    return {"id": bid, "path": "blueprints/g.bpt", "pages": PAGES, "items": items, "base": [], "other_names": [],
            "info": {}, "units": [{"kind": "text", "name": "dob_dt", "type": "string", "entity_type": "date",
                                   "items": ["dob_month", "dob_day", "dob_yr"]}]}


def test_a_combined_field_takes_an_entity_type():
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
    assert out["shown"] == "date"                                        # the saved type on the card
    assert out["choices"][0] == "" and "id_number" in out["choices"] and out["choices"][-1] == "other"
    assert out["saved"][-2:] == [["id_number"], [None]]                  # a pick saved; (none) takes it off
    assert out["button"] == "make entity (4)"
    assert out["made"] == [["a_1", "a_2", "a_3", "a_4"]]                 # four fields, one entity, one click
    assert out["typed"] == [[["a_1", "a_2", "a_3"], "date"]]           # picked, typed and made in one step
    c = out["colors"]
    assert c[0] == c[1] and c[0].startswith("#") and c[2].startswith("#") and c[2] != c[0]   # one colour per entity
    assert c[3] not in (c[0], c[2])                                       # a loose text field: neither
