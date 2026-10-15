"""Jev (TypeSafe System One) on every field of a blueprint, with the page image (2026-10-15).

Andrew: Jev is far cheaper than the models in use, so wire the page image in now and get better answers as the
models improve. One request per page (split when the page has many fields): the `state` is the page of the blank
with every box outlined in red and numbered (the page check's picture, `page_check.render`, at Jev's image limit:
1568 px long edge, ~140 dpi on a letter page) and the field list; each field gets the Noul `name_fits` (does the name
say what a filer writes in the box tagged with its number?) with the text evidence text-only Jev had (`states`:
printed text at the box, column / row headers, publisher text, the classifier's caption, neighbours), and each
checkbox also `one_question` (one of several checkboxes answering one question?).

Measured against the known errors on the 19 validated forms (eval/jev_page_check.py, 2026-10-15): at the page check's
234 flagged fields Jev catches 122 of 240 (the page check 209); text only it needed 821 fields to catch 130. About
0.3 cents a page. A 300 dpi close-up per box did not help, so the whole page it is.

Responses are cached under runs/jev/cache by request hash. The key is TYPESAFE_API_KEY (.env).
"""
from __future__ import annotations

import base64
import concurrent.futures as cf
import hashlib
import json
import math
import os
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx
import yaml

from petey.paths import RUNS
from petey.validate import page_check as pc
from petey.validate import witness as W
from petey.validate.field_chain import _page_lines
from petey.validate.retype import resolve_blank

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.14.0"           # pinned (an alias moves when a release ships); images need 1.13+
LIMITS = (1568, 2_458_624)     # Jev's image limits: long edge px, total px
PER_REQUEST = 20               # fields per request; 60 with the text evidence went over the 64k-token limit
CACHE = RUNS / "jev" / "cache"
N_NEIGHBOURS = 6
PRICE = 0.042                  # $ per million input tokens, output free (2026-10-15)

QUESTION = ("`page` is one page of a blank form; every fillable box is outlined in red with its number in a small red "
            "tag at its top-left (an option group's boxes N.a, N.b, ...). `fields` lists each number's name, type and "
            "pixel box. Look at the box tagged `field.id` and the caption printed for it (inside, above, below or "
            "beside it; a table's column header and row label count). Does `field.name` say what a person filling in "
            "the form would write or mark in that box? Names are snake_case with suffixes (_nm name, _dt date, _amt "
            "money, _cd code, _ind checkbox, _txt text, _nbr number); abbreviations and word order are fine.")
FITS = {
    "true": "The name describes the value a filer writes or marks in this box, and tells it apart from the "
            "neighbouring boxes.",
    "false": "The name describes a different box (a neighbour's caption, the row or column next to it, swapped with "
             "another field), is too vague to tell this box from the others, or nothing is written in this box.",
}
ONE_QUESTION = ("`page` is one page of a blank form with every fillable box outlined in red and numbered. The box "
                "tagged `field.id` is a checkbox. Is it one of several separate checkboxes on the page that together "
                "answer a single question (pick one, or pick several, from options printed side by side or stacked), "
                "so that the options belong in one field rather than one field per checkbox?")
ONE_CRITERIA = {
    "true": "It is one option of a printed question whose other options are separate neighbouring checkboxes.",
    "false": "It is a stand-alone yes/no checkbox, or its question has no other separate checkbox on the page.",
}


def _key() -> Optional[str]:
    from petey.synth.generate import _load_keys
    _load_keys()
    return os.environ.get("TYPESAFE_API_KEY")


# ------------------------------------------------------------------ text evidence

def _centre(spec: dict):
    w = (W._widgets(spec) or [{}])[0]
    r = w.get("rect")
    return (w.get("page"), (r[0] + r[2]) / 2, (r[1] + r[3]) / 2) if r else None


def states(bpt: Path) -> dict[str, dict]:
    """`{field: text evidence}` for every field of the blueprint, from the blank, the cached class map and the file:
    what text-only Jev reads (eval/jev_hand_check.py, 2026-10-05)."""
    bp = W._load(bpt)
    blank = resolve_blank(bp)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    words = W.publisher_words(blank) if blank and blank.exists() else {}
    lines = _page_lines(str(blank)) if blank and blank.exists() else {}
    by_page = W.class_map_boxes(blank, None)
    printed = {n: W.page_texts(s, lines) for n, s in fields.items()}
    centres = {n: _centre(s) for n, s in fields.items()}
    out = {}
    for name, spec in fields.items():
        w = (W._widgets(spec) or [{}])[0]
        kind = "option group" if spec.get("widgets") else (w.get("widget_type") or "text")
        b = W._box(spec, by_page) if by_page else None
        near = []
        c = centres[name]
        if c:
            dist = sorted((math.hypot(c[1] - o[1], c[2] - o[2]), n) for n, o in centres.items()
                          if n != name and o and o[0] == c[0])
            for _, n in dist[:N_NEIGHBOURS]:
                ow = (W._widgets(fields[n]) or [{}])[0]
                near.append({"name": n, "kind": ow.get("widget_type") or ("option group" if fields[n].get("widgets") else "text"),
                             "printed_text_at_box": (printed[n] or [None])[0],
                             "publisher_text": (W.publisher_texts(fields[n], words) or [None])[0]})
        st = {
            "form": bp.get("name"),
            "field": {k: v for k, v in {
                "name": name, "kind": kind, "type": spec.get("type"), "semantic_type": spec.get("semantic_type"),
                "description": (spec.get("description") or "")[:240] or None,
                "options": [x.get("caption") or k for k, x in spec["widgets"].items()] if spec.get("widgets") else None,
            }.items() if v},
            "publisher_text": W.publisher_texts(spec, words) or None,
            "printed_text_at_box": printed[name][:3] or None,
            "classifier_caption": (b or {}).get("label"),
            "classifier_class": (b or {}).get("class"),
            "neighbours": near,
        }
        if w.get("rect") and lines.get(w.get("page")):
            pl = lines[w["page"]]
            st["column_header"] = W.column_header(w["rect"], pl)
            st["row_header"] = W.row_header(w["rect"], pl)
        out[name] = {k: v for k, v in st.items() if v not in (None, [], {})}
    return out


# ------------------------------------------------------------------ requests

def image_ref(png: bytes, kind: str = "page") -> str:
    """A reference that cannot occur in the text, stable per image so the cache key is too."""
    return f"{kind}-{uuid.UUID(hashlib.md5(png).hexdigest())}"


def requests(bpt: Path, *, text: bool = True) -> list[tuple[int, dict, dict[str, bytes], dict[str, tuple[str, str]]]]:
    """(page, body, {ref: png}, {question id: (field, 'name_fits' | 'one_question')}) per request."""
    bp = yaml.safe_load(Path(bpt).read_text())
    blank = resolve_blank(bp)
    rows = pc.numbered(bp)
    ev = states(Path(bpt)) if text else {}
    out = []
    for page_no in sorted({b["page"] for r in rows for b in r["boxes"]}):
        png, _dpi, px = pc.render(blank, page_no, rows, limits=LIMITS)
        items = pc.field_list(rows, page_no, px)
        ref = image_ref(png)
        for i in range(0, len(items), PER_REQUEST):
            qs, names = {}, {}
            for it in items[i:i + PER_REQUEST]:
                q = {"field": {k: v for k, v in it.items() if k != "pixel_box"}, "question": QUESTION}
                e = ev.get(it["name"]) or {}
                if e:
                    q["text_at_the_box"] = {k: v for k, v in e.items() if k not in ("form", "field")}
                qs[f"f{it['id']}"] = {"type": "noul", "instructions": q, "criteria": FITS}
                names[f"f{it['id']}"] = (it["name"], "name_fits")
                if (e.get("field") or {}).get("kind") in ("checkbox", "radiobutton"):
                    qs[f"g{it['id']}"] = {"type": "noul", "instructions": dict(q, question=ONE_QUESTION),
                                          "criteria": ONE_CRITERIA}
                    names[f"g{it['id']}"] = (it["name"], "one_question")
            body = {"model": MODEL, "state": {"form": bp.get("name"), "page_number": page_no, "page": ref,
                                              "fields": items}, "questions": qs}
            out.append((page_no, body, {ref: png}, names))
    return out


def ask(client: httpx.Client, key: str, body: dict, imgs: dict[str, bytes]) -> dict:
    """One request, from the cache when it was asked before; raises RuntimeError on an API error."""
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()
                       + b"".join(hashlib.sha256(imgs[r]).digest() for r in sorted(imgs))).hexdigest()
    cp = CACHE / f"img_{h}.json"
    if cp.exists():
        return json.loads(cp.read_text())
    full = dict(body, assets={r: {"type": "image", "format": "png", "data_base64": base64.b64encode(b).decode()}
                              for r, b in imgs.items()})
    for attempt in range(6):
        r = client.post(URL, json=full, timeout=180, headers={"Authorization": f"Bearer {key}",
                                                              "TypeSafe-Danger-Zone-Images": "true"})
        if r.status_code in (429, 529) and attempt < 5:
            time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:400]}")
        break
    out = r.json()
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(out))
    return out


def ask_split(client: httpx.Client, key: str, body: dict, imgs: dict[str, bytes]) -> dict:
    """`ask`, halving the questions while the request is over Jev's token limit; answers and usage merged."""
    try:
        return ask(client, key, body, imgs)
    except RuntimeError as e:
        if "max_tokens_exceeded" not in str(e) or len(body["questions"]) < 2:
            raise
    qs = list(body["questions"].items())
    out = {"answers": {}, "usage": {"input_tokens": 0}}
    for half in (qs[:len(qs) // 2], qs[len(qs) // 2:]):
        b = dict(body, questions=dict(half))
        text = json.dumps(b)
        res = ask_split(client, key, b, {r: v for r, v in imgs.items() if r in text})
        out["answers"].update(res.get("answers") or {})
        out["usage"]["input_tokens"] += (res.get("usage") or {}).get("input_tokens", 0)
    return out


def check(bpts: list[Path], *, text: bool = True, workers: int = 6) -> tuple[dict[str, dict[str, dict]], int]:
    """({blueprint path: {field: {'name_fits': p, 'one_question': p (checkboxes)}}}, input tokens, cached responses included)."""
    key = _key()
    if not key:
        raise SystemExit("TYPESAFE_API_KEY not set (.env)")
    jobs = [(str(p), *r) for p in bpts for r in requests(Path(p), text=text)]
    out: dict[str, dict[str, dict]] = {str(p): {} for p in bpts}
    tokens = 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(ask_split, client, key, j[2], j[3]): j for j in jobs}
        for f in cf.as_completed(futs):
            path, _page, _body, _imgs, names = futs[f]
            res = f.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, (name, q) in names.items():
                v = ((res.get("answers") or {}).get(qid) or {}).get("noul")
                if v is not None:
                    out[path].setdefault(name, {})[q] = v
    return out, tokens
