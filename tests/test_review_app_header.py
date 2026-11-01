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
    assert "'structure accepted' : 'accept structure'" in HEADER and ">accept all</button>" not in HEADER
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


def test_text_and_printed_fields_are_filled_on_review():
    assert "(f.printed ? ' printed' : f.printed === false ? ' txt' : ' choice')" in (SRC / "modes" / "review" / "index.tsx").read_text()
    css = (SRC / "styles.css").read_text()
    for k, v in (("txt", "text"), ("printed", "printed"), ("choice", "choice")):
        assert f".rv.{k}, .ovl.kind.{k} {{ background:var(--fill-{v}); }}" in css


def test_the_two_whole_form_accepts_save_after_and_a_field_accept_does_not():
    """Andrew, 2026-10-31: "just the accept settled and accept structure buttons should save everything. not the
    individual accept buttons"."""
    store = (SRC / "modes" / "review" / "store.ts").read_text()
    for fn in ("async function bulkAccept", "async function acceptStructure"):
        body = store[store.index(fn):store.index("\n}\n", store.index(fn))]
        assert "await saveAfter();" in body, fn
    sv = store.index("export async function setVerdict") if "export async function setVerdict" in store else store.index("function setVerdict")
    assert "saveAfter" not in store[sv:store.index("\n}\n", sv)]


def test_kind_fills_on_every_tab_but_add_remove():
    canvas = (SRC / "components" / "Canvas.tsx").read_text()
    assert "mode !== 'review' && mode !== 'add'" in canvas and "'ovl kind '" in canvas
    css = (SRC / "styles.css").read_text()
    assert "--fill-printed:" in css and "--fill-choice:" in css


def test_grouped_fields_filled_in_their_group_colour():
    """Andrew, 2026-10-31: "can you make grouped fields have the same color as their group color? (instead of the color
    they would have as singletons)": on Review and the shared page layer, while groups show; after the kind fills."""
    review = (SRC / "modes" / "review" / "index.tsx").read_text()
    assert "(fill[f.name] ? ' grp' : '')" in review and "color={fill[f.name]}" in review
    canvas = (SRC / "components" / "Canvas.tsx").read_text()
    assert "if (on('groups'))" in canvas and "(fill[f.name] ? ' grp' : '')" in canvas
    css = (SRC / "styles.css").read_text()
    rule = ".rv.grp, .ovl.kind.grp { background:color-mix(in srgb, var(--c) 30%, transparent); }"
    assert css.index(rule) > css.index(".rv.choice, .ovl.kind.choice {")


def test_add_cards_convert_and_choices_are_filled():
    panel = (SRC / "modes" / "add" / "Panel.tsx").read_text()
    # the kind a dropdown since (Andrew, 2026-10-31: "can you make the 'kind' field on the add card a dropdown that has
    # text, choice and printed?")
    assert '<option value="text">text</option><option value="choice">choice</option><option value="printed">printed</option>' in panel
    assert "value={p.kind === 'option' ? 'choice' : p.printed ? 'printed' : 'text'}" in panel
    assert ".ov.field.choice, .ov.prop.choice, .ov.added.choice { background:var(--fill-choice); }" in (SRC / "styles.css").read_text()


def test_another_form_opens_on_page_1():
    """Andrew, 2026-10-31: "can you make it so loading a new document automatically opens page 1?"."""
    actions = (SRC / "state" / "actions.ts").read_text()
    assert "set({ bid: id, page: 1, loaded: null, loadError: null });" in actions
    assert "await loadMode(true);" in actions and "(!fresh && !d.pageLabel(page))" in actions


def test_not_a_field_is_on_every_card_and_z_brings_it_back():
    # Andrew, 2026-11-01: "every time I click on a field in add/remove, 'not a field' should be available";
    # "'not a field' removes the outline from the add/remove layout. z brings it back"
    panel, store = (SRC / "modes" / "add" / "Panel.tsx").read_text(), (SRC / "modes" / "add" / "store.ts").read_text()
    assert "sidsOf" not in panel and "onClick={() => notAField(i)}>not a field</button>" in panel
    assert "dismissed: [...S().dismissed, ...out]" in store                   # listed under Not fields, × puts it back
    assert "source: 'area'" in store                                         # a card with nothing behind it: its box
    assert "!gone.has(s.sid) && !covered(s)" in store                         # an underline set aside leaves the page
    assert "e.key === 'x' && props.length) notAField(0)" in store and "e.key === 'z') undoNotAField()" in store
    assert "nav, s.sid);" in store                                           # a removed field's box: the card knows it
