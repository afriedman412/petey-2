"""OpenAI's Decisions API on the same page requests Jev gets (2026-10-15, Andrew: "can you see how well openAI
decisions does?"; developers.openai.com/api/docs/guides/decisions, public beta).

The request Jev gets (`jev_page.requests`, `eval/jev_page_check.jobs_for`: the page image with every box outlined and
numbered, the field list, one Noul per field) is sent as one Decisions call: the state as text, the page as an inline
base64 image, each Noul as a `predicate` question whose instructions carry Jev's question and its true / false
criteria. Answers come back in Jev's shape (`{"answers": {qid: {"noul": p}}, "usage": {"input_tokens": n}}`) so the
scoring is the same.

Model gpt-6-luna; $0.10 per million input tokens, output free (2026-10-15). The key is OPENAI_API_KEY, read from
.env or petey-master/.env at run time (`generate._load_keys`). Responses cached under runs/decisions/cache.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Optional

import httpx

from petey.paths import RUNS

URL = "https://api.openai.com/v1/decisions"
MODEL = "gpt-6-luna"
PRICE = 0.10                   # $ per million input tokens, output free (2026-10-15)
CACHE = RUNS / "decisions" / "cache"


def _key() -> Optional[str]:
    from petey.synth.generate import _load_keys
    _load_keys()
    return os.environ.get("OPENAI_API_KEY")


def to_openai(body: dict, imgs: dict[str, bytes]) -> dict:
    """Jev's System One body as a Decisions request."""
    state = body["state"]
    content = [{"type": "input_text", "text": "state: " + json.dumps(state, ensure_ascii=False)}]
    for ref, png in imgs.items():
        content.append({"type": "input_text", "text": f"image `{ref}`:"})
        content.append({"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()})
    qs = []
    for qid, q in body["questions"].items():
        crit = q.get("criteria") or {}
        text = json.dumps(q["instructions"], ensure_ascii=False) if not isinstance(q["instructions"], str) else q["instructions"]
        if crit:
            text += f"\nTrue: {crit.get('true', '')}\nFalse: {crit.get('false', '')}"
        qs.append({"type": "predicate", "name": qid, "instructions": text})
    return {"model": MODEL, "input": [{"role": "user", "content": content}], "questions": qs}


def ask(client: httpx.Client, key: str, body: dict, imgs: dict[str, bytes]) -> dict:
    """One request, from the cache when it was asked before; raises RuntimeError on an API error."""
    req = to_openai(body, imgs)
    h = hashlib.sha256(json.dumps(req, sort_keys=True).encode()).hexdigest()
    cp = CACHE / f"{h}.json"
    if cp.exists():
        return json.loads(cp.read_text())
    for attempt in range(6):
        r = client.post(URL, json=req, timeout=180, headers={"Authorization": f"Bearer {key}"})
        if r.status_code in (429, 500, 502, 503) and attempt < 5:
            time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
            continue
        if r.status_code >= 400:
            raise RuntimeError(f"{r.status_code}: {r.text[:600]}")
        break
    raw = r.json()
    out = {"answers": {a["name"]: {"noul": a.get("probability")} for a in raw.get("answers") or []
                       if a.get("type") == "predicate"},
           "refusals": [a.get("name") for a in raw.get("answers") or [] if a.get("type") == "refusal"],
           "usage": {"input_tokens": (raw.get("usage") or {}).get("input_tokens", 0)}}
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(out))
    return out


def ask_split(client: httpx.Client, key: str, body: dict, imgs: dict[str, bytes]) -> dict:
    """`ask`, halving the questions while the request is too long for the API; answers and usage merged."""
    try:
        return ask(client, key, body, imgs)
    except RuntimeError as e:
        s = str(e).lower()
        if not any(w in s for w in ("token", "too long", "too large", "context")) or len(body["questions"]) < 2:
            raise
    qs = list(body["questions"].items())
    out = {"answers": {}, "usage": {"input_tokens": 0}}
    for half in (qs[:len(qs) // 2], qs[len(qs) // 2:]):
        res = ask_split(client, key, dict(body, questions=dict(half)), imgs)
        out["answers"].update(res.get("answers") or {})
        out["usage"]["input_tokens"] += (res.get("usage") or {}).get("input_tokens", 0)
    return out
