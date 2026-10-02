"""Hand review of a blueprint against its blank: a web page that draws every field's rect on the rendered page and
takes accept / flag / a one-line note per field. The person's verdicts are the fixture the loop cannot make for
itself (Andrew, 2026-10-02: a working blueprint is a working blueprint; the promotion rule needs a check outside
the loop). Adapted from petey-master's `petey-eval/scripts/label_server.py`, which asked a person to type labels;
this asks them to judge the ones a blueprint already has.

    PYTHONPATH=. venv/bin/python -m petey.validate.hand_review [--port 5005]      # then open http://127.0.0.1:5005/
    PYTHONPATH=. venv/bin/python -m petey.validate.hand_review --summary          # verdicts so far, per blueprint

Blueprints offered: the library (`blueprints/`), the judge-eval side copies (`runs/judge_eval/blueprints/`, current
files only) and the relabels (`runs/relabel/blueprints/`). Verdicts go to `runs/hand_review/<id>.json` with the
blueprint's path, sha and build stamp, and are keyed by field name; a verdict written against one version of the
file is reported as stale when the file changes.

Keys on the page: a accept, f flag, c clear, n / p next and previous field in reading order, u toggle unreviewed
only, 1-9 page. Every verdict saves immediately.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import socketserver
import time
import webbrowser
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

import yaml

from petey.paths import BLUEPRINTS, RUNS
from petey.validate.retype import resolve_blank

OUT = RUNS / "hand_review"
HTML_PATH = Path(__file__).with_suffix(".html")
DPI = 110
SOURCES = {"lib": BLUEPRINTS, "je": RUNS / "judge_eval" / "blueprints", "rl": RUNS / "relabel" / "blueprints"}


def blueprint_paths() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for tag, d in SOURCES.items():
        if not d.exists():
            continue
        for p in sorted(d.glob("*.bpt")):
            if tag == "je" and p.stem.endswith(("_v0", "_run1")):
                continue
            out[f"{tag}__{p.stem}"] = p
    return out


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


def verdict_path(bid: str) -> Path:
    return OUT / f"{bid}.json"


def load_verdicts(bid: str) -> dict:
    p = verdict_path(bid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


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
        rows.append({
            "name": name, "page": rects[0]["page"], "rects": rects, "options": options,
            "type": spec.get("type"), "semantic_type": spec.get("semantic_type"), "pattern": spec.get("pattern"),
            "values": spec.get("values"), "description": spec.get("description"),
            "path": (spec.get("widget") or {}).get("path") or next(iter(spec.get("widgets", {}).values()), {}).get("path"),
            "loop": ({"changed": rv.get("changed"), "reason": rv.get("reason"), "old_name": rv.get("old_name"),
                      "before": rv.get("before")} if rv else None),
            "adjudication": spec.get("x_petey_adjudication"),
        })
    rows.sort(key=lambda r: (r["page"], round(r["rects"][0]["rect"][1] / 6), r["rects"][0]["rect"][0]))
    return rows


class State:
    def __init__(self) -> None:
        self.paths = blueprint_paths()
        self.png: dict[tuple[str, int], bytes] = {}
        self.sizes: dict[str, list[dict]] = {}

    def listing(self) -> list[dict]:
        out = []
        for bid, p in self.paths.items():
            bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            v = load_verdicts(bid); vs = v.get("verdicts") or {}
            fields = [n for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)]
            out.append({"id": bid, "source": bid.split("__")[0], "form": p.stem, "fields": len(fields),
                        "accepted": sum(1 for n in fields if vs.get(n, {}).get("verdict") == "accept"),
                        "flagged": sum(1 for n in fields if vs.get(n, {}).get("verdict") == "flag"),
                        "stale": bool(v) and v.get("blueprint_sha") != _sha(p),
                        "finder": (bp.get("x_petey_build") or {}).get("finder")})
        return out

    def detail(self, bid: str) -> Optional[dict]:
        p = self.paths.get(bid)
        if p is None:
            return None
        bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        blank = resolve_blank(bp)
        pages = []
        if blank and blank.exists():
            import pymupdf
            doc = pymupdf.open(str(blank))
            try:
                for i, pg in enumerate(doc, start=1):
                    pages.append({"page": i, "w_pt": pg.rect.width, "h_pt": pg.rect.height})
            finally:
                doc.close()
        self.sizes[bid] = pages
        v = load_verdicts(bid)
        return {"id": bid, "path": str(p), "blank": str(blank) if blank else None, "sha": _sha(p),
                "build": bp.get("x_petey_build"), "pages": pages, "fields": field_rows(bp),
                "verdicts": v.get("verdicts") or {}, "stale": bool(v) and v.get("blueprint_sha") != _sha(p),
                "dpi": DPI}

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key in self.png:
            return self.png[key]
        p = self.paths.get(bid)
        if p is None:
            return None
        bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
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

    def put_verdicts(self, bid: str, incoming: dict) -> dict:
        p = self.paths.get(bid)
        if p is None:
            raise KeyError(bid)
        bp = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        cur = load_verdicts(bid)
        vs = cur.get("verdicts") or {}
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for name, rec in (incoming.get("verdicts") or {}).items():
            if rec is None or not rec.get("verdict"):
                vs.pop(name, None)
            else:
                vs[name] = {"verdict": rec["verdict"], "note": (rec.get("note") or "").strip()[:300], "when": now}
        out = {"blueprint": str(p), "form": p.stem, "blueprint_sha": _sha(p), "build": bp.get("x_petey_build"),
               "updated": now, "verdicts": vs}
        OUT.mkdir(parents=True, exist_ok=True)
        verdict_path(bid).write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
        return out


STATE: Optional[State] = None


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

    def do_GET(self):
        path = unquote(urlparse(self.path).path)
        parts = path.strip("/").split("/")
        if path in ("/", "/index.html"):
            self._send(HTML_PATH.read_bytes(), "text/html; charset=utf-8")
        elif path == "/api/blueprints":
            self._json(STATE.listing())
        elif len(parts) == 3 and parts[:2] == ["api", "blueprints"]:
            d = STATE.detail(parts[2])
            self._json(d) if d else self._send(b"no such blueprint", "text/plain", 404)
        elif len(parts) == 5 and parts[:2] == ["api", "blueprints"] and parts[3] == "png":
            png = STATE.page_png(parts[2], int(parts[4]))
            self._send(png, "image/png") if png else self._send(b"no such page", "text/plain", 404)
        else:
            self._send(b"not found", "text/plain", 404)

    def do_PUT(self):
        parts = unquote(urlparse(self.path).path).strip("/").split("/")
        if len(parts) == 4 and parts[:2] == ["api", "blueprints"] and parts[3] == "verdicts":
            length = int(self.headers.get("Content-Length", "0"))
            try:
                incoming = json.loads(self.rfile.read(length))
                self._json(STATE.put_verdicts(parts[2], incoming))
            except KeyError:
                self._send(b"no such blueprint", "text/plain", 404)
            except Exception as e:  # noqa: BLE001
                self._send(str(e).encode(), "text/plain", 400)
        else:
            self._send(b"not found", "text/plain", 404)


def summary() -> None:
    paths = blueprint_paths()
    rows = []
    for vp in sorted(OUT.glob("*.json")):
        v = json.loads(vp.read_text(encoding="utf-8")); vs = v.get("verdicts") or {}
        p = paths.get(vp.stem)
        stale = p is None or v.get("blueprint_sha") != _sha(p)
        acc = sum(1 for r in vs.values() if r.get("verdict") == "accept")
        flg = [(n, r.get("note", "")) for n, r in vs.items() if r.get("verdict") == "flag"]
        rows.append((vp.stem, acc, len(flg), stale, v.get("updated"), flg))
    print(f"{'blueprint':40} {'accepted':>8} {'flagged':>7} {'stale':>5}  updated")
    for bid, acc, nf, stale, upd, flg in rows:
        print(f"{bid[:40]:40} {acc:8} {nf:7} {'yes' if stale else '':>5}  {upd}")
        for n, note in flg[:8]:
            print(f"      flag  {n[:40]:40} {note[:80]}")
    if not rows:
        print(f"no verdicts yet under {OUT}")


def main() -> int:
    global STATE
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5005)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if args.summary:
        summary()
        return 0
    STATE = State()
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), Handler) as srv:
        url = f"http://127.0.0.1:{args.port}/"
        print(f"hand review -> {url}  ({len(STATE.paths)} blueprints; verdicts in {OUT})")
        if not args.no_open:
            webbrowser.open(url)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
