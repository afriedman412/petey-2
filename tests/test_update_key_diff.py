"""The update-key skill's comparison script: what a rebuild changed in each set, and the page files it left behind."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / ".claude" / "skills" / "update-key" / "scripts" / "key_diff.py"
spec = importlib.util.spec_from_file_location("key_diff", SCRIPT)
kd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kd)


def _page(pid, n, kinds=None, groups=()):
    fields = [{"id": f"f{i}", "rect": [i * 10, 0, i * 10 + 8, 8], "kind": (kinds or {}).get(i, "text")} for i in range(n)]
    return {"page_id": pid, "fields": fields, "groups": [list(g) for g in groups]}


def _write(d, pages):
    d.mkdir(parents=True)
    (d / "index.json").write_text(json.dumps([{"page_id": p["page_id"]} for p in pages]))
    for p in pages:
        (d / f"{p['page_id']}.json").write_text(json.dumps(p))


def test_forms_in_pages_changed_totals_and_stale_files(tmp_path, capsys):
    before, live = tmp_path / "before", tmp_path / "live"
    _write(before / "key", [_page("a__f__p1", 3), _page("a__f__p2", 2)])
    _write(before / "dev_key", [_page("a__f__p3", 4)])
    # after: page 1 gained a field and a split value, a new form b came in, page 2 unchanged; a stale page file left over
    _write(live / "key", [_page("a__f__p1", 4, groups=[("f0", "f1")]), _page("a__f__p2", 2),
                          _page("b__g__p1", 5, kinds={0: "choice", 1: "choice", 2: "printed"}, groups=[("f0", "f1")])])
    _write(live / "dev_key", [_page("a__f__p3", 4)])
    (live / "key" / "zz__old__p1.json").write_text("{}")
    (live / "key" / "pages").mkdir()
    (live / "key" / "pages" / "zz__old__p1.pdf").write_bytes(b"")
    (live / "key" / "pages" / "a__f__p1.pdf").write_bytes(b"")

    assert kd.main(["--before", str(before), "--key", str(live / "key"), "--dev", str(live / "dev_key")]) == 0
    out = capsys.readouterr().out
    assert "benchmark key: forms 1 -> 2, pages 2 -> 3" in out
    assert "forms in: 1 (b__g)" in out
    assert "pages in: 1; pages out: 0" in out
    assert "pages kept whose fields changed: 1 (a__f__p1 3->4)" in out
    assert "fields: 5 -> 11" in out and "printed: 0 -> 1" in out
    assert "option groups: 0 -> 1" in out and "split values: 0 -> 1" in out
    assert "tuning set: forms 1 -> 1, pages 1 -> 1" in out
    assert "2 page files not in the index any more (--prune removes them)" in out
    assert (live / "key" / "zz__old__p1.json").exists()

    kd.main(["--before", str(before), "--key", str(live / "key"), "--dev", str(live / "dev_key"), "--prune"])
    assert not (live / "key" / "zz__old__p1.json").exists()
    assert not (live / "key" / "pages" / "zz__old__p1.pdf").exists()
    assert (live / "key" / "pages" / "a__f__p1.pdf").exists()
