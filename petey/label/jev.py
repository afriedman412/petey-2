"""Jev (TypeSafe System One) as a second opinion on name flags: do this text and this field refer to the same thing?

The name check's text-match model is strict but misreads abbreviations it never learned (`gl_med_exp`: 0.015);
Jev reads them (0.93) but accepts look-alikes too readily (a combined name holding the right words), so it does not
vote: a tooltip flag Jev scores as a clear match carries a note for the reviewer (`witness.second_opinion`). As a vote
(flag -> hint) it cleared 2 looked-at false alarms and lost 2 real errors of 57 (2026-10-13).

The question is the lean one (`QUESTION`): as good as the long text-match-eval wording on 491 abbreviated pairs and
25% fewer tokens. Answers are cached on disk by request hash (runs/jev/cache, shared with eval/text_match_eval.py),
so a field is asked once per (text, name, question). PETEY_JEV=0 turns it off; without TYPESAFE_API_KEY it is off.
An API failure answers None and changes nothing.
"""
from __future__ import annotations

import concurrent.futures as cf
import hashlib
import json
import os
from typing import Optional

from petey.paths import RUNS

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
CACHE = RUNS / "jev" / "cache"
QUESTION = {"type": "noul", "instructions": "Do `text` and `field` refer to the same thing?",
            "criteria": {"true": "The same thing, possibly abbreviated or in other words.",
                         "false": "Different things, even if they look alike (another row, column or item)."}}


def _key() -> Optional[str]:
    from petey.synth.generate import _load_keys
    _load_keys()
    return os.environ.get("TYPESAFE_API_KEY")


def available() -> bool:
    return os.environ.get("PETEY_JEV", "1") != "0" and bool(_key())


def describes(pairs: list[tuple[str, str]], workers: int = 8) -> list[Optional[float]]:
    """P(text and field are the same thing) for each (text, field), from the cache or one call each; None where
    Jev is off or the call failed."""
    if not pairs or not available():
        return [None] * len(pairs)
    key = _key()

    def one(p: tuple[str, str]) -> Optional[float]:
        body = {"model": MODEL, "state": {"text": p[0], "field": p[1]}, "questions": {"describes": QUESTION}}
        cp = CACHE / f"{hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()}.json"
        if cp.exists():
            res = json.loads(cp.read_text())
        else:
            try:
                import httpx
                with httpx.Client() as c:
                    for attempt in range(4):
                        r = c.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=60)
                        if r.status_code == 429 and attempt < 3:
                            import time
                            time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
                            continue
                        r.raise_for_status()
                        break
                res = r.json()
            except Exception:
                return None
            CACHE.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(res))
        return ((res.get("answers") or {}).get("describes") or {}).get("noul")

    with cf.ThreadPoolExecutor(workers) as ex:
        return list(ex.map(one, pairs))
