"""Model-free ground truth from the blueprint itself (STRATEGY_v1 §3.6).

`generate_local(bpt)` returns `{acroform_path: value}` in the same shape
`generate_from_pdf` produces, so `render_pdf` and `score` consume it
unchanged. No API, deterministic per seed.

Where a value comes from, in order:
  1. the field's `pattern` — sampled from the regex, so the case satisfies
     the shape the blueprint (publisher-declared or inferred) will gate on;
  2. the field's `semantic_type` — a realistic value (a street, a name, a
     phone) that is then checked against the pattern if there is one;
  3. the field's `type` — a plain string, number, ISO date, boolean, or a
     member of `values`.
Cross-field `rules` / `x_petey_rules` (mutex) are enforced after the draw.

This keys on the blueprint's own paths, the same key the extractor reads
back through: it is a regression test of extraction mechanics, not a test
of blueprint correctness (EVAL_STATE.md; §3.6). The multimodal generator
stays as the independent referee.
"""
from __future__ import annotations

import argparse
import json
import random
import re
import zlib
from pathlib import Path
from typing import Any, Callable, Optional

try:
    import re._parser as sre_parse  # 3.11+
except ImportError:  # pragma: no cover
    import sre_parse  # type: ignore

import yaml

from petey.semantic_types import REGISTRY

# ----------------------------------------------------------- regex sampler

_MAX_UNBOUNDED = 6
_ANY_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 "
_CATEGORY = {
    sre_parse.CATEGORY_DIGIT: "0123456789",
    sre_parse.CATEGORY_NOT_DIGIT: "abcxyzABC ",
    sre_parse.CATEGORY_SPACE: " ",
    sre_parse.CATEGORY_NOT_SPACE: "abcxyz0123ABC",
    sre_parse.CATEGORY_WORD: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJ0123456789_",
    sre_parse.CATEGORY_NOT_WORD: " -.",
}


def _class_chars(items) -> str:
    chars: list[str] = []
    negate = False
    for op, av in items:
        if op == sre_parse.NEGATE:
            negate = True
        elif op == sre_parse.LITERAL:
            chars.append(chr(av))
        elif op == sre_parse.RANGE:
            lo, hi = av
            chars.extend(chr(c) for c in range(lo, min(hi, lo + 80) + 1))
        elif op == sre_parse.CATEGORY:
            chars.extend(_CATEGORY.get(av, ""))
    if negate:
        excl = set(chars)
        chars = [c for c in _ANY_CHARS if c not in excl]
    return "".join(chars) or "x"


def _sample_parsed(parsed, rng: random.Random) -> str:
    out: list[str] = []
    for op, av in parsed:
        if op == sre_parse.LITERAL:
            out.append(chr(av))
        elif op == sre_parse.NOT_LITERAL:
            out.append(rng.choice([c for c in _ANY_CHARS if ord(c) != av]))
        elif op == sre_parse.ANY:
            out.append(rng.choice(_ANY_CHARS.strip()))
        elif op == sre_parse.IN:
            out.append(rng.choice(_class_chars(av)))
        elif op in (sre_parse.MAX_REPEAT, sre_parse.MIN_REPEAT):
            lo, hi, sub = av
            if hi == sre_parse.MAXREPEAT:
                hi = lo + _MAX_UNBOUNDED
            n = rng.randint(lo, hi)
            for _ in range(n):
                out.append(_sample_parsed(sub, rng))
        elif op == sre_parse.SUBPATTERN:
            out.append(_sample_parsed(av[-1], rng))
        elif op == sre_parse.BRANCH:
            out.append(_sample_parsed(rng.choice(av[1]), rng))
        elif op == sre_parse.AT:
            continue
        elif op == sre_parse.ASSERT or op == sre_parse.ASSERT_NOT:
            continue
        elif op == sre_parse.GROUPREF:
            continue
        else:
            continue
    return "".join(out)


def sample_from_pattern(pattern: str, rng: random.Random,
                        tries: int = 20) -> Optional[str]:
    """A string matching `pattern`, or None if the sampler cannot produce one."""
    try:
        parsed = sre_parse.parse(pattern)
    except Exception:
        return None
    for _ in range(tries):
        s = _sample_parsed(parsed, rng)
        try:
            if re.fullmatch(pattern, s):
                return s
        except re.error:
            return None
    return None


# ------------------------------------------------------ realistic values

_FIRST = ["Marcus", "Evelyn", "Priya", "Daniel", "Rosa", "Kenji", "Amara",
          "Tobias", "Leah", "Omar", "Ingrid", "Samuel", "Nadia", "Victor"]
_LAST = ["Thornton", "Okafor", "Lindqvist", "Ramirez", "Nakamura", "Bell",
         "Haddad", "Kowalski", "Mbeki", "Fischer", "Delgado", "Whitaker"]
_STREETS = ["Cedarwood Lane", "Harbor View Drive", "Maple Street",
            "Willow Court", "Granite Avenue", "Riverbend Road",
            "Old Mill Way", "Summit Boulevard"]
_CITIES = ["Columbus", "Tacoma", "Albany", "Boise", "Savannah", "Tucson",
           "Madison", "Reno", "Durham", "Fresno"]
_STATES = ["OH", "WA", "NY", "ID", "GA", "AZ", "WI", "NV", "NC", "CA", "TX"]
_COUNTRIES = ["United States", "Canada", "Mexico", "Germany", "Japan"]
_COUNTRY_CODES = ["US", "CA", "MX", "DE", "JP"]
_BUSINESS = ["Northwind Traders LLC", "Cedar Ridge Dental PC",
             "Harbor Light Logistics Inc", "Blue Fern Studio",
             "Granite Peak Consulting", "Maple & Vine Bakery"]
_WORDS = ["quarterly", "review", "invoice", "services", "rendered",
          "equipment", "lease", "consulting", "maintenance", "delivery",
          "north", "site", "annual", "contract", "renewal"]


def _date(rng: random.Random, lo: int = 1990, hi: int = 2026) -> str:
    y = rng.randint(lo, hi)
    m = rng.randint(1, 12)
    d = rng.randint(1, 28)
    return f"{y:04d}-{m:02d}-{d:02d}"


def _money(rng: random.Random, whole: bool = False) -> str:
    v = rng.choice([rng.randint(1, 999), rng.randint(1000, 99999),
                    rng.randint(100000, 2500000)])
    if whole:
        return str(v)
    return f"{v}.{rng.randint(0, 99):02d}"


def _words(rng: random.Random, n: int) -> str:
    return " ".join(rng.choice(_WORDS) for _ in range(n)).capitalize()


SEMANTIC: dict[str, Callable[[random.Random], str]] = {
    "ssn": lambda r: f"{r.randint(100, 899):03d}-{r.randint(10, 99):02d}-{r.randint(1000, 9999):04d}",
    "ein": lambda r: f"{r.randint(10, 99):02d}-{r.randint(1000000, 9999999):07d}",
    "itin": lambda r: f"9{r.randint(10, 99):02d}-{r.choice(['70', '75', '80', '88'])}-{r.randint(1000, 9999):04d}",
    "npi": lambda r: f"{r.randint(1000000000, 1999999999)}",
    "routing_number": lambda r: f"{r.randint(1, 12):02d}{r.randint(1000000, 9999999):07d}",
    "account_number": lambda r: str(r.randint(10000000, 999999999999)),
    "naics": lambda r: str(r.choice([541110, 722511, 236220, 621210, 445110])),
    "tin": lambda r: f"{r.randint(100, 899):03d}-{r.randint(10, 99):02d}-{r.randint(1000, 9999):04d}",
    "money": lambda r: _money(r),
    "money_whole_dollar": lambda r: _money(r, whole=True),
    "percent": lambda r: f"{r.choice([5, 10, 12.5, 25, 50, 100])}",
    "count": lambda r: str(r.randint(0, 12)),
    "birth_date": lambda r: _date(r, 1940, 2005),
    "service_date": lambda r: _date(r, 2018, 2026),
    "iso_date": lambda r: _date(r, 2015, 2026),
    "year": lambda r: str(r.randint(2018, 2026)),
    "phone": lambda r: f"{r.randint(201, 989)}-{r.randint(200, 999)}-{r.randint(1000, 9999)}",
    "email": lambda r: f"{r.choice(_FIRST).lower()}.{r.choice(_LAST).lower()}@example.com",
    "state_abbr": lambda r: r.choice(_STATES),
    "zip": lambda r: f"{r.randint(10000, 99999):05d}",
    "city": lambda r: r.choice(_CITIES),
    "country_code": lambda r: r.choice(_COUNTRY_CODES),
    "country": lambda r: r.choice(_COUNTRIES),
    "street_address": lambda r: f"{r.randint(10, 9899)} {r.choice(_STREETS)}",
    "entity_name": lambda r: r.choice(_BUSINESS),
    "business_name": lambda r: r.choice(_BUSINESS),
    "first_name": lambda r: r.choice(_FIRST),
    "last_name": lambda r: r.choice(_LAST),
    "person_name": lambda r: f"{r.choice(_FIRST)} {r.choice(_LAST)}",
    "description": lambda r: _words(r, 4),
    "text": lambda r: _words(r, 2),
}

_REGISTRY_PATTERN = {st.name: st.pattern for st in REGISTRY if st.pattern}


def value_for(spec: dict, rng: random.Random) -> Any:
    """A scalar value for a string / number / date field spec."""
    ftype = spec.get("type", "string")
    st = spec.get("semantic_type")
    pattern = spec.get("pattern") if ftype == "string" else None
    gen = SEMANTIC.get(st) if st else None
    if gen is not None:
        v = gen(rng)
        if not pattern or re.fullmatch(pattern, v):
            return v
    if pattern:
        v = sample_from_pattern(pattern, rng)
        if v is not None:
            return v
    if st and st in _REGISTRY_PATTERN and ftype == "string":
        v = sample_from_pattern(_REGISTRY_PATTERN[st], rng)
        if v is not None:
            return v
    if ftype == "date":
        return _date(rng)
    if ftype in ("number", "integer"):
        return _money(rng, whole=(ftype == "integer"))
    return _words(rng, rng.randint(1, 3))


# --------------------------------------------------------------- generate

def _clear(spec: dict, gt: dict) -> None:
    ftype = spec.get("type", "string")
    if spec.get("widgets"):
        for wb in spec["widgets"].values():
            if wb.get("path"):
                gt[wb["path"]] = False
        return
    path = (spec.get("widget") or {}).get("path")
    if not path:
        return
    gt[path] = False if ftype == "boolean" else ""


def _held(spec: dict, gt: dict) -> bool:
    if spec.get("widgets"):
        return any(gt.get(wb.get("path")) is True
                   for wb in spec["widgets"].values())
    path = (spec.get("widget") or {}).get("path")
    v = gt.get(path)
    return v not in (None, "", False, "Off")


def generate_local(
    bpt: dict, *, seed: int = 0, fill_rate: float = 0.85,
    check_rate: float = 0.4,
) -> dict[str, Any]:
    """`{acroform_path: value}` for every widget the blueprint owns."""
    rng = random.Random(seed)
    gt: dict[str, Any] = {}
    fields: dict[str, dict] = bpt.get("fields", {})
    for name, spec in fields.items():
        ftype = spec.get("type", "string")
        widgets = spec.get("widgets")
        path = (spec.get("widget") or {}).get("path")
        if ftype in ("category", "multi_category") and widgets:
            values = list(widgets.keys())
            if ftype == "category":
                pick = {rng.choice(values)} if rng.random() < fill_rate else set()
            else:
                pick = {v for v in values if rng.random() < check_rate}
            for v, wb in widgets.items():
                if wb.get("path"):
                    gt[wb["path"]] = v in pick
            continue
        if not path:
            continue
        if ftype == "category":
            values = spec.get("values") or []
            gt[path] = rng.choice(values) if values and rng.random() < fill_rate else ""
        elif ftype == "boolean":
            gt[path] = rng.random() < check_rate
        else:
            if spec.get("required") or rng.random() < fill_rate:
                gt[path] = value_for(spec, rng)
            else:
                gt[path] = ""

    for rule in bpt.get("rules") or bpt.get("x_petey_rules") or []:
        members = [m for m in rule.get("mutex", []) if m in fields]
        held = [m for m in members if _held(fields[m], gt)]
        for m in held[1:]:
            _clear(fields[m], gt)
    return gt


def seed_from_key(key: Optional[str]) -> int:
    return zlib.crc32((key or "").encode("utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser(description="Model-free ground truth from a blueprint.")
    ap.add_argument("bpt", type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    bpt = yaml.safe_load(args.bpt.read_text(encoding="utf-8"))
    gt = generate_local(bpt, seed=args.seed)
    text = json.dumps(gt, indent=2)
    if args.out:
        args.out.write_text(text)
        print(f"[ok] {len(gt)} values -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
