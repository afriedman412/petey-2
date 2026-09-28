"""Persist every model call so a failure is diagnosable without a re-run.

Written after losing time to four separate truncations this session, each
of which had to be re-run to find out what happened:

  - `auto_label` raised "did not return {'labels': [...]} shape" while
    printing `text[:500]`. The response was 22,916 chars with 658 entries
    and had been cut mid-JSON; its first 500 chars looked perfectly valid.
  - Two Gemini calls in the VLM sweep returned truncated / empty bodies;
    the `.raw` file was only written on parse failure, so the empty one
    left nothing behind at all.
  - `petey extract` exits 0 and writes `[]` when its API call fails, so a
    failed call is indistinguishable from a model that found nothing.

The common missing signal is `finish_reason` / `stop_reason`. Every
provider returns it, it says "length" or "max_tokens" when the answer was
cut, and reading it turns a mystery into a one-line diagnosis. So: log the
raw body and the finish reason for EVERY call, not just failing ones, and
make truncation a named failure rather than a shape error.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from petey.paths import RUNS
HERE = Path(__file__).resolve().parent
CALLS = RUNS / "_calls"

# finish_reason / stop_reason values that mean "the answer was cut off".
TRUNCATED = {"length", "max_tokens", "MAX_TOKENS", "model_length"}


def record(tag: str, *, raw: str, finish_reason: Optional[str] = None,
           request: Optional[dict] = None, usage: Optional[dict] = None,
           elapsed: Optional[float] = None) -> Path:
    """Write one call's full record. Returns the path."""
    d = CALLS / tag
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{time.strftime('%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.json"
    p.write_text(json.dumps({
        "tag": tag,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_s": round(elapsed, 2) if elapsed is not None else None,
        "finish_reason": finish_reason,
        "truncated": finish_reason in TRUNCATED if finish_reason else None,
        "chars": len(raw or ""),
        "usage": usage,
        "request": request,
        "raw": raw,
    }, indent=2, ensure_ascii=False))
    return p


def describe(raw: str, finish_reason: Optional[str] = None,
             expected: Optional[int] = None) -> str:
    """A one-line diagnosis for an error message."""
    bits = [f"{len(raw or ''):,} chars"]
    if finish_reason:
        bits.append(f"finish_reason={finish_reason}")
    if finish_reason in TRUNCATED:
        bits.append("TRUNCATED — raise max_tokens or shrink the batch")
    elif not (raw or "").strip():
        bits.append("EMPTY body")
    elif not (raw or "").rstrip().endswith(("}", "]")):
        bits.append("ends mid-structure, likely truncated")
    if expected is not None:
        bits.append(f"expected {expected} entries")
    return ", ".join(bits)
