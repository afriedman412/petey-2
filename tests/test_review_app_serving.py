"""The React review page (petey/validate/review_app, Andrew 2026-10-26: "let's build the current app in react"): the
server builds it when its code changed since the last build and serves it at /next/ beside the old page."""
import os
import time

from petey.validate import blueprint_review as br


def _app(tmp_path):
    app = tmp_path / "review_app"
    (app / "src").mkdir(parents=True)
    (app / "src" / "main.tsx").write_text("x")
    (app / "package.json").write_text("{}")
    return app


def _built(app):
    dist = app / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<div id=root></div>")
    (dist / "assets" / "index-abc.js").write_text("js")
    return dist


def test_stale_without_a_build_and_after_a_code_change(tmp_path):
    app = _app(tmp_path)
    assert br.app_stale(app)
    dist = _built(app)
    later = time.time() + 5
    os.utime(dist / "index.html", (later, later))
    assert not br.app_stale(app)
    os.utime(app / "src" / "main.tsx", (later + 5, later + 5))       # a file of its code edited after the build
    assert br.app_stale(app)


def test_up_to_date_builds_nothing(tmp_path, monkeypatch):
    app = _app(tmp_path)
    later = time.time() + 5
    os.utime(_built(app) / "index.html", (later, later))
    monkeypatch.setattr(br.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ran npm")))
    assert br.build_app(app) == "up to date"


def test_no_npm_is_said_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(br.shutil, "which", lambda name: None)
    assert br.build_app(_app(tmp_path)).startswith("not built: npm not found")


def test_next_serves_assets_and_otherwise_the_page(tmp_path):
    dist = _built(_app(tmp_path))
    assert br.app_file("/next/assets/index-abc.js", dist) == (dist / "assets" / "index-abc.js").resolve()
    assert br.app_file("/next", dist) == dist / "index.html"
    assert br.app_file("/next/", dist) == dist / "index.html"
    assert br.app_file("/next/review/lib__fw9", dist) == dist / "index.html"   # not a file: the page
    (tmp_path / "secret.txt").write_text("no")
    assert br.app_file("/next/../../secret.txt", dist) == dist / "index.html"   # nothing outside dist


def test_nothing_built_serves_nothing(tmp_path):
    assert br.app_file("/next/", tmp_path / "dist") is None
