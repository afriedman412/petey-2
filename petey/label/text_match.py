"""Does this text describe this field? A small cross-encoder that scores a (text, field) pair from 0 to 1, run
offline with onnxruntime (Andrew, 2026-10-09: adjudicate between text options with a local model instead of
synonym lists and hand-set weights).

The text is something the PDF says about a widget: the tooltip, the XFA caption, a readable widget path
("Parient Last Name", `CommercialStructure_PhysicalAddress_LineTwo_A`), a line printed near the box, the
classifier's caption. The field is the blueprint's name in words ("patient sex code"), or for an option its
group, key and own tooltip. Which fields a text is compared against (near the box, same section) is decided by
`witness.Names.rivals`, not here.

Trained by `eval/text_match_train.py` on pairs from `eval/text_match_data.py`; weights in `models/text_match/`
(gitignored). Without a model file every scorer returns None and callers fall back to the rules.

`model.int8.onnx` (dynamic int8 quantization, written by the training script) is 2.3x faster on the M1 with held-out
top-1 86.6% -> 86.4%, but it moves scores near the witness's 'does not describe' cutoff (P < 0.01): on the name
fixture it lost 2 of 15 real errors (1014r 'Contractor or Agent' vs `email_address_txt`: 0.0067 -> 0.0115). The
full-precision model is the default; PETEY_TEXT_MATCH_INT8=1 picks int8 for long dev runs (the fixture: 24 -> 9 min).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from petey.paths import MODELS

MODEL_DIR = Path(os.environ.get("PETEY_TEXT_MATCH_DIR") or MODELS / "text_match")     # override: compare two models
MAX_LEN = 96
_BATCH = 64

# slug pieces the labeler writes, in words; the model learns the rest (street ~ address, M ~ male)
_WORDS = {"nm": "name", "no": "number", "nbr": "number", "num": "number", "dt": "date", "amt": "amount",
          "addr": "address", "cd": "code", "ind": "checkbox", "txt": "text", "cnt": "count", "pct": "percent",
          "st": "state", "acct": "account", "emp": "employer", "tel": "phone", "ph": "phone", "yr": "year",
          "desc": "description", "qty": "quantity", "id": "identification", "ssn": "social security number",
          "ein": "employer identification number", "fein": "federal employer identification number",
          "dob": "date of birth", "zip": "zip code", "boy": "beginning of year", "eoy": "end of year",
          "mm": "month", "dd": "day", "yyyy": "year", "bldg": "building", "bld": "building", "insr": "insurer",
          "ltr": "letter", "eff": "effective", "exp": "expiration", "info": "information", "dba": "doing business as",
          "lbn": "legal business name", "tin": "taxpayer identification number", "pos": "position"}

_GENERIC = re.compile(r"^(?:text|field|check|box|checkbox|button|radio|group|choice|untitled|topmostsubform|form|"
                      r"page|subform|f|c|p|tf|cb|rb|txt|undefined|fill|textfield|dropdown|list|combo)$")


def name_words(name: str, expand: bool = True, text: Optional[str] = None) -> str:
    """`patient_sex_cd` -> 'patient sex code'; `insured_policy_eff_dt2` -> 'insured policy effective date 2' (a
    number glued to a word is split off, so the word is read as itself). `expand=False` keeps the labeler's
    abbreviations ('insured policy eff dt 2'): training sees both, so the model learns abbreviations `_WORDS`
    does not list (`gl`, `insd`) from examples. With `text`, a part `_WORDS` does not know is written out as the
    text's word it abbreviates (`abbreviates`): `gl_addl_insd_txt` against '... named as an additional insured'
    -> 'gl additional insured text' (2026-10-12; the model read 'gl addl insd text' at 0.09, written out 0.74)."""
    tw = re.findall(r"[a-z]+", text.lower()) if (text and expand) else []
    seen = set(tw)
    out = []
    for t in re.split(r"[_\s]+", (name or "").lower()):
        for p in re.sub(r"^([a-z]+)(\d+)$", r"\1 \2", t).split():
            if expand and p in _WORDS:
                out.append(_WORDS[p])
            elif p not in seen and (w := next((w for w in tw if abbreviates(p, w)), None)):
                out.append(w)
            else:
                out.append(p)
    return " ".join(w for w in out if w)


def abbreviates(short: str, long: str) -> bool:
    """`short` reads as an abbreviation of `long`: at least three letters, the same first letter, and its letters
    in `long` in order ('addl' ~ 'additional', 'insd' ~ 'insured', 'subr' ~ 'subrogation', 'wvd' ~ 'waived'). No
    list (Andrew, 2026-10-12). It also matches 'insd' ~ 'inside': callers compare against one text's words."""
    if len(short) < 3 or len(short) >= len(long) or short[0] != long[0] or not short.isalpha():
        return False
    it = iter(long)
    return all(c in it for c in short)


def path_words(path: Optional[str]) -> Optional[str]:
    """The readable part of a widget path, or None when it says nothing (`form1[0].#subform[3].TextField5[1]`,
    `f1_1[0]`, `Check Box58`). `F[0].P2[0].CommercialStructure_PhysicalAddress_LineTwo_A[0]` -> 'Commercial
    Structure Physical Address Line Two'; 'Parient Last Name' stays as it is."""
    if not path:
        return None
    last = re.sub(r"\[\d+\]", "", path).split(".")[-1]
    last = re.sub(r"_[A-Z]$", "", last)                      # ACORD's copy letter: _A, _B
    last = re.sub(r"([a-z])([A-Z])", r"\1 \2", last)
    last = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", last)
    words = [w for w in re.split(r"[\s_\-#]+", last) if w]
    real = [w for w in words if re.search(r"[A-Za-z]{2,}", w) and not _GENERIC.match(re.sub(r"\d+$", "", w.lower()))]
    if not real:
        return None
    return " ".join(words)


def option_desc(group: str, key: str, tooltip: Optional[str] = None) -> str:
    """What an option means, for choosing its caption: the group's name, the option key, and the option's own
    tooltip when it has one (ACORD: 'Indicates the legal entity code for the named insured is "Corporation"')."""
    s = f"{name_words(group)}: {name_words(key)}"
    if tooltip:
        s += f" | {tooltip.strip()[:200]}"
    return s


def clean_text(t: Optional[str]) -> Optional[str]:
    """A publisher or page text worth scoring: not empty, not 'undefined', not a bare widget label."""
    if not t:
        return None
    t = " ".join(str(t).split())
    if not t or t.lower() in ("undefined", "null", "none") or re.fullmatch(r"(?i)(check ?box|text|field)\s*\d*", t):
        return None
    return t[:300]


@lru_cache(maxsize=1)
def _session():
    onnx = MODEL_DIR / "model.onnx"
    if os.environ.get("PETEY_TEXT_MATCH_INT8") == "1" and (MODEL_DIR / "model.int8.onnx").exists():
        onnx = MODEL_DIR / "model.int8.onnx"        # dev runs only: see the module docstring
    if not onnx.exists():
        return None
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(MODEL_DIR / "tokenizer.json"))
    tok.enable_truncation(MAX_LEN)
    tok.enable_padding()
    return ort.InferenceSession(str(onnx), providers=["CPUExecutionProvider"]), tok


def available() -> bool:
    return _session() is not None


def score_pairs(pairs: list[tuple[str, str]]) -> Optional[list[float]]:
    """P(text describes field) for each (text, field); None without the model."""
    s = _session()
    if s is None:
        return None
    if not pairs:
        return []
    import numpy as np
    sess, tok = s
    todo = list(dict.fromkeys(p for p in pairs if p not in _cache))     # a witness asks the same pair many times
    todo.sort(key=lambda p: len(p[0]) + len(p[1]))       # similar lengths together: each batch pads to its longest
    names = {i.name for i in sess.get_inputs()}
    for i in range(0, len(todo), _BATCH):
        enc = tok.encode_batch(todo[i:i + _BATCH])
        feed = {"input_ids": np.array([e.ids for e in enc], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in enc], dtype=np.int64)}
        if "token_type_ids" in names:
            feed["token_type_ids"] = np.array([e.type_ids for e in enc], dtype=np.int64)
        logits = sess.run(None, feed)[0].reshape(-1)
        _cache.update(zip(todo[i:i + _BATCH], (1.0 / (1.0 + np.exp(-logits))).tolist()))
    return [_cache[p] for p in pairs]


_cache: dict[tuple[str, str], float] = {}


def score(text: str, field: str) -> Optional[float]:
    r = score_pairs([(text, field)])
    return r[0] if r else None
