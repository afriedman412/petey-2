"""Andrew's hand-picked benchmark forms have their own section on the review page (2026-10-28: "can you put them in their
own section?"): blueprints under runs/manual_grabs/blueprints are listed as mg__<stem>."""
from petey.validate import hand_review as h


def test_manual_grabs_listed_under_their_own_prefix(tmp_path, monkeypatch):
    d = tmp_path / "manual_grabs"
    d.mkdir()
    (d / "pb_0123456789ab.bpt").write_text("name: pb_0123456789ab\nfields: {}\n")
    monkeypatch.setattr(h, "SOURCES", {"mg": d})
    assert list(h.blueprint_paths()) == ["mg__pb_0123456789ab"]


def test_mg_is_a_source():
    assert "mg" in h.SOURCES and h.SOURCES["mg"].parts[-2:] == ("manual_grabs", "blueprints")


def test_finance_batch_is_a_source():
    # Andrew, 2026-10-29: today's finance downloads in their own section
    assert h.SOURCES["fin"].parts[-2:] == ("finance", "blueprints")
