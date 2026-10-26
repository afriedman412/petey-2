"""Page-grounded box classification (TODO v6, synthetic data step 1).

The model sees the page image with a numbered red box on every fillable box
the page finder found (`synth.boxes`, run on the rendered blank; nothing
from the AcroForm layer) and an inventory that is nothing but the box ids.
It returns, per box, the caption it read, a class from the closed
vocabulary below, whose value it is (`entity`), and for option boxes the
question a set of them answers (`group`). It decides for itself whether a
box takes text or a mark, and which marks belong together.

Two consumers:
  * the value bank (`synth.bank`): a class map plus a bank of names,
    addresses and numbers builds any number of cases for free, one
    persona per entity, so header copies of one identifier agree;
  * the class check (`validate.class_check`, a scoring step): the class is a
    blueprint-independent second opinion on every box's semantic type
    (`SEMANTIC_TO_CLASS` maps the blueprint's vocabulary onto this one).

Everything is keyed by the box's page and rect (`boxes.rect_key`), never by
an AcroForm path. Cached once per (blank bytes, finder version, model,
prompt version) under `runs/_gen_cache/classify/`.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

from petey.paths import RUNS
from petey.synth.boxes import FINDER_VERSION, find_boxes, render_numbered_pages
from petey.models import model_for
from petey.synth.generate import _extract_json_object, call_page, make_client

MODEL = model_for("classifier")

PROMPT_VERSION = "4"
CACHE_DIR = RUNS / "_gen_cache" / "classify"

# class -> what it means. Order is the order shown to the model.
CLASSES: dict[str, str] = {
    "first_name": "a person's given name only",
    "middle_name": "a person's middle name or initial only",
    "last_name": "a person's family name only",
    "full_name": "a whole person name in one box (any order)",
    "business_name": "a company, employer, insurer, agency, trust or other organization name",
    "ssn": "Social Security number, whole (9 digits, any punctuation)",
    "ein": "Employer Identification Number, whole",
    "itin": "Individual Taxpayer Identification Number",
    "id_part": "one PART of a longer identifier split across boxes (first three of an SSN, one digit of a comb)",
    "other_id": "another identifier: A-Number, policy or claim number, license or account number, VA file number, control number",
    "code": "a short code or letter chosen from a printed list or legend (tax classification letter, exemption code, insurer letter A-F, status or category code)",
    "street": "street address line (number and street)",
    "unit": "apartment, suite, floor or unit designator or number",
    "city": "city or town",
    "state": "US state or province",
    "zip": "ZIP or postal code",
    "country": "country",
    "city_state_zip": "city, state and ZIP together in one box",
    "address_block": "a whole mailing address (street through ZIP, often with the name) in one box",
    "phone": "telephone or fax number, whole",
    "phone_part": "one PART of a phone number (area code, exchange, extension)",
    "email": "email address",
    "date": "a whole calendar date (any printed format)",
    "birth_date": "a whole date of birth",
    "date_month": "the month part of a date split into parts",
    "date_day": "the day part of a date split into parts",
    "date_year": "the year part of a date split into parts",
    "year": "a standalone year (tax year, model year)",
    "money": "a dollar amount",
    "percent": "a percentage",
    "count": "a count of things (number of dependents, employees, pages)",
    "number": "another numeric value (age, weight, mileage, rate)",
    "title": "a job title, role, or relationship word (Spouse, Owner, Director)",
    "signature": "a signature box (drawn or typed)",
    "free_text": "prose or a description the filer writes in their own words",
    "other": "a fillable box whose kind you cannot tell",
    # marks and non-boxes: the model decides these from the page
    "option": "a box that takes a MARK, not text: a checkbox square, a radio circle, or a small cell where an X is typed to pick a column",
    "none": "not a fillable box at all: a heading, an instruction line, a printed label, a table cell that holds no filer value",
}

# Persona-bearing classes: the bank draws these from one persona per entity.
PERSON_CLASSES = {"first_name", "middle_name", "last_name", "full_name", "ssn", "itin",
                  "birth_date", "street", "unit", "city", "state", "zip", "country",
                  "city_state_zip", "address_block", "phone", "phone_part", "email", "id_part"}
BUSINESS_CLASSES = {"business_name", "ein"}

# Blueprint semantic_type (petey.semantic_types) -> this vocabulary.
SEMANTIC_TO_CLASS: dict[str, str] = {
    "date_month": "date_month", "date_day": "date_day", "date_year": "date_year",
    "id_part": "id_part", "ssn": "ssn", "ein": "ein", "itin": "itin", "npi": "other_id",
    "routing_number": "other_id", "account_number": "other_id", "naics": "other_id",
    "tin": "ssn", "money_whole_dollar": "money", "money": "money", "percent": "percent",
    "count": "count", "birth_date": "birth_date", "service_date": "date", "iso_date": "date", "datetime": "date",
    "year": "year", "phone": "phone", "email": "email", "state_abbr": "state", "zip": "zip",
    "city": "city", "country_code": "country", "country": "country",
    "street_address": "street", "name_and_address": "address_block", "entity_name": "business_name",
    "business_name": "business_name", "first_name": "first_name", "last_name": "last_name",
    "person_name": "full_name", "description": "free_text", "text": "free_text",
    "indicator": "option", "name": "full_name", "ca_postal_code": "zip", "uk_postcode": "zip", "uk_phone": "phone",
    "intl_phone": "phone",
}

# Classes that agree with each other for the labeler comparison (a whole
# name typed person_name is not wrong because the page says last_name).
CLASS_FAMILY: dict[str, str] = {
    "first_name": "name", "middle_name": "name", "last_name": "name", "full_name": "name",
    "signature": "name",
    "date": "date", "birth_date": "date",
    "date_month": "date_part", "date_day": "date_part", "date_year": "date_part", "year": "date_part",
    "ssn": "tax_id", "itin": "tax_id", "ein": "tax_id",
    "money": "number", "percent": "number", "count": "number", "number": "number",
    "street": "address", "unit": "address", "address_block": "address", "city_state_zip": "address",
    "id_part": "id_part", "phone_part": "id_part",
    "option": "control", "checkbox": "control", "yes_no": "control", "choice": "control", "mark": "control",
    "code": "code",
}

_ENTITIES = ("applicant", "spouse", "dependent_1", "dependent_2", "employer", "preparer",
             "representative", "insured", "producer", "insurer", "certificate_holder",
             "provider", "contact", "payer", "recipient", "other")

SYSTEM_PROMPT = """You classify the boxes on a blank form. You see the page \
image with a numbered red rectangle drawn on every box a layout pass found, \
and a list of the box numbers. Nothing else is known about the boxes: read \
the page and say, for each one, what KIND of value belongs there and WHOSE \
value it is. Some rectangles are not fillable boxes at all (the layout pass \
over-proposes); say so with the class "none".

OUTPUT SHAPE:
- Return JSON only. No prose, no markdown, no code fences.
- Top-level shape: {{"boxes": {{"<box number>": {{"label": "<caption or null>", "class": "<class>", "entity": "<entity or null>", "group": "<question or null>"}}, ...}}}}
- One entry per box number in the list.

LABEL: the caption printed for THIS box, verbatim (a column heading counts \
when the box sits under it). null when the box has no caption of its own: \
one of several unlabeled lines under a block heading such as PRODUCER or \
INSURED. For such blocks use the common convention in reading order (name, \
street, street 2, city; the short boxes ending a line are state then ZIP) \
and still give label null, so the reader knows the class is by position, \
not by caption.

CLASS: exactly one of the names below. Pick the most specific that fits. \
A box that holds one part of a split value (month of a date, first three \
digits of an SSN, area code) takes the PART class, never the whole one. A \
small square, circle or cell that is ticked rather than written in is \
"option". A rectangle that is not a place for the filer to put anything is \
"none". A fillable box whose kind you cannot tell is "other".

{classes}

GROUP: for "option" boxes only. When several option boxes on the page are \
the choices of ONE question (Apt / Ste / Flr; Single / Married / Divorced / \
Widowed; Yes / No; the entity-type boxes on a W-9), give every box of that \
set the same short string, the question's printed text (e.g. "Marital \
Status", "Unit type, physical address", "Federal tax classification"). null \
for a standalone option box and for every non-option box. Boxes of one set \
share a group even when the form allows more than one to be checked.

ENTITY: whose value the box holds, as a short slug. Use the form's own \
words for the role when it prints them (Insured, Producer, Certificate \
Holder, Preparer, Spouse, Dependent 1). Prefer these slugs when they fit: \
{entities}. The filer of the form is "applicant". A box that belongs to \
no person or organization (a plain date, an amount, free text, an option) \
takes entity null.

Ground every answer in this page. You may recognize the form; the page \
image supplied here is authoritative for this file.
"""

USER_TEMPLATE = """Box numbers on this page: {ids}

The page image is attached with each box number drawn at the top-left \
corner of its red rectangle. Classify every box. Return JSON:

{{"boxes": {{"<box number>": {{"label": "<caption or null>", "class": "<class>", "entity": "<entity or null>", "group": "<question or null>"}}, ...}}}}
"""


def _system_prompt() -> str:
    lines = "\n".join(f"- {name}: {desc}" for name, desc in CLASSES.items())
    return SYSTEM_PROMPT.format(classes=lines, entities=", ".join(_ENTITIES))


def cache_path(pdf_bytes: bytes, model: str, cache_dir: Path = CACHE_DIR) -> Path:
    h = hashlib.sha256()
    h.update(pdf_bytes)
    h.update(b"\x00classify\x00")
    h.update(FINDER_VERSION.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(PROMPT_VERSION.encode("utf-8"))
    return cache_dir / f"{h.hexdigest()}.json"


def dry_run(pdf_path: Path, out_dir: Path) -> dict:
    """Write the numbered pages and the box list the model would see; no API."""
    out_dir.mkdir(parents=True, exist_ok=True)
    boxes = find_boxes(pdf_path)
    pngs = render_numbered_pages(pdf_path, boxes)
    for page_no, png in pngs.items():
        (out_dir / f"page_{page_no:02d}.png").write_bytes(png)
    (out_dir / "boxes.json").write_text(json.dumps(boxes, indent=1))
    return {"pages": len(pngs), "boxes": len(boxes), "out": str(out_dir)}


def classify_form(
    pdf_path: str | Path, *, model: str = MODEL, cache_dir: Path = CACHE_DIR,
    client: Any = None, cache_only: bool = False, form_id: Optional[str] = None,
) -> Optional[dict]:
    """The class map for one blank form, from cache or one call per page.

    Returns `{"boxes": {rect_key: {class, entity, label, group, box, page,
    rect, kind}}, "raw": {page: model output}, ...provenance}`, or None when
    `cache_only` and nothing is cached. `kind` is the finder's own guess
    (text / checkbox / radio), kept for the diagnostic, not shown to the
    model.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"blank PDF not found: {pdf_path}")
    pdf_bytes = pdf_path.read_bytes()
    cp = cache_path(pdf_bytes, model, cache_dir)
    if cp.exists():
        return _guard(json.loads(cp.read_text(encoding="utf-8")))
    if cache_only:
        return None

    boxes = find_boxes(pdf_path)
    by_id = {b["id"]: b for b in boxes}
    pngs = render_numbered_pages(pdf_path, boxes)
    if client is None:
        client = make_client(model)
    tag = f"classify/{form_id or pdf_path.stem}/{model.replace('/', '_')}"
    system = _system_prompt()

    out_boxes: dict[str, dict] = {}
    raw: dict[str, Any] = {}
    unknown: list[str] = []
    bad_class: dict[str, str] = {}
    seen: set[str] = set()
    def one_page(page_no):
        ids = [b["id"] for b in boxes if b["page"] == page_no]
        user_text = USER_TEMPLATE.format(ids=", ".join(ids))
        text = call_page(client, model, pngs[page_no], system, user_text, tag)
        parsed = _extract_json_object(text)
        if not parsed or not isinstance(parsed.get("boxes"), dict):
            # one retry with the bad reply quoted back: Sonnet 4.6 returned a stray brace on Form 5500 page 3 twice
            # on 2026-10-01, and a dead page took the whole form's set rebuild with it
            retry = (user_text + "\n\nYour previous reply was not one valid JSON object (it began: "
                     + text[:200].replace("\n", " ") + " ...). Return exactly one JSON object of the shape above, "
                     "with every box number once, and nothing else.")
            text = call_page(client, model, pngs[page_no], system, retry, tag + "/retry")
            parsed = _extract_json_object(text)
        if not parsed or not isinstance(parsed.get("boxes"), dict):
            raise RuntimeError(f"classifier did not return {{'boxes': {{...}}}} on page {page_no}.\n"
                               f"Got: {text[:500]}")
        return ids, parsed
    # the pages' calls go out together (2026-10-19: one after another they cost 64 + 34 + 11 + 11 s on ACORD 90 NY;
    # a call's time is its output, so the form costs its slowest page); the answers are read in page order
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=max(1, len(pngs))) as ex:
        answers = dict(zip(sorted(pngs), ex.map(one_page, sorted(pngs))))
    for page_no in sorted(pngs):
        ids, parsed = answers[page_no]
        raw[str(page_no)] = parsed["boxes"]
        page_ids = set(ids)
        for bid, ans in parsed["boxes"].items():
            bid = str(bid)
            if bid not in page_ids:
                unknown.append(bid)
                continue
            if isinstance(ans, str):
                ans = {"class": ans}
            ans = ans or {}
            cls = str(ans.get("class") or "").strip()
            if cls not in CLASSES:
                bad_class[bid] = cls
                cls = "other"

            def _s(v):
                return str(v).strip() if v not in (None, "", "null") else None
            ent = _s(ans.get("entity"))
            ent = ent.lower().replace(" ", "_") if ent else None
            b = by_id[bid]
            seen.add(bid)
            out_boxes[b["key"]] = {"class": cls, "entity": ent, "label": _s(ans.get("label")),
                                   "group": _s(ans.get("group")) if cls == "option" else None,
                                   "box": bid, "page": page_no, "rect": b["rect"], "kind": b["kind"]}
    unclassified = [b["id"] for b in boxes if b["id"] not in seen]

    result = {
        "form": form_id or pdf_path.stem,
        "blank": str(pdf_path),
        "blank_sha": hashlib.sha256(pdf_bytes).hexdigest()[:16],
        "finder": FINDER_VERSION,
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_boxes": len(out_boxes),
        "n_none": sum(1 for b in out_boxes.values() if b["class"] == "none"),
        "n_option": sum(1 for b in out_boxes.values() if b["class"] == "option"),
        "n_unlabeled": sum(1 for b in out_boxes.values() if b["label"] is None and b["class"] != "none"),
        "n_option_groups": len({(b["page"], b["group"]) for b in out_boxes.values() if b.get("group")}),
        "unknown_boxes": unknown,
        "unclassified": unclassified,
        "bad_class": bad_class,
        "boxes": out_boxes,
        "raw": raw,
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(result, indent=1))
    return _guard(result)


_MARK_KINDS = {"checkbox", "radio", "comb"}


def _guard(cmap: dict) -> dict:
    """An "option" needs a small square, circle or cell under it. The finder's
    kind and the rect are page geometry, so they may vote: a wide text line
    the model called an option (the W-9's instruction table: rows of words
    such as "Corporation", "Partnership") becomes "none"; a narrow text cell
    of any height (ACORD 25's ADDL INSD / SUBR WVD columns, where an X is
    typed per row) stays an option. Applied on every load, so a cached map
    gets it too."""
    n = 0
    for b in cmap.get("boxes", {}).values():
        r = b.get("rect") or [0, 0, 0, 0]
        narrow = (r[2] - r[0]) <= 30      # a cell an X or a letter goes in, however tall the column
        if b.get("class") == "option" and b.get("kind") not in _MARK_KINDS and not narrow:
            b["class"] = "none"
            b["group"] = None
            b["guarded"] = "option_on_text_geometry"
            n += 1
    cmap["n_guarded"] = n
    cmap["n_none"] = sum(1 for b in cmap["boxes"].values() if b["class"] == "none")
    cmap["n_option"] = sum(1 for b in cmap["boxes"].values() if b["class"] == "option")
    cmap["n_option_groups"] = len({(b["page"], b["group"]) for b in cmap["boxes"].values() if b.get("group")})
    return cmap


def class_counts(cmap: dict) -> dict[str, int]:
    import collections
    return dict(collections.Counter(b["class"] for b in cmap["boxes"].values()).most_common())


def entity_counts(cmap: dict) -> dict[str, int]:
    import collections
    return dict(collections.Counter(str(b.get("entity")) for b in cmap["boxes"].values()).most_common())


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Classify a blank form's boxes from the page, blind.")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--form-id", default=None)
    ap.add_argument("--cache-only", action="store_true")
    ap.add_argument("--dry-run", type=Path, metavar="DIR",
                    help="write the numbered pages and box list to DIR and stop; no API call")
    ap.add_argument("--out", type=Path, help="also write the class map here")
    args = ap.parse_args()
    if args.dry_run:
        print(dry_run(args.pdf, args.dry_run))
        return 0
    cmap = classify_form(args.pdf, model=args.model, form_id=args.form_id, cache_only=args.cache_only)
    if cmap is None:
        print("no cached classification")
        return 1
    if args.out:
        args.out.write_text(json.dumps(cmap, indent=1))
    summary = {k: cmap.get(k) for k in ("form", "model", "n_boxes", "n_none", "n_option", "n_unlabeled",
                                        "n_option_groups", "n_guarded")}
    summary.update({"unknown": len(cmap["unknown_boxes"]), "unclassified": len(cmap["unclassified"]),
                    "bad_class": cmap["bad_class"], "classes": class_counts(cmap),
                    "entities": entity_counts(cmap)})
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
