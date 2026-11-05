"""The benchmark key's page pick is permanent (Andrew, 2026-11-04: "the benchmark pages should be stable between
builds"; "all that building the key should do is select pages from new forms and encode them to the appropriate
set"): recorded the first time a form is built, reused after, seeded from the indexes already built."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "eval"))
import benchmark_key as bk  # noqa: E402


def _keys(*counts):
    """A form's pages, page 1.. with that many fields each."""
    return {i + 1: {"fields": [{"id": f"f{j}"} for j in range(n)], "groups": []} for i, n in enumerate(counts)}


def test_a_new_form_is_picked_once_and_the_pick_holds():
    picks = {}
    first = bk.picked("t__form", _keys(30, 12, 20, 4), picks)
    assert first == {"key": [1, 3], "spare": [2]}            # the two fullest pages; page 4 has too few for the tuning set
    assert picks == {"t__form": first}
    # fields added to page 2 on the review page: a fresh pick would swap it in; the recorded one stands
    again = bk.picked("t__form", _keys(30, 40, 20, 4), picks)
    assert again == {"key": [1, 3], "spare": [2]}
    assert bk.pick_pages(_keys(30, 40, 20, 4)) == [2, 1]


def test_the_record_is_seeded_from_the_indexes_then_read_as_written(tmp_path):
    key, dev = tmp_path / "key", tmp_path / "dev_key"
    key.mkdir(), dev.mkdir()
    (key / "index.json").write_text(json.dumps([{"page_id": "a__f__p1"}, {"page_id": "a__f__p3"}, {"page_id": "b__g__p2"}]))
    (dev / "index.json").write_text(json.dumps([{"page_id": "a__f__p2"}]))
    record = tmp_path / "picks.json"
    picks = bk.load_picks(record, key, dev)
    assert picks == {"a__f": {"key": [1, 3], "spare": [2]}, "b__g": {"key": [2], "spare": []}}
    record.write_text(json.dumps(picks))
    (key / "index.json").write_text("[]")                     # the indexes no longer matter once the record exists
    assert bk.load_picks(record, key, dev) == picks
    assert bk.load_picks(tmp_path / "none.json", tmp_path / "no", tmp_path / "no") == {}
