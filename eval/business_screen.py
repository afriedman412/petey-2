"""Is a corpus form business-like or homemade? One Jev question on page 1 (Andrew, 2026-10-26: "I would hope we could
find some more complicated 'business-like' forms -- some of these feel extremely homemade and not useful at scale";
"lets see how well the jev checks works on the 374").

Jev sees the flat copy's first page and the host it was published on, and answers one Noul: a standardized form an
established organization publishes and processes at scale, or an informal one-off. Scores go to
runs/acquisition/safedocs/business_scores.json; the top and bottom of the ranking are printed with review links so the
screen can be checked by eye before it decides what is fetched.

    PYTHONPATH=. venv/bin/python eval/business_screen.py [--show 10]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flat_light import _ask_all  # noqa: E402

from petey.paths import REPO, RUNS  # noqa: E402
from petey.validate import page_check as pc  # noqa: E402
from petey.validate.jev_page import LIMITS, MODEL, PRICE, image_ref  # noqa: E402

D = RUNS / "acquisition" / "safedocs"
QUESTION = ("`page` is the first page of a fillable form found on the web; `host` is the website that published it. "
            "Is this a standardized business form that an established organization (a bank, insurer, health system or "
            "hospital, employer's HR department, school district, university, government contractor, professional or "
            "trade body) publishes and processes at volume, as opposed to an informal one-off form made by a small "
            "club, event, team, church group or one-person business?")
CRITERIA = {
    "true": "A standardized form from an established organization: consistent professional layout, an organization's "
            "identity, often a form number or revision date, fields a back office processes in volume.",
    "false": "An informal or homemade form: a club or event sign-up, a raffle or sponsorship sheet, a small business's "
             "one-off, or a word-processor page with fields dropped on it.",
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--show", type=int, default=10)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--fetched", action="store_true",
                    help="score every kept fetched form not scored yet (page 1 of the original), before staging")
    ap.add_argument("--min-widgets", type=int, default=0, help="with --fetched: only forms with this many widgets")
    args = ap.parse_args()
    out = D / "business_scores.json"
    old = json.loads(out.read_text()) if out.exists() else {}
    fetched = [json.loads(line) for line in (D / "fetched.jsonl").open()]
    hosts = {r["url_id"]: r["host"] for r in fetched}
    if args.fetched:
        staged = [{"url_id": r["url_id"], "url": r["url"], "sector": r["sector"], "boxes": r["widgets"],
                   "pdf": str((D / "pdf" / r["sector"] / r["file_name"]).relative_to(REPO))}
                  for r in fetched if r.get("kept") and r["url_id"] not in old and r["widgets"] >= args.min_widgets]
    else:
        staged = [dict(s, pdf=s["flat"]) for s in (json.loads(line) for line in (D / "staged.jsonl").open())]
    jobs = []
    for s in staged:
        png, _dpi, _px = pc.render(REPO / s["pdf"], 1, [], limits=LIMITS)
        ref = image_ref(png)
        body = {"model": MODEL, "state": {"page": ref, "host": hosts.get(s["url_id"], "")},
                "questions": {"business": {"type": "noul", "instructions": {"question": QUESTION},
                                           "criteria": CRITERIA}}}
        jobs.append((1, body, {ref: png}, {"business": s["url_id"]}))
    got, tokens = _ask_all(jobs, args.workers)
    out.write_text(json.dumps({**old, **got}, indent=0))
    rows = sorted(((got.get(s["url_id"]), s) for s in staged if got.get(s["url_id"]) is not None),
                  key=lambda r: -r[0])
    print(f"{len(rows)} of {len(staged)} answered; Jev {tokens:,} tokens = ${tokens / 1e6 * PRICE:.3f}")
    for cut in (0.3, 0.5, 0.7, 0.9):
        print(f"  >= {cut}: {sum(v >= cut for v, _ in rows)}")
    by = collections.defaultdict(list)
    for v, s in rows:
        by[s["sector"]].append(v)
    print("  share >= 0.5 by sector:", {k: f"{sum(x >= 0.5 for x in vs)}/{len(vs)}" for k, vs in sorted(by.items())})

    def line(v, s):
        return (f"  {v:.2f}  {s['boxes']:4} boxes  {s['sector']:10}  http://localhost:5005/#review/fl__sd_{s['url_id']}"
                f"\n         {s['url'][:110]}")
    print(f"\nmost business-like {args.show}:")
    for v, s in rows[:args.show]:
        print(line(v, s))
    print(f"\nleast business-like {args.show}:")
    for v, s in rows[-args.show:]:
        print(line(v, s))
    mid = [r for r in rows if 0.4 <= r[0] <= 0.6]
    print(f"\nundecided (0.4-0.6): {len(mid)}")
    for v, s in mid[:args.show]:
        print(line(v, s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
