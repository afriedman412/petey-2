"""The mechanical pass on generated blueprints: the fixes and checks of the 2026-10-13/14 review round that need no
model, in one place (they were scratch scripts then). Run it on a form before any model check (Jev, the VLM page
check), so those see a blueprint the rules have already cleaned.

Fixes, written into the review page's working copy (`draft`), so Andrew checks and saves them as usual; each field
records `x_petey_hand_edit` {by: claude, kind: type, why}:

    person_name   the leftover `person_name` semantic type is cleared (it is no longer assigned; it changed nothing)
    pattern       a string field whose semantic type has a registry pattern gets it (`semantic_types.pattern_for`)
    yes_no        loose Yes / No checkbox pairs become one group each (`yes_no_groups`)

Checks, reported only:

    unclaimed     AcroForm widgets no field covers (missing boxes; I-130 had two)
    keys_inverted a Yes / No option whose key says yes and whose export value says no, or the reverse
    code_caption  option captions that are export codes ('BLK', 'N') rather than the printed words
    far_pages     an option group whose boxes are on pages more than one apart
    bad_semtype   a semantic type the registry does not know
    name_errors   fields the review page marks as errors (the name checks: belongs to / does not describe, item
                  number only, suffix against type); `name_hints` the suggestions

    PYTHONPATH=. venv/bin/python eval/mechanical_pass.py lib__fw9 lib__ds11 [--dry]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import yes_no_groups as yn  # noqa: E402

from petey.semantic_types import pattern_for, registered_names  # noqa: E402
from petey.validate import draft, field_add, group_review as g, hand_review as h, witness  # noqa: E402
from petey.validate.retype import resolve_blank  # noqa: E402

CODEISH = re.compile(r"^(Y|N|YES|NO|[A-Z]{2,4}|\d+[a-zA-Z]?|[a-z]\d*|#20.*|\s*)$")
FIXES = ("person_name", "pattern", "yes_no")
CHECKS = ("unclaimed", "keys_inverted", "code_caption", "far_pages", "bad_semtype", "name_errors", "name_hints")


def type_edits(fields: dict) -> tuple[dict, dict]:
    """({field: edit}, {field: {kind, why}}) for the person_name and pattern fixes."""
    edits, extra = {}, {}
    for n, s in fields.items():
        if not isinstance(s, dict):
            continue
        st = s.get("semantic_type")
        if st == "person_name":
            edits[n] = {"semantic_type": "none"}
            extra[n] = {"kind": "type", "why": "person_name is no longer assigned (it changed nothing)"}
        elif s.get("type", "string") == "string" and not s.get("pattern") and pattern_for(st):
            edits[n] = {"pattern": pattern_for(st)}
            extra[n] = {"kind": "type", "why": f"the pattern of its semantic type ({st})"}
    return edits, extra


def checks(bid: str, p: Path, bp: dict, blank: Path) -> tuple[collections.Counter, list[str]]:
    """The report-only checks: counts, and one line per finding."""
    c, lines = collections.Counter(), []
    valid = set(registered_names())
    try:
        ctx = field_add.Context(bid, p)
        for w in ctx.widgets:
            if not w["claimed_by"] and not w["copy"]:
                c["unclaimed"] += 1
                lines.append(f"unclaimed     p{w.get('page')} {w.get('path') or w.get('rect')}")
    except Exception as e:                              # a blank the finder cannot read: say so, go on
        lines.append(f"unclaimed     not checked ({type(e).__name__}: {e})")
    items, units = g.option_items(bp)
    for u in units:
        its = [items[i] for i in u["items"]]
        pages = sorted({it["page"] for it in its})
        if len(pages) > 1 and pages[-1] - pages[0] > 1:
            c["far_pages"] += 1
            lines.append(f"far_pages     {u['name']} pages {pages}")
        for it in its:
            k, on = (it["key"] or it["field"]).lower(), str(it.get("on_state") or "").lower().replace("#20", "")
            if on in ("y", "yes", "n", "no") and (("_yes" in k and on.startswith("n")) or
                                                  ("_no_" in k + "_" and on.startswith("y"))):
                c["keys_inverted"] += 1
                lines.append(f"keys_inverted {u['name']} :: {it['key'] or it['field']} on={it.get('on_state')}")
            cap = it.get("caption")
            if len(its) > 1 and cap is not None and CODEISH.match(str(cap)) and str(cap).strip().lower() not in ("yes", "no"):
                c["code_caption"] += 1
                lines.append(f"code_caption  {u['name']} :: {it['key'] or it['field']} caption={cap!r}")
    for n, s in (bp.get("fields") or {}).items():
        st = (s or {}).get("semantic_type") if isinstance(s, dict) else None
        if st and st not in valid and st != "none":
            c["bad_semtype"] += 1
            lines.append(f"bad_semtype   {n} {st}")
    res = witness.witnesses(p)
    code = {n: f"{p.stem}_{s.get('x_petey_id')}" for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    for n, f in (res.get("fields") or {}).items():
        why = f.get("why") or []
        errs = [w for w in why if w.get("kind") == "error"]
        if errs:
            c["name_errors"] += 1
            lines.append(f"name_error    {code.get(n, n)} {n}: {errs[0]['text'][:140]}")
        elif why:
            c["name_hints"] += 1
    return c, lines


def run(bid: str, dry: bool) -> dict:
    real = h.blueprint_paths()[bid]
    p = h.working_path(bid)
    bp = h._load(p)
    blank = resolve_blank(bp)
    edits, extra = type_edits(bp.get("fields") or {})
    pairs = yn.pairs(bp, blank) if blank else []
    fixed = collections.Counter({"person_name": sum("semantic_type" in e for e in edits.values()),
                                 "pattern": sum("pattern" in e for e in edits.values()), "yes_no": len(pairs)})
    if not dry and edits:
        p = draft.ensure(bid, real)
        bp = h._load(p)
        clean = {n: e for n, e in ((n, h.clean_edit(n, bp["fields"][n], e)) for n, e in edits.items()) if e}
        before = h._sha(p)
        bp["fields"] = h.edit_fields(bp["fields"], clean, {n: n for n in clean}, time.strftime("%Y-%m-%d %H:%M:%S"),
                                     "eval/mechanical_pass.py", by="claude", extra=extra)
        p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        draft.follow(bid, before, h._sha(p))
        draft.log(bid, "claude", [f"{n}: {extra[n]['why']}" for n in clean])
    if not dry and pairs:
        yn.run(bid, False, [])
    p = h.working_path(bid)
    c, lines = checks(bid, p, h._load(p), blank) if blank else (collections.Counter(), ["no blank"])
    return {"bid": bid, "fixed": dict(fixed), "checks": dict(c), "lines": lines}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+", help="review-page ids (lib__fw9)")
    ap.add_argument("--dry", action="store_true", help="count the fixes, write nothing")
    ap.add_argument("--save", help="write the report (json) here")
    args = ap.parse_args()
    out = []
    print(f"{'form':30} " + " ".join(f"{k:>11}" for k in FIXES + CHECKS))
    for bid in args.ids:
        r = run(bid, args.dry)
        out.append(r)
        print(f"{bid:30} " + " ".join(f"{r['fixed'].get(k, r['checks'].get(k, 0)):>11}" for k in FIXES + CHECKS),
              flush=True)
    tot = collections.Counter()
    for r in out:
        tot.update(r["fixed"])
        tot.update(r["checks"])
    print(f"{'total':30} " + " ".join(f"{tot.get(k, 0):>11}" for k in FIXES + CHECKS))
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
