"""How well a triage check finds the real errors on the validated forms (2026-10-14, Andrew: launch is 200+ validated
forms with no generation in the app, so the job is the cheapest validation; the question is what a person can skip).

The forms are judged as first generated: the copies `belongs_to_fixture.before_copy` writes (git at its BASE, earlier
hand renames undone), with the fixture's rows saying which reviewed fields had a wrong name (`is_known`) and which
were accepted. A check flags fields; for each check, and for 'any of them', this gives the known errors it catches
and how many fields a person would look at, counted by field (forms differ too much in size for a per-form
rate), with the catches split by error pattern (number, swap, shift, other).

    jev       Jev's name_fits below a cutoff (calls cached under runs/jev/cache; about 5 cents a few thousand fields)
    checks    the name check's 'belongs to' or 'does not describe' (the fixture's own rows, no calls)
    page      the VLM page check's flags, from its saved records (`petey.validate.page_check`, run on the before
              copies; 2026-10-14: about 7 cents a page with Opus 5); 'page names' counts only the flags about the
              name (wrong_name, not_a_field, continues, other), not type / grouping / option flags

    PYTHONPATH=. venv/bin/python eval/triage_score.py --rows runs/belongs_to/validated_2026-10-14.json --jev
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import sys
from pathlib import Path

import httpx
from dotenv import dotenv_values

sys.path.insert(0, str(Path(__file__).resolve().parent))
from belongs_to_fixture import BEFORE, is_known  # noqa: E402
from jev_hand_check import ask, states  # noqa: E402

CUTS = (0.3, 0.5, 0.7)
NAME_PROBLEMS = ("wrong_name", "not_a_field", "continues", "other")


def page_verdicts(bid: str) -> dict:
    """{name in the before copy: verdict} from the newest page-check record made on the before copy (its
    `blueprint` path), else the newest one filed under the review id (runs before 2026-10-14 were made on the
    library copy, which was the same version), else the verdicts the copy itself carries; {} when there is none."""
    copies = [str(c.resolve()) for c in (BEFORE / bid).glob("*.bpt")]
    best = None
    for rp in (Path("runs/page_check")).glob("*.json"):
        try:
            r = json.loads(rp.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(r, dict) or "fields" not in r:
            continue
        mine = str(Path(r.get("blueprint") or "").resolve()) in copies
        if mine or rp.name.startswith(f"{bid}__"):
            rank = (mine, rp.stat().st_mtime)
            if best is None or rank > best[0]:
                best = (rank, r["fields"])
    if best:
        return best[1]
    from petey.validate.page_check import verdicts       # the judge-eval copies carry theirs in the blueprint
    import yaml
    return verdicts(yaml.safe_load(Path(copies[0]).read_text())) if copies else {}


def jev_scores(bids: list[str], workers: int) -> dict[tuple[str, str], float]:
    """{(form, name in the before copy): name_fits} for every field of each form's before copy."""
    key = dotenv_values(Path(__file__).resolve().parents[1] / ".env").get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY not in .env")
    jobs = []
    for bid in bids:
        copies = list((BEFORE / bid).glob("*.bpt"))
        if not copies:
            print(f"  {bid}: no before copy (run belongs_to_fixture first)", file=sys.stderr)
            continue
        for name, st in states(copies[0]).items():
            jobs.append((bid, name, st, st["field"].get("kind") in ("checkbox", "radiobutton")))
        print(f"  {bid}: {sum(1 for j in jobs if j[0] == bid)} fields", file=sys.stderr)
    out = {}
    with httpx.Client() as client, cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(ask, client, key, st, cb): (bid, name) for bid, name, st, cb in jobs}
        for f in cf.as_completed(futs):
            v = (f.result().get("answers") or {}).get("name_fits", {}).get("noul")
            if v is not None:
                out[futs[f]] = v
    return out


def report(rows: list[dict], flags: dict[str, set], forms: list[str]) -> None:
    """flags: {check: {(form, current name)}}."""
    rows = [r for r in rows if r["bid"] in forms]
    known = {(r["bid"], r["field"]) for r in rows if is_known(r)}
    ok = {(r["bid"], r["field"]) for r in rows if not r["wrong"]}
    flags = dict(flags, any=set().union(*flags.values()))
    print(f"\n{len(rows)} reviewed fields on {len(forms)} forms; {len(known)} known name errors, {len(ok)} accepted")
    print(f"  {'check':18} {'caught':>12} {'fields to look at':>18} {'accepted among them':>20}")
    for k, fl in flags.items():
        fl = fl & ({(r['bid'], r['field']) for r in rows})
        c = len(fl & known)
        print(f"  {k:18} {c:>5}/{len(known):<4} {c / max(1, len(known)):>4.0%} {len(fl):>12} "
              f"({len(fl) / max(1, len(rows)):.0%}) {len(fl & ok):>12}")
    pats = collections.defaultdict(set)
    for r in rows:
        if (r["bid"], r["field"]) in known:
            pats[r.get("pattern") or "flag"].add((r["bid"], r["field"]))
    print(f"\n  caught by error pattern: {'':10} " + " ".join(f"{k:>12}" for k in flags))
    for pat, ks in sorted(pats.items(), key=lambda x: -len(x[1])):
        print(f"  {pat:12} {len(ks):>4} errors{'':10} " + " ".join(f"{len(fl & ks):>12}" for fl in flags.values()))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rows", required=True, help="belongs_to_fixture --save output")
    ap.add_argument("--forms", nargs="*", help="default: the 19 validated in the 2026-10-13/14 round")
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--jev-scores", help="Jev's scores saved by an earlier --save (no calls)")
    ap.add_argument("--page", action="store_true", help="the page check's saved flags")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--save", help="write Jev's scores here")
    args = ap.parse_args()
    rows = json.loads(Path(args.rows).read_text())
    forms = args.forms or list(json.loads(Path("runs/belongs_to/validated_forms_2026-10-14.json").read_text())["forms"])
    to_now = {(r["bid"], r.get("before") or r["field"]): r["field"] for r in rows}
    flags = {"checks": {(r["bid"], r["field"]) for r in rows if r["belongs"] or r["undescribed"]}}
    if args.jev or args.jev_scores:
        sc = ({(b, n): v for b, n, v in json.loads(Path(args.jev_scores).read_text())} if args.jev_scores
              else jev_scores(forms, args.workers))
        if args.save and not args.jev_scores:
            Path(args.save).write_text(json.dumps([[b, n, v] for (b, n), v in sc.items()]))
        for cut in CUTS:
            flags[f"jev<{cut}"] = {(b, to_now[(b, n)]) for (b, n), v in sc.items() if v < cut and (b, n) in to_now}
    if args.page:
        flags["page"], flags["page names"] = set(), set()
        for bid in forms:
            v = page_verdicts(bid)
            if not v:
                print(f"  {bid}: no page check", file=sys.stderr)
            for n, x in v.items():
                if x.get("verdict") == "flag" and (bid, n) in to_now:
                    flags["page"].add((bid, to_now[(bid, n)]))
                    if x.get("problem") in NAME_PROBLEMS:
                        flags["page names"].add((bid, to_now[(bid, n)]))
    report(rows, flags, forms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
