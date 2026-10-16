"""Field kinds for a flat form for pennies? (Andrew, 2026-10-15: "how does it do at identifying field types?")

Each text field and lone checkbox of a validated blueprint gets a kind from a small set (checkbox, signature, email,
phone, name, date, money, number, identifier, address, text). Truth: the validated field's type and suffix (the
naming standard makes the suffix say the kind: _dt date, _amt money, _nm name, ...). Three ways to guess it, none
from the widget layer or the validated name:
  * words: a rule on the printed caption candidates near the box (code, free);
  * Jev: a choice question with the page image (widgets stripped, boxes numbered, no names) and the caption
    candidates as text;
  * classifier: Sonnet's cached class map, where the form has one, matched to the field by box overlap.

    PYTHONPATH=. venv/bin/python eval/cheap_kinds.py --forms-list ID ... --save runs/jev/cheap_kinds_2026-10-15.json
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import re
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cheap_names import form_items  # noqa: E402
from jev_is_field import cached_boxes  # noqa: E402

from petey.synth import boxes as B  # noqa: E402
from petey.synth.classify import classify_form  # noqa: E402
from petey.validate import hand_review as h, page_check as pc  # noqa: E402
from petey.validate.jev_page import MODEL, _key, ask_split  # noqa: E402

KINDS = {
    "checkbox": "a box to tick or mark, not to write words in",
    "signature": "a signature (or initials) line",
    "email": "an email address",
    "phone": "a telephone or fax number",
    "name": "the name of a person, company or organization",
    "date": "a date, or one part of a date (month, day or year)",
    "money": "an amount of money",
    "number": "a count, quantity, measurement or percentage that is not money",
    "identifier": "an ID number or code (account, policy, license, SSN, tax ID, case number, ZIP code, state code)",
    "address": "a street address, city, state or full mailing address",
    "text": "any other words: a description, explanation, title, answer in words",
}
QUESTION = ("`page` is one page of a blank form; every fillable box is outlined in red and tagged with its number at "
            "its top-left. `captions` are printed texts near the box tagged `box.id`. What will a person filling in "
            "the form write or mark in that box?")
PER_REQUEST = 20


def truth(name: str, spec: dict) -> str:
    toks = name.split("_")
    st = (spec.get("semantic_type") or "")
    if spec.get("type") == "boolean":
        return "checkbox"
    if "signature" in toks or "initials" in toks or st == "signature":
        return "signature"
    if "email" in toks or st == "email":
        return "email"
    if (set(toks) & {"phone", "fax", "telephone", "tel"}) or st.startswith("phone"):
        return "phone"
    tail = [t for t in toks if not t.isdigit()]
    last = tail[-1] if tail else ""
    if last in ("area", "prefix", "line", "local") and "phone" in toks:
        return "phone"
    if last == "nm" or st in ("person_name", "company_name"):
        return "name"
    if last in ("dt", "month", "day", "yr") or st.startswith("date"):
        return "date"
    if last == "amt" or st.startswith("money"):
        return "money"
    if last in ("cnt", "qty", "pct", "days", "months", "years") or spec.get("type") in ("integer", "number"):
        return "number"
    if last in ("nbr", "ssn", "ein", "tin", "npi", "cd", "zip") or "zip" in toks:
        return "identifier"
    if set(toks) & {"address", "street", "city", "state", "addr"}:
        return "address"
    return "text"


WORD_RULES = [  # the code-only guess, first match wins, on the caption candidates joined
    ("signature", r"\bsignature\b|\bsigned\b|\binitials\b"),
    ("email", r"e-?mail"),
    ("phone", r"\bphone\b|\btelephone\b|\bfax\b|\btel\b"),
    ("date", r"\bdate\b|\bdob\b|mm\s*/\s*dd|\bmonth\b|\byear\b|\byyyy\b"),
    ("money", r"\$|\bamount\b|\bfee\b|\bcost\b|\bprice\b|\bpremium\b|\btotal\b|\bpaid\b|\bwages\b|\bincome\b|\btax\b"),
    ("identifier", r"\bno\.?\b|\bnumber\b|\b#|\bid\b|\bssn\b|\bein\b|\bcode\b|\bzip\b|\blicense\b|\baccount\b|\bpolicy\b"),
    ("name", r"\bname\b"),
    ("address", r"\baddress\b|\bstreet\b|\bcity\b|\bstate\b"),
    ("number", r"\bhow many\b|\bnumber of\b|\bquantity\b|\bpercent\b|%|\bage\b|\bweight\b|\bheight\b|\bhours\b"),
]


def by_words(cands: list[str], is_box: bool) -> str:
    if is_box:
        return "checkbox"
    text = " ".join(cands[:2]).lower()
    for kind, rx in WORD_RULES:
        if re.search(rx, text):
            return kind
    return "text"


CLASS_TO_KIND = {"none": None, "option": "checkbox", "checkbox": "checkbox", "signature": "signature", "email": "email",
                 "phone": "phone", "full_name": "name", "first_name": "name", "last_name": "name", "middle_name": "name",
                 "company_name": "name", "org_name": "name", "date": "date", "month": "date", "day": "date",
                 "year": "date", "money": "money", "amount": "money", "count": "number", "quantity": "number",
                 "percent": "number", "number": "number", "ssn": "identifier", "ein": "identifier", "other_id": "identifier",
                 "zip": "identifier", "postal_code": "identifier", "street": "address", "address": "address",
                 "city": "address", "state": "address", "country": "address", "free_text": "text", "other": "text"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms-list", nargs="+", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--save", required=True)
    args = ap.parse_args()
    fields, jobs = [], []
    for bid in args.forms_list:
        f, j = form_items(bid)            # the caption candidates and the page renders of the names test
        fields += f
        # the names test's requests carry the page and boxes; swap in kind questions
        for (b, page_no, body, imgs, _names) in j:
            ids = {q[1:] for q in body["questions"]}
            qs, names = {}, {}
            for x in f:
                if x["page"] == page_no and x["id"] in ids:
                    qs[f"k{x['id']}"] = {"type": "choice", "instructions": {"box": {"id": x["id"]}, "captions": x["cands"][:4],
                                                                            "question": QUESTION}, "criteria": KINDS}
                    names[f"k{x['id']}"] = x["id"]
            jobs.append((b, page_no, dict(body, questions=qs), imgs, names))
        # fields with fewer than two candidates had no names question: ask their kind too
        asked = {(b, i) for (b, _p, _bd, _im, nm) in jobs for i in nm.values()}
        for x in f:
            if (bid, x["id"]) not in asked:
                src = next((jb for jb in jobs if jb[0] == bid and jb[1] == x["page"]), None)
                if src:
                    q = {f"k{x['id']}": {"type": "choice", "instructions": {"box": {"id": x["id"]}, "captions": x["cands"][:4],
                                                                         "question": QUESTION}, "criteria": KINDS}}
                    jobs.append((bid, x["page"], dict(src[2], questions=q), src[3], {f"k{x['id']}": x["id"]}))
    print(f"{len(args.forms_list)} forms, {len(fields)} fields, {len(jobs)} requests", file=sys.stderr)
    key, got, tokens = _key(), {}, 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(ask_split, client, key, j[2], j[3]): j for j in jobs if j[2]["questions"]}
        for fut in cf.as_completed(futs):
            j = futs[fut]
            res = fut.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, fid in j[4].items():
                got[(j[0], fid)] = ((res.get("answers") or {}).get(qid) or {}).get("choice")
    # the classifier, where cached: the finder box under the field
    cls = {}
    for bid in args.forms_list:
        bp = h._load(h.working_path(bid))
        blank = pc.resolve_blank(bp)
        bx = cached_boxes(blank) if blank else None
        try:
            cm = (classify_form(blank, cache_only=True) or {}).get("boxes") or {}
        except Exception:
            cm = {}
        if not bx or not cm:
            continue
        for r in pc.numbered(bp):
            b0 = r["boxes"][0]
            best = max(((B.overlap(b0["rect"], b["rect"]), b) for b in bx if b["page"] == b0["page"]), key=lambda x: x[0],
                       default=(0, None))
            if best[0] >= 0.5:
                c = (cm.get(best[1]["key"]) or {}).get("class")
                cls[(bid, r["id"])] = CLASS_TO_KIND.get(c, "text" if c else None)
    out, S, conf = [], collections.Counter(), collections.defaultdict(collections.Counter)
    for x in fields:
        t = truth(x["name"], x["spec"])
        g = {"words": by_words(x["cands"], x["type"] == "boolean"), "Jev": got.get((x["bid"], x["id"])),
             "classifier": cls.get((x["bid"], x["id"]))}
        for k, v in g.items():
            if v is not None:
                S[(k, "n")] += 1
                S[(k, "ok")] += v == t
        if g["Jev"]:
            conf[t][g["Jev"]] += 1
        out.append({"bid": x["bid"], "id": x["id"], "name": x["name"], "truth": t, **g})
    Path(args.save).write_text(json.dumps(out, indent=1))
    pages = len({(j[0], j[1]) for j in jobs})
    print(f"input tokens {tokens:,} (~${tokens / 1e6 * 0.042:.3f}, ${tokens / 1e6 * 0.042 / max(pages, 1):.4f}/page)")
    for k in ("words", "Jev", "classifier"):
        print(f"{k:11} {S[(k, 'ok')]:5} of {S[(k, 'n')]:5} right ({S[(k, 'ok')] / max(S[(k, 'n')], 1):.0%})")
    both = [o for o in out if o["classifier"] and o["Jev"]]
    if both:
        print(f"on the {len(both)} fields with a class map: Jev {sum(o['Jev'] == o['truth'] for o in both) / len(both):.0%}, "
              f"classifier {sum(o['classifier'] == o['truth'] for o in both) / len(both):.0%}, words "
              f"{sum(o['words'] == o['truth'] for o in both) / len(both):.0%}")
    print("\nJev by true kind (right / total, its commonest wrong answer):")
    for t, c in sorted(conf.items(), key=lambda x: -sum(x[1].values())):
        n = sum(c.values())
        wrong = [(k, v) for k, v in c.most_common() if k != t][:2]
        print(f"  {t:11} {c[t]:5}/{n:<5} {c[t] / n:4.0%}   {wrong}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
