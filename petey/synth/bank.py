"""Bank-backed case builder (TODO v6, synthetic data step 2).

`generate_from_bank(class_map, seed=...)` returns `{rect_key: value}`: one
entry per box the page classifier called fillable, keyed by the box's page
and rect (`boxes.rect_key`). Text boxes take a string; option boxes take a
mark (True / False). Nothing here reads the blueprint or the AcroForm
layer: the case is a description of what a filled page looks like, and the
filler (`render.render_case`) is the only step that touches widgets.

Where a value comes from:
  * the box's CLASS (from `synth.classify`, a page-grounded model call
    cached once per form) picks the kind of value;
  * the box's ENTITY picks WHOSE value: every entity in a case gets one
    persona and one business from `bank.yaml`, so the applicant's SSN is
    the same string in every applicant SSN box and differs from the
    spouse's;
  * an `other_id` box takes the shape of the identifier its caption names
    (`id_kinds` in bank.yaml: A-Number, NAIC, policy, VA file ...), else a
    generic prefixed number; adding a kind is one YAML line;
  * runs of consecutive part boxes (id_part, phone_part, date parts) are
    filled from one whole value split by the known shapes (SSN 3-2-4, EIN
    2-7, phone 3-3-4) by box count, else by the boxes' widths;
  * free text takes a line from the bank (Andrew: a value of the right type
    is enough; prose is a later problem);
  * option boxes the classifier grouped under one question get at most
    one mark; a standalone option box is marked at `check_rate`.

Values are sized to the box's width only. A widget's MaxLen or comb count
is applied by the filler, which reports what it actually wrote.

Deterministic per seed. No API.
"""
from __future__ import annotations

import random
import re
from pathlib import Path
from typing import Any, Optional

import yaml

from petey.synth.local import _words

BANK_PATH = Path(__file__).with_name("bank.yaml")
_PT_PER_CHAR = 5.5   # a 9-10pt form font, roughly

# entities whose "person" boxes are really an organization's
_ORG_ENTITIES = {"employer", "insurer", "producer", "certificate_holder", "payer",
                 "provider", "company", "organization", "business", "agency", "carrier"}

_SKIP = {"none", "option"}          # not drawn as text
_OPTIONAL_CLASSES = {"free_text", "money", "percent", "count", "number", "date", "title", "unit", "other"}


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


def _from_shape(shape: str, rng: random.Random) -> str:
    """`#` a digit, `A` a letter, anything else literal."""
    return "".join(rng.choice("0123456789") if ch == "#" else rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ")
                   if ch == "A" else ch for ch in shape)


def _other_id(rng: random.Random, bank: dict, box: dict) -> str:
    """The identifier kind the caption names (bank.yaml `id_kinds`), else a
    generic: a bank prefix plus digits when the box is wide, digits alone
    when it is short. A blueprint pattern that rejects one of these is a
    question about the pattern (Andrew, 2026-09-30), not a reason to shape
    the value."""
    label = (box.get("label") or "").lower()
    for kind in bank.get("id_kinds") or []:
        if any(term in label for term in kind.get("match", [])):
            return _from_shape(kind["shape"], rng)
    budget = _budget(box) or 12
    if budget < 8:
        return "".join(rng.choice("0123456789") for _ in range(max(budget, 1)))
    pre = rng.choice(bank.get("id_prefixes") or ["A"])
    return f"{pre}{rng.randint(100000000, 999999999)}"


def _width(box: dict) -> float:
    r = box.get("rect") or [0, 0, 0, 0]
    return float(r[2] - r[0])


def _budget(box: dict) -> int:
    return int(_width(box) / _PT_PER_CHAR)


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
    is one run of five boxes: [3,2,4] then [2,7]). Boxes whose lengths are
    unknown (0) take a shape by box count. Leftovers get random digits."""
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


def _cells(run: list[str], boxes: dict) -> list[int]:
    """Cells per box in a comb run, taking the narrowest box as one cell."""
    widths = [max(_width(boxes[k]), 1.0) for k in run]
    unit = min(widths)
    cells = [max(1, int(round(w / unit))) for w in widths]
    # cell borders make the widest box read a little long or short; nine
    # cells is an SSN or an EIN, so nudge the widest box to make nine
    if 8 <= sum(cells) <= 10 and sum(cells) != 9:
        i = max(range(len(cells)), key=lambda j: widths[j])
        cells[i] += 9 - sum(cells)
    return cells


def _split_cells(cells: list[int], wholes: list[str]) -> Optional[list[str]]:
    """Nine cells in any grouping hold an SSN or an EIN: the group
    boundaries say which (3|2|4 -> SSN, 2|7 -> EIN). `wholes` is
    [ssn, ein]."""
    if sum(cells) != 9:
        return None
    cum = set()
    t = 0
    for c in cells[:-1]:
        t += c
        cum.add(t)
    whole = _digits(wholes[0]) if ({3, 5} & cum) or 2 not in cum else _digits(wholes[1 % len(wholes)])
    return _split_by_lens(whole, cells)


def _runs(items: list[tuple[int, str]]) -> list[list[str]]:
    """Group `(box_id, key)` pairs whose box ids are consecutive."""
    runs: list[list[str]] = []
    prev = None
    for bid, key in sorted(items):
        if prev is not None and bid == prev + 1:
            runs[-1].append(key)
        else:
            runs.append([key])
        prev = bid
    return runs


def fit_width(value: str, box: dict, is_date: bool = False) -> str:
    """Shorten a string so the box's width can show it at a form font size.
    Dates take the longest printed form that fits rather than being cut."""
    if not value:
        return value
    budget = _budget(box)
    if not budget:
        return value
    if is_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        y, m, d = value.split("-")
        for f in (value, f"{m}/{d}/{y}", f"{m}/{d}/{y[2:]}", f"{int(m)}/{int(d)}/{y[2:]}", f"{m}{d}{y[2:]}"):
            if len(f) <= budget:
                return f
        return f"{m}{d}{y[2:]}"
    if len(value) <= budget:
        return value
    words = value.split()
    while len(words) > 1 and len(" ".join(words)) > budget:
        words.pop()
    v = " ".join(words)
    return v if len(v) <= budget else v[:max(budget, 2)]


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

    def value(self, cls: str, ent: str, box: dict) -> Any:
        p = self.persona[ent]
        b = self.business[ent]
        org = ent in _ORG_ENTITIES
        rng = self.rng
        narrow = 0 < _budget(box) <= 11
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
            return _digits(p["ssn"]) if narrow else p["ssn"]
        if cls == "ein":
            return _digits(b["ein"]) if narrow else b["ein"]
        if cls == "itin":
            return p["itin"]
        if cls == "other_id":
            return _other_id(rng, self.bank, box)
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
            if _budget(box) <= 2:
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
        if cls == "other":
            return _words(rng, 2)
        return None


def generate_from_bank(
    class_map: dict, *, seed: int = 0, bank: Optional[dict] = None,
    fill_rate: float = 0.9, check_rate: float = 0.4,
) -> dict[str, Any]:
    """`{rect_key: value}` for every fillable box in the class map. Text boxes
    get strings; option boxes get True / False marks."""
    rng = random.Random(seed)
    bank = bank or load_bank()
    boxes: dict[str, dict] = class_map["boxes"]

    entities = sorted({(b.get("entity") or "applicant") for b in boxes.values()
                       if b["class"] not in _SKIP})
    # the applicant first so it always takes persona 0 of the shuffle
    entities.sort(key=lambda e: (e != "applicant", e))
    case = _Case(bank, rng, entities or ["applicant"])

    gt: dict[str, Any] = {}
    parts: dict[tuple[str, str], list[tuple[int, str]]] = {}   # (entity, kind) -> [(box id, key)]

    # Option sets the page reads as one question: at most one mark each.
    groups: dict[tuple, list[str]] = {}
    for key, b in boxes.items():
        if b["class"] == "option" and b.get("group"):
            groups.setdefault((b.get("page"), b["group"]), []).append(key)
    marked: dict[str, bool] = {}
    for members in groups.values():
        pick = rng.choice(members) if rng.random() < fill_rate else None
        for m in members:
            marked[m] = (m == pick)

    for key, b in boxes.items():
        cls = b["class"]
        ent = b.get("entity") or "applicant"
        if cls == "none":
            continue
        if cls == "option":
            gt[key] = marked[key] if key in marked else (rng.random() < check_rate)
            continue
        if cls in ("id_part", "phone_part", "date_month", "date_day", "date_year"):
            kind = "date" if cls.startswith("date_") else cls
            parts.setdefault((ent, kind), []).append((int(b.get("box") or 0), key))
            continue
        if cls in _OPTIONAL_CLASSES and rng.random() > fill_rate:
            gt[key] = ""
            continue
        v = case.value(cls, ent, b)
        gt[key] = fit_width(v, b, is_date=cls in ("date", "birth_date")) if isinstance(v, str) else ""

    # Part runs: consecutive boxes of one kind for one entity share a whole.
    for (ent, kind), items in parts.items():
        for run in _runs(items):
            lens = [_budget(boxes[k]) for k in run]
            if kind == "id_part":
                wholes = [case.persona[ent]["ssn"], case.business[ent]["ein"]]
                pieces = _split_run([0] * len(run), wholes, _ID_SHAPES, rng)   # by count first
                if any(len(p) > (l or 99) for p, l in zip(pieces, lens)):
                    # comb cells: the finder may return a 3-cell box, two
                    # single cells and a 4-cell box for one SSN; cells per
                    # box from the narrowest box in the run
                    cells = _cells(run, boxes)
                    pieces = _split_cells(cells, wholes) or _split_run(cells, wholes, _ID_SHAPES, rng)
                    if any(len(p) > (c or 99) for p, c in zip(pieces, cells)):
                        pieces = _split_run(lens, wholes, _ID_SHAPES, rng)     # then by width
            elif kind == "phone_part":
                src = case.business[ent] if ent in _ORG_ENTITIES else case.persona[ent]
                pieces = _split_run([0] * len(run), [src["phone"]], _PHONE_SHAPES, rng)
            else:
                d = case.persona[ent]["dob"] if len(run) == 3 and rng.random() < 0.3 else _date(rng)
                y, m, dd = d.split("-")
                pieces = []
                for k in run:
                    c = boxes[k]["class"]
                    if c == "date_month":
                        pieces.append(m)
                    elif c == "date_day":
                        pieces.append(dd)
                    else:
                        pieces.append(y[2:] if 0 < _budget(boxes[k]) <= 2 else y)
            for k, piece in zip(run, pieces):
                gt[k] = piece
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
    gt = generate_from_bank(cmap, seed=args.seed)
    text = json.dumps(gt, indent=2)
    if args.out:
        args.out.write_text(text)
        print(f"[ok] {len(gt)} values ({cmap['model']}) -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
