"""form_run passes --rebuild-set to the loop (2026-10-26: case sets built under another pymupdf / tesseract)."""
from petey.validate import form_run


def test_rebuild_set_reaches_the_run(monkeypatch):
    got = {}
    monkeypatch.setattr(form_run, "run", lambda form, blank, **kw: got.update(kw, form=form))
    form_run.main(["--form", "x", "--blank", "x.pdf", "--reloop", "--rebuild-set"])
    assert got["form"] == "x" and got["reloop"] and got["rebuild_set"]
    form_run.main(["--form", "x", "--blank", "x.pdf"])
    assert got["rebuild_set"] is False
