"""Can Jev tell which finder boxes are real fields? (Andrew, 2026-10-15: "could we use jev to decide what fields on a
flat form were real?")

The finder (`petey.synth.boxes.find_boxes`) proposes boxes from the drawn page, with many false positives. Here Jev
sees each page with every finder box outlined and tagged with its number (the blank with its widgets stripped, so
the page looks like a flat form) and answers one Noul per box: would a person filling in the form write or mark
something in it? Truth on validated forms: a finder box a blueprint field covers (overlap >= 0.5) is a field, any
other is not (a little unfair to Jev: some uncovered boxes are real blanks the blueprint lacks). The baseline is the
classifier that screens finder boxes for Add / remove today (`classify_form`, cached class map; class none = not a
field).

    PYTHONPATH=. venv/bin/python -m petey.validate.jev_is_field --forms 40 --save runs/jev/is_field_2026-10-15.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import random
import sys
from pathlib import Path

import httpx
import pymupdf

from petey.synth import boxes as B
from petey.synth.classify import classify_form
from petey.validate import hand_review as h, page_check as pc
from petey.validate.jev_page import LIMITS, MODEL, _key, ask_split, image_ref

QUESTION = ("`page` is one page of a blank form. Candidate boxes are outlined in red, each tagged with its number at "
            "its top-left; `boxes` gives each number's pixel box and the detector's guess of its kind. Look at the box "
            "tagged `box.id`: is it a place where a person filling in this form writes, types or marks an answer (a "
            "blank line, an empty cell under or beside a caption, a checkbox or radio circle, a signature or date "
            "line)?")
CRITERIA = {
    "true": "A person filling in the form writes, types or marks something in this box.",
    "false": "Nothing is filled in here: printed text, a heading, a logo or picture, a decorative rule or bullet, "
             "a gap between ruled lines, or the empty part of a cell whose content is already printed.",
}
PER_REQUEST = 20
SCRATCH = Path("runs/jev/is_field_pages")


def cached_boxes(blank: Path):
    hh = hashlib.sha256(blank.read_bytes() + b"\x00boxes\x00" + B.FINDER_VERSION.encode()).hexdigest()
    cp = B.CACHE_DIR / f"{hh}.json"
    return json.loads(cp.read_text()) if cp.exists() else None


def flat_copy(blank: Path) -> Path:
    """The blank with its widgets removed: what a flat form shows."""
    SCRATCH.mkdir(parents=True, exist_ok=True)
    out = SCRATCH / f"{hashlib.md5(blank.read_bytes()).hexdigest()}.pdf"
    if not out.exists():
        doc = pymupdf.open(str(blank))
        for pg in doc:
            for w in list(pg.widgets()):
                pg.delete_widget(w)
        doc.save(str(out))
    return out


def form_jobs(bid: str):
    """(bid, page, body, imgs, {qid: box}) per request, and the boxes with truth and the classifier's class."""
    bp = h._load(h.working_path(bid))
    blank = pc.resolve_blank(bp)
    bx = cached_boxes(blank)
    pages = set(bp.get("source_pages") or [])
    bx = [b for b in bx if not pages or b["page"] in pages]
    fb = [b for s in bp["fields"].values() if isinstance(s, dict) for b in pc.boxes(s)]
    try:
        cm = (classify_form(blank, cache_only=True) or {}).get("boxes") or {}
    except Exception:
        cm = {}
    flat = flat_copy(blank)
    truth = []
    for b in bx:
        real = any(f["page"] == b["page"] and B.overlap(b["rect"], f["rect"]) >= 0.5 for f in fb)
        truth.append({"bid": bid, "id": b["id"], "page": b["page"], "kind": b["kind"], "real": real,
                      "cls": (cm.get(b["key"]) or {}).get("class")})
    jobs = []
    for page_no in sorted({b["page"] for b in bx}):
        on = [b for b in bx if b["page"] == page_no]
        rows = [{"boxes": [{"page": page_no, "rect": b["rect"], "label": b["id"]}]} for b in on]
        png, _dpi, px = pc.render(flat, page_no, rows, limits=LIMITS)
        ref = image_ref(png)
        items = [{"id": b["id"], "kind": b["kind"], "pixel_box": [round(v) for v in px[b["id"]]]} for b in on if b["id"] in px]
        for i in range(0, len(items), PER_REQUEST):
            qs, names = {}, {}
            for it in items[i:i + PER_REQUEST]:
                qs[f"b{it['id']}"] = {"type": "noul", "instructions": {"box": it, "question": QUESTION}, "criteria": CRITERIA}
                names[f"b{it['id']}"] = it["id"]
            body = {"model": MODEL, "state": {"form": bp.get("name"), "page_number": page_no, "page": ref, "boxes": items},
                    "questions": qs}
            jobs.append((bid, page_no, body, {ref: png}, names))
    return jobs, truth


def auc(pos: list[float], neg: list[float]) -> float:
    """Probability a random real box scores above a random non-field (ties half)."""
    if not pos or not neg:
        return float("nan")
    allv = sorted([(v, 1) for v in pos] + [(v, 0) for v in neg])
    rank, i, rs = 1, 0, 0.0
    while i < len(allv):
        j = i
        while j < len(allv) and allv[j][0] == allv[i][0]:
            j += 1
        r = (rank + rank + (j - i) - 1) / 2
        rs += r * sum(1 for k in range(i, j) if allv[k][1])
        rank += j - i
        i = j
    return (rs - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", type=int, default=40, help="validated forms of at most --max-pages pages, sampled")
    ap.add_argument("--max-pages", type=int, default=4)
    ap.add_argument("--list", default="", help="the review page's listing (/api/blueprints) saved as JSON")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--forms-list", nargs="*", help="these review ids (those with a cached finder run) instead of a sample")
    ap.add_argument("--save", required=True)
    args = ap.parse_args()
    listing = json.loads(Path(args.list).read_text()) if args.list else httpx.get("http://127.0.0.1:5005/api/blueprints", timeout=120).json()
    cands = []
    for e in ([{"id": i, "checked": {"validated": True}, "pages": 1} for i in args.forms_list] if args.forms_list else listing):
        if not (e.get("checked") or {}).get("validated") or (e.get("pages") or 99) > args.max_pages:
            continue
        bp = h._load(h.working_path(e["id"]))
        blank = pc.resolve_blank(bp)
        if blank and cached_boxes(blank) is not None:
            cands.append(e["id"])
    random.Random(7).shuffle(cands)
    forms = cands if args.forms_list else cands[:args.forms]
    jobs, truth = [], []
    for bid in forms:
        j, t = form_jobs(bid)
        jobs += j
        truth += t
    print(f"{len(forms)} forms, {len({(j[0], j[1]) for j in jobs})} pages, {len(truth)} finder boxes "
          f"({sum(t['real'] for t in truth)} real), {len(jobs)} requests", file=sys.stderr)
    key = _key()
    score, tokens = {}, 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(ask_split, client, key, j[2], j[3]): j for j in jobs}
        for f in cf.as_completed(futs):
            j = futs[f]
            res = f.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, box_id in j[4].items():
                v = ((res.get("answers") or {}).get(qid) or {}).get("noul")
                if v is not None:
                    score[(j[0], box_id)] = v
    for t in truth:
        t["jev"] = score.get((t["bid"], t["id"]))
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(truth))
    pages = len({(j[0], j[1]) for j in jobs})
    print(f"input tokens {tokens:,} (~${tokens / 1e6 * 0.042:.3f}, ${tokens / 1e6 * 0.042 / max(pages, 1):.4f}/page)")

    T = [t for t in truth if t["jev"] is not None]
    real = [t for t in T if t["real"]]
    fake = [t for t in T if not t["real"]]
    print(f"\n{len(T)} boxes answered: {len(real)} real, {len(fake)} not")
    print(f"Jev AUC {auc([t['jev'] for t in real], [t['jev'] for t in fake]):.3f}")
    cls = lambda t: 0.5 if t["cls"] is None else (0.0 if t["cls"] == "none" else 1.0)   # noqa: E731
    print(f"classifier AUC {auc([cls(t) for t in real], [cls(t) for t in fake]):.3f} "
          f"(class map on {sum(t['cls'] is not None for t in T)} of {len(T)} boxes)")
    kept = [t for t in T if t["cls"] not in (None, "none")]
    if kept:
        print(f"classifier keeps {len(kept)}: {sum(t['real'] for t in kept)} real ({sum(t['real'] for t in kept) / len(real):.0%} of "
              f"real), {len(kept) - sum(t['real'] for t in kept)} not")
    for cut in (0.3, 0.5, 0.7):
        k = [t for t in T if t["jev"] >= cut]
        print(f"Jev >= {cut}: keeps {len(k)}: {sum(t['real'] for t in k)} real ({sum(t['real'] for t in k) / len(real):.0%} of real), "
              f"{len(k) - sum(t['real'] for t in k)} not ({(len(k) - sum(t['real'] for t in k)) / max(len(fake), 1):.0%} of the false ones)")
    for kind in sorted({t["kind"] for t in T}):
        r = [t["jev"] for t in real if t["kind"] == kind]
        n = [t["jev"] for t in fake if t["kind"] == kind]
        print(f"  {kind:10} real {len(r):5} not {len(n):5}  Jev AUC {auc(r, n):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
