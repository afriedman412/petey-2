"""How stable is the loop's judge? Read the same filled cases several times and see which fields flip.

The name-based reader is the loop's judge, and on I-765 the same blueprint and document once gave 40 and 45
detections (RESULTS 2026-09-29). Andrew: no noise floor; measure what is and is not stable. This reads each case
of a frozen case set `--reads` times with the reader cache bypassed (a salt per read index,
`extract_llm(cache_salt=...)`), scores every read the way validate does, and classifies each field per case:

    stable_right   every read agrees with the ground truth
    stable_wrong   every read disagrees, with the same answer each time
    flipping       the verdict or the answer changes between reads

Across the cases, a field that flips on every case is a property of the field (the hypothesis in the TODO:
fields the blueprint leaves ambiguous); one that flips on a single case is about that case's value. A wrong
answer is traced to the box it came from by value identity (bank values are distinct per box), so a flip names
the pair of fields the reader confuses. Two cheap ambiguity proxies are recorded per field to test the
hypothesis: a numbered sibling (the name with digits removed matches another field) and a description shared
with another field.

Reads are cached under their salt, so rerunning the script replays them for free; change `--salt-prefix` for a
fresh batch. Fields no synthetic box reached (`case_unreached.json`) are `not_generated` and left out.

    PYTHONPATH=. venv/bin/python eval/reader_stability.py --form i765 --case-set 2 --dry-run
    PYTHONPATH=. venv/bin/python eval/reader_stability.py --form i765 --case-set 2 --cases 3 --reads 5
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey import extract_llm  # noqa: E402
from petey.paths import RUNS  # noqa: E402
from petey.validate.correct import field_paths, norm  # noqa: E402
from petey.validate.review import PRICES  # noqa: E402
from petey.validate.score import score  # noqa: E402

IMAGE_FORMS = {"vba21526ez", "ma1", "va760"}   # filled values missing from the text layer
SETS_DIR = RUNS / "_gen_cache" / "sets"


def set_run(form: str, case_set: int) -> Optional[Path]:
    """The latest run of a frozen case set, from its manifest."""
    mp = SETS_DIR / f"{form}_set{case_set}.json"
    if not mp.exists():
        return None
    for name in reversed(json.loads(mp.read_text(encoding="utf-8")).get("runs") or []):
        run = RUNS / name
        if (run / "blueprint.bpt").exists() and (run / "case_001_intact" / "filled_intact.pdf").exists():
            return run
    return None


def _key(v: Any) -> str:
    """One comparable string per answer, so 'Haddad' and ' haddad ' count as the same read."""
    if isinstance(v, str):
        return norm(v) or ""
    if v in (None, False, [], ""):
        return ""
    return json.dumps(v, sort_keys=True, default=str)


def ambiguity_proxies(bpt: dict) -> dict[str, list[str]]:
    """Per field, the cheap signs that the blueprint leaves it ambiguous."""
    fields = bpt.get("fields") or {}
    stems = collections.Counter(re.sub(r"\d+", "#", n) for n in fields)
    descs = collections.Counter((s or {}).get("description") for s in fields.values()
                                if isinstance(s, dict) and (s or {}).get("description"))
    out: dict[str, list[str]] = {}
    for name, spec in fields.items():
        tags = []
        if stems[re.sub(r"\d+", "#", name)] > 1:
            tags.append("numbered_sibling")
        d = (spec or {}).get("description") if isinstance(spec, dict) else None
        if d and descs[d] > 1:
            tags.append("shared_description")
        out[name] = tags
    return out


def source_of(value: Any, own: str, gt: dict, owner_of: dict[str, str]) -> Optional[str]:
    """Which field's ground truth holds this wrong answer: a field name, up to three candidates joined by
    ' | ' (the bank repeats one persona's values across that entity's boxes), 'ambiguous(n)', or None."""
    k = _key(value)
    if not k:
        return None
    hits = {owner_of.get(p, p) for p, v in gt.items() if _key(v) == k}
    hits.discard(own)
    if not hits:
        return None
    return " | ".join(sorted(hits)) if len(hits) <= 3 else f"ambiguous({len(hits)})"


def classify(reads: list[dict]) -> str:
    """reads: [{verdict, key}] for one field on one case."""
    verdicts = {r["verdict"] for r in reads}
    if verdicts == {"agree"}:
        return "stable_right"
    if "agree" not in verdicts and len({r["key"] for r in reads}) == 1:
        return "stable_wrong"
    return "flipping"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", default="i765")
    ap.add_argument("--case-set", type=int, default=2)
    ap.add_argument("--run", type=Path, default=None, help="a run dir instead of the set manifest's latest")
    ap.add_argument("--cases", type=int, default=3)
    ap.add_argument("--reads", type=int, default=5)
    ap.add_argument("--model", default=extract_llm.DEFAULT_MODEL)
    ap.add_argument("--parser", default=None, help="pymupdf | image (default: image on IMAGE_FORMS)")
    ap.add_argument("--salt-prefix", default="stability", help="change for a fresh batch of reads")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the plan and the call count; no API")
    args = ap.parse_args()

    run = args.run or set_run(args.form, args.case_set)
    if run is None:
        print(f"{args.form}: no run for case set {args.case_set} (manifest {SETS_DIR}/{args.form}_set{args.case_set}.json)")
        return 1
    bpt = yaml.safe_load((run / "blueprint.bpt").read_text(encoding="utf-8"))
    cases = sorted(d for d in run.glob("case_*_intact")
                   if (d / "filled_intact.pdf").exists() and (d / "ground_truth.json").exists())[:args.cases]
    parser = args.parser or ("image" if args.form in IMAGE_FORMS else "pymupdf")
    n_fields = len(bpt.get("fields") or {})
    calls = len(cases) * args.reads * math.ceil(n_fields / extract_llm.MAX_FIELDS_PER_CALL)
    print(f"[plan] {args.form} run {run.name}: {len(cases)} cases x {args.reads} reads, {n_fields} fields, "
          f"parser {parser}, model {args.model}; up to {calls} reader calls (cached reads replay free)")
    if args.dry_run:
        return 0
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass

    owner_of = {p: n for n, p in field_paths(bpt).items()}
    proxies = ambiguity_proxies(bpt)
    extract_llm.USAGE.update({"input_tokens": 0, "output_tokens": 0, "calls": 0})

    per_case: dict[str, dict[str, list[dict]]] = {}   # case -> field -> reads
    detections: dict[str, list[int]] = {}             # case -> differ + miss per read
    for case in cases:
        gt = json.loads((case / "ground_truth.json").read_text(encoding="utf-8"))
        up = case / "case_unreached.json"
        unreached = set(json.loads(up.read_text())) if up.exists() else set()
        fields: dict[str, list[dict]] = collections.defaultdict(list)
        detections[case.name] = []
        for r in range(1, args.reads + 1):
            values = extract_llm.extract_llm(bpt, case / "filled_intact.pdf", parser=parser, model=args.model,
                                             cache_salt=f"{args.salt_prefix}-r{r}")
            rep = score(bpt, gt, values, unreached=unreached)
            v = rep["verdicts"]
            detections[case.name].append(v.get("differ", 0) + v.get("extract_miss", 0))
            for p in rep["per_field"]:
                fields[p["field"]].append({
                    "read": r, "verdict": p["verdict"], "key": _key(p["extracted_value"]),
                    "extracted": p["extracted_value"], "gt": p["gt_value"],
                    "source": (source_of(p["extracted_value"], p["field"], gt, owner_of)
                               if p["verdict"] == "differ" else None),
                })
        per_case[case.name] = fields
        print(f"  {case.name}: detections per read {detections[case.name]}")

    # per field: status on each case, then across cases
    rows = []
    for name in bpt.get("fields") or {}:
        statuses, filled, sources = {}, False, collections.Counter()
        for cname, fields in per_case.items():
            reads = fields.get(name) or []
            if not reads or all(x["verdict"] == "not_generated" for x in reads):
                continue
            statuses[cname] = classify(reads)
            filled = filled or any(_key(x["gt"]) for x in reads)
            sources.update(x["source"] for x in reads if x["source"])
        if not statuses:
            continue
        n_flip = sum(1 for s in statuses.values() if s == "flipping")
        across = ("flips_every_case" if n_flip == len(statuses)
                  else "flips_some_cases" if n_flip else
                  "stable_wrong" if "stable_wrong" in statuses.values() else "stable_right")
        rows.append({"field": name, "across": across, "per_case": statuses, "gt_filled": filled,
                     "proxies": proxies.get(name, []), "confused_with": dict(sources.most_common())})

    u = dict(extract_llm.USAGE)
    pin, pout = PRICES.get(args.model, (0, 0))
    cost = u["input_tokens"] / 1e6 * pin + u["output_tokens"] / 1e6 * pout

    print()
    tally = collections.Counter(r["across"] for r in rows)
    filled_tally = collections.Counter(r["across"] for r in rows if r["gt_filled"])
    print(f"fields judged: {len(rows)}  (ground truth filled in some case: {sum(r['gt_filled'] for r in rows)})")
    for k in ("stable_right", "stable_wrong", "flips_some_cases", "flips_every_case"):
        print(f"  {k:<18} {tally[k]:>4}   of which filled {filled_tally[k]:>4}")
    flagged = [r for r in rows if r["proxies"]]
    plain = [r for r in rows if not r["proxies"]]

    def flip_share(rs):
        return f"{sum(r['across'].startswith('flips') for r in rs)}/{len(rs)}"
    print(f"\nhypothesis check: flipping among fields with an ambiguity proxy {flip_share(flagged)}, "
          f"without {flip_share(plain)}")
    flips = [r for r in rows if r["across"].startswith("flips")]
    if flips:
        print("\nflipping fields:")
        for r in sorted(flips, key=lambda r: (r["across"] != "flips_every_case", r["field"])):
            conf = ", ".join(f"{k} x{v}" for k, v in r["confused_with"].items()) or "-"
            print(f"  {r['field']:<44} {r['across']:<17} proxies {','.join(r['proxies']) or '-':<34} "
                  f"confused with: {conf}")
    print(f"\nusage: {u['calls']} calls, {u['input_tokens']} in / {u['output_tokens']} out tokens, ${cost:.2f}")

    out = args.out or RUNS / "reader_stability" / f"{args.form}_set{args.case_set}_{args.model}_{args.salt_prefix}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "form": args.form, "run": run.name, "case_set": args.case_set, "model": args.model, "parser": parser,
        "reads": args.reads, "salt_prefix": args.salt_prefix, "detections_per_read": detections,
        "summary": dict(tally), "summary_filled": dict(filled_tally), "fields": rows,
        "reads_raw": per_case, "usage": u, "cost_usd": round(cost, 4),
    }, indent=1, default=str))
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
