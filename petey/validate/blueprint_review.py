"""Blueprint review: one web page for checking a blueprint against its blank, in three modes over the same picker,
page and zoom:

    Review       accept / flag / note per field, risk-first by witness tier   (`hand_review`, runs/hand_review/)
    Groups       confirm option groups, drag boxes to regroup, drag text boxes together to combine them
                                                                                (`group_review`, runs/group_review/)
    Add / remove suggestions and drawn areas -> proposed fields; not-a-field; remove a field
                                                                                (`field_add`, runs/field_add/)

    PYTHONPATH=. venv/bin/python -m petey.validate.blueprint_review [--port 5005] [--mode review|groups|add]

Each mode's logic, record and command line stay in its own module; this file serves the one page and routes to
them. The old entry points (`python -m petey.validate.hand_review`, `group_review`, `field_add` with no subcommand)
open this page in their mode.

One working copy (2026-10-13, Andrew: "everything should be reading from the same source"): the page's first change
to a blueprint opens a copy of it (`draft.py`), and every change is applied to the copy at once, so all three modes
show the same file: a Review correction or removal as it is saved, an Add / remove change as it is saved, a Groups
regrouping when you leave Groups (or press its apply button; mid-regrouping states are often not valid yet). The
header's "save blueprint" copies it over the blueprint; "discard" throws it away and puts the three records back.
The modules' `--apply` command lines still write whichever file the page would (the copy while one is open).
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import pymupdf

from petey import web
from petey.validate import draft, field_add, group_review, hand_review
from petey.validate.retype import resolve_blank

HTML_PATH = Path(__file__).with_suffix(".html")
DPI = 144                      # option boxes are 8-10 pt; at 110 dpi (the old hand review) they are 12 px targets
MODES = ("review", "groups", "add")


class App:
    def __init__(self) -> None:
        self.review = hand_review.State()
        self.groups = group_review.State()
        self.add = field_add.State()
        self.paths = self.review.paths
        self.png: dict[tuple[str, int], bytes] = {}
        self.mtimes: dict[str, float] = {}

    def index(self) -> None:
        self.review.index()
        self.groups.index()
        self.mtimes = {bid: self.working(bid).stat().st_mtime for bid in self.paths}

    def working(self, bid: str) -> Path:
        return hand_review.working_path(bid, self.paths)

    def open_draft(self, bid: str) -> Path:
        return draft.ensure(bid, self.paths[bid])

    def follow(self, bid: str, before: str) -> None:
        """After a change the page made itself (a regrouping, fields added or removed), the Review and Add / remove
        records written against the file before it move to the file after it, so they do not read as stale. The
        Groups record is left alone: its units name fields, and a stale one is rebased by its boxes."""
        import json
        after = hand_review._sha(self.working(bid))
        for rp in (hand_review.verdict_path(bid), field_add.record_path(bid)):
            if not rp.exists():
                continue
            rec = json.loads(rp.read_text(encoding="utf-8"))
            if rec.get("blueprint_sha") != before:
                continue
            rec["blueprint_sha"] = after
            ck = rec.get("checked")
            if isinstance(ck, dict) and ck.get("blueprint_sha") == before:
                ck["blueprint_sha"] = after
            rp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")

    def refresh(self) -> None:
        """Re-read the picker rows of blueprints whose file changed since they were indexed (an --apply, a loop, an
        edit by hand): the indexes are built once at startup."""
        for bid in self.paths:
            m = self.working(bid).stat().st_mtime
            if self.mtimes.get(bid) == m:
                continue
            self.mtimes[bid] = m
            self.review._index[bid] = self.review._entry(bid)
            g = self.groups._entry(bid)
            if g:
                self.groups._index[bid] = g
            else:
                self.groups._index.pop(bid, None)

    def entry(self, bid: str) -> dict:
        """One picker row: what each mode has recorded for this blueprint."""
        r = self.review._index.get(bid) or self.review._entry(bid)
        g = self.groups._index.get(bid)
        rec = field_add.load_record(bid)
        return {**r,
                "groups": ({k: g[k] for k in ("groups", "orphans", "confirmed", "units", "combos", "stale")} if g else None),
                "add": {"added": len(rec.get("added") or []), "dismissed": len(rec.get("dismissed") or []),
                        "removed": len(rec.get("removed") or []),
                        "applied": sum(len(a.get("changes") or []) for a in rec.get("applied") or [])}}

    def apply_groups(self, bid: str) -> dict:
        """Groups' regrouping into the working copy (on leaving Groups, its apply button, or Save)."""
        before = hand_review._sha(self.open_draft(bid))
        try:
            pl = group_review.apply(bid)
        except SystemExit as e:                 # apply's refusals (stale record, plan errors) are SystemExit
            raise ValueError(str(e)) from None
        self.follow(bid, before)
        draft.log(bid, "groups", pl["changes"])
        self.refresh()
        return {"changes": pl["changes"], "entry": self.entry(bid)}

    def apply_review(self, bid: str) -> dict:
        """The record's corrections not yet applied, into the working copy. A refusal (a rename onto a name another
        field still has) leaves them pending and comes back as `apply_error`; applying again once the other field is
        renamed takes both."""
        vs = hand_review.load_verdicts(bid).get("verdicts") or {}
        if not any(v.get("edit") and not v.get("applied") for v in vs.values()):
            return {}
        self.open_draft(bid)
        lines: list[str] = []
        try:
            hand_review.apply_edits(bid, log=lines.append)
        except SystemExit as e:
            return {"apply_error": str(e)}
        changes = [ln.strip() for ln in lines if ln.startswith("  ")]
        draft.log(bid, "review", changes)
        self.refresh()
        return {"applied": changes}

    def apply_add(self, bid: str, out: dict) -> dict:
        """Add / remove's recorded additions and removals, into the working copy, when they plan cleanly."""
        if not out.get("changes") or out.get("errors"):
            return out
        before = hand_review._sha(self.open_draft(bid))
        try:
            pl = field_add.apply(bid) or {}
        except SystemExit as e:
            return {**out, "apply_error": str(e)}
        self.follow(bid, before)
        draft.log(bid, "add", pl.get("changes") or [])
        self.refresh()
        return {**out, "applied": pl.get("changes") or [], "changes": [], "skipped": pl.get("skipped") or []}

    def put_verdicts(self, bid: str, body: dict) -> dict:
        out = self.review.put_verdicts(bid, body, on_pending=lambda: self.open_draft(bid))
        ap = self.apply_review(bid)
        if ap.get("applied"):
            out = hand_review.load_verdicts(bid)
        return {**out, **ap, "entry": self.entry(bid)}

    def save_add(self, bid: str, body: dict) -> dict:
        if body.get("added") or body.get("removed"):
            self.open_draft(bid)
        out = self.apply_add(bid, self.add.save(bid, body))
        return {**out, "entry": self.entry(bid)}

    def save_draft(self, bid: str, force: bool = False) -> dict:
        """The header's save: whatever is still pending goes into the copy first (a Groups regrouping not applied
        yet); a correction that cannot be applied, or a regrouping or addition with errors, stops it."""
        p = self.working(bid)
        if p == self.paths[bid]:
            raise ValueError("no working copy open")
        bp = hand_review._load(p)
        _, units, _ = group_review.current_units(bid, bp, hand_review._sha(p))
        gp = group_review.plan(bp, units, resolve_blank(bp))
        if gp["errors"]:
            raise ValueError("Groups has errors to fix first:\n  " + "\n  ".join(gp["errors"]))
        if gp["changes"]:
            self.apply_groups(bid)
        self.apply_review(bid)                  # corrections saved before the working copy (the old apply button)
        vs = hand_review.load_verdicts(bid).get("verdicts") or {}
        fields = hand_review._load(self.working(bid)).get("fields") or {}
        stuck = [n for n, v in vs.items() if v.get("edit") and not v.get("applied") and n in fields]
        if stuck:
            raise ValueError(f"{len(stuck)} correction(s) could not be applied (a name another field has): "
                             + ", ".join(stuck))
        rec = field_add.load_record(bid)
        if rec.get("added") or rec.get("removed"):
            raise ValueError("Add / remove has changes that do not apply cleanly; see its change list")
        out = draft.save(bid, self.paths[bid], force)
        self.refresh()
        return {**out, "entry": self.entry(bid)}

    def discard_draft(self, bid: str) -> dict:
        out = draft.discard(bid, self.paths[bid])
        self.refresh()
        return {**out, "entry": self.entry(bid)}

    def listing(self) -> list[dict]:
        if not self.review._index:
            self.index()
        self.refresh()
        return [self.entry(bid) for bid in self.paths]

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key not in self.png:
            p = self.working(bid) if bid in self.paths else None
            blank = resolve_blank(hand_review._load(p)) if p else None
            if not blank or not blank.exists():
                return None
            doc = pymupdf.open(str(blank))
            try:
                if not 1 <= page <= len(doc):
                    return None
                self.png[key] = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
            finally:
                doc.close()
        return self.png[key]


APP: Optional[App] = None
SERVED: dict = {}                       # the port and mode serve() was started with, for the restart button


def restart() -> None:
    """The page's reboot button: replace this process with a fresh one on the same port, so edited code (this
    file, the modes' modules, the page) loads without going back to the terminal. The listening socket is not
    inherited across exec (PEP 446), so the new process binds the port again."""
    time.sleep(0.3)                     # let the handler's reply reach the page first
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable, "-m", "petey.validate.blueprint_review",
                              "--port", str(SERVED["port"]), "--mode", SERVED["mode"], "--no-open"])


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def _send(self, body: bytes, ctype: str, code: int = 200) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(json.dumps(obj, default=str).encode(), "application/json", code)

    def _body(self) -> dict:
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")

    def _route(self, fn, bid: Optional[str] = None):
        if bid is not None and bid not in APP.paths:
            return self._send(b"no such blueprint", "text/plain", 404)
        try:
            out = fn()
        except KeyError as e:
            return self._send(f"not found: {e}".encode(), "text/plain", 404)
        except Exception as e:  # noqa: BLE001
            return self._send(f"{type(e).__name__}: {e}".encode(), "text/plain", 400)
        if out is None:
            return self._send(b"not found", "text/plain", 404)
        self._json(out)

    def _parts(self) -> list[str]:
        return unquote(urlparse(self.path).path).strip("/").split("/")

    def do_GET(self):
        if web.route(self, "GET"):                       # the extractor (petey.web), at /extract
            return
        path = unquote(urlparse(self.path).path)
        parts = self._parts()
        if path in ("/", "/index.html"):
            return self._send(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/blueprints":
            return self._json(APP.listing())
        if len(parts) == 4 and parts[:2] == ["api", "blueprints"] and parts[3] == "sha":
            return self._route(lambda: {"sha": hand_review._sha(APP.working(parts[2]))}, parts[2])
        if len(parts) == 3 and parts[:2] == ["api", "draft"]:
            return self._route(lambda: {"draft": draft.status(parts[2], APP.paths[parts[2]])}, parts[2])
        if len(parts) == 5 and parts[:2] == ["api", "blueprints"] and parts[3] == "png":
            png = APP.page_png(parts[2], int(parts[4]))
            return self._send(png, "image/png") if png else self._send(b"no such page", "text/plain", 404)
        if len(parts) == 4 and parts[:2] == ["api", "review"] and parts[3] == "removals":
            return self._route(lambda: {"removed": field_add.load_record(parts[2]).get("removed") or []}, parts[2])
        if len(parts) == 3 and parts[0] == "api" and parts[1] in MODES:
            mode, bid = parts[1], parts[2]
            state = getattr(APP, mode)
            return self._route(lambda: state.detail(bid), bid)
        self._send(b"not found", "text/plain", 404)

    def do_PUT(self):
        parts = self._parts()
        if len(parts) != 4 or parts[0] != "api":
            return self._send(b"not found", "text/plain", 404)
        mode, bid, what = parts[1], parts[2], parts[3]
        body = self._body()
        if (mode, what) == ("review", "verdicts"):
            return self._route(lambda: APP.put_verdicts(bid, body), bid)
        if (mode, what) == ("groups", "units"):
            def units():
                APP.open_draft(bid)
                return APP.groups.put_units(bid, body) | {"entry": APP.entry(bid)}
            return self._route(units, bid)
        if (mode, what) == ("review", "removals"):           # Review's remove button: the field-add record's removals
            return self._route(lambda: APP.save_add(bid, {"removed": body.get("removed") or []}), bid)
        if (mode, what) == ("add", "record"):
            return self._route(lambda: APP.save_add(bid, body), bid)
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        if web.route(self, "POST"):
            return
        parts = self._parts()
        if parts == ["api", "restart"]:
            self._json({"restarting": True})
            threading.Thread(target=restart, daemon=True).start()
            return
        if len(parts) != 4 or parts[0] != "api":
            return self._send(b"not found", "text/plain", 404)
        mode, bid, what = parts[1], parts[2], parts[3]
        body = self._body()
        if (mode, what) == ("draft", "save"):
            return self._route(lambda: APP.save_draft(bid, bool(body.get("force"))), bid)
        if (mode, what) == ("draft", "discard"):
            return self._route(lambda: APP.discard_draft(bid), bid)
        if (mode, what) == ("groups", "plan"):
            return self._route(lambda: APP.groups.plan_for(bid, body), bid)
        if (mode, what) == ("groups", "apply"):
            return self._route(lambda: APP.apply_groups(bid), bid)
        if (mode, what) == ("add", "propose"):
            return self._route(lambda: field_add.propose(APP.add.ctx(bid), int(body.get("page") or 1), body.get("rect"),
                                                         body.get("sid"), set(body.get("taken") or [])), bid)
        if (mode, what) == ("add", "labeler"):
            return self._route(lambda: {"name": field_add.labeler_name(APP.add.ctx(bid), body["proposal"],
                                                                       think=body.get("from") != "groups"),
                                        "model": field_add.LABEL_MODEL}, bid)
        if (mode, what) == ("add", "finder"):
            def run():
                APP.add.ctx(bid).load_finder(run=True)
                return APP.add.detail(bid)
            return self._route(run, bid)
        if (mode, what) == ("review", "apply"):          # a retry, after a clash that held a correction back
            return self._route(lambda: {**APP.apply_review(bid), "entry": APP.entry(bid)}, bid)
        if (mode, what) == ("add", "apply"):
            return self._route(lambda: APP.save_add(bid, {}), bid)
        if (mode, what) == ("review", "agent"):          # "review edits": the flags with notes go to the agent
            from petey.validate import flag_agent
            return self._route(lambda: {"started": flag_agent.start(bid)}, bid)
        if (mode, what) == ("review", "agent_field"):    # "fix captions": one field, answered now, not stored
            from petey.validate import flag_agent
            return self._route(lambda: flag_agent.propose_field(bid, body["name"], body.get("note") or ""), bid)
        self._send(b"not found", "text/plain", 404)


def serve(port: int = 5005, mode: str = "review", open_browser: bool = True) -> int:
    global APP
    SERVED.update(port=port, mode=mode)
    APP = App()
    print(f"blueprint review: {len(APP.paths)} blueprints")
    t0 = time.time()
    APP.index()
    print(f"  indexed in {time.time() - t0:.1f}s")
    web.REVIEW["on"] = True
    web.start()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as srv:
        url = f"http://127.0.0.1:{port}/#{mode}"
        print(f"blueprint review -> {url}")
        if open_browser:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--mode", choices=MODES, default="review")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    return serve(args.port, args.mode, not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
