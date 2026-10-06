"""Page check: a vision model does the first pass of hand review, one call per page of the blank.

Hand review (`hand_review.py`) is a person looking at the rendered blank with every field's box drawn on it and
accepting or flagging each field. This asks a model the same question from the same picture, so the person starts
from its flags instead of from a blank form (Andrew, 2026-10-05: minimise attention spent on hand review).

    input     one page of the BLANK rendered near the model's image limit (2576 px long edge, ~3.75 MP; about
              200 dpi on a letter page), every field the blueprint places on the page outlined in red and numbered
              (an option group's boxes N.a, N.b, ...), plus a list giving each number's name, type, semantic type,
              description, options, publisher field name and pixel box. A whole page, not a crop per field: the
              errors people flag are mostly about neighbours (names slid one row or column, day / month swapped,
              a state box named City) and a table's column header is in view.
    question  per field: what would a filer write in the box, judged from the printed captions; do the name and
              type fit it? Accepted fields come back as bare numbers (most of the output was explaining accepts,
              2026-10-06); a flag carries a problem (wrong_name / wrong_type / not_a_field /
              should_group / options / other), a proposed name or type, and a one-line reason.
    output    `runs/page_check/<source>__<stem>__<fields hash>.json` (one per version of the fields), keyed by field name, each verdict with a hash of the field's
              definition; and `x_petey_page_check` on the blueprint (when, model, prompt version, counts, record
              path), the only change it makes to a blueprint. `verdicts(bp)` gives the verdicts still valid for
              the fields as they are now: the `page_check` witness (`witness.py`) and, through it, the loop's
              reviewer and adjudicator. Never touches the person's verdicts in `runs/hand_review/`.

Answers are cached per (model, prompt, page image, field list) in `runs/page_check/_cache/`, so re-scoring is free.
Measured against hand review by `eval/page_check_fixture.py`.

    PYTHONPATH=. venv/bin/python -m petey.validate.page_check blueprints/5021.bpt [--pages 1,2] [--model claude-opus-5]
    PYTHONPATH=. venv/bin/python -m petey.validate.page_check blueprints/fw9.bpt blueprints/ds11.bpt --batch   # half price
    PYTHONPATH=. venv/bin/python -m petey.validate.page_check blueprints/5021.bpt --dry --png-dir /tmp/pc   # images only
"""
from __future__ import annotations

import argparse
import base64
import collections
import hashlib
import json
import math
import string
import time
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml

from petey.paths import RUNS
from petey.validate.adjudicate import PRICES
from petey.validate.retype import resolve_blank

MODEL = "claude-opus-5"
OUT = RUNS / "page_check"
CACHE = OUT / "_cache"
MAX_EDGE, MAX_PX = 2576, 3_750_000         # Opus 5 / Sonnet 5 image limit; larger images are downscaled server-side
LABEL_PT = 6.0                             # label font size on the page, in points (about 17 px at 200 dpi)
PROBLEMS = ("none", "wrong_name", "wrong_type", "not_a_field", "should_group", "options", "other")

SYSTEM = """You check a form blueprint against its blank form. A blueprint names and types every fillable box \
on the form so a program can fill it in and read it back. The image is one page of the blank PDF. Every box the \
blueprint defines on this page is outlined in red with its number in a small red tag at the box's top-left; an \
option group's boxes are numbered N.a, N.b, ... The list gives each number's name, type, semantic type, \
description, options, the publisher's own field name for the widget, and the box in image pixels.

For each field decide whether the blueprint is right about its box. First read the page: what would a person \
filling in this form by hand write or mark in the box? Decide that from the captions printed for the box (inside \
it, directly above, below or beside it as this form lays out its captions; a table's column header and row label \
count for a cell). The publisher's field name and the description are hints; when they disagree with the caption \
printed at the box, the page wins. Mind neighbours: on dense forms a name often belongs to the box one row or one \
column over, two fields swap (day / month), or a whole block slides by one line, so check that the caption you use \
is this box's own.

Flag a field when you can point to the problem on the page:
- wrong_name: the name does not describe what a filer writes in the box (another item, the neighbour's caption, \
swapped with another field). Do not flag style: abbreviations, suffixes (_nm name, _dt date, _amt money, _cd code, \
_ind checkbox, _txt text, _nbr number), word order, copy numbers, or a name that is correct but could be more \
detailed.
- wrong_type: the type or semantic type does not fit the value (a date typed as plain text, a count typed as a \
year, a box that takes one of a printed list of choices typed as free text).
- not_a_field: nothing is written here by a filer (the box sits on printed text, a heading, an instruction, a \
"continued" line, or it duplicates another field's box).
- should_group: this checkbox is one of several that answer one question with one choice and the blueprint keeps \
them as separate fields; name the others in the reason.
- options: an option group's members, on-states or captions do not match the boxes.
- other: anything else a person correcting this blueprint would change.
Otherwise accept. Most fields on a blueprint are right. Put the number of every field you accept in \
`accepted`, with nothing else. Put every field you flag in `flags`, with what a filer writes in the box, the \
problem, the name and / or type you would use (empty when not applicable) and a one-line reason that quotes the \
caption you relied on. Every number in the list goes in exactly one of the two."""

SCHEMA = {
    "type": "object",
    "properties": {
        "accepted": {"type": "array", "items": {"type": "string"}},
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "box_holds": {"type": "string"},
                    "problem": {"type": "string", "enum": [p for p in PROBLEMS if p != "none"]},
                    "proposed_name": {"type": "string"},
                    "proposed_type": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "box_holds", "problem", "proposed_name", "proposed_type", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["accepted", "flags"],
    "additionalProperties": False,
}

_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
PROMPT_VERSION = hashlib.sha256((SYSTEM + json.dumps(SCHEMA, sort_keys=True)).encode()).hexdigest()[:8]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


# ---------------------------------------------------------------- fields

def boxes(spec: dict) -> list[dict]:
    """The field's boxes on the blank: one per widget, an option group's with their on-state and caption."""
    if spec.get("widgets"):
        return [{"page": w["page"], "rect": w["rect"], "on_state": on, "caption": w.get("caption")}
                for on, w in spec["widgets"].items() if w.get("rect") and w.get("page")]
    w = spec.get("widget") or {}
    return [{"page": w["page"], "rect": w["rect"]}] if w.get("rect") and w.get("page") else []


def numbered(bp: dict) -> list[dict]:
    """Every field with a box, in reading order, numbered from 1; option boxes lettered a, b, ... (aa, ab past z)."""
    rows = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        bx = boxes(spec)
        if bx:
            rows.append({"name": name, "spec": spec, "boxes": bx})
    rows.sort(key=lambda r: (r["boxes"][0]["page"], round(r["boxes"][0]["rect"][1] / 6), r["boxes"][0]["rect"][0]))
    for i, r in enumerate(rows, start=1):
        r["id"] = str(i)
        if r["spec"].get("widgets"):
            for j, b in enumerate(r["boxes"]):
                b["label"] = f"{i}.{_letters(j)}"
        else:
            r["boxes"][0]["label"] = str(i)
    return rows


def _letters(j: int) -> str:
    a = string.ascii_lowercase
    return a[j] if j < 26 else a[j // 26 - 1] + a[j % 26]


# ---------------------------------------------------------------- render

def page_dpi(page) -> int:
    w_in, h_in = page.rect.width / 72, page.rect.height / 72
    return int(min(MAX_EDGE / max(w_in, h_in), math.sqrt(MAX_PX / (w_in * h_in))))


def render(blank: Path, page_no: int, rows: list[dict]) -> tuple[bytes, float, dict[str, list[float]]]:
    """The page with every box on it outlined and labelled. Returns (png, dpi, {label: pixel box})."""
    doc = pymupdf.open(str(blank))
    try:
        page = doc[page_no - 1]
        dpi = page_dpi(page)
        k = dpi / 72
        px: dict[str, list[float]] = {}
        on_page = [b for r in rows for b in r["boxes"] if b["page"] == page_no]
        for b in on_page:
            r = pymupdf.Rect(*b["rect"])
            page.draw_rect(r, color=(0.85, 0, 0), width=0.7)
            px[b["label"]] = [round(r.x0 * k), round(r.y0 * k), round(r.x1 * k), round(r.y1 * k)]
        for b in on_page:                  # tags after outlines, so no outline crosses a number
            r = pymupdf.Rect(*b["rect"])
            fs = min(LABEL_PT, max(3.5, r.height * 0.75))
            tw = pymupdf.get_text_length(b["label"], fontname="helv", fontsize=fs)
            tag = pymupdf.Rect(r.x0, r.y0, r.x0 + tw + 1.2, r.y0 + fs + 0.6)
            page.draw_rect(tag, color=None, fill=(1, 1, 1), fill_opacity=0.85)
            page.insert_text((tag.x0 + 0.6, tag.y1 - fs * 0.22), b["label"], fontname="helv", fontsize=fs,
                             color=(0.85, 0, 0))
        png = page.get_pixmap(dpi=dpi).tobytes("png")
        return png, dpi, px
    finally:
        doc.close()


def field_list(rows: list[dict], page_no: int, px: dict[str, list[float]]) -> list[dict]:
    out = []
    for r in rows:
        here = [b for b in r["boxes"] if b["page"] == page_no]
        if not here:
            continue
        s = r["spec"]
        item: dict[str, Any] = {"id": r["id"], "name": r["name"], "type": s.get("type")}
        for k in ("semantic_type", "pattern"):
            if s.get(k):
                item[k] = s[k]
        if s.get("values") and not s.get("widgets"):
            item["values"] = s["values"][:30]
        if s.get("description"):
            item["description"] = str(s["description"])[:200]
        w = s.get("widget") or next(iter((s.get("widgets") or {}).values()), {})
        if w.get("path"):
            item["publisher_field_name"] = w["path"]
        if s.get("widgets"):
            item["options"] = [{"box": b["label"], "on_state": b.get("on_state"), "caption": b.get("caption"),
                                "pixel_box": px[b["label"]]} for b in here]
            if len(here) < len(r["boxes"]):
                item["note"] = f"{len(r['boxes']) - len(here)} more option box(es) on other pages"
        else:
            item["pixel_box"] = px[here[0]["label"]]
        out.append(item)
    return out


# ------------------------------------------------------------------ model

def _client(model: str):
    from petey.synth.generate import make_client
    return make_client(model)


def _key(model: str, png: bytes, listing: str) -> str:
    h = hashlib.sha256()
    for part in (model.encode(), SYSTEM.encode(), json.dumps(SCHEMA, sort_keys=True).encode(), png, listing.encode()):
        h.update(hashlib.sha256(part).digest())
    return h.hexdigest()[:24]


def request(model: str, png: bytes, items: list[dict], *, page_no: int, n_pages: int, form: str) -> tuple[str, dict]:
    """(cache key, Messages API params) for one page."""
    listing = json.dumps(items, ensure_ascii=False)
    user = (f"Form {form}, page {page_no} of {n_pages}. The fields outlined on this page:\n{listing}\n\n"
            "Check every field and return JSON.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                            "data": base64.standard_b64encode(png).decode("ascii")}},
               {"type": "text", "text": user}]
    return _key(model, png, listing), dict(
        model=model, max_tokens=64000, system=SYSTEM, messages=[{"role": "user", "content": content}],
        output_config={"format": {"type": "json_schema", "schema": SCHEMA}})


def parse(resp) -> tuple[dict, dict]:
    """({id: answer}, usage) from a response: accepted ids become bare accepts, flags keep their detail."""
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
             "stop_reason": resp.stop_reason, "model_served": resp.model}
    answers: dict[str, dict] = {}
    try:
        j = json.loads(text)
        for i in j.get("accepted") or []:
            answers[str(i)] = {"id": str(i), "verdict": "accept", "problem": "none"}
        for a in j.get("flags") or []:
            answers[str(a.get("id"))] = {**a, "verdict": "flag"}
    except (json.JSONDecodeError, AttributeError):
        usage["parse_error"] = text[:200]
    return answers, usage


def _store(key: str, answers: dict, usage: dict, form: str, page_no: int) -> None:
    if usage.get("stop_reason") == "end_turn" and answers:      # only complete answers are cached
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / f"{key}.json").write_text(json.dumps({"answers": answers, "usage": usage, "form": form,
                                                       "page": page_no}, indent=1))


def cached(key: str) -> Optional[dict]:
    cp = CACHE / f"{key}.json"
    return json.loads(cp.read_text()) if cp.exists() else None


def ask(client, model: str, png: bytes, items: list[dict], *, page_no: int, n_pages: int,
        form: str) -> tuple[dict, dict]:
    """One call for one page (cached). Returns ({id: answer}, usage)."""
    key, params = request(model, png, items, page_no=page_no, n_pages=n_pages, form=form)
    c = cached(key)
    if c is not None:
        return c["answers"], {**c["usage"], "cached": True}
    t0 = time.time()
    with client.messages.stream(**params) as s:
        resp = s.get_final_message()
    answers, usage = parse(resp)
    usage["seconds"] = round(time.time() - t0, 1)
    try:
        from petey.label import call_log
        call_log.record(f"page_check/{model}", raw=json.dumps(answers), finish_reason=resp.stop_reason,
                        request={"model": model, "form": form, "page": page_no, "fields": len(items)},
                        usage={k: usage[k] for k in ("input_tokens", "output_tokens")}, elapsed=usage["seconds"])
    except Exception:
        pass
    _store(key, answers, usage, form, page_no)
    return answers, usage


def pages_of(bpt: Path, pages: Optional[set[int]] = None):
    """(blueprint, blank, rows, n_pages, chosen pages) for a blueprint file."""
    bp = yaml.load(bpt.read_text(encoding="utf-8"), Loader=_LOADER) or {}
    blank = resolve_blank(bp)
    if blank is None:
        raise SystemExit(f"{bpt}: blank PDF not found")
    rows = numbered(bp)
    with pymupdf.open(str(blank)) as d:
        n_pages = len(d)
    want = sorted({b["page"] for r in rows for b in r["boxes"]} & (pages or set(range(1, n_pages + 1))))
    return bp, blank, rows, n_pages, want


def run_batch(bpts: list[Path], *, model: str = MODEL, pages: Optional[set[int]] = None, poll: int = 30,
              resume: Optional[str] = None, log=print) -> dict:
    """Every uncached page of the blueprints in one Message Batch (half price; most finish within the hour).
    Results go to the cache, so `check` afterwards reads them without calls. `resume` collects a batch already
    submitted for the same pages (custom ids are the cache keys, so the same blueprints map onto it)."""
    import anthropic
    reqs, meta = [], {}
    for bpt in bpts:
        bp, blank, rows, n_pages, want = pages_of(bpt, pages)
        form = bp.get("name") or bpt.stem
        for pg in want:
            png, _, px = render(blank, pg, rows)
            key, params = request(model, png, field_list(rows, pg, px), page_no=pg, n_pages=n_pages, form=form)
            if cached(key) is None and key not in meta:
                reqs.append({"custom_id": key, "params": params})
                meta[key] = (form, pg)
    if not reqs:
        log("batch: every page cached")
        return {"requests": 0, "cost_usd": 0.0}
    client = _client(model)
    if resume:
        b = client.messages.batches.retrieve(resume)
        log(f"batch {b.id}: resumed, {b.processing_status}")
    else:
        b = client.messages.batches.create(requests=reqs)
        log(f"batch {b.id}: {len(reqs)} pages submitted")
    t0 = time.time()
    while b.processing_status != "ended":
        time.sleep(poll)
        try:
            b = client.messages.batches.retrieve(b.id)
        except anthropic.APIConnectionError as e:      # a dropped connection while polling; the batch runs on
            log(f"  poll failed ({e}); retrying")        # (2026-10-06: one DNS failure killed the first run)
            continue
        rc = b.request_counts
        log(f"  {int(time.time() - t0)}s: processing {rc.processing}, succeeded {rc.succeeded}, errored {rc.errored}")
    tin = tout = 0
    failed = []
    for r in client.messages.batches.results(b.id):
        form, pg = meta[r.custom_id]
        if r.custom_id not in meta:
            continue
        if r.result.type != "succeeded":
            failed.append(f"{form} p{pg}: {r.result.type}")
            continue
        answers, usage = parse(r.result.message)
        usage["batch"] = b.id
        tin += usage["input_tokens"]; tout += usage["output_tokens"]
        _store(r.custom_id, answers, usage, form, pg)
        if usage.get("stop_reason") != "end_turn" or not answers:
            failed.append(f"{form} p{pg}: {usage.get('stop_reason')} {usage.get('parse_error', '')[:80]}")
    pin, pout = PRICES.get(model, (0.0, 0.0))
    cost = 0.5 * (tin / 1e6 * pin + tout / 1e6 * pout)
    log(f"batch {b.id}: {len(reqs) - len(failed)}/{len(reqs)} pages, {tin} in / {tout} out tokens, "
        f"${cost:.2f} at batch price, {int(time.time() - t0)}s" + (f"; failed: {failed}" if failed else ""))
    return {"batch": b.id, "requests": len(reqs), "failed": failed, "input_tokens": tin, "output_tokens": tout,
            "cost_usd": round(cost, 4)}


# ------------------------------------------------------------------ check

def check(bpt: Path, *, model: str = MODEL, pages: Optional[set[int]] = None, dry: bool = False,
          png_dir: Optional[Path] = None, client=None, log=print) -> dict:
    """Every field on the chosen pages (default all): its answer, keyed by field name."""
    bp, blank, rows, n_pages, want = pages_of(bpt, pages)
    by_id = {r["id"]: r for r in rows}
    fields: dict[str, dict] = {}
    usage_total: collections.Counter = collections.Counter()
    form = bp.get("name") or bpt.stem
    for pg in want:
        png, dpi, px = render(blank, pg, rows)
        items = field_list(rows, pg, px)
        if png_dir is not None:
            png_dir.mkdir(parents=True, exist_ok=True)
            (png_dir / f"{bpt.stem}_p{pg}.png").write_bytes(png)
            (png_dir / f"{bpt.stem}_p{pg}.json").write_text(json.dumps(items, indent=1, ensure_ascii=False))
        if dry:
            log(f"  page {pg}: {len(items)} fields, {dpi:.0f} dpi, {len(png) // 1024} KB")
            continue
        if client is None:
            client = _client(model)
        answers, usage = ask(client, model, png, items, page_no=pg, n_pages=n_pages, form=form)
        if not usage.get("cached"):
            for k in ("input_tokens", "output_tokens"):
                usage_total[k] += usage.get(k, 0)
            usage_total["calls"] += 1
        else:
            usage_total["cached"] += 1
        missing = [it["id"] for it in items if it["id"] not in answers]
        log(f"  page {pg}: {len(items)} fields, {sum(a.get('verdict') == 'flag' for a in answers.values())} flagged"
            + (f", {len(missing)} unanswered" if missing else "")
            + (" (cached)" if usage.get("cached") else f", {usage.get('seconds')}s, {usage.get('stop_reason')}"))
        for it in items:
            name = by_id[it["id"]]["name"]
            a = answers.get(it["id"])
            rec = ({"verdict": a.get("verdict"), "problem": a.get("problem"), "box_holds": a.get("box_holds"),
                    "proposed_name": a.get("proposed_name") or None, "proposed_type": a.get("proposed_type") or None,
                    "reason": a.get("reason"), "page": pg}
                   if a else {"verdict": None, "problem": "unanswered", "page": pg})
            rec["spec"] = spec_hash(by_id[it["id"]]["spec"])
            prev = fields.get(name)
            if prev is None or (rec["verdict"] == "flag" and prev.get("verdict") != "flag"):
                fields[name] = rec            # a group over several pages: a flag on any page stands
    pin, pout = PRICES.get(model, (0.0, 0.0))
    cost = usage_total["input_tokens"] / 1e6 * pin + usage_total["output_tokens"] / 1e6 * pout
    return {"blueprint": str(bpt), "form": form, "blueprint_sha": _sha(bpt), "model": model, "prompt": PROMPT_VERSION,
            "when": time.strftime("%Y-%m-%d %H:%M:%S"), "pages": want, "usage": dict(usage_total),
            "cost_usd": round(cost, 4), "fields": fields}


# ------------------------------------------------------------- record, stamp

def spec_hash(spec: dict) -> str:
    """A field's definition without the `x_petey_*` bookkeeping: a verdict holds while this is unchanged."""
    core = {k: v for k, v in spec.items() if not str(k).startswith("x_petey")}
    return hashlib.sha256(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:10]


def fields_hash(bp: dict) -> str:
    """The blueprint's fields as a whole (each by `spec_hash`): one record per version of the fields."""
    defs = {n: spec_hash(sp) for n, sp in (bp.get("fields") or {}).items() if isinstance(sp, dict)}
    return hashlib.sha256(json.dumps(defs, sort_keys=True).encode()).hexdigest()[:8]


def record_path(bpt: Path, bp: Optional[dict] = None) -> Path:
    """`runs/page_check/<source>__<stem>__<fields hash>.json`, with the hand-review page's source tags (lib / je /
    rl / fl): a library blueprint and its side copy of the same name keep separate records, and so does every
    version of one file (2026-10-06: the pre-loop copy and the post-loop blueprint shared a record, the post-loop
    check overwrote the pre-loop verdicts, and a re-run loop from the pre-loop copy lost the page check's flags)."""
    from petey.validate.hand_review import SOURCES
    if bp is None:
        bp = yaml.load(bpt.read_text(encoding="utf-8"), Loader=_LOADER) or {}
    rp = bpt.resolve()
    tag = next((t for t, d in SOURCES.items() if rp.parent == d.resolve()), None)
    stem = f"{tag}__{bpt.stem}" if tag else f"{bpt.stem}__{hashlib.sha256(str(rp).encode()).hexdigest()[:6]}"
    return OUT / f"{stem}__{fields_hash(bp)}.json"


def save(res: dict, bpt: Path, *, stamp: bool = True) -> Path:
    """Write the record and, unless `stamp` is False, `x_petey_page_check` on the blueprint: when, model, prompt
    version, counts, and where the record is. The stamp travels with copies of the blueprint (a loop's run dir), so
    the witness finds the record from any copy; it changes the file's sha, which hand review reads as stale."""
    bp = yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}
    out = record_path(bpt, bp)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1, ensure_ascii=False))
    if stamp:
        fl = res["fields"].values()
        bp["x_petey_page_check"] = {
            "when": res["when"], "model": res["model"], "prompt": res["prompt"], "pages": res["pages"],
            "fields": len(res["fields"]), "flagged": sum(1 for f in fl if f.get("verdict") == "flag"),
            "unanswered": sum(1 for f in fl if not f.get("verdict")),
            "record": str(out.relative_to(RUNS.parent))}
        bpt.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                       encoding="utf-8")
    return out


def verdicts(bp: dict) -> dict[str, dict]:
    """The stamped page check's verdict per field, for the fields whose definition is unchanged since the check
    (`spec_hash`); a field renamed or retyped since has none. Empty when the blueprint has no stamp or the record is
    gone. No API calls."""
    st = bp.get("x_petey_page_check") or {}
    rp = RUNS.parent / st["record"] if st.get("record") else None
    if rp is None or not rp.exists():
        return {}
    rec = json.loads(rp.read_text(encoding="utf-8"))
    out = {}
    for name, spec in (bp.get("fields") or {}).items():
        v = (rec.get("fields") or {}).get(name)
        if isinstance(spec, dict) and v and v.get("verdict") and v.get("spec") == spec_hash(spec):
            out[name] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("bpt", type=Path, nargs="+")
    ap.add_argument("--pages", default=None, help="comma-separated page numbers (default: every page with fields)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--batch", action="store_true", help="send uncached pages as one Message Batch (half price)")
    ap.add_argument("--resume", default=None, help="collect this already-submitted batch id instead of submitting")
    ap.add_argument("--no-stamp", action="store_true", help="write the record only, leave the blueprint as it is")
    ap.add_argument("--dry", action="store_true", help="render and list only, no model calls")
    ap.add_argument("--png-dir", type=Path, default=None, help="also write each page image and its field list")
    args = ap.parse_args()
    pages = {int(p) for p in args.pages.split(",")} if args.pages else None
    if (args.batch or args.resume) and not args.dry:
        run_batch(args.bpt, model=args.model, pages=pages, resume=args.resume)
    for bpt in args.bpt:
        print(bpt)
        res = check(bpt, model=args.model, pages=pages, dry=args.dry, png_dir=args.png_dir)
        if args.dry:
            continue
        out = save(res, bpt, stamp=not args.no_stamp)
        flags = {n: f for n, f in res["fields"].items() if f.get("verdict") == "flag"}
        print(f"{res['form']}: {len(res['fields'])} fields, {len(flags)} flagged"
              + (f", ${res['cost_usd']} live" if res["cost_usd"] else "") + f"  -> {out}")
        for n, f in flags.items():
            prop = " ".join(x for x in (f.get("proposed_name"), f.get("proposed_type")) if x)
            print(f"  {n:44} {f['problem']:13} {prop:30} {(f.get('reason') or '')[:100]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
