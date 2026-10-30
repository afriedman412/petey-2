"""Jev on every field of some forms, no hand review needed (2026-10-14: a batch of generated blueprints after the
mechanical pass, to see what Jev says before the VLM page check). Since 2026-10-15 Jev sees the page: one request per
page with the marked-up page image, the field list and each field's text evidence (`petey.validate.jev_page`), asking
name_fits, and one_question for checkboxes; `--text-only` asks the earlier way (`jev_hand_check.ask`, one field per
request, no image). On the review page's working copy when one is open. Each field is listed by its review-page code
with Jev's numbers and whether the name checks already call it an error.

    PYTHONPATH=. venv/bin/python eval/jev_forms.py lib__fw9 lib__ds11 --save runs/jev/forms.json
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jev_hand_check import ask, states  # noqa: E402

from petey.validate import hand_review as h, jev_page, witness  # noqa: E402

DOUBT = 0.5          # name_fits below this: Jev doubts the name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--text-only", action="store_true", help="the earlier requests: one field each, no page image")
    ap.add_argument("--save", required=True)
    args = ap.parse_args()
    key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY not in .env")
    jobs, paths = [], {}
    for bid in args.ids:
        p = h.working_path(bid)
        paths[bid] = p
        bp = h._load(p)
        st = states(p)
        res = witness.witnesses(p)["fields"]
        for name, s in st.items():
            spec = bp["fields"][name]
            why = (res.get(name) or {}).get("why") or []
            jobs.append({"bid": bid, "field": name, "code": f"{p.stem}_{spec.get('x_petey_id')}",
                         "check_error": next((w["text"] for w in why if w.get("kind") == "error"), None),
                         "state": s, "checkbox": s["field"].get("kind") in ("checkbox", "radiobutton")})
        print(f"  {bid}: {len(st)} fields", file=sys.stderr)
    tokens = 0
    if args.text_only:
        with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
            futs = {ex.submit(ask, client, key, j["state"], j["checkbox"]): j for j in jobs}
            for f in cf.as_completed(futs):
                j = futs[f]
                res = f.result()
                a = res.get("answers", {})
                j["name_fits"] = a.get("name_fits", {}).get("noul")
                j["one_question"] = a.get("one_question", {}).get("noul")
                tokens += (res.get("usage") or {}).get("input_tokens", 0)
    else:
        got, tokens = jev_page.check(list(paths.values()), workers=args.workers)
        for j in jobs:
            a = got[str(paths[j["bid"]])].get(j["field"]) or {}
            j["name_fits"], j["one_question"] = a.get("name_fits"), a.get("one_question")
            j["image"], j["model"] = True, jev_page.MODEL
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps(jobs, indent=1))
    print(f"{len(jobs)} fields; input tokens {tokens} (~${tokens / 1e6 * jev_page.PRICE:.4f}, cached responses included)")
    print(f"\n{'form':26} {'fields':>6} {'jev doubts':>10} {'check errors':>12} {'both':>5}")
    for bid in args.ids:
        js = [j for j in jobs if j["bid"] == bid]
        d = [j for j in js if j["name_fits"] is not None and j["name_fits"] < DOUBT]
        e = [j for j in js if j["check_error"]]
        print(f"{bid:26} {len(js):>6} {len(d):>10} {len(e):>12} {sum(1 for j in d if j['check_error']):>5}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
