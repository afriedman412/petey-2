"""Hand review of a blueprint against its blank: a web page that draws every field's rect on the rendered page and
takes accept / flag / a one-line note per field. The person's verdicts are the fixture the loop cannot make for
itself (Andrew, 2026-10-02: a working blueprint is a working blueprint; the promotion rule needs a check outside
the loop). Adapted from petey-master's `petey-eval/scripts/label_server.py`, which asked a person to type labels;
this asks them to judge the ones a blueprint already has.

    PYTHONPATH=. venv/bin/python -m petey_review.hand_review [--port 5005]      # then open http://127.0.0.1:5005/
    PYTHONPATH=. venv/bin/python -m petey_review.hand_review --summary          # verdicts so far, per blueprint

Blueprints offered: the dataset's sections (`petey_dataset.SOURCES`: the library, the judge-eval side copies, the
benchmark's sections, ...). Verdicts go to `runs/hand_review/<id>.json` (`petey_dataset.verdicts`) with the
blueprint's path, sha and build stamp, and are keyed by field name; a verdict written against one version of the
file is reported as stale when the file changes. Since 2026-10-13 a correction saved on the page goes into the
page's working copy of the blueprint at once (`draft.py`); the header's save writes the blueprint.

Keys on the page: a accept, f flag, c clear, n / p next and previous field, u toggle unreviewed only, 1-9 page.
Every verdict saves immediately.

Fields come in risk order by default (2026-10-05): each carries its witness tier from `witness.py` (contested,
unknown, single, settled; computed from the blueprint, the blank, the cached class map and the last run, no API
calls), contested first, and the panel shows which witness disagreed and why. "accept settled" accepts every
unreviewed settled field in one step, with the note `bulk: settled`, so a later calibration can tell those verdicts
from looked-at ones. Reading order is one click away.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

import yaml

import petey_dataset as D
from petey.paths import BLUEPRINTS, RUNS, SOURCE_PDFS
from petey.synth.boxes import FINDER_LABEL
from petey.validate import witness
from petey_dataset import HAND_REVIEW, blueprints
from petey_dataset.blueprints import SOURCES, blueprint_paths, page_sizes, resolve_blank, reviewable, sha as _sha, \
    warm_parsed, working_path
from petey_dataset.verdicts import (FORM_NOTES, LOCK as _VERDICT_LOCK, checked, form_notes, load_verdicts, new_to_check,  # noqa: F401
                                    reset_verdicts, set_form_note,
                                    stamp_structure, structure, structure_ok, unstamp_structure, verdict_path,
                                    write_verdicts as _write_verdicts)

OUT = HAND_REVIEW
PARSED = blueprints.PARSED
_parsed_path, _load, _stale = blueprints._parsed_path, blueprints.load, blueprints.stale


DPI = 110
LAUNCH_TIERS = D.launch_tiers()


def _check_counts(bp: dict) -> dict:
    """The page check's current flags on a blueprint, split as the review page grades them (witness.grade):
    errors (wrong name / type / other) and suggestions (captions, grouping, not a field)."""
    if not bp.get("x_petey_page_check"):
        return {}
    from petey.validate.page_check import verdicts
    from petey.validate.witness import PAGE_CHECK_SUGGESTIONS
    fl = [v for v in verdicts(bp).values() if v.get("verdict") == "flag"]
    sug = sum(1 for v in fl if v.get("problem") in PAGE_CHECK_SUGGESTIONS)
    return {"check_errors": len(fl) - sug, "check_suggestions": sug}


def field_rows(bp: dict) -> list[dict]:
    rows = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        rects, options = [], []
        if spec.get("widgets"):
            for on, w in spec["widgets"].items():
                if w.get("rect") and w.get("page"):
                    rects.append({"page": w["page"], "rect": w["rect"]})
                    options.append({"on_state": on, "caption": w.get("caption"), "page": w["page"], "rect": w["rect"]})
        else:
            w = spec.get("widget") or {}
            if w.get("rect") and w.get("page"):
                rects.append({"page": w["page"], "rect": w["rect"]})
        if not rects:
            continue
        rv = spec.get("x_petey_review") or {}
        # a dropdown's entries, shown and corrected like a group's options (no boxes of their own)
        choices = ([{"key": k, "caption": (o or {}).get("caption"), "stored": (o or {}).get("stored")}
                    for k, o in spec["options"].items()] if isinstance(spec.get("options"), dict) and not spec.get("widgets") else [])
        rows.append({
            "name": name, "id": spec.get("x_petey_id"), "page": rects[0]["page"], "rects": rects, "options": options,
            "choices": choices,
            "type": spec.get("type"), "semantic_type": spec.get("semantic_type"), "pattern": spec.get("pattern"),
            "values": spec.get("values"), "description": spec.get("description"),
            "path": (spec.get("widget") or {}).get("path") or next(iter(spec.get("widgets", {}).values()), {}).get("path"),
            "loop": ({"changed": rv.get("changed"), "reason": rv.get("reason"), "old_name": rv.get("old_name"),
                      "before": rv.get("before")} if rv else None),
            "adjudication": spec.get("x_petey_adjudication"),
            "claude": claude_change(spec),
            # expected to be hand-written (signature, initials, printed name), text fields only (2026-10-31)
            "printed": _printed(spec),
        })
    rows.sort(key=lambda r: (r["page"], round(r["rects"][0]["rect"][1] / 6), r["rects"][0]["rect"][0]))
    return rows


def _printed(spec: dict) -> Optional[bool]:
    """True / False on a text field (printed or not), None on a choice: the Review tab's printed toggle."""
    from petey.validate.printed_fields import is_printed, is_text
    return is_printed(spec) if is_text(spec) else None


def identifiers(bid: str, bp: dict) -> dict:
    """{field: (identifiers, flags)}: the parts the field name is printed from (docs/NAMING.md "Identifiers",
    `field_identifiers.read_form`): stored on the field once edited or filled, else read from the name."""
    try:
        from petey.validate import field_identifiers
        return field_identifiers.read_form(bid, bp)
    except Exception as e:                      # a page without identifiers is still a review page
        print(f"  identifiers: {e}")
        return {}


def claude_change(spec: dict) -> Optional[dict]:
    """What Claude's pass did to a field (`eval/claude_pass_apply.py`): {kind, why, from, when}, or None."""
    if not isinstance(spec, dict):
        return None
    he = spec.get("x_petey_hand_edit") or {}
    # clearing person_name alone needs no review (Andrew, 2026-10-14): it changed nothing the field holds
    if he.get("by") == "claude" and (he.get("why") or "").startswith(("person_name is no longer assigned",
                                                                       "the pattern of its semantic type")):
        return None                             # ... nor the pattern a semantic type brings with it
    if he.get("by") == "claude":
        return {"kind": he.get("kind") or "wrong", "why": he.get("why"), "from": (he.get("from") or {}).get("name"),
                "when": he.get("when")}
    ad = spec.get("x_petey_added") or {}
    if ad.get("name_from") == "claude":
        return {"kind": "add", "why": ad.get("why"), "from": None, "when": ad.get("when")}
    return None


def _git(*args: str, cwd: Path = BLUEPRINTS.parent) -> str:
    try:
        return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd, timeout=10).stdout.strip()
    except Exception:
        return ""


# where the library was labeled before the port (petey-master's widget-mapper repo, no remote); read when present
ORIGIN_BLUEPRINTS = Path.home() / "Documents" / "code" / "petey-master" / "widget-mapper" / "blueprints"


def git_dates(repo: Path, subdir: str) -> dict[str, dict]:
    """`{file name: {first, last, who}}` for every file git has seen under `subdir`, from one `git log` (the picker
    lists ~230 blueprints; a call per file would undo the fast startup).

    Renames and copies are followed (widget-mapper's `acord25.bpt` was copied from `acord25_blank.bpt`, two months
    older): history runs newest first, and at a rename or copy the old name's earlier commits are credited to the
    new file too; `first_as` names the file at its first commit when that differs."""
    out: dict[str, dict] = {}
    alias: dict[str, list[str]] = {}       # a name in older history -> the current files it became
    log = _git("log", "--format=@@%ad|%an", "--date=format:%Y-%m-%d", "--name-status", "-M", "-C",
               "--find-copies-harder", "--", subdir, cwd=repo)
    when = who = None

    def credit(name: str, as_name: str) -> None:
        for t in alias.get(name, [name]):
            rec = out.setdefault(t, {"last": when, "who": who})
            rec["first"] = when             # newest first: the last one seen is the first commit
            if as_name != t:
                rec["first_as"] = as_name
            else:
                rec.pop("first_as", None)

    for line in log.splitlines():
        if line.startswith("@@"):
            when, who = line[2:].split("|", 1)
            continue
        parts = line.split("\t")
        if len(parts) == 3 and parts[0][:1] in "RC":
            old, new = Path(parts[1]).name, Path(parts[2]).name
            credit(new, new)
            alias[old] = list(dict.fromkeys(alias.get(old, [old] if parts[0][0] == "C" else [])
                                            + alias.get(new, [new])))
        elif len(parts) == 2:
            name = Path(parts[1]).name
            credit(name, name)
    return out


def age(p: Path, bp: dict, here: dict[str, dict], origin: dict[str, dict]) -> dict:
    """Short provenance for the picker: who made the blueprint and when, and what it was last validated on."""
    a = bp.get("authoring") or {}
    g = here.get(p.name) if p.parent.resolve() == BLUEPRINTS.resolve() else None
    o = origin.get(p.name) if p.parent.resolve() == BLUEPRINTS.resolve() else None
    if a:
        by = (a.get("model") or a.get("method") or "?").replace("claude-", "")
        when = (a.get("when") or "")[:10] or (g or {}).get("first")
    elif o:
        by, when = "petey-master", o.get("first")
        if o.get("first_as"):
            by += f" (as {o['first_as']})"
    else:
        by, when = "unrecorded", (g or {}).get("first")
    if not when:
        when = time.strftime("%Y-%m-%d", time.localtime(p.stat().st_mtime))
    b = bp.get("x_petey_build") or {}
    finder = b.get("finder_label") or (b.get("finder") or "").split("+")[0] or None
    return {"by": by, "when": when, "validated": (b.get("when") or "")[:10] or None, "finder": finder,
            "finder_current": finder == FINDER_LABEL if finder else None}


def added(p: Path, bp: dict, here: dict[str, dict]) -> Optional[str]:
    """The day the form came into the library (Andrew, 2026-11-04: "can you also add an 'added' date to the index"):
    the download date a scraped or hand-picked form records, else the library file's first commit, else the file's
    creation (kept through saves). Day only: the downloads record no time."""
    d = (bp.get("x_petey_source") or {}).get("date")
    if d:
        return str(d)[:10]
    g = here.get(p.name) if p.parent.resolve() == BLUEPRINTS.resolve() else None
    if g and g.get("first"):
        return g["first"][:10]
    st = p.stat()
    return time.strftime("%Y-%m-%d", time.localtime(getattr(st, "st_birthtime", st.st_mtime)))


def _commits(path: Path, cwd: Path) -> list[dict]:
    log = _git("log", "--follow", "--format=%h|%ad|%an|%s", "--date=format:%Y-%m-%d %H:%M", "--", str(path), cwd=cwd)
    return [dict(zip(("commit", "when", "who", "subject"), r.split("|", 3))) for r in log.splitlines()]


def made(p: Path, bp: dict) -> dict:
    """When the blueprint was made and by whom, from whatever the file and the repo record (Andrew, 2026-10-05):
    the labeler's `authoring` block (method, model; `when` since 2026-10-05), git's first and latest commit of the
    file with their authors (the library came over from petey-master, so its first commit here is the port, not
    the labeling), the models whose edits the loop kept, and the latest validation's build stamp. Side copies under
    runs/ are outside git; their file time stands in."""
    out: dict = {}
    a = bp.get("authoring") or {}
    if a:
        out["labeler"] = {k: a.get(k) for k in ("method", "model", "geometry", "when") if a.get(k)}
    rows = _commits(p, BLUEPRINTS.parent)
    if rows:
        out["git_first"], out["git_last"], out["git_commits"] = rows[-1], rows[0], len(rows)
        if subprocess.run(["git", "diff", "--quiet", "--", str(p)], cwd=BLUEPRINTS.parent).returncode:
            out["uncommitted"] = True
    else:
        out["file_time"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime))
    origin = ORIGIN_BLUEPRINTS / p.name
    if p.parent.resolve() == BLUEPRINTS.resolve() and origin.exists():
        orows = _commits(origin, ORIGIN_BLUEPRINTS.parent)
        if orows:
            out["origin"] = {"repo": "petey-master/widget-mapper", "first": orows[-1], "last": orows[0]}
    reviewers = collections.Counter((s.get("x_petey_review") or {}).get("model") for s in (bp.get("fields") or {}).values()
                                    if isinstance(s, dict) and s.get("x_petey_review"))
    if reviewers:
        out["loop_edits"] = dict(reviewers)
    b = bp.get("x_petey_build") or {}
    if b:
        out["validated"] = {k: b.get(k) for k in ("when", "run", "generator", "case_set") if b.get(k)}
    return out


class State:
    def __init__(self) -> None:
        self.paths = blueprint_paths()
        self.png: dict[tuple[str, int], bytes] = {}
        self.sizes: dict[str, list[dict]] = {}
        self._index: dict[str, dict] = {}
        self._witness: dict[tuple, dict] = {}
        self._git_here: dict[str, dict] = {}
        self._git_origin: dict[str, dict] = {}

    def path(self, bid: str) -> Optional[Path]:
        return working_path(bid, self.paths)

    def _entry(self, bid: str, notes: Optional[dict] = None) -> dict:
        from petey.validate import draft
        real, p = self.paths[bid], self.path(bid)
        focus = (_focus().get("forms") or {}).get(bid)
        bp = _load(p)
        v = load_verdicts(bid); vs = v.get("verdicts") or {}
        fields = [n for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)]
        return {"id": bid, "source": bid.split("__")[0], "form": p.stem, "fields": len(fields),
                "accepted": sum(1 for n in fields if vs.get(n, {}).get("verdict") == "accept"),
                "flagged": sum(1 for n in fields if vs.get(n, {}).get("verdict") == "flag"),
                "stale": bool(v) and v.get("blueprint_sha") != _sha(p),
                "checked": checked(v, p, bp), "structure": structure(v, p),
                "new_fields": new_to_check(v, p, bp),
                "finder": (bp.get("x_petey_build") or {}).get("finder"),
                "age": age(real, bp, self._git_here, self._git_origin),
                "added": added(real, bp, self._git_here),
                # a library form run again through the current code (scripts/run_form.sh, form_run.py): the picker
                # lists these first, with the page check's count and whether the loop stopped on its own
                "rerun": bid.startswith("je__") and (BLUEPRINTS / f"{p.stem}.bpt").exists(),
                "page_check_flags": (bp.get("x_petey_page_check") or {}).get("flagged"),
                **_check_counts(bp),
                "launch": LAUNCH_TIERS.get(Path(str(bp.get("source_pdf") or "")).name) if bid.startswith("je__") else None,
                "run": {k: (bp.get("x_petey_run") or {}).get(k) for k in ("stable", "stop")}
                       if bp.get("x_petey_run") else None,
                # listed first in the picker: forms with name-check flags still to confirm (runs/hand_review/focus.json)
                "focus": focus,
                # the home page's table (2026-10-15)
                "collection": collection(bp), "pages": len(bp.get("source_pages") or []) or None,
                "desc": describe(bp), "blank": bp.get("source_pdf_hash"),
                "touched": v.get("updated"), "note": (notes if notes is not None else form_notes()).get(bid),
                # cleared: through the automated passes (eval/passes_record.py), the home page's pipeline stage
                "passes": passes_record().get(bid),
                "draft": draft.status(bid, real)}

    def index(self) -> None:
        """Read every blueprint once at startup; the listing is served from memory and one entry is refreshed
        when its verdicts change."""
        t0 = time.time()
        self._git_here = git_dates(BLUEPRINTS.parent, "blueprints")
        self._git_origin = git_dates(ORIGIN_BLUEPRINTS.parent, "blueprints") if ORIGIN_BLUEPRINTS.exists() else {}
        notes = form_notes()
        self._index = {bid: self._entry(bid, notes) for bid in self.paths}
        save_descriptions()
        print(f"  indexed {len(self._index)} blueprints in {time.time() - t0:.1f}s")

    def listing(self) -> list[dict]:
        if not self._index:
            self.index()
        return list(self._index.values())

    def detail(self, bid: str) -> Optional[dict]:
        p = self.path(bid)
        if p is None:
            return None
        real = self.paths[bid]
        bp = _load(p)
        blank = resolve_blank(bp)
        pages = page_sizes(bp, blank)
        self.sizes[bid] = pages
        v = load_verdicts(bid)
        rows = field_rows(bp)
        wit = self.witnesses(bid, p)
        cs = claude_suggestions(bid)
        ids = identifiers(bid, bp)
        for r in rows:
            w = (wit.get("fields") or {}).get(r["name"]) or {}
            r["tier"], r["witnesses"], r["why"] = w.get("tier"), w.get("witnesses"), w.get("why") or []
            r["why"] = r["why"] + [{"kind": "suggestion", **x} for x in cs.get(r["name"]) or []]
            ident, flags = ids.get(r["name"]) or ({}, [])
            r["identifiers"], r["identifier_flags"] = ident, flags
            r["identifiers_stored"] = isinstance((bp["fields"].get(r["name"]) or {}).get("x_petey_identifiers"), dict)
        return {"id": bid, "path": str(real), "working": str(p) if p != real else None,
                "blank": str(blank) if blank else None, "sha": _sha(p),
                "build": bp.get("x_petey_build"), "pages": pages, "fields": rows,
                "verdicts": v.get("verdicts") or {}, "stale": bool(v) and v.get("blueprint_sha") != _sha(p),
                "agent_running": _flag_agent().running(bid), "agent_todo": len(_flag_agent().todo(v)),
                "semantic_types": __import__("petey.semantic_types", fromlist=["registered_names"]).registered_names(),
                "witness_run": wit.get("run"), "witness_error": wit.get("error"), "made": made(real, bp),
                "checked": checked(v, p, bp), "structure": structure(v, p), "dpi": DPI}

    def witnesses(self, bid: str, p: Path) -> dict:
        """Per-field witnesses and tier (`witness.py`), once per blueprint version; no API calls."""
        key = (bid, _sha(p))
        if key not in self._witness:
            try:
                self._witness[key] = witness.witnesses(p)
            except Exception as e:                 # a page without tiers is still a review page
                self._witness[key] = {"fields": {}, "error": f"{type(e).__name__}: {e}"}
        return self._witness[key]

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key in self.png:
            return self.png[key]
        p = self.path(bid)
        if p is None:
            return None
        bp = _load(p)
        blank = resolve_blank(bp)
        if not blank or not blank.exists():
            return None
        import pymupdf
        doc = pymupdf.open(str(blank))
        try:
            if page < 1 or page > len(doc):
                return None
            png = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
        finally:
            doc.close()
        self.png[key] = png
        return png

    def put_verdicts(self, bid: str, incoming: dict, on_pending=None) -> dict:
        """Merge the page's verdicts into the record. `on_pending` is called before the record is written when it
        holds a correction not yet applied (the page opens its working copy there, so the copy's snapshot of the
        record predates the correction)."""
        with _VERDICT_LOCK:
            return self._put_verdicts(bid, incoming, on_pending)

    def _put_verdicts(self, bid: str, incoming: dict, on_pending=None) -> dict:
        p = self.path(bid)
        if p is None:
            raise KeyError(bid)
        real = self.paths[bid]
        bp = _load(p)
        cur = load_verdicts(bid)
        vs = cur.get("verdicts") or {}
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        fields = bp.get("fields") or {}
        for name, rec in (incoming.get("verdicts") or {}).items():
            # a correction for a field that is gone, asking for a name a field has: a repeat sent after the rename went
            # in (2026-10-13, ACORD 130: a second save while the page reloaded left three dead 'held-back' entries)
            if name not in fields and isinstance((rec or {}).get("edit"), dict) and (rec["edit"].get("name") or "") in fields:
                continue
            if rec is None or not rec.get("verdict"):
                vs.pop(name, None)
            else:
                prev = vs.get(name) or {}
                vs[name] = {"verdict": rec["verdict"], "note": (rec.get("note") or "").strip()[:300], "when": now}
                edit = clean_edit(name, (bp.get("fields") or {}).get(name) or {}, rec.get("edit"))
                if edit:
                    vs[name]["edit"] = edit
                elif prev.get("applied") and rec.get("edit") == prev.get("edit"):
                    edit = vs[name]["edit"] = prev["edit"]      # an applied correction no longer differs from the file
                if edit and prev.get("applied") and edit == prev.get("edit"):
                    vs[name]["applied"] = prev["applied"]       # re-saving a verdict keeps it applied
                if prev.get("agent") and (prev["agent"].get("for_note") or "") == vs[name]["note"]:
                    vs[name]["agent"] = prev["agent"]           # the post-review agent's proposal survives re-saves
        if on_pending is not None and any(x.get("edit") and not x.get("applied") for x in vs.values()):
            on_pending()
        sha = _sha(p)
        out = {"blueprint": str(real), "form": real.stem, "blueprint_sha": sha, "build": bp.get("x_petey_build"),
               "updated": now, "verdicts": vs}
        if cur.get("structure"):
            out["structure"] = cur["structure"]          # "accept structure" stays through verdict saves
        # checked: every reviewable field has a verdict. The first moment that holds is kept (re-saving a note
        # does not move it); clearing a verdict, or completing it again on a changed file, starts over
        names = reviewable(bp)
        if names and all(vs.get(n, {}).get("verdict") for n in names):
            prev = cur.get("checked") or {}
            out["checked"] = (prev if prev.get("blueprint_sha") == sha else
                              {"when": now, "blueprint_sha": sha})
            out["checked"].update(fields=len(names), flagged=sum(1 for n in names if vs[n]["verdict"] == "flag"))
        elif cur.get("checked") or cur.get("was_checked"):
            # once fully checked, remembered through saves of a form with new fields (`new_to_check`)
            out["was_checked"] = {"when": (cur.get("checked") or cur.get("was_checked") or {}).get("when")}
        OUT.mkdir(parents=True, exist_ok=True)
        _write_verdicts(bid, out)
        if self._index:
            self._index[bid] = self._entry(bid)
        return out


from petey.validate.edits import EDIT_TYPES, SLUG as _SLUG, clean_edit, edit_fields  # noqa: E402,F401


def claude_suggestions(bid: str) -> dict:
    """runs/claude_pass/suggestions/<id>.json: Claude's unsure changes, {field: [{"text", "fix"}]}, shown under the
    field with a "use" button (`eval/claude_pass_apply.py`, 2026-10-13); {} when there are none."""
    p = RUNS / "claude_pass" / "suggestions" / f"{bid}.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


_PDF_DIRS: dict[str, str] = {}
_PASSES: dict = {"mtime": None, "rec": {}}


def passes_record() -> dict[str, dict]:
    """runs/hand_review/passes.json `{bid: {when, steps}}` (eval/passes_record.py), read again only when it changes."""
    p = OUT / "passes.json"
    try:
        m = p.stat().st_mtime
    except OSError:
        return {}
    if _PASSES["mtime"] != m:
        try:
            _PASSES.update(mtime=m, rec=json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return _PASSES["rec"]
    return _PASSES["rec"]


DESC_CACHE = RUNS / "hand_review" / "form_descriptions.json"      # {blank sha: describe()}, kept across restarts
_DESC: dict[str, Optional[dict]] = {}
_DESC_NEW = [False]
FILE_LIKE = re.compile(r"\.(pdf|xlsx?|docx?)$|^(book|layout|untitled|document)\s*\d*$", re.I)
APP_PREFIX = re.compile(r"^microsoft \w+ - ", re.I)                # "Microsoft Word - EP-2 20251029_Final"


def _heading(page) -> str:
    """The largest-font lines in the top half of a page, top to bottom: the form's printed title, near enough."""
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            t = " ".join(sp["text"].strip() for sp in ln["spans"]).strip()
            if len(t) > 2 and any(c.isalpha() for c in t) and ln["bbox"][1] < page.rect.height / 2:
                lines.append((max(sp["size"] for sp in ln["spans"]), ln["bbox"][1], t))
    if not lines:
        return ""
    top = max(sz for sz, _, _ in lines)
    return " ".join(t for sz, _, t in sorted(lines, key=lambda x: x[1]) if sz >= 0.8 * top)


def describe(bp: dict) -> Optional[dict]:
    """What the form is, for the home page (Andrew, 2026-10-15: "add a description to each form on the homepage so we
    can figure out what duplicates we have"; "the info for the PDF might be a good place to start"): the blank's PDF
    title, with its subject when that adds words; when the title is weak (under three words, or a file name such as
    Book1.xlsx), the largest print on page 1 too. {"text", "from"}; None without a blank, or a blank with no title
    and no text (a scanned page). Cached by blank (DESC_CACHE)."""
    if not _DESC and DESC_CACHE.exists():
        _DESC.update(json.loads(DESC_CACHE.read_text()))
    key = bp.get("source_pdf_hash") or str(bp.get("source_pdf"))
    if key in _DESC:
        return _DESC[key]
    path = resolve_blank(bp)
    if not path:
        return None
    import pymupdf
    doc = pymupdf.open(path)
    info = doc.metadata or {}
    clean = lambda v: " ".join(str(v or "").split())
    title, subject = clean(info.get("title")), clean(info.get("subject"))
    if APP_PREFIX.search(title):
        title = APP_PREFIX.sub("", title).replace("_", " ")
        title = " ".join(title.split()[:2])         # the file name's form number; its date and "Final" say nothing
    if FILE_LIKE.search(title):
        title = ""
    words = lambda t: set(re.findall(r"[a-z0-9]+", t.lower()))
    parts, src = [title] if title else [], ["pdf title"] if title else []
    if subject and not words(subject) <= words(title):
        parts.append(subject)
        src.append("subject")
    if len(title.split()) < 3 and len(doc):
        head = _heading(doc[0])
        if head and not words(head) <= words(" ".join(parts)):
            parts.append(head if len(head) <= 110 else head[:110].rsplit(" ", 1)[0] + " …")
            src.append("page 1")
    out = {"text": " · ".join(parts), "from": " + ".join(src)} if parts else None
    _DESC[key] = out
    _DESC_NEW[0] = True
    return out


def save_descriptions() -> None:
    if _DESC_NEW[0]:
        DESC_CACHE.write_text(json.dumps(_DESC, indent=0, ensure_ascii=False), encoding="utf-8")
        _DESC_NEW[0] = False


def collection(bp: dict) -> Optional[str]:
    """The source_pdfs folder the form's blank sits in (tax, uscis, ca_courts, ...; "" at the top), for the home
    page: one walk of source_pdfs, not a search per blueprint."""
    src = str(bp.get("source_pdf") or "")
    if not src:
        return None
    if "/" in src:
        return src.split("/")[0]
    if not _PDF_DIRS:
        for f in SOURCE_PDFS.rglob("*"):
            if f.is_file() and "source_pdfs_old" not in f.parts:
                rel = f.relative_to(SOURCE_PDFS).parts
                _PDF_DIRS.setdefault(f.name, rel[0] if len(rel) > 1 else "")
    return _PDF_DIRS.get(Path(src).name)


def _focus() -> dict:
    """runs/hand_review/focus.json: `{"why": ..., "forms": {bid: count}}`, the review list put at the top of the
    picker (2026-10-13: the name-check flags on fields not yet confirmed, form by form); {} when there is none."""
    p = OUT / "focus.json"
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}


def apply_edits(bid: str, *, dry: bool = False, log=print) -> int:
    """Write the review record's name / type corrections into the blueprint. A rename keeps the field's position;
    a type change drops what no longer fits (`pattern` unless the field stays a string; `semantic_type` on boolean /
    category / multi_category; `values` unless one of those, and an option group turned into one gets its keys as
    `values` when it has none). Each field records `x_petey_hand_edit` {when, from, to, record}; the review
    record follows the rename; a form_run blueprint gets a `hand_edit` round in its run record. Writes the working
    copy while one is open (`draft.py`)."""
    with _VERDICT_LOCK:
        return _apply_edits(bid, dry=dry, log=log)


def _apply_edits(bid: str, *, dry: bool = False, log=print) -> int:
    p = working_path(bid)
    if p is None:
        raise SystemExit(f"{bid}: no such blueprint")
    rec = load_verdicts(bid)
    vs = rec.get("verdicts") or {}
    bp = _load(p)
    fields = bp.get("fields") or {}
    edits = {n: v["edit"] for n, v in vs.items() if v.get("edit") and not v.get("applied") and n in fields}
    if not edits:
        log(f"{bid}: no corrections to apply")
        return 0
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    renames = {}
    for n, e in edits.items():
        to = e.get("name", n)
        if to != n and to in fields and to not in edits:
            raise SystemExit(f"{bid}: renaming {n} to {to} would collide with an existing field")
        log(f"  {n}: " + ", ".join(f"{k} {(n if k == 'name' else fields[n].get(k))!r} -> "
                                   f"{({x: d for x, d in v.items()} if k == 'options' else v)!r}" for k, v in e.items()))
        renames[n] = to
    if dry:
        return len(edits)
    out = edit_fields(fields, edits, renames, now, f"runs/hand_review/{bid}.json")
    bp["fields"] = out
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    run = (bp.get("x_petey_run") or {}).get("record")
    rp = RUNS.parent / run if run else None
    if rp is not None and rp.exists():
        r = json.loads(rp.read_text())
        changed = {renames[n]: out[renames[n]] for n in edits}
        r["rounds"].append({"round": len(r["rounds"]), "stage": "hand_edit", "when": now, "changed": changed,
                            "removed": [n for n in edits if renames[n] != n], "renamed": {renames[n]: n for n in edits
                                                                                    if renames[n] != n}})
        rp.write_text(json.dumps(r, indent=1, ensure_ascii=False, default=str))
    for n in edits:                            # the record follows the rename; the correction is now applied
        v = vs.pop(n)
        v["applied"] = now
        vs[renames[n]] = v
    old_sha = rec.get("blueprint_sha")
    rec.update(verdicts=vs, blueprint_sha=_sha(p), updated=now)
    ck = rec.get("checked")
    if isinstance(ck, dict) and ck.get("blueprint_sha") == old_sha:
        ck["blueprint_sha"] = rec["blueprint_sha"]       # applying the corrections does not undo the check
    _write_verdicts(bid, rec)
    log(f"{bid}: {len(edits)} correction(s) applied to {p}")
    return len(edits)


def summary() -> None:
    paths = blueprint_paths()
    rows = []
    for vp in sorted(OUT.glob("*.json")):
        v = json.loads(vp.read_text(encoding="utf-8")); vs = v.get("verdicts") or {}
        p = working_path(vp.stem, paths)
        stale = p is None or v.get("blueprint_sha") != _sha(p)
        acc = sum(1 for r in vs.values() if r.get("verdict") == "accept")
        flg = [(n, r.get("note", "")) for n, r in vs.items() if r.get("verdict") == "flag"]
        ck = checked(v, p, _load(p)) if p is not None else None
        rows.append((vp.stem, acc, len(flg), stale, v.get("updated"), flg, ck))
    print(f"{'blueprint':40} {'accepted':>8} {'flagged':>7} {'stale':>5} {'checked':>8}  updated")
    for bid, acc, nf, stale, upd, flg, ck in rows:
        print(f"{bid[:40]:40} {acc:8} {nf:7} {'yes' if stale else '':>5} {'yes' if ck else '':>8}  {upd}")
        for n, note in flg[:8]:
            print(f"      flag  {n[:40]:40} {note[:80]}")
    if not rows:
        print(f"no verdicts yet under {OUT}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    ap.add_argument("--apply", metavar="ID", help="write the review record's name / type corrections into blueprint ID "
                    "(e.g. je__acord_126); with --dry, list them only")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    if args.apply:
        apply_edits(args.apply, dry=args.dry)
        return 0
    if args.summary:
        summary()
        return 0
    from petey_review.blueprint_review import serve
    return serve(args.port, "review", not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
