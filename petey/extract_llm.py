"""Meaning-based extraction: find each blueprint field on the page by NAME.

The production extractor (`petey/extract.py`) reads by geometry and never
calls a model. This one is the other arm of the validation loop: it is
shown the blueprint's field names, types and descriptions and the page
(text layer, or rendered images), and nothing about geometry — no rects,
no AcroForm paths, no widget block. Where the two arms disagree on a case
the geometry arm agreed on, the name does not describe the widget it is
bound to (`method_delta.py`). It is a measuring instrument, not a product
path; it used to be the external `petey` CLI and now runs in this repo.

    parser="pymupdf"  the page text layer goes to the model (cheap)
    parser="image"    page images go to the model (for flattened scans)

Responses are cached under runs/_petey_cache keyed by (fields, document
bytes, parser, model), so re-scoring a run costs nothing. A non-empty
`cache_salt` adds itself to the key: repeated reads of one document under
different salts are fresh calls (eval/reader_stability.py), and an empty
salt leaves every existing key unchanged.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml

from petey.models import model_for
from petey.paths import RUNS

DEFAULT_MODEL = model_for("reader")
CACHE = RUNS / "_petey_cache"
MAX_FIELDS_PER_CALL = 120
MAX_PAGES = 40   # a hard ceiling; the pages sent are the ones that carry fields
MAX_TOKENS = 16384
USAGE: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "calls": 0}  # accumulates per process

SYSTEM = """You extract values from a COMPLETED form according to a \
blueprint. You are given the blueprint's fields — each with a name, a type, \
and sometimes a description or the allowed values — and the form's content \
(page text, or page images). Return the value present on the form for each \
field.

You are given NO coordinates and NO widget information. Locate each field \
yourself, from its name and description and the printed labels on the form.

Rules:
- Return the value as it appears on the form. Dates may be written as \
YYYY-MM-DD; otherwise do not reformat or correct values.
- boolean fields: true if the box is marked, false if it is present and \
unmarked, null if you cannot tell.
- In page text, a checkbox or radio option appears as [x] (selected) or \
[ ] (not selected) just before its printed caption. Read a category \
field from which caption carries [x]; map the caption to one of the \
listed values using the field's description when the values are codes.
- category fields: one of the listed values, or null.
- If nothing on the form corresponds to a field, return null. Do NOT guess \
and do NOT return a value from a different field because it seems close.
- GROUND EVERY ANSWER IN THIS DOCUMENT. You may recognise the form; do not \
answer from that recollection. If your memory of the form conflicts with \
the content shown, the content wins.

Return JSON only: {"values": {"<field_name>": <value>, ...}}"""

_HIDDEN = {"widget", "widgets", "pattern", "semantic_type"}


def field_view(bpt: dict) -> list[dict]:
    """The blueprint as the meaning-based reader sees it: no geometry."""
    out = []
    for name, spec in (bpt.get("fields") or {}).items():
        e: dict[str, Any] = {"name": name, "type": spec.get("type", "string")}
        if spec.get("description"):
            e["description"] = spec["description"]
        if spec.get("values"):
            e["values"] = list(spec["values"])
        out.append(e)
    return out


def field_pages(bpt: dict, page_count: int) -> list[int]:
    """1-based pages that carry a field, else every page. The reader used
    to see the first 12 pages only: on 21-526EZ that hid 116 fields on
    pages 13-15, and no name could make them findable."""
    pages = set()
    for spec in (bpt.get("fields") or {}).values():
        w = spec.get("widget") or {}
        if w.get("page"):
            pages.add(int(w["page"]))
        for wb in (spec.get("widgets") or {}).values():
            if wb.get("page"):
                pages.add(int(wb["page"]))
    pages = sorted(p for p in pages if 1 <= p <= page_count)
    return (pages or list(range(1, page_count + 1)))[:MAX_PAGES]


def page_texts(pdf: Path, pages: Optional[list[int]] = None) -> list[tuple[int, str]]:
    doc = pymupdf.open(str(pdf))
    try:
        pages = pages or list(range(1, min(len(doc), MAX_PAGES) + 1))
        return [(p, doc[p - 1].get_text("text")) for p in pages]
    finally:
        doc.close()


def option_boxes(bpt: dict) -> dict[int, list[dict]]:
    """Every checkbox / radio option box in the blueprint, by page: `{page:
    [{rect, group, key}]}` — a category's options (group = field name, key =
    the option's on-state) and lone booleans (group = None)."""
    out: dict[int, list[dict]] = {}
    for name, spec in (bpt.get("fields") or {}).items():
        ws = spec.get("widgets") or {}
        if ws:
            for st, wb in ws.items():
                if wb.get("page") and wb.get("rect"):
                    out.setdefault(int(wb["page"]), []).append({"rect": wb["rect"], "group": name, "key": st,
                                                                "caption": wb.get("caption") or (st if not str(st).isdigit() else None)})
            continue
        w = spec.get("widget") or {}
        if w.get("widget_type") in ("checkbox", "radiobutton") and w.get("page") and w.get("rect"):
            out.setdefault(int(w["page"]), []).append({"rect": w["rect"], "group": None, "key": name, "caption": None})
    return out


def page_texts_with_marks(pdf: Path, blank: Path, bpt: dict,
                          pages: Optional[list[int]] = None) -> list[tuple[int, str]]:
    """Page text with a [x] / [ ] token at every option box, decided by the
    ink in the box against the blank (petey.validate.ink). The text layer
    never records which option is selected — the mark is drawn, not
    written — so a text-mode reader could not see radio states at all
    (10-10EZ: 19 groups unlocatable). The blueprint's rectangles place the
    tokens; the reader still gets no coordinates and no widget names."""
    from petey.validate import ink
    boxes = option_boxes(bpt)
    doc = pymupdf.open(str(pdf))
    bdoc = pymupdf.open(str(blank))
    try:
        pages = pages or list(range(1, min(len(doc), MAX_PAGES) + 1))
        out = []
        for p in pages:
            page = doc[p - 1]
            words = [(w[0], w[1], w[2], w[3], w[4]) for w in page.get_text("words")]
            marks = []
            if p in boxes and p - 1 < len(bdoc):
                bpage = bdoc[p - 1]
                # the state itself: from the widget when the document still
                # has its form layer (exact), else from ink in the box
                # against the blank (flattened cases, flat forms)
                states = {}
                for w in page.widgets() or []:
                    if w.field_type_string in ("CheckBox", "RadioButton"):
                        states[tuple(round(c, 1) for c in w.rect)] = w.field_value not in (None, "", "Off")
                by_group: dict = {}
                for b in boxes[p]:
                    by_group.setdefault(b["group"], []).append(b)
                for group, opts in by_group.items():
                    if states:
                        for o in opts:
                            marks.append((o, bool(states.get(tuple(round(c, 1) for c in o["rect"]), False))))
                        continue
                    deltas = [(ink.ink_delta(page, bpage, o["rect"]), o) for o in opts]
                    if group is None:
                        for d, o in deltas:
                            marks.append((o, d >= ink.THRESHOLD))
                    else:
                        best = max(deltas, key=lambda t: t[0])
                        for d, o in deltas:
                            marks.append((o, o is best[1] and d >= ink.THRESHOLD))
            # the widget's own glyph (a ZapfDingbats check reads as "3") sits
            # inside the box in the text layer; the token replaces it
            rects = [pymupdf.Rect(*o["rect"]) for o, _ in marks]
            words = [w for w in words if not any(r.contains(pymupdf.Point((w[0] + w[2]) / 2, (w[1] + w[3]) / 2)) for r in rects)]
            tokens = {}
            for o, on in marks:
                x0, y0, x1, y1 = o["rect"]
                words.append((x0, y0, x1, y1, "[x]" if on else "[ ]"))
                tokens[(x0, y0)] = o.get("caption")
            # lines in reading order: cluster by vertical centre, then x. A
            # token sits just before the caption printed beside its box; when
            # the caption is not the next word (column headers above a grid),
            # the token carries it: "[x] NO"
            words.sort(key=lambda w: (round((w[1] + w[3]) / 2 / 4), w[0]))
            lines, cur, cur_y = [], [], None
            def _emit(ws):
                parts = []
                for i, w in enumerate(ws):
                    t = w[4]
                    cap = tokens.get((w[0], w[1])) if t in ("[x]", "[ ]") else None
                    # a printed word starting within 14 pt of the box's right
                    # edge IS the caption a person reads; the blueprint's
                    # caption is added only when nothing is printed beside
                    # the box (column headers above a yes/no grid)
                    nxt = ws[i + 1] if i + 1 < len(ws) else None
                    adjacent = nxt is not None and nxt[4] not in ("[x]", "[ ]") and 0 <= nxt[0] - w[2] <= 14
                    if cap and not adjacent:
                        t = f"{t} {str(cap).strip()}"
                    parts.append(t)
                return " ".join(parts)
            for w in words:
                cy = round((w[1] + w[3]) / 2 / 4)
                if cur and cy != cur_y:
                    lines.append(_emit(cur)); cur = []
                cur.append(w); cur_y = cy
            if cur:
                lines.append(_emit(cur))
            out.append((p, "\n".join(lines)))
        return out
    finally:
        doc.close(); bdoc.close()


def page_images(pdf: Path, pages: Optional[list[int]] = None, dpi: int = 150) -> list[bytes]:
    doc = pymupdf.open(str(pdf))
    try:
        pages = pages or list(range(1, min(len(doc), MAX_PAGES) + 1))
        return [doc[p - 1].get_pixmap(dpi=dpi).tobytes("png") for p in pages]
    finally:
        doc.close()


def _parse(text: str) -> dict:
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return {}
    try:
        return (json.loads(m.group(0)) or {}).get("values") or {}
    except json.JSONDecodeError:
        return {}


def _ask_local(model: str, fields: list[dict], doc_parts: list[dict]) -> str:
    """A local model through ollama (`ollama:<name>`), text mode only. The
    same system prompt and field list; no API, no key."""
    import os
    import urllib.request
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    user = "\n\n".join(p["text"] for p in doc_parts if p.get("type") == "text")
    user += ("\n\nBlueprint fields:\n```json\n" + json.dumps(fields, indent=1) + "\n```\n"
             "Return {\"values\": {...}} with one entry per field.")
    body = json.dumps({"model": model.split(":", 1)[1], "stream": False, "format": "json",
                       "options": {"temperature": 0, "num_ctx": 32768, "num_predict": 8192},
                       "messages": [{"role": "system", "content": SYSTEM},
                                    {"role": "user", "content": user}]}).encode()
    req = urllib.request.Request(f"{host}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=1800) as resp:
        data = json.loads(resp.read())
    USAGE["input_tokens"] += int(data.get("prompt_eval_count") or 0)
    USAGE["output_tokens"] += int(data.get("eval_count") or 0)
    USAGE["calls"] += 1
    return data["message"]["content"]


def _ask(client, model: str, fields: list[dict], doc_parts: list[dict],
         doc_key: bytes, parser: str, salt: str = "") -> dict:
    key = hashlib.sha256(
        doc_key + b"\x00" + model.encode() + b"\x00" + parser.encode()
        + b"\x00" + json.dumps(fields, sort_keys=True).encode()
        + b"\x00fixed-sampling-fieldpages"  # cache namespace: answers sampled at temperature 0 / low effort
        + (b"\x00salt:" + salt.encode() if salt else b"")
    ).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))
    content = list(doc_parts)
    content.append({"type": "text", "text":
                    "Blueprint fields:\n```json\n"
                    + json.dumps(fields, indent=1) + "\n```\n"
                    "Return {\"values\": {...}} with one entry per field."})
    if model.startswith("ollama:"):
        out = _parse(_ask_local(model, fields, doc_parts))
        cached.write_text(json.dumps(out, indent=2, default=str))
        return out
    from petey.synth.generate import chat_compat, provider_for
    if provider_for(model) is not None:
        text, _, u = chat_compat(client, model, system=SYSTEM, content=content, max_tokens=MAX_TOKENS)
        USAGE["input_tokens"] += u["input_tokens"]
        USAGE["output_tokens"] += u["output_tokens"]
        USAGE["calls"] += 1
        out = _parse(text)
        cached.write_text(json.dumps(out, indent=2, default=str))
        return out
    kwargs: dict = dict(model=model, max_tokens=MAX_TOKENS, system=SYSTEM,
                        messages=[{"role": "user", "content": content}])
    # The reader is the loop's judge, so it should read the same way twice.
    # Models up to the 4.6 generation take a temperature; the 5 generation
    # rejects sampling parameters and takes an effort level instead.
    if re.search(r"-(4-[0-6]|3-\d)", model):
        kwargs["extra_body"] = {"temperature": 0}   # not a typed parameter in SDK 1.x
    else:
        kwargs["output_config"] = {"effort": "low"}
    with client.messages.stream(**kwargs) as stream:
        final = stream.get_final_message()
    USAGE["input_tokens"] += final.usage.input_tokens
    USAGE["output_tokens"] += final.usage.output_tokens
    USAGE["calls"] += 1
    text = "".join(b.text for b in final.content
                   if getattr(b, "type", None) == "text")
    out = _parse(text)
    cached.write_text(json.dumps(out, indent=2, default=str))
    return out


def field_page_of(spec: dict) -> Optional[int]:
    w = spec.get("widget") or {}
    if w.get("page"):
        return int(w["page"])
    for wb in (spec.get("widgets") or {}).values():
        if wb.get("page"):
            return int(wb["page"])
    return None


def extract_llm(
    bpt: dict, pdf: Path, *, parser: str = "pymupdf",
    model: str = DEFAULT_MODEL, client: Any = None, cache_salt: str = "",
) -> dict[str, Any]:
    """`{field_name: value}` for one document, found by meaning. One call per page (2026-10-19: it was one call per
    120 fields with the whole document in each, cached on the whole document and the whole field list, so any
    rename or refill missed every page): a page's fields are read against that page's text (or image) and cached on
    them, so a page nothing changed on is free in the next round; fields on no page are read against the whole
    document. The pages go out together."""
    pdf = Path(pdf)
    with pymupdf.open(str(pdf)) as _d:
        pages = field_pages(bpt, len(_d))
    blank = None
    if parser == "pymupdf" and option_boxes(bpt):
        try:
            from petey.validate.retype import resolve_blank
            blank = resolve_blank(bpt)
        except Exception:
            blank = None
    if parser == "image":
        parts = {p: ({"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                  "data": base64.b64encode(png).decode()}}, png)
                 for p, png in zip(pages, page_images(pdf, pages))}
    elif parser == "pymupdf":
        texts = page_texts_with_marks(pdf, blank, bpt, pages) if blank else page_texts(pdf, pages)
        parts = {p: ({"type": "text", "text": f"Form content (page {p} of the document):\n{t}"}, t.encode()) for p, t in texts}
    else:
        raise ValueError(f"unknown parser {parser!r}; use pymupdf or image")
    fields = field_view(bpt)
    specs = bpt.get("fields") or {}
    by_page: dict[Optional[int], list[dict]] = {}
    for f in fields:
        pg = field_page_of(specs.get(f["name"]) or {})
        by_page.setdefault(pg if pg in parts else None, []).append(f)
    if client is None and not model.startswith("ollama:"):
        from petey.synth.generate import make_client, provider_for
        if provider_for(model) is not None:             # Gemini, a local model (petey/models.py)
            client = make_client(model)
        else:
            import anthropic
            client = anthropic.Anthropic()
    jobs = []                       # (fields batch, doc parts, key bytes)
    for pg, fs in by_page.items():
        if pg is None:              # no page of their own: the whole document, as before
            doc_parts = [parts[p][0] for p in pages]
            key = b"".join(parts[p][1] for p in pages)
        else:
            doc_parts, key = [parts[pg][0]], parts[pg][1]
        for i in range(0, len(fs), MAX_FIELDS_PER_CALL):
            jobs.append((fs[i:i + MAX_FIELDS_PER_CALL], doc_parts, key))
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, min(8, len(jobs)))) as ex:
        results = list(ex.map(lambda j: _ask(client, model, j[0], j[1], j[2], parser, salt=cache_salt), jobs))
    values: dict[str, Any] = {}
    for (batch, _, _), got in zip(jobs, results):
        for f in batch:
            values[f["name"]] = got.get(f["name"])
    return values


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--blueprint", required=True, type=Path)
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--parser", choices=["pymupdf", "image"], default="pymupdf")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass
    bpt = yaml.safe_load(args.blueprint.read_text(encoding="utf-8"))
    values = extract_llm(bpt, args.pdf, parser=args.parser, model=args.model)
    text = json.dumps(values, indent=2, default=str)
    if args.output:
        args.output.write_text(text)
        print(f"[ok] {len(values)} fields -> {args.output}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
