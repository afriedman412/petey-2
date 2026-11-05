"""Manual sweeps of the benchmark key's pages, one sheet at /sweep (Andrew, 2026-10-31: "single sweep to ignore pages
with no or few fields"; "the 'checklist' issue will be handled by 'ignore this page'"; "sweep to add fields in
'internal use only' sections of pages, and other similar"; "I am expecting to have to do some manual work").

Each sweep proposes pages; Andrew looks at each and says what it is:

    few         at most FEW fields on the page          ignore (reason "few fields") or keep
    checklist   half or more of the fields are boxes,   ignore (reason "checklist") or keep
                with words a list of things to hand
                in uses (attach, enclose, copy of, ...)
    office      a printed "office use only" or "do not  fields added on the review page ("done"), none needed
                write below" section                    ("keep"), or ignore
    signature   a short line asking for a signature,    the same as office: fields added (and marked printed
                initials or a printed name with no      on the Review tab, w), none needed, or ignore
                field near it (2026-10-31: "what matters is we are aware of everywhere there could be
                information we need on a page")

The words only rank pages for a person to look at; nothing is decided by them. Candidates are cached in
runs/benchmark/sweeps/candidates.json (`find`, rebuilt when the key's index is newer); what was said goes to
runs/benchmark/sweeps/seen.json {sweep: {page id: {verdict, when}}}, and an ignore also to the ignored pages record
(petey_dataset.ignored_pages), the one the key and scorer read.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import threading
from pathlib import Path
from typing import Optional

from petey_dataset import ignored_pages

ROOT = Path(__file__).resolve().parents[2]
KEY = ROOT / "runs" / "benchmark" / "key"
DIR = ROOT / "runs" / "benchmark" / "sweeps"
HTML_PATH = Path(__file__).with_name("page_sweeps.html")
FEW = 9
SWEEPS = {
    "few": {"title": f"Pages with {FEW} fields or fewer", "reason": "few fields", "verdicts": ["ignore", "keep"]},
    "checklist": {"title": "Checklists", "reason": "checklist", "verdicts": ["ignore", "keep"]},
    "office": {"title": "Office use only sections", "reason": "office use only", "verdicts": ["done", "keep", "ignore"]},
    "signature": {"title": "Signature lines with no field", "reason": "signature lines", "verdicts": ["done", "keep", "ignore"]},
}
OFFICE = re.compile(r"\b(for\s+(office|official|staff|department|agency|internal|clerk'?s?|admin\w*)\s+use(\s+only)?"
                    r"|(office|internal|official)\s+use\s+only|do\s+not\s+write\s+(below|in\s+this\s+(space|area|box)))\b", re.I)
CHECKLIST = re.compile(r"\b(check\s*list|attach(ed|ments?)?|enclose[ds]?|copy\s+of|documents?\s+(required|needed|to\s+"
                       r"(submit|include|attach))|have\s+you\s+(included|attached))\b", re.I)
SIGN = re.compile(r"\b(signature|sign\s+here|initials|print(ed)?\s+name|name\s*\(print)", re.I)
HEADING = re.compile(r"^\s*(section|part)\b", re.I)
SIGN_WORDS = 8          # a caption, not a sentence about signing
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _write(obj, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, indent=1, sort_keys=True))
    os.replace(tmp, path)


def page_text(pid: str, key_dir: Path = KEY) -> str:
    import pymupdf
    pdf = key_dir / "pages" / f"{pid}.pdf"
    if not pdf.exists():
        return ""
    pymupdf.TOOLS.mupdf_display_errors(False)
    with pymupdf.open(str(pdf)) as doc:
        return " ".join(doc[0].get_text().split())


def page_lines(pid: str, key_dir: Path = KEY) -> list[tuple[str, tuple]]:
    """(text, bbox) of each printed line on the key page."""
    import pymupdf
    pdf = key_dir / "pages" / f"{pid}.pdf"
    if not pdf.exists():
        return []
    pymupdf.TOOLS.mupdf_display_errors(False)
    out = []
    with pymupdf.open(str(pdf)) as doc:
        for b in doc[0].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = " ".join(" ".join(sp["text"] for sp in ln["spans"]).split())
                if t:
                    out.append((t, tuple(ln["bbox"])))
    return out


def _near_a_field(bbox, fields) -> bool:
    """A field where the line's answer would be: on its line to the right, or just above (a signature line over its
    caption) or below."""
    x0, y0, x1, y1 = bbox
    return any(r[3] >= y0 - 28 and r[1] <= y1 + 14 and r[2] >= x0 - 40 and r[0] <= x1 + 320
               for r in (f["rect"] for f in fields))


def unsigned(key: dict, lines: list) -> list[str]:
    """Short lines asking for a signature, initials or a printed name, with no field near them."""
    return [t for t, bb in lines if SIGN.search(t) and len(t.split()) <= SIGN_WORDS and not HEADING.match(t)
            and not _near_a_field(bb, key["fields"])]


def why(key: dict, text: str, lines: Optional[list] = None) -> dict:
    """{sweep: why} for one key page."""
    n = len(key["fields"])
    boxes = sum(f.get("kind") == "choice" for f in key["fields"])
    out = {}
    if n <= FEW:
        out["few"] = f"{n} field{'' if n == 1 else 's'}"
    hits = sorted({m.group(0).lower() for m in CHECKLIST.finditer(text)})
    if boxes >= 5 and boxes * 2 >= n and len(CHECKLIST.findall(text)) >= 2:
        out["checklist"] = f"{boxes} of {n} fields are boxes; " + ", ".join(hits[:5])
    m = OFFICE.search(text)
    if m:
        out["office"] = f'"{m.group(0)}"'
    miss = unsigned(key, lines or [])
    if miss:
        out["signature"] = "no field near: " + "; ".join(f'"{t}"' for t in miss[:4]) + (f" and {len(miss) - 4} more" if len(miss) > 4 else "")
    return out


def find(key_dir: Path = KEY, out: Optional[Path] = None) -> dict:
    """{sweep: {page id: why}} over every key page; cached."""
    out = out or DIR / "candidates.json"
    found = {s: {} for s in SWEEPS}
    for x in json.loads((key_dir / "index.json").read_text()):
        pid = x["page_id"]
        for s, w in why(json.loads((key_dir / f"{pid}.json").read_text()), page_text(pid, key_dir),
                        page_lines(pid, key_dir)).items():
            found[s][pid] = w
    _write(found, out)
    return found


def candidates(key_dir: Path = KEY) -> dict:
    c, idx = DIR / "candidates.json", key_dir / "index.json"
    if c.exists() and c.stat().st_mtime >= idx.stat().st_mtime:
        return json.loads(c.read_text())
    return find(key_dir, c)


def seen() -> dict:
    p = DIR / "seen.json"
    return json.loads(p.read_text()) if p.exists() else {}


def sheet(sweep: str, key_dir: Path = KEY) -> dict:
    if sweep not in SWEEPS:
        raise KeyError(sweep)
    cand, said, ign = candidates(key_dir).get(sweep, {}), seen().get(sweep, {}), ignored_pages.load()
    pages = []
    for pid, w in cand.items():
        k = json.loads((key_dir / f"{pid}.json").read_text())
        pages.append({"page_id": pid, "form": k["form"], "page": k["page"], "set": k.get("set"), "size": k.get("size"),
                      "why": w, "fields": [{"id": f["id"], "rect": f["rect"], "kind": f.get("kind")} for f in k["fields"]],
                      "verdict": (said.get(pid) or {}).get("verdict"), "ignored": (ign.get(pid) or {}).get("reason")})
    pages.sort(key=lambda p: (len(p["fields"]), p["page_id"]) if sweep == "few" else (p["set"] or "", p["page_id"]))
    return {"sweep": sweep, **SWEEPS[sweep], "sweeps": {s: v["title"] for s, v in SWEEPS.items()}, "pages": pages,
            "done": sum(p["verdict"] is not None for p in pages)}


def mark(sweep: str, pid: str, verdict: str, reason: str = "") -> dict:
    """Say what the page is in this sweep; "ignore" also ignores it (reason: the sweep's unless given), anything else
    takes back an ignore this sweep made."""
    if sweep not in SWEEPS or verdict not in SWEEPS[sweep]["verdicts"]:
        raise ValueError(f"{sweep!r} takes {SWEEPS.get(sweep, {}).get('verdicts')}, not {verdict!r}")
    with _LOCK:
        rec = seen()
        was = (rec.get(sweep) or {}).get(pid) or {}
        if verdict == "ignore":
            ignored_pages.put(pid, True, reason or SWEEPS[sweep]["reason"])
        elif was.get("verdict") == "ignore":
            ignored_pages.put(pid, False)
        rec.setdefault(sweep, {})[pid] = {"verdict": verdict, "when": _now()}
        _write(rec, DIR / "seen.json")
    return {"page_id": pid, "verdict": verdict, "ignored": (ignored_pages.load().get(pid) or {}).get("reason")}
