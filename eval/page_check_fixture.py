"""Page check against hand review: how many of the person's flags does the vision first pass find, and how many of
their accepts does it flag?

Every record in `runs/hand_review/` is scored on the blueprint version it was written against (its sha; the
version is taken from git when the file has changed since, e.g. by the 2026-10-05 group apply). Only the pages
holding reviewed fields are sent. Truth is the person's verdict, overridden by `eval/page_check_known.json` where a
record accepts a field known to be wrong (ACORD 25's slid producer / insured blocks). The page check's flags on
fields the person did not review are counted, not scored.

    PYTHONPATH=. venv/bin/python eval/page_check_fixture.py [--only lib__5021,je__rdt120] [--model claude-opus-5] [--dry]

Writes `runs/page_check/fixture_<model>.json` (per-field rows, with a copy of the verdicts scored).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import subprocess
from pathlib import Path

import yaml

from petey.paths import RUNS
from petey.validate import page_check

ROOT = Path(__file__).resolve().parents[1]
KNOWN = ROOT / "eval" / "page_check_known.json"
REVIEWED = RUNS / "page_check" / "reviewed"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:12]


def reviewed_version(bid: str, rec: dict) -> Path | None:
    """The blueprint file as the person saw it: the current file when its sha matches, else the git revision that
    does, written to runs/page_check/reviewed/<id>/<stem>.bpt (same stem, so the blank resolves the same way)."""
    p, want = Path(rec["blueprint"]), rec["blueprint_sha"]
    if p.exists() and _sha(p.read_bytes()) == want:
        return p
    try:
        rel = p.resolve().relative_to(ROOT)
    except ValueError:
        return None
    revs = subprocess.run(["git", "log", "--format=%h", "--", str(rel)], cwd=ROOT, capture_output=True,
                          text=True).stdout.split()
    for r in revs:
        b = subprocess.run(["git", "show", f"{r}:{rel}"], cwd=ROOT, capture_output=True).stdout
        if _sha(b) == want:
            out = REVIEWED / bid / p.name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(b)
            return out
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--only", default=None, help="comma-separated hand-review ids")
    ap.add_argument("--model", default=page_check.MODEL)
    ap.add_argument("--dry", action="store_true", help="pages and field counts only, no model calls")
    args = ap.parse_args()
    known = json.loads(KNOWN.read_text())
    only = set(args.only.split(",")) if args.only else None

    rows, per_form, cost, calls = [], [], 0.0, 0
    for vp in sorted((RUNS / "hand_review").glob("*.json")):
        bid = vp.stem
        if only and bid not in only:
            continue
        rec = json.loads(vp.read_text())
        verdicts = {n: v for n, v in (rec.get("verdicts") or {}).items() if v.get("verdict") in ("accept", "flag")}
        if not verdicts:
            continue
        bpt = reviewed_version(bid, rec)
        if bpt is None:
            print(f"{bid}: reviewed version {rec['blueprint_sha']} not found, skipped")
            continue
        bp = yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}
        pages = {b["page"] for r in page_check.numbered(bp) if r["name"] in verdicts for b in r["boxes"]}
        if not pages:
            continue
        print(f"{bid}  ({len(verdicts)} verdicts, pages {sorted(pages)}{'' if bpt == Path(rec['blueprint']) else ', from git'})")
        res = page_check.check(bpt, model=args.model, pages=pages, dry=args.dry, log=lambda s: print(s))
        if args.dry:
            continue
        cost += res["cost_usd"]
        calls += res["usage"].get("calls", 0)
        fixes = (known.get(bid) or {}).get(rec["blueprint_sha"]) or {}
        c = collections.Counter()
        for name, v in verdicts.items():
            truth = "flag" if (v["verdict"] == "flag" or v.get("edit") or name in fixes) else "accept"   # corrected = wrong
            a = res["fields"].get(name) or {}
            got = a.get("verdict") or "none"
            c[(truth, got)] += 1
            rows.append({"id": bid, "field": name, "truth": truth, "person": v["verdict"],
                         "note": v.get("note") or "", "known": fixes.get(name), "bulk": "bulk" in (v.get("note") or ""),
                         "agent": got, **{k: a.get(k) for k in ("problem", "box_holds", "proposed_name",
                                                                  "proposed_type", "reason", "page")}})
        extra = sum(1 for n, a in res["fields"].items() if n not in verdicts and a.get("verdict") == "flag")
        per_form.append({"id": bid, "verdicts": len(verdicts), "truth_flags": c[("flag", "flag")] + c[("flag", "accept")]
                         + c[("flag", "none")], "caught": c[("flag", "flag")], "missed": c[("flag", "accept")] + c[("flag", "none")],
                         "false_flags": c[("accept", "flag")], "unanswered": c[("flag", "none")] + c[("accept", "none")],
                         "unreviewed_flagged": extra, "cost": res["cost_usd"]})
    if args.dry:
        return 0

    print(f"\n{'id':34} {'verd':>5} {'flags':>5} {'caught':>6} {'missed':>6} {'false':>5} {'unrev':>5} {'cost':>6}")
    for f in per_form:
        print(f"{f['id']:34} {f['verdicts']:>5} {f['truth_flags']:>5} {f['caught']:>6} {f['missed']:>6} "
              f"{f['false_flags']:>5} {f['unreviewed_flagged']:>5} {f['cost']:>6.2f}")
    t = collections.Counter()
    for f in per_form:
        t.update({k: f[k] for k in ("verdicts", "truth_flags", "caught", "missed", "false_flags", "unanswered",
                                    "unreviewed_flagged")})
    acc = t["verdicts"] - t["truth_flags"]
    print(f"{'total':34} {t['verdicts']:>5} {t['truth_flags']:>5} {t['caught']:>6} {t['missed']:>6} "
          f"{t['false_flags']:>5} {t['unreviewed_flagged']:>5} {cost:>6.2f}")
    print(f"\nfound {t['caught']}/{t['truth_flags']} flags; flagged {t['false_flags']}/{acc} accepts; "
          f"{t['unanswered']} unanswered; {calls} calls ${cost:.2f}")

    print("\nMISSED (person flagged / known wrong, page check accepted):")
    for r in rows:
        if r["truth"] == "flag" and r["agent"] != "flag":
            print(f"  {r['id']:28} {r['field']:42} person: {(r['note'] or r['known'] or '')[:60]!r}\n"
                  f"  {'':28} {'':42} agent: {r.get('box_holds')!r} - {(r.get('reason') or '')[:110]}")
    print("\nFLAGGED ACCEPTS (read these: some may be errors the person missed):")
    for r in rows:
        if r["truth"] == "accept" and r["agent"] == "flag":
            prop = " ".join(x for x in (r.get("proposed_name"), r.get("proposed_type")) if x)
            print(f"  {r['id']:28} {r['field']:42} {r['problem']:12} {prop}\n"
                  f"  {'':28} {'':42} {(r.get('reason') or '')[:130]}")

    out = RUNS / "page_check" / f"fixture_{args.model}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"model": args.model, "totals": dict(t), "cost_usd": round(cost, 4),
                               "forms": per_form, "rows": rows}, indent=1, ensure_ascii=False))
    print(f"\n-> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
