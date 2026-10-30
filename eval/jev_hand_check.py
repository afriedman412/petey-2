"""Jev (TypeSafe's System One model) as the hand-check scorer, measured against Andrew's hand-review verdicts.

The question (Andrew, 2026-10-05): can a calibrated yes/no model decide which fields a person must look at? Each
hand-reviewed field becomes one request: the field's text evidence as `state` (name, type, description, the
publisher's tooltip / XFA caption, the printed text at the box and its column / row headers, the classifier's
caption and class, the nearest fields on the page with their own captions) and two Noul questions:

    name_fits     does the name say what a filer writes in this box?
    one_question  (checkboxes) is this one of several separate checkboxes answering one question, which Andrew's
                  convention makes a single category field?

Jev reads text only, so the page geometry reaches it as the captions `witness.py` already extracts; it combines
the same evidence the witnesses read, it does not see the page. Scored like the witness tiers: rank fields by
how sure Jev is they are fine, skip the surest, count the flags among the skipped. The tiers skip 313 of 442 and
miss 5 (2026-10-05).

    PYTHONPATH=. venv/bin/python eval/jev_hand_check.py [--limit N] [--workers 8]

Responses are cached under runs/jev/cache by request hash; a rerun calls nothing it has asked before. The key is
TYPESAFE_API_KEY in .env. Price at writing: $0.042 per million input tokens, output free.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import math
from pathlib import Path

import httpx
from dotenv import dotenv_values

from petey.paths import RUNS
from petey.validate import witness as W
from petey.validate.jev_page import states  # noqa: F401  (moved there 2026-10-15; imported from here by other evals)

URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"          # pinned: an alias moves when a release ships, and thresholds are per version
CACHE = RUNS / "jev" / "cache"

NAME_FITS = {
    "type": "noul",
    "instructions": (
        "Does `field.name` say what a person filling in this form would write in this box? Judge from the "
        "printed text at the box (`printed_text_at_box`, `column_header`, `row_header`), the publisher's own "
        "words for the box (`publisher_text`) and the page reader's caption (`classifier_caption`). Field names "
        "are snake_case slugs with suffixes: _nm name, _cd code, _dt date, _amt money, _ind checkbox, _txt free "
        "text, _nbr number. `neighbours` are the boxes nearest to this one, with their names and captions."),
    "criteria": {
        "true": "The name describes the value that goes in this box, and tells it apart from the neighbouring boxes.",
        "false": ("The name describes a different box (for example a neighbour's caption, or the row or column "
                  "next to it), is too vague to tell this box from the others, or the box is not a place where "
                  "anything is written."),
    },
}
ONE_QUESTION = {
    "type": "noul",
    "instructions": (
        "This box is a checkbox. Is it one of several separate checkboxes among `neighbours` that together answer "
        "a single question on the form (pick one, or pick several, from a list of options printed side by side "
        "or stacked), so that the options belong in one field rather than one field per checkbox?"),
    "criteria": {
        "true": "It is one option of a printed question whose other options are separate neighbouring checkboxes.",
        "false": "It is a stand-alone yes/no checkbox, or its question has no other checkbox among the neighbours.",
    },
}


def ask(client: httpx.Client, key: str, state: dict, checkbox: bool) -> dict:
    body = {"model": MODEL, "state": state,
            "questions": {"name_fits": NAME_FITS, **({"one_question": ONE_QUESTION} if checkbox else {})}}
    h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    cp = CACHE / f"{h}.json"
    if cp.exists():
        return json.loads(cp.read_text())
    for attempt in range(4):
        r = client.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=60)
        if r.status_code == 429 and attempt < 3:
            import time
            time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
            continue
        r.raise_for_status()
        break
    out = r.json()
    CACHE.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(out))
    return out


def structural(note: str) -> bool:
    """Andrew's notes that are about grouping, not naming ('should be one category widget')."""
    n = (note or "").lower()
    return any(k in n for k in ("category", "one widget", "should be one", "other four"))


def skip_curve(rows: list[dict], key, label: str) -> None:
    """Skip the fields `key` ranks surest-fine first; flags among the skipped at several skip counts."""
    ranked = sorted(rows, key=key)
    n, flags = len(rows), sum(r["flag"] for r in rows)
    pts = []
    for k in (n // 2, int(n * 0.6), 313, int(n * 0.8)):
        skipped = ranked[:k]
        pts.append(f"skip {k}: miss {sum(r['flag'] for r in skipped)} "
                   f"({sum(r['flag'] and not r['structural'] for r in skipped)} naming)")
    print(f"  {label:28} " + "  |  ".join(pts) + f"   [of {flags} flags]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="only the first N verdicts (a smoke test)")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY not in .env")
    jobs = []
    tiers = {}
    for vp in sorted((RUNS / "hand_review").glob("*.json")):
        v = json.loads(vp.read_text())
        bpt = Path(v["blueprint"])
        if not bpt.exists():
            continue
        st = states(bpt)
        tw = W.witnesses(bpt)["fields"]
        for name, rec in (v.get("verdicts") or {}).items():
            if name not in st or rec.get("note", "").startswith("bulk:"):
                continue
            checkbox = st[name]["field"].get("kind") in ("checkbox", "radiobutton")
            jobs.append({"form": bpt.stem, "field": name, "flag": rec["verdict"] == "flag" or bool(rec.get("edit")),
                         "note": rec.get("note", ""), "structural": structural(rec.get("note", "")),
                         "state": st[name], "checkbox": checkbox, "tier": tw.get(name, {}).get("tier")})
    if args.limit:
        jobs = jobs[:args.limit]
    print(f"{len(jobs)} hand-reviewed fields, {sum(j['flag'] for j in jobs)} flagged")
    tokens = 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(ask, client, key, j["state"], j["checkbox"]): j for j in jobs}
        for f in cf.as_completed(futs):
            j = futs[f]
            res = f.result()
            a = res.get("answers", {})
            j["name_fits"] = a.get("name_fits", {}).get("noul")
            j["one_question"] = a.get("one_question", {}).get("noul")
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
    out = RUNS / "jev" / "hand_check.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps([{k: v for k, v in j.items() if k != "state"} for j in jobs], indent=1))
    print(f"input tokens this run (uncached calls only count once): {tokens}  (~${tokens / 1e6 * 0.042:.4f})")

    tier_rank = {"settled": 0, "single": 1, "unknown": 2, "contested": 3}

    def jev_ok(j):           # how sure Jev is the field is fine: name fits, and not one of a split question
        p = j["name_fits"] if j["name_fits"] is not None else 0.5
        if j["checkbox"] and j["one_question"] is not None:
            p = min(p, 1 - j["one_question"])
        return p
    print("\nskip the surest-fine fields first; flags missed among the skipped:")
    skip_curve(jobs, lambda j: (tier_rank.get(j["tier"], 2), j["form"]), "witness tiers")
    skip_curve(jobs, lambda j: -jev_ok(j), "jev")
    skip_curve(jobs, lambda j: -(j["name_fits"] if j["name_fits"] is not None else 0.5), "jev name_fits only")
    skip_curve(jobs, lambda j: (tier_rank.get(j["tier"], 2) == 3, -jev_ok(j)), "tiers gate, jev orders")

    print("\nflags, with Jev's numbers:")
    for j in sorted((j for j in jobs if j["flag"]), key=lambda j: -jev_ok(j)):
        oq = f" one_q {j['one_question']:.2f}" if j["one_question"] is not None else ""
        print(f"  name_fits {j['name_fits']:.2f}{oq}  [{j['tier']}]  {j['form']} {j['field']}  -- {j['note'][:60]}")
    lo = sorted((j for j in jobs if not j["flag"]), key=jev_ok)[:10]
    print("\naccepted fields Jev doubts most:")
    for j in lo:
        print(f"  name_fits {j['name_fits']:.2f}  [{j['tier']}]  {j['form']} {j['field']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
