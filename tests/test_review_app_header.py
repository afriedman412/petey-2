"""The review page's header after the 2026-10-31 cleanup ("accept all" became "accept structure" the same day) (Andrew: remove "hide tabs" (t does it), "extract" and "audit"
(not currently relevant), put "accept all", "accept settled" and "reset validation" together)."""
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "petey" / "validate" / "review_app" / "src"
HEADER = (SRC / "components" / "Header.tsx").read_text()


def test_no_hide_tabs_or_extract_button():
    assert 'id="tabsBtn"' not in HEADER
    assert 'href="/extract"' not in HEADER


def test_t_still_hides_the_tabs():
    assert "e.key === 't'" in (SRC / "App.tsx").read_text()


def test_the_three_verdict_buttons_sit_in_one_cluster():
    m = re.search(r'<span className="btngroup" id="verdictBtns">(.*?)</span>', HEADER, re.S)
    assert m, "no verdict cluster"
    assert re.findall(r'id="(\w+)"', m.group(1)) == ["bulk", "acceptStructure", "resetV"]


def test_audit_has_no_tab_and_no_key():
    ids = re.search(r"export const MODE_IDS: ModeId\[\] = \[([^\]]*)\]", (SRC / "lib" / "types.ts").read_text()).group(1)
    assert "'audit'" not in ids and "'blocks'" in ids
    assert "MODE_IDS.map" in (SRC / "components" / "Frame.tsx").read_text()


def test_ignore_page_reason_starts_as_too_few_fields():
    frame = (SRC / "components" / "Frame.tsx").read_text()
    assert "const DEFAULT_REASON = 'too few fields';" in frame
    assert "useState(DEFAULT_REASON)" in frame and "e.currentTarget.select()" in frame


def test_accept_structure_replaces_accept_all():
    assert ">accept structure</button>" in HEADER and ">accept all</button>" not in HEADER
    home = (SRC / "components" / "home-data.ts").read_text()
    assert "{ k: 'structure', t: 'structure validated' }" in home


def test_home_has_a_column_picker_kept_per_browser():
    home = (SRC / "components" / "Home.tsx").read_text()
    assert '<Columns all={ALL} hidden={hidden} />' in home
    assert "c.k === 'form' || !hidden.has(c.k)" in home              # the form column (the link) always shows
    assert "hidden?: string[];" in (SRC / "state" / "app.ts").read_text()   # saved with the other home settings


def test_home_counts_fold_away_and_structure_validated_can_be_hidden():
    home = (SRC / "components" / "Home.tsx").read_text()
    assert 'id="hstatsTab"' in home and "{!H.hideStats && <div className=\"hstats\">" in home
    assert 'id="hideStruct"' in home and "statusOf(b).k === 'structure'" in home
    assert "hideStats?: boolean; hideStruct?: boolean;" in (SRC / "state" / "app.ts").read_text()


def test_printed_fields_are_hatched_on_review():
    assert "(f.printed ? ' printed' : '')" in (SRC / "modes" / "review" / "index.tsx").read_text()
    css = (SRC / "styles.css").read_text()
    assert ".rv.printed:not(.flag):not(.removed) { background:repeating-linear-gradient(" in css


def test_the_two_whole_form_accepts_save_after_and_a_field_accept_does_not():
    """Andrew, 2026-10-31: "just the accept settled and accept structure buttons should save everything. not the
    individual accept buttons"."""
    store = (SRC / "modes" / "review" / "store.ts").read_text()
    for fn in ("async function bulkAccept", "async function acceptStructure"):
        body = store[store.index(fn):store.index("\n}\n", store.index(fn))]
        assert "await saveAfter();" in body, fn
    sv = store.index("export async function setVerdict") if "export async function setVerdict" in store else store.index("function setVerdict")
    assert "saveAfter" not in store[sv:store.index("\n}\n", sv)]
