"""The review page's sidebar keeps what you type (bindSidebarKeys in blueprint_review.html), run in headless Chrome:
a box whose own input handler changes the sidebar (the block matrix's name preview) takes every letter typed
(2026-10-26: "the 'edit parts' button in the block window doesn't let you type more than a couple letters into the
fields"), and a redraw while typing still puts back the box and its text.

The guard's code is taken from the page itself, into a bare sidebar. Playwright is not in the project venv: the test
runs in ~/.venvs/petey-playwright and is skipped where that is missing."""
import json
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "petey" / "validate" / "blueprint_review.html"
PW = Path.home() / ".venvs" / "petey-playwright" / "bin" / "python"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

RUN = """
import json, sys
from playwright.sync_api import sync_playwright
html = sys.stdin.read()
with sync_playwright() as p:
    b = p.chromium.launch(executable_path=%r)
    pg = b.new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.set_content(html)
    out = {}
    # a box whose own handler changes the sidebar on every keystroke
    pg.click("#parts"); pg.keyboard.press("End"); pg.keyboard.type("abcdef", delay=30)
    out["typed"] = pg.input_value("#parts")
    # a redraw while typing in another box: the new box has the text typed and the cursor
    pg.click("#label"); pg.keyboard.type("xyz", delay=30)
    pg.evaluate("draw()")
    out["redrawn"] = pg.evaluate("[document.activeElement.id, document.querySelector('#label').value]")
    pg.keyboard.type("q")
    out["after"] = pg.input_value("#label")
    out["errors"] = errs
    b.close()
print(json.dumps(out))
"""


def _guard() -> str:
    src = PAGE.read_text()
    start, end = src.index("const FIELD_SEL"), src.index("// one palette for the things drawn around boxes")
    return src[start:end]


def test_typing_in_the_sidebar_keeps_every_letter():
    if not PW.exists() or not Path(CHROME).exists():
        pytest.skip("Playwright venv or Chrome not installed")
    html = f"""<html><body><div id="panel"></div><script>
const $ = s => document.querySelector(s);
{_guard()}
function draw() {{
  $('#panel').innerHTML = '<input type="text" id="parts" value="ye"><span id="preview">ye</span>'
    + '<input type="text" id="label" value="">';
  $('#parts').addEventListener('input', e => {{ $('#preview').textContent = e.target.value + '_txt'; }});
}}
draw(); bindSidebarKeys();
</script></body></html>"""
    res = subprocess.run([str(PW), "-c", RUN % CHROME], input=html, capture_output=True, text=True, timeout=90)
    assert res.returncode == 0, res.stderr
    out = json.loads(res.stdout.strip().splitlines()[-1])
    assert out["errors"] == []
    assert out["typed"] == "yeabcdef"
    assert out["redrawn"] == ["label", "xyz"]
    assert out["after"] == "xyzq"
