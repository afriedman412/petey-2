"""Page-grounded box classification (TODO v6, synthetic data step 1).

The model sees exactly what the blind generator sees: the page image with a
numbered red box on every widget and an inventory of box ids and control
types. No AcroForm names, no export values. It returns, per box, a class
from the closed vocabulary below and an entity slug (whose SSN is this).

Two consumers:
  * the value bank (`synth.bank`): a class map plus a bank of names,
    addresses and numbers builds any number of cases for free, one
    persona per entity, so header copies of one identifier agree;
  * the labeler check: the class is a blueprint-independent second
    opinion on every box's semantic type (`SEMANTIC_TO_CLASS` maps the
    blueprint's vocabulary onto this one for the comparison).

Cached once per (blank bytes, model, prompt version) under
`runs/_gen_cache/classify/`; no case key, the classification is a fact
about the form. Written into runs as `class_map.json`.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

from petey.paths import RUNS
from petey.synth.generate import (
    MODEL, _extract_json_object, _model_view, blind_inventory, call_page,
    make_client, render_annotated_pages,
)

PROMPT_VERSION = "3"
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
    "mark": "a small text box where the filer types an X, Y or check mark to mark a column (ADDL INSD, SUBR WVD, OTHER); not a checkbox control",
    "free_text": "prose or a description the filer writes in their own words",
    "other": "none of the above",
    # controls (the model still classes them, so a yes/no pair is known as one)
    "yes_no": "a radio group or combobox whose options are Yes / No (or True / False)",
    "choice": "any other radio group or combobox: one option from a printed list",
    "checkbox": "a standalone checkbox",
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
    "count": "count", "birth_date": "birth_date", "service_date": "date", "iso_date": "date",
    "year": "year", "phone": "phone", "email": "email", "state_abbr": "state", "zip": "zip",
    "city": "city", "country_code": "country", "country": "country",
    "street_address": "street", "entity_name": "business_name",
    "business_name": "business_name", "first_name": "first_name", "last_name": "last_name",
    "person_name": "full_name", "description": "free_text", "text": "free_text",
    "indicator": "checkbox",
}

# Classes that agree with each other for the labeler comparison (a whole
# name typed person_name is not wrong because the page says last_name).
CLASS_FAMILY: dict[str, str] = {
    "first_name": "name", "middle_name": "name", "last_name": "name", "full_name": "name",
    "date": "date", "birth_date": "date",
    "date_month": "date_part", "date_day": "date_part", "date_year": "date_part",
    "ssn": "tax_id", "itin": "tax_id", "ein": "tax_id",
    "money": "number", "percent": "number", "count": "number", "number": "number",
    "street": "address", "unit": "address", "address_block": "address", "city_state_zip": "address",
    "year": "date_part", "code": "code", "mark": "control",
    "yes_no": "control", "choice": "control", "checkbox": "control",
    "signature": "name", "id_part": "id_part", "phone_part": "id_part",
}

_ENTITIES = ("applicant", "spouse", "dependent_1", "dependent_2", "employer", "preparer",
             "representative", "insured", "producer", "insurer", "certificate_holder",
             "provider", "contact", "payer", "recipient", "other")

SYSTEM_PROMPT = """You classify the fillable boxes on a blank form. You see \
the page image with a numbered red box drawn on every fillable widget, and \
an inventory listing each box number with its control type. Read the \
printed label next to each box and say what KIND of value belongs there \
and WHOSE value it is.

OUTPUT SHAPE:
- Return JSON only. No prose, no markdown, no code fences.
- Top-level shape: {{"boxes": {{"<box number>": {{"label": "<caption or null>", "class": "<class>", "entity": "<entity or null>", "group": "<question or null>"}}, ...}}}}
- One entry per box in the inventory. Radio groups are one box (the group \
id); classify the group, not its options.

LABEL: the caption printed for THIS box, verbatim (a column heading counts \
when the box sits under it). null when the box has no caption of its own: \
one of several unlabeled lines under a block heading such as PRODUCER or \
INSURED. For such blocks use the common convention in reading order (name, \
street, street 2, city; the short boxes ending a line are state then ZIP) \
and still give label null, so the reader knows the class is by position, \
not by caption.

CLASS: exactly one of the names below. Pick the most specific that fits. \
A box that holds one part of a split value (month of a date, first three \
digits of an SSN, area code) takes the PART class, never the whole one. \
A box whose label you cannot read confidently is "other".

{classes}

GROUP: for a checkbox only. When several checkboxes on the page are the \
options of ONE question (Apt / Ste / Flr; Single / Married / Divorced / \
Widowed; the entity-type boxes on a W-9), give every box of that set the \
same short string, the question's printed text (e.g. "Marital Status", \
"Unit type, physical address", "Federal tax classification"). null for a \
standalone checkbox and for every non-checkbox box. Boxes of one set share \
a group even when the form allows more than one to be checked.

ENTITY: whose value the box holds, as a short slug. Use the form's own \
words for the role when it prints them (Insured, Producer, Certificate \
Holder, Preparer, Spouse, Dependent 1). Prefer these slugs when they fit: \
{entities}. The filer of the form is "applicant". A box that belongs to \
no person or organization (a plain date, an amount, free text, a control) \
takes entity null.

Ground every answer in this page. You may recognize the form; the page \
image and inventory supplied here are authoritative for this file.
"""

USER_TEMPLATE = """Boxes on this page:

```json
{inventory_json}
```

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
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(PROMPT_VERSION.encode("utf-8"))
    return cache_dir / f"{h.hexdigest()}.json"


def _control_type(box: dict) -> str:
    return box["type"]


def classify_form(
    pdf_path: str | Path, *, model: str = MODEL, cache_dir: Path = CACHE_DIR,
    client: Any = None, cache_only: bool = False, form_id: Optional[str] = None,
) -> Optional[dict]:
    """The class map for one blank form, from cache or one call per page.

    Returns `{"boxes": {acroform_path: {class, entity, box, page, control}},
    "raw": {page: model output}, "unknown_boxes": [...], "unclassified": [...],
    ...provenance}`, or None when `cache_only` and nothing is cached.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"blank PDF not found: {pdf_path}")
    pdf_bytes = pdf_path.read_bytes()
    cp = cache_path(pdf_bytes, model, cache_dir)
    if cp.exists():
        return json.loads(cp.read_text(encoding="utf-8"))
    if cache_only:
        return None

    per_page, key = blind_inventory(pdf_path)
    pngs = render_annotated_pages(pdf_path, per_page)
    if client is None:
        client = make_client(model)
    tag = f"classify/{form_id or pdf_path.stem}/{model.replace('/', '_')}"
    system = _system_prompt()

    boxes: dict[str, dict] = {}
    raw: dict[str, Any] = {}
    unknown: list[str] = []
    bad_class: dict[str, str] = {}
    seen: set[str] = set()
    for page_no in sorted(per_page):
        view = _model_view(per_page[page_no])
        if not view:
            continue
        user_text = USER_TEMPLATE.format(inventory_json=json.dumps(view, indent=2))
        text = call_page(client, model, pngs[page_no - 1], system, user_text, tag)
        parsed = _extract_json_object(text)
        if not parsed or not isinstance(parsed.get("boxes"), dict):
            raise RuntimeError(f"classifier did not return {{'boxes': {{...}}}} on page {page_no}.\n"
                               f"Got: {text[:500]}")
        raw[str(page_no)] = parsed["boxes"]
        control_of = {b["id"]: _control_type(b) for b in view}
        for bid, ans in parsed["boxes"].items():
            bid = str(bid)
            k = key.get(bid)
            if k is None or k["type"] == "radio_option" or bid not in control_of:
                unknown.append(bid)
                continue
            if isinstance(ans, str):
                ans = {"class": ans, "entity": None, "label": None}
            cls = str((ans or {}).get("class") or "").strip()
            ent = (ans or {}).get("entity")
            label = (ans or {}).get("label")
            label = str(label).strip() if label not in (None, "", "null") else None
            group = (ans or {}).get("group")
            group = str(group).strip() if group not in (None, "", "null") else None
            if cls not in CLASSES:
                bad_class[bid] = cls
                cls = "other"
            ent = str(ent).strip().lower().replace(" ", "_") if ent not in (None, "", "null") else None
            seen.add(bid)
            boxes[k["path"]] = {"class": cls, "entity": ent, "label": label, "box": bid,
                                "page": page_no, "control": control_of[bid],
                                "group": group if control_of[bid] == "checkbox" else None}
    unclassified = [b["id"] for p in per_page.values() for b in _model_view(p) if b["id"] not in seen]

    result = {
        "form": form_id or pdf_path.stem,
        "blank": str(pdf_path),
        "blank_sha": hashlib.sha256(pdf_bytes).hexdigest()[:16],
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "n_boxes": len(boxes),
        "n_unlabeled": sum(1 for b in boxes.values() if b["label"] is None),
        "n_checkbox_groups": len({(b["page"], b["group"]) for b in boxes.values() if b.get("group")}),
        "unknown_boxes": unknown,
        "unclassified": unclassified,
        "bad_class": bad_class,
        "boxes": boxes,
        "raw": raw,
    }
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(result, indent=1))
    return result


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
    ap.add_argument("--out", type=Path, help="also write the class map here")
    args = ap.parse_args()
    cmap = classify_form(args.pdf, model=args.model, form_id=args.form_id, cache_only=args.cache_only)
    if cmap is None:
        print("no cached classification")
        return 1
    if args.out:
        args.out.write_text(json.dumps(cmap, indent=1))
    print(json.dumps({"form": cmap["form"], "model": cmap["model"], "n_boxes": cmap["n_boxes"],
                      "unlabeled": cmap.get("n_unlabeled"), "checkbox_groups": cmap.get("n_checkbox_groups"),
                      "unknown": len(cmap["unknown_boxes"]), "unclassified": len(cmap["unclassified"]),
                      "bad_class": cmap["bad_class"], "classes": class_counts(cmap),
                      "entities": entity_counts(cmap)}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
