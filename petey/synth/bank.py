"""Bank-backed case builder (TODO, synthetic data step 2).

`generate_from_bank(class_map, blank_pdf, seed=...)` returns
`{acroform_path: value}` in the shape `generate_from_pdf` and
`generate_local` produce, so `render_pdf` and `score` consume it unchanged.

Where a value comes from:
  * the box's CLASS (from `synth.classify`, a page-grounded model call
    cached once per form) picks the kind of value; nothing here reads the
    blueprint, which is the thing the case will judge;
  * the box's ENTITY picks WHOSE value: every entity in a case gets one
    persona and one business from `bank.yaml`, so the applicant's SSN is
    the same string in every applicant SSN box and differs from the
    spouse's;
  * runs of consecutive part boxes (id_part, phone_part, date parts) are
    filled from one whole value split by the boxes' lengths;
  * free text takes the donor case's value when a donor is given (the
    cached blind case), else a line from the bank;
  * controls draw as `generate_local` does: one on-state per group at
    `fill_rate`, checkboxes at `check_rate`.

Deterministic per seed. No API.
"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from petey.synth.local import _words, fit_to_widget, widget_limits

BANK_PATH = Path(__file__).with_name("bank.yaml")

# entities whose "person" boxes are really an organization's
_ORG_ENTITIES = {"employer", "insurer", "producer", "certificate_holder", "payer",
                 "provider", "company", "organization", "business", "agency", "carrier"}


def load_bank(path: Path = BANK_PATH) -> dict:
    """bank.yaml, with every scalar a string: YAML reads an unquoted
    `1978-03-14` as a date object, and the ground truth is JSON."""
    import datetime

    def _str(v):
        if isinstance(v, dict):
            return {k: _str(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_str(x) for x in v]
        if isinstance(v, (datetime.date, datetime.datetime)):
            return v.isoformat()[:10]
        return v
    return _str(yaml.safe_load(path.read_text(encoding="utf-8")))


# ------------------------------------------------------------- helpers

def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _date(rng: random.Random, lo: int = 2015, hi: int = 2026) -> str:
    return f"{rng.randint(lo, hi):04d}-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d}"


def _money(rng: random.Random) -> str:
    v = rng.choice([rng.randint(1, 999), rng.randint(1000, 99999), rng.randint(100000, 2500000)])
    return f"{v}.{rng.randint(0, 99):02d}"


def _other_id(rng: random.Random, bank: dict, maxlen: int) -> str:
    """An identifier of no particular kind: a bank prefix plus digits when
    the box is unbounded, digits alone when it declares a length. A
    blueprint pattern that rejects one of these is a question about the
    pattern (Andrew, 2026-09-30), not a reason to shape the value."""
    if 0 < maxlen <= 12:
        return "".join(rng.choice("0123456789") for _ in range(maxlen))
    pre = rng.choice(bank.get("id_prefixes") or ["A"])
    return f"{pre}{rng.randint(100000000, 999999999)}"


def _box_len(lim: Optional[dict]) -> int:
    """Characters a part box holds: MaxLen when declared, else from width."""
    if not lim:
        return 0
    if lim.get("maxlen"):
        return int(lim["maxlen"])
    w = lim.get("width") or 0
    return int(w / 5.5) if w else 0


def _split_by_lens(whole_digits: str, lens: list[int]) -> Optional[list[str]]:
    if sum(lens) != len(whole_digits) or any(n <= 0 for n in lens):
        return None
    out, i = [], 0
    for n in lens:
        out.append(whole_digits[i:i + n])
        i += n
    return out


_ID_SHAPES = ([3, 2, 4], [2, 7], [9])          # SSN parts, EIN parts, a whole in one comb
_PHONE_SHAPES = ([3, 3, 4], [3, 7], [10])


def _split_run(lens: list[int], wholes: list[str], shapes, rng: random.Random) -> list[str]:
    """Fill a run of part boxes from whole values, matching known shapes
    greedily from the left (a W-9 SSN row directly followed by the EIN row
    is one run of five boxes: [3,2,4] then [2,7]). Boxes with no declared
    length take a shape by box count. Leftovers get random digits."""
    out: list[str] = []
    i = 0
    wi = 0
    while i < len(lens):
        matched = False
        for shape in shapes:
            seg = lens[i:i + len(shape)]
            if len(seg) != len(shape):
                continue
            known = all(n > 0 for n in seg)
            if (known and seg == shape) or (not any(seg) and len(lens) - i == len(shape)):
                whole = _digits(wholes[wi % len(wholes)]) if wholes else ""
                wi += 1
                pieces = _split_by_lens(whole, shape)
                if pieces is None:
                    break
                out.extend(pieces)
                i += len(shape)
                matched = True
                break
        if not matched:
            n = lens[i] or 3
            out.append("".join(rng.choice("0123456789") for _ in range(n)))
            i += 1
    return out


def _runs(items: list[tuple[int, str]]) -> list[list[str]]:
    """Group `(box_id, path)` pairs whose box ids are consecutive."""
    runs: list[list[str]] = []
    prev = None
    for bid, path in sorted(items):
        if prev is not None and bid == prev + 1:
            runs[-1].append(path)
        else:
            runs.append([path])
        prev = bid
    return runs


class _Case:
    """One case's persona/business assignment: consistent within a case."""

    def __init__(self, bank: dict, rng: random.Random, entities: list[str]):
        personas = list(bank["personas"])
        businesses = list(bank["businesses"])
        rng.shuffle(personas)
        rng.shuffle(businesses)
        self.persona: dict[str, dict] = {}
        self.business: dict[str, dict] = {}
        for i, ent in enumerate(entities):
            self.persona[ent] = personas[i % len(personas)]
            self.business[ent] = businesses[i % len(businesses)]
        self.rng = rng
        self.bank = bank

    def value(self, cls: str, ent: str, lim: Optional[dict]) -> Any:
        p = self.persona[ent]
        b = self.business[ent]
        org = ent in _ORG_ENTITIES
        rng = self.rng
        if cls == "first_name":
            return p["first"]
        if cls == "middle_name":
            return p["middle"]
        if cls == "last_name":
            return p["last"]
        if cls == "full_name":
            return f"{p['first']} {p['middle']} {p['last']}"
        if cls == "business_name":
            return b["name"]
        if cls == "ssn":
            s = p["ssn"]
            return _digits(s) if (lim or {}).get("maxlen") == 9 or (lim or {}).get("comb") else s
        if cls == "ein":
            s = b["ein"]
            return _digits(s) if (lim or {}).get("maxlen") == 9 or (lim or {}).get("comb") else s
        if cls == "itin":
            return p["itin"]
        if cls == "other_id":
            return _other_id(rng, self.bank, (lim or {}).get("maxlen") or 0)
        src = b if org else p
        if cls == "street":
            return src["street"]
        if cls == "unit":
            return p.get("unit") or f"Apt {rng.randint(1, 40)}"
        if cls == "city":
            return src["city"]
        if cls == "state":
            return src["state"]
        if cls == "zip":
            return src["zip"]
        if cls == "country":
            return p.get("country") or "United States"
        if cls == "city_state_zip":
            return f"{src['city']}, {src['state']} {src['zip']}"
        if cls == "address_block":
            who = b["name"] if org else f"{p['first']} {p['last']}"
            return f"{who}, {src['street']}, {src['city']}, {src['state']} {src['zip']}"
        if cls == "code":
            n = (lim or {}).get("maxlen") or 0
            if n == 1:
                return rng.choice("ABCDEFGHJKLMNP")
            return rng.choice(["A", "B", "C", "D", "E", "F", "1", "2", "5", "13", "P", "S"])
        if cls == "phone":
            return src["phone"]
        if cls == "email":
            return src["email"]
        if cls == "birth_date":
            return p["dob"]
        if cls == "date":
            return _date(rng)
        if cls == "year":
            return str(rng.randint(2018, 2026))
        if cls == "money":
            return _money(rng)
        if cls == "percent":
            return str(rng.choice([5, 10, 12.5, 25, 50, 100]))
        if cls == "count":
            return str(rng.randint(0, 12))
        if cls == "number":
            return str(rng.randint(1, 500))
        if cls == "title":
            return rng.choice(self.bank["titles"])
        if cls == "signature":
            return f"{p['first']} {p['last']}"
        if cls == "free_text":
            return rng.choice(self.bank["free_text"])
        return None


def generate_from_bank(
    class_map: dict, blank_pdf: Optional[Path], *, seed: int = 0, bank: Optional[dict] = None,
    donor: Optional[dict] = None, fill_rate: float = 0.9, check_rate: float = 0.4,
) -> dict[str, Any]:
    """`{acroform_path: value}` for every box in the class map."""
    rng = random.Random(seed)
    bank = bank or load_bank()
    limits = widget_limits(blank_pdf)
    boxes: dict[str, dict] = class_map["boxes"]
    donor = donor or {}

    entities = sorted({(b.get("entity") or "applicant") for b in boxes.values()
                       if b["class"] not in ("yes_no", "choice", "checkbox")})
    # the applicant first so it always takes persona 0 of the shuffle
    entities.sort(key=lambda e: (e != "applicant", e))
    case = _Case(bank, rng, entities or ["applicant"])

    gt: dict[str, Any] = {}
    parts: dict[tuple[str, str], list[tuple[int, str]]] = {}   # (entity, kind) -> [(box, path)]

    # Checkbox sets the page reads as one question (I-765 Apt/Ste/Flr, marital
    # status): kids with distinct paths, so neither the inventory nor the
    # filler sees a group. At most one box of a set is ticked.
    groups: dict[tuple, list[str]] = {}
    for path, b in boxes.items():
        if b.get("group") and (b.get("control") == "checkbox" or b["class"] == "checkbox"):
            groups.setdefault((b.get("page"), b["group"]), []).append(path)
    chosen: dict[str, bool] = {}
    for key, members in groups.items():
        if len(members) < 2:
            continue
        pick = rng.choice(members) if rng.random() < fill_rate else None
        for m in members:
            chosen[m] = (m == pick)

    for path, b in boxes.items():
        cls = b["class"]
        ent = b.get("entity") or "applicant"
        lim = limits.get(path) or {}
        control = b.get("control") or lim.get("kind") or "text"

        if cls in ("yes_no", "choice") or control in ("radio", "radiobutton", "combobox", "listbox"):
            ons = lim.get("on_states") or []
            choices = lim.get("choices") or []
            pool = ons or choices
            if pool and rng.random() < fill_rate:
                gt[path] = rng.choice(pool)
            else:
                gt[path] = "" if pool else False
            continue
        if cls == "mark":
            gt[path] = "X" if rng.random() < check_rate else ""
            continue
        if cls == "checkbox" or control == "checkbox":
            ons = lim.get("on_states") or []
            if path in chosen:
                gt[path] = chosen[path]
                continue
            if len(ons) > 1:
                gt[path] = rng.choice(ons) if rng.random() < fill_rate else ""
            else:
                gt[path] = rng.random() < check_rate
            continue
        if cls == "signature" and lim.get("kind") not in ("text", None):
            continue
        if cls in ("id_part", "phone_part", "date_month", "date_day", "date_year"):
            bid = int(b.get("box") or 0)
            kind = "date" if cls.startswith("date_") else cls
            parts.setdefault((ent, kind), []).append((bid, path))
            continue
        if cls in ("other", "free_text"):
            dv = donor.get(path)
            if isinstance(dv, str) and dv.strip():
                gt[path] = fit_to_widget(dv, lim, {}, rng)
                continue
            if cls == "other":
                gt[path] = ""
                continue
        if rng.random() > fill_rate and cls in ("free_text", "money", "percent", "count",
                                                 "number", "date", "title", "unit"):
            gt[path] = ""
            continue
        v = case.value(cls, ent, lim)
        if v is None:
            gt[path] = ""
            continue
        spec = {"type": "date"} if cls in ("date", "birth_date") else {}
        gt[path] = fit_to_widget(v, lim, spec, rng)

    # Part runs: consecutive boxes of one kind for one entity share a whole.
    for (ent, kind), items in parts.items():
        for run in _runs(items):
            lens = [_box_len(limits.get(p)) for p in run]
            if kind == "id_part":
                pieces = _split_run(lens, [case.persona[ent]["ssn"], case.business[ent]["ein"]],
                                    _ID_SHAPES, rng)
            elif kind == "phone_part":
                src = case.business[ent] if ent in _ORG_ENTITIES else case.persona[ent]
                pieces = _split_run(lens, [src["phone"]], _PHONE_SHAPES, rng)
            else:
                d = case.persona[ent]["dob"] if len(run) == 3 and rng.random() < 0.3 else _date(rng)
                y, m, dd = d.split("-")
                pieces = []
                for p in run:
                    c = boxes[p]["class"]
                    n = _box_len(limits.get(p))
                    if c == "date_month":
                        pieces.append(m)
                    elif c == "date_day":
                        pieces.append(dd)
                    else:
                        pieces.append(y[2:] if n == 2 else y)
            for p, piece in zip(run, pieces):
                gt[p] = piece
    return gt


def main() -> int:
    import argparse
    import json
    from petey.synth.classify import classify_form
    ap = argparse.ArgumentParser(description="Bank-backed synthetic case from a cached class map.")
    ap.add_argument("blank", type=Path)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    cmap = classify_form(args.blank, cache_only=True)
    if cmap is None:
        raise SystemExit("no cached classification for this blank; run petey.synth.classify first")
    gt = generate_from_bank(cmap, args.blank, seed=args.seed)
    text = json.dumps(gt, indent=2)
    if args.out:
        args.out.write_text(text)
        print(f"[ok] {len(gt)} values ({cmap['model']}) -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
