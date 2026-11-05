"""The review page's light misses / junk layers (2026-11-04): each missed key field's cause (eval/light_misses.py) and
the reader the overlay uses (petey/validate/light_misses.py)."""
import json
import os

import light_misses as LM

from petey.validate import light_misses as R

KEY = [{"id": "a", "rect": [100, 100, 300, 112], "kind": "text"},      # found
       {"id": "b", "rect": [100, 200, 300, 212], "kind": "text"},      # no finder box
       {"id": "c", "rect": [100, 300, 300, 312], "kind": "text"},      # finder box, Jev under the line
       {"id": "d", "rect": [100, 400, 200, 412], "kind": "text"},      # d and e under one kept box
       {"id": "e", "rect": [210, 400, 300, 412], "kind": "text"}]
FINDER = [{"id": "1", "rect": [100, 100, 300, 112]}, {"id": "2", "rect": [100, 300, 300, 312]},
          {"id": "3", "rect": [100, 400, 300, 412]}]
SCORE = {"1": 0.9, "2": 0.3, "3": 0.8}
PRED = [{"id": "p1_f1", "rect": [100, 100, 300, 112]}, {"id": "p1_f2", "rect": [100, 400, 300, 412]},
        {"id": "p1_f3", "rect": [400, 600, 500, 612]}]


def test_each_miss_gets_its_cause():
    got = {m["code"]: m["cause"] for m in LM.classify(KEY, FINDER, SCORE, PRED, 0.6)}
    assert got["b"] == "no box" and got["c"] == "jev" and "a" not in got
    assert {got.get("d"), got.get("e")} <= {"one box", None} and "one box" in got.values()


def test_junk_is_a_kept_box_on_no_key_field_with_its_jev_score():
    got = LM.junk(KEY, PRED, {"p1_f3": 0.71})
    assert got == [{"rect": [400, 600, 500, 612], "jev": 0.71}]


def test_jev_of_reads_group_and_single_scores():
    bp = {"fields": {"p1_f1": {"x_petey_geometry": {"jev_is_field": 0.8}},
                     "p1_o1": {"widgets": {"opt1": {}, "opt2": {}}, "x_petey_geometry": {"jev_is_field": [0.9, 0.4]}}}}
    assert LM.jev_of(bp) == {"p1_f1": 0.8, "p1_o1.opt1": 0.9, "p1_o1.opt2": 0.4}


def test_reader_gives_a_form_its_pages_and_marks_stale(tmp_path):
    key_index = tmp_path / "index.json"
    key_index.write_text("[]")
    f = tmp_path / "light_misses.json"
    f.write_text(json.dumps({"built": {"when": "2026-11-04 21:00", "key_index_mtime": key_index.stat().st_mtime},
                             "forms": {"lib__x": {"3": {"missed": [{"code": "b", "rect": [1, 2, 3, 4], "cause": "jev"}],
                                                        "junk": [{"rect": [5, 6, 7, 8], "jev": 0.7}]}}}}))
    got = R.for_form("lib__x", f, key_index)
    assert got["missed"][0]["page"] == 3 and got["junk"][0]["page"] == 3 and got["stale"] is False
    assert R.for_form("lib__other", f, key_index) is None
    t = key_index.stat().st_mtime + 60                   # the tuning set rebuilt after the file
    os.utime(key_index, (t, t))
    assert R.for_form("lib__x", f, key_index)["stale"] is True


def test_no_file_no_layer(tmp_path):
    assert R.for_form("lib__x", tmp_path / "none.json", tmp_path / "index.json") is None


def test_counts_per_form(tmp_path):
    f = tmp_path / "light_misses.json"
    f.write_text(json.dumps({"built": {}, "forms": {"lib__x": {"1": {"missed": [{}, {}], "junk": [{}]},
                                                             "2": {"missed": [{}], "junk": []}}}}))
    assert R.counts(f) == {"lib__x": {"missed": 3, "junk": 1}}
