"""Associated fields, the one model call per form (Andrew, 2026-10-14: "you could probably just one shot that and see how
it goes"): the rule pass (`eval/associate.py`) finds what the names say; this asks a model to correct and complete it
from the whole field list in reading order (names, types, where each box sits, the publisher's words), the parts names
cannot carry: the form's own subject (the applicant's name, birth date and address with no prefix), blocks the labeler
named without a shared prefix, and groupings that only share a word.

Input: a standardized copy (runs/standardized/<id>/) and its rule associations (runs/associations/<id>__standardized/).
Output: runs/associations/<id>__model/<file>.bpt with `x_petey_associations` (same shape as the rule pass) and the
model's own wording in `x_petey_associations_model`; a comparison with the rule pass is printed.

    PYTHONPATH=. venv/bin/python eval/associate_model.py je__ds11 lib__i485 [--model claude-opus-5]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from petey.paths import RUNS
from petey.validate import hand_review as h

sys.path.insert(0, str(Path(__file__).resolve().parent))
from associate import KINDS, _box  # noqa: E402

MODEL = "claude-opus-5"
SYSTEM = """You organize the fields of a fillable form into associations.

Terms. A GROUP (already in the field list, type category / multi_category) is one question answered by several
checkboxes; leave groups as they are, but a group can belong to an entity. ASSOCIATED fields come in two kinds:
- ENTITY: fields that describe one thing: a person (the applicant, Parent 1, the spouse, the preparer), an organization
  (the employer, the agency), an address, an event or item (a prior loss, a vehicle, a premises location). Name it in
  snake_case for the thing (applicant, parent_1, preparer, mailing_address, prior_loss_2). An entity may contain a
  smaller one (the applicant's mailing address can be its own entity); a field belongs to at most one entity, the most
  specific.
- COMPOUND VALUE: several boxes that together hold ONE value, from this closed list only: date (month / day / yr),
  phone (area / prefix / line, or area / local), money (dollars / cents), ssn, ein, zip (zip + 4), lines (one text
  written over several numbered lines), digits (one number written a digit per box). Never anything else.
- REPEAT: entities that are instances of the same thing (parent_1, parent_2; premises_1 .. premises_4).

Rules. Judge from the field names, the publisher's words and where the boxes sit (page, row y, column x: fields of one
entity sit together). Fields that only share a word are not an entity (a current spouse's marriage date and a prior
spouse's marriage date belong to two different spouses; two unrelated yes / no questions that both start "intend to"
are not a thing). Do not invent fields; use the names exactly as listed. Many fields belong to no entity (a form-level
date, a signature block may be its own entity: preparer, interpreter). A draft from name rules is given: keep what is
right, fix what is wrong, add what is missing. Return JSON only."""

SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["entities", "compound_values", "repeats"],
    "properties": {
        "entities": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "fields"],
            "properties": {"name": {"type": "string"}, "fields": {"type": "array", "items": {"type": "string"}}}}},
        "compound_values": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "kind", "parts"],
            "properties": {"name": {"type": "string"}, "kind": {"type": "string", "enum": sorted(KINDS)},
                           "parts": {"type": "array", "items": {
                               "type": "object", "additionalProperties": False, "required": ["part", "field"],
                               "properties": {"part": {"type": "string"}, "field": {"type": "string"}}}}}}},
        "repeats": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["name", "of"],
            "properties": {"name": {"type": "string"}, "of": {"type": "array", "items": {"type": "string"}}}}},
    },
}


def listing(bp: dict) -> str:
    rows = []
    for n, s in (bp.get("fields") or {}).items():
        if not isinstance(s, dict):
            continue
        pg, r = _box(s)
        what = s.get("type") or "string"
        if s.get("widgets"):
            what += " group: " + ", ".join(list(s["widgets"])[:6])
        desc = " ".join(str(s.get("description") or "").split())[:70]
        rows.append((pg or 0, round(r[1]), round(r[0]), f"p{pg} y{round(r[1])} x{round(r[0])} {n} [{what}]"
                     + (f' "{desc}"' if desc else "")))
    rows.sort()
    return "\n".join(x[3] for x in rows)


def draft(assoc: list[dict]) -> dict:
    return {"entities": [{"name": a["name"], "fields": a["fields"]} for a in assoc if a["kind"] == "entity"],
            "compound_values": [{"name": a["name"], "kind": a["kind_of_value"],
                                 "parts": [{"part": p, "field": f} for p, f in a["fields"].items()]}
                                for a in assoc if a["kind"] == "compound_value"],
            "repeats": [{"name": a["name"], "of": a["of"]} for a in assoc if a["kind"] == "repeat"]}


def ask(client, model: str, bp: dict, assoc: list[dict]) -> tuple[dict, dict]:
    user = (f"Form: {bp.get('name')}\n\nFields in reading order (page, row y, column x, name, type, publisher's words):\n"
            f"{listing(bp)}\n\nDraft from name rules:\n{json.dumps(draft(assoc), ensure_ascii=False)}\n\n"
            "Return the corrected and completed associations.")
    resp = client.messages.create(model=model, max_tokens=32000, system=SYSTEM,
                                  messages=[{"role": "user", "content": user}],
                                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    text = next((x.text for x in resp.content if getattr(x, "type", None) == "text"), "{}")
    u = resp.usage
    return json.loads(text), {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens}


def to_assoc(out: dict, fields: dict) -> tuple[list[dict], list[str]]:
    """The model's answer in the rule pass's shape; names it invented are dropped and listed."""
    bad, res, seen = [], [], set()
    for cv in out.get("compound_values") or []:
        parts = {p["part"]: p["field"] for p in cv.get("parts") or [] if p.get("field") in fields}
        bad += [p["field"] for p in cv.get("parts") or [] if p.get("field") not in fields]
        if len(parts) >= 2:
            res.append({"name": cv["name"], "kind": "compound_value", "kind_of_value": cv["kind"],
                        "page": _box(fields[next(iter(parts.values()))])[0], "fields": parts})
    for e in out.get("entities") or []:
        fs = [f for f in e.get("fields") or [] if f in fields and f not in seen]
        bad += [f for f in e.get("fields") or [] if f not in fields]
        seen |= set(fs)
        if len(fs) >= 2:
            res.append({"name": e["name"], "kind": "entity", "page": _box(fields[fs[0]])[0], "fields": sorted(fs)})
    for r in out.get("repeats") or []:
        res.append({"name": r["name"], "kind": "repeat", "of": r.get("of") or []})
    return res, bad


def covered(assoc: list[dict]) -> set:
    return {f for a in assoc if a["kind"] == "entity" for f in a["fields"]} | \
           {f for a in assoc if a["kind"] == "compound_value" for f in a["fields"].values()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--model", default=MODEL)
    args = ap.parse_args()
    from petey.synth.generate import make_client
    from petey.validate.page_check import PRICES
    client = make_client(args.model)
    for bid in args.ids:
        src = next((RUNS / "associations" / f"{bid}__standardized").glob("*.bpt"))
        bp = yaml.safe_load(src.read_text())
        fields = {n: s for n, s in bp["fields"].items() if isinstance(s, dict)}
        rule = bp.get("x_petey_associations") or []
        raw, usage = ask(client, args.model, bp, rule)
        assoc, bad = to_assoc(raw, fields)
        pi, po = PRICES.get(args.model, (0, 0))
        cost = (usage["input_tokens"] * pi + usage["output_tokens"] * po) / 1e6
        bp["x_petey_associations"] = assoc
        bp["x_petey_associations_model"] = {"model": args.model, "usage": usage, "cost_usd": round(cost, 4), "invented": bad}
        out = RUNS / "associations" / f"{bid}__model" / src.name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        pages = len({_box(s)[0] for s in fields.values()})
        re_ = {a["name"]: set(a["fields"]) for a in rule if a["kind"] == "entity"}
        me_ = {a["name"]: set(a["fields"]) for a in assoc if a["kind"] == "entity"}
        print(f"\n{bid}: {len(fields)} fields, {pages} pages; ${cost:.3f} (${cost / max(1, pages):.3f}/page); "
              f"invented names dropped: {len(bad)}")
        print(f"  in an association: rules {len(covered(rule))}, model {len(covered(assoc))}")
        print(f"  entities: rules {len(re_)}, model {len(me_)}; kept as is {sum(1 for v in me_.values() if v in re_.values())}")
        print(f"  compound values: rules {sum(a['kind'] == 'compound_value' for a in rule)}, "
              f"model {sum(a['kind'] == 'compound_value' for a in assoc)}")
        new = [(n, sorted(v)) for n, v in me_.items() if v not in re_.values()]
        for n, v in new[:12]:
            print(f"    model entity {n}: {', '.join(v)[:150]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
