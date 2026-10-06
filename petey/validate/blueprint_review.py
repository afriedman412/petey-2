"""Blueprint review: one web page for checking a blueprint against its blank, in three modes over the same picker,
page and zoom:

    Review       accept / flag / note per field, risk-first by witness tier   (`hand_review`, runs/hand_review/)
    Groups       confirm option groups, drag boxes to regroup, drag text boxes together to combine them
                                                                                (`group_review`, runs/group_review/)
    Add / remove suggestions and drawn areas -> proposed fields; not-a-field; remove a field
                                                                                (`field_add`, runs/field_add/)

    PYTHONPATH=. venv/bin/python -m petey.validate.blueprint_review [--port 5005] [--mode review|groups|add]

Each mode's logic, record and command line stay in its own module; this file serves the one page and routes to
them. The page only records. Blueprints change through each module's `--apply` (`group_review --apply <id>`,
`field_add --apply <id>`), and `hand_review --summary` lists verdicts. The old entry points
(`python -m petey.validate.hand_review`, `group_review`, `field_add` with no subcommand) open this page in their
mode.
"""
from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import pymupdf

from petey.validate import field_add, group_review, hand_review
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
        self.mtimes = {bid: p.stat().st_mtime for bid, p in self.paths.items()}

    def refresh(self) -> None:
        """Re-read the picker rows of blueprints whose file changed since they were indexed (an --apply, a loop, an
        edit by hand): the indexes are built once at startup."""
        for bid, p in self.paths.items():
            m = p.stat().st_mtime
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

    def listing(self) -> list[dict]:
        if not self.review._index:
            self.index()
        self.refresh()
        return [self.entry(bid) for bid in self.paths]

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key not in self.png:
            p = self.paths.get(bid)
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
        path = unquote(urlparse(self.path).path)
        parts = self._parts()
        if path in ("/", "/index.html"):
            return self._send(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        if path == "/api/blueprints":
            return self._json(APP.listing())
        if len(parts) == 4 and parts[:2] == ["api", "blueprints"] and parts[3] == "sha":
            return self._route(lambda: {"sha": hand_review._sha(APP.paths[parts[2]])}, parts[2])
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
            return self._route(lambda: APP.review.put_verdicts(bid, body) | {"entry": APP.entry(bid)}, bid)
        if (mode, what) == ("groups", "units"):
            return self._route(lambda: APP.groups.put_units(bid, body) | {"entry": APP.entry(bid)}, bid)
        if (mode, what) == ("review", "removals"):           # Review's remove button: the field-add record's removals
            return self._route(lambda: APP.add.save(bid, {"removed": body.get("removed") or []}) | {"entry": APP.entry(bid)}, bid)
        if (mode, what) == ("add", "record"):
            return self._route(lambda: APP.add.save(bid, body) | {"entry": APP.entry(bid)}, bid)
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        parts = self._parts()
        if len(parts) != 4 or parts[0] != "api":
            return self._send(b"not found", "text/plain", 404)
        mode, bid, what = parts[1], parts[2], parts[3]
        body = self._body()
        if (mode, what) == ("groups", "plan"):
            return self._route(lambda: APP.groups.plan_for(bid, body), bid)
        if (mode, what) == ("add", "propose"):
            return self._route(lambda: field_add.propose(APP.add.ctx(bid), int(body.get("page") or 1), body.get("rect"),
                                                         body.get("sid"), set(body.get("taken") or [])), bid)
        if (mode, what) == ("add", "labeler"):
            return self._route(lambda: {"name": field_add.labeler_name(APP.add.ctx(bid), body["proposal"]),
                                        "model": field_add.LABEL_MODEL}, bid)
        if (mode, what) == ("add", "finder"):
            def run():
                APP.add.ctx(bid).load_finder(run=True)
                return APP.add.detail(bid)
            return self._route(run, bid)
        self._send(b"not found", "text/plain", 404)


def serve(port: int = 5005, mode: str = "review", open_browser: bool = True) -> int:
    global APP
    APP = App()
    print(f"blueprint review: {len(APP.paths)} blueprints")
    t0 = time.time()
    APP.index()
    print(f"  indexed in {time.time() - t0:.1f}s")
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
