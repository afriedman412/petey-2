"""Parsed blueprints kept on disk (hand_review._load, Andrew 2026-10-22: "can you look into if there's a way to speed
up the reboot?"): a copy is used while its file is unchanged, parsed again once it changes; files outside the repo
are never kept."""
import os

import pytest

from petey.validate import hand_review as h


@pytest.fixture
def kept(monkeypatch, tmp_path):
    store = tmp_path / "parsed"
    monkeypatch.setattr(h, "PARSED", store)
    monkeypatch.setattr(h, "_parsed_path", lambda p: store / (p.name + ".pickle"))
    return store


def test_a_parsed_copy_is_used_until_the_file_changes(kept, tmp_path, monkeypatch):
    f = tmp_path / "x.bpt"
    f.write_text("fields:\n  a_txt: {type: string}\n")
    assert h._load(f)["fields"]["a_txt"]["type"] == "string"
    assert h._stale(f) is False
    monkeypatch.setattr(h.yaml, "load", lambda *a, **k: pytest.fail("parsed again while unchanged"))
    first = h._load(f)
    first["fields"]["a_txt"]["type"] = "number"            # a caller changing what it got changes nothing kept
    assert h._load(f)["fields"]["a_txt"]["type"] == "string"
    monkeypatch.undo()
    monkeypatch.setattr(h, "PARSED", kept)
    monkeypatch.setattr(h, "_parsed_path", lambda p: kept / (p.name + ".pickle"))
    f.write_text("fields:\n  b_nm: {type: string}\n")
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 1_000_000))
    assert h._stale(f) and list(h._load(f)["fields"]) == ["b_nm"]


def test_files_outside_the_repo_are_not_kept(tmp_path):
    assert h._parsed_path(tmp_path / "y.bpt") is None
