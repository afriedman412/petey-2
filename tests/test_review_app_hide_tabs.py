"""'hide tabs' in the review page's header hides every label drawn on the page, on every tab at once (Andrew,
2026-10-27: "can 'hide/show tabs' affect groups grids and blocks at the same time?"): the tabs' own labels and the grid
ids and block labels "show" draws for the other tabs (.ovl span), which stayed up on Groups, Add / remove and Review."""
import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[1] / "petey" / "validate" / "review_app" / "src" / "styles.css"


def _hidden():
    rules = [m.group(1) for m in re.finditer(r"([^{}]*body\.notabs[^{}]*)\{\s*display\s*:\s*none", re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S))]
    assert rules, "no body.notabs rule in styles.css"
    return {re.sub(r"\s+", " ", s.strip()).removeprefix("body.notabs ") for r in rules for s in r.split(",")}


def test_hide_tabs_covers_every_label_on_the_page():
    hidden = _hidden()
    for sel in (".ghtab", ".gtab .gtid", ".btb span", ".ov.added .tag", ".ovl span"):
        assert sel in hidden, sel
