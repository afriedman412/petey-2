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
bytes, parser, model), so re-scoring a run costs nothing.
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

from petey.paths import RUNS

DEFAULT_MODEL = "claude-sonnet-4-6"
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
         doc_key: bytes, parser: str) -> dict:
    key = hashlib.sha256(
        doc_key + b"\x00" + model.encode() + b"\x00" + parser.encode()
        + b"\x00" + json.dumps(fields, sort_keys=True).encode()
        + b"\x00fixed-sampling-fieldpages"  # cache namespace: answers sampled at temperature 0 / low effort
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


def extract_llm(
    bpt: dict, pdf: Path, *, parser: str = "pymupdf",
    model: str = DEFAULT_MODEL, client: Any = None,
) -> dict[str, Any]:
    """`{field_name: value}` for one document, found by meaning."""
    pdf = Path(pdf)
    doc_bytes = pdf.read_bytes()
    with pymupdf.open(str(pdf)) as _d:
        pages = field_pages(bpt, len(_d))
    if parser == "image":
        doc_parts = [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": "image/png",
                                         "data": base64.b64encode(p).decode()}}
            for p in page_images(pdf, pages)
        ]
    elif parser == "pymupdf":
        texts = page_texts(pdf, pages)
        joined = "\n\n".join(f"=== page {p} ===\n{t}" for p, t in texts)
        doc_parts = [{"type": "text", "text": "Form content:\n" + joined}]
    else:
        raise ValueError(f"unknown parser {parser!r}; use pymupdf or image")
    fields = field_view(bpt)
    if client is None and not model.startswith("ollama:"):
        import anthropic
        client = anthropic.Anthropic()
    values: dict[str, Any] = {}
    for i in range(0, len(fields), MAX_FIELDS_PER_CALL):
        batch = fields[i:i + MAX_FIELDS_PER_CALL]
        got = _ask(client, model, batch, doc_parts, doc_bytes, parser)
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
