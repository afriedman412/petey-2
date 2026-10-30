"""Petey web app: drop filled PDFs, get their data. The form is detected (`petey.detect`), its library blueprint
read, and the fields extracted (`petey.extract`); no model, no API keys, no blueprint to pick.

    PYTHONPATH=. venv/bin/python -m petey.web [--port 5010] [--no-open]

The blueprint review server (`petey.validate.blueprint_review`) serves it too, at /extract; both route through
`route`, so the page and its API (/extract/api/...) are the same on either server.

Replaces the petey-master web app (petey-web), which built a blueprint per upload and sent the text to an LLM.
Each file comes back as the record that app returned, one flat object per document:

    {"_source_file": "w9_acme.pdf", "_form": {"blueprint", "form_id", "title", "method", "score", ...},
     "<field>": <value>, ...}

A file that is not a library form comes back with `_error` and the closest form in `_form.runner_up`; the page
offers to extract it as that form (or any library form), which sends the blueprint by name.
"""
from __future__ import annotations

import argparse
import http.server
import json
import socketserver
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import yaml

from petey.detect import Library
from petey.extract import extract

HTML_PATH = Path(__file__).with_suffix(".html")
MAX_BYTES = 50 * 1024 * 1024
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


class App:
    """The library, indexed in the background so the page opens at once; extraction waits for it."""

    def __init__(self) -> None:
        self.lib: Optional[Library] = None
        self.ready = threading.Event()
        self.error: Optional[str] = None

    def load(self) -> None:
        t0 = time.time()
        try:
            self.lib = Library()
            print(f"  {len(self.lib.entries)} library blueprints indexed in {time.time() - t0:.1f}s")
        except Exception as e:  # noqa: BLE001
            self.error = f"{type(e).__name__}: {e}"
            print(f"  library index failed: {self.error}")
        self.ready.set()

    def forms(self) -> list[dict]:
        self.ready.wait()
        if self.lib is None:
            return []
        return [{"blueprint": e.stem, "form_id": e.form_id, "title": e.title, "fields": e.fields}
                for e in self.lib.entries]

    def run(self, data: bytes, filename: str, blueprint: Optional[str] = None) -> dict:
        self.ready.wait()
        out: dict = {"_source_file": filename}
        if self.lib is None:
            return {**out, "_error": f"library not loaded ({self.error})"}
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(data)
            tmp.flush()
            try:
                form = self.lib.detect(tmp.name)
            except Exception as e:  # noqa: BLE001
                return {**out, "_error": f"could not read the PDF ({type(e).__name__}: {e})"}
            if blueprint:
                if blueprint not in self.lib.by_stem:
                    return {**out, "_form": form, "_error": f"no library blueprint {blueprint!r}"}
                e = self.lib.by_stem[blueprint]
                form = {**form, "blueprint": e.stem, "form_id": e.form_id, "title": e.title, "method": "chosen"}
            out["_form"] = form
            if not form["blueprint"]:
                return {**out, "_error": "not a form in the library"}
            entry = self.lib.by_stem[form["blueprint"]]
            bp = yaml.load(entry.path.read_text(encoding="utf-8"), Loader=_LOADER)
            t0 = time.time()
            try:
                values = extract(bp, Path(tmp.name))
            except Exception as e:  # noqa: BLE001
                return {**out, "_error": f"extraction failed ({type(e).__name__}: {e})"}
        values.pop("_meta", None)
        form["seconds"] = round(time.time() - t0, 2)
        return {**out, **values}


APP = App()
STARTED = threading.Event()
REVIEW = {"on": False}             # served by the review server: the page links back to it


def start() -> None:
    """Index the library in the background, once."""
    if not STARTED.is_set():
        STARTED.set()
        print("petey web: indexing the library")
        threading.Thread(target=APP.load, daemon=True).start()


def _send(h: http.server.BaseHTTPRequestHandler, body: bytes, ctype: str, code: int = 200) -> None:
    h.send_response(code)
    h.send_header("Content-Type", ctype)
    h.send_header("Content-Length", str(len(body)))
    h.end_headers()
    h.wfile.write(body)


def _json(h: http.server.BaseHTTPRequestHandler, obj, code: int = 200) -> None:
    _send(h, json.dumps(obj, default=str).encode(), "application/json", code)


def route(h: http.server.BaseHTTPRequestHandler, method: str) -> bool:
    """Answer the request if it is this app's (/extract, /extract/api/...); False leaves it to the caller.

    POST /extract/api/extract: the PDF is the request body, its name the X-Filename header (URL-encoded), and
    X-Blueprint names a library blueprint to use instead of the detected one."""
    path = unquote(urlparse(h.path).path).rstrip("/")
    if method == "GET" and path == "/extract":
        _send(h, HTML_PATH.read_bytes(), "text/html; charset=utf-8")
    elif method == "GET" and path == "/extract/api/status":
        n = len(APP.lib.entries) if APP.lib else 0
        _json(h, {"ready": APP.ready.is_set(), "forms": n, "error": APP.error, "review": REVIEW["on"]})
    elif method == "GET" and path == "/extract/api/forms":
        _json(h, APP.forms())
    elif method == "POST" and path == "/extract/api/extract":
        n = int(h.headers.get("Content-Length", "0"))
        if not n or n > MAX_BYTES:
            _json(h, {"_error": f"empty or larger than {MAX_BYTES >> 20} MB"}, 400)
            return True
        data = h.rfile.read(n)
        name = unquote(h.headers.get("X-Filename", "document.pdf"))
        if not data.startswith(b"%PDF"):
            _json(h, {"_source_file": name, "_error": "not a PDF"}, 400)
            return True
        _json(h, APP.run(data, name, unquote(h.headers.get("X-Blueprint", "")) or None))
    else:
        return False
    return True


class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        return

    def do_GET(self):
        if urlparse(self.path).path in ("/", "/index.html"):
            self.path = "/extract"
        if not route(self, "GET"):
            _send(self, b"not found", "text/plain", 404)

    def do_POST(self):
        if not route(self, "POST"):
            _send(self, b"not found", "text/plain", 404)


def serve(port: int = 5010, open_browser: bool = True) -> int:
    start()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as srv:
        url = f"http://127.0.0.1:{port}/"
        print(f"petey web -> {url}")
        if open_browser:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5010)
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    return serve(args.port, not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
