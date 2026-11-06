"""The index's "added" column (Andrew, 2026-11-04: "can you also add an 'added' date to the index"): the day a form
came into the library, from its download date, else the library file's first commit, else the file's creation."""
import time

from petey_review import hand_review as h


def test_download_date_first(tmp_path):
    p = tmp_path / "pb_0123456789ab.bpt"
    p.write_text("name: x\n")
    assert h.added(p, {"x_petey_source": {"date": "2026-11-03"}}, {}) == "2026-11-03"


def test_library_form_uses_first_commit(tmp_path, monkeypatch):
    monkeypatch.setattr(h, "BLUEPRINTS", tmp_path)
    p = tmp_path / "w9.bpt"
    p.write_text("name: x\n")
    assert h.added(p, {}, {"w9.bpt": {"first": "2026-09-28", "last": "2026-11-01"}}) == "2026-09-28"


def test_otherwise_the_files_creation_day(tmp_path):
    p = tmp_path / "sd_123.bpt"
    p.write_text("name: x\n")
    assert h.added(p, {"x_petey_source": {"corpus": "CC"}}, {}) == time.strftime("%Y-%m-%d")
