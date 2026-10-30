"""The adjudicator on cases with a known answer, for any model (2026-10-13: can a local model adjudicate?).

The adjudicator (`petey/validate/adjudicate.py`) sees a crop of the page with one box outlined, the box's tooltip,
the field's current name with its description and type, a proposed name and the reviewer's reason, and answers
current / proposed / unclear. Replaying past adjudications does not work (the reviewer's reasons are not kept, and
Sonnet's verdicts would only measure agreement with Sonnet), so the cases are built from hand review:

- **slip cases**, from fields Andrew looked at and accepted: the true name against a nearby field's name
  (`witness.Names.rivals`, the slips a reviewer proposes), either 'current = true name, proposed = neighbour'
  (answer: current) or 'current = neighbour, proposed = true name' (answer: proposed); the current name brings
  its own description and type, so nothing but the crop and tooltip points at the answer. Every form is half
  'current', half 'proposed' answers, so always answering one way scores 50%.
- **real cases**, from Andrew's hand renames (`x_petey_hand_edit`): current = the wrong name, proposed = his
  correction (answer: proposed).

The reviewer's reason is the same neutral line for every case. Forms run in order; a model under `--gate` on the
first form stops there (Andrew: do not run all three if the first is under 75%). Answers are appended to
runs/local_vlm/adjudicate/<model>.jsonl and a rerun skips cases already answered.

    PYTHONPATH=. venv/bin/python eval/local_vlm/adjudicate_test.py claude-sonnet-4-6
    PETEY_LOCAL_LLM_URL=http://127.0.0.1:8081/v1 PYTHONPATH=. venv/bin/python eval/local_vlm/adjudicate_test.py local-...
"""
from __future__ import annotations

import argparse
import collections
import json
import random
import sys
import time
from pathlib import Path

from petey.paths import RUNS
from petey.synth.local import widget_limits
from petey.validate import adjudicate as A
from petey.validate import witness as W

FORMS = ["lib__dd1155", "je__ca_courts_dv_130", "lib__acord25"]     # DoD, California courts, ACORD (+ real errors)
OUT = RUNS / "local_vlm" / "adjudicate"
REASON = "The reviewer proposes renaming this field."


def cases(bid: str, per_form: int, seed: int = 13) -> list[dict]:
    v = json.loads((RUNS / "hand_review" / f"{bid}.json").read_text())
    bpt = Path(v["blueprint"])
    bp = W._load(bpt)
    blank = W.resolve_blank(bp)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    single = {n for n, s in fields.items() if not s.get("widgets") and (s.get("widget") or {}).get("rect")}
    names = W.Names(fields, W.section_rules(blank))
    rng = random.Random(f"{seed}:{bid}")
    out = []
    # real errors first: Andrew's hand renames
    for n in sorted(single):
        he = fields[n].get("x_petey_hand_edit") or {}
        was = (he.get("from") or {}).get("name")
        if was and was != n:
            spec = {**fields[n], "type": (he.get("from") or {}).get("type") or fields[n].get("type")}
            out.append({"id": f"{bid}:real:{n}", "kind": "real", "box": n, "current": was, "proposed": n,
                        "spec_of": n, "spec": spec, "truth": "proposed"})
    rng.shuffle(out)
    out = out[:per_form // 2]
    pairs = []
    for n, rec in sorted(v.get("verdicts", {}).items()):
        note = rec.get("note") or ""
        if n not in single or rec.get("verdict") != "accept" or note.startswith(("auto:", "bulk")) or rec.get("edit"):
            continue
        if fields[n].get("x_petey_hand_edit"):
            continue
        rivals = sorted(r for r in names.rivals(n) if r in single)
        if rivals:
            pairs.append((n, rng.choice(rivals)))
    rng.shuffle(pairs)
    pairs = pairs[:per_form - len(out)]
    # exactly half the answers 'current', half 'proposed' (the real cases are all 'proposed')
    n_fix = max(0, len(pairs) + len(out)) // 2 - len(out)
    for i, (n, other) in enumerate(pairs):
        if i < n_fix:       # the box carries the neighbour's name, description and type; the true name is proposed
            spec = {**fields[other], "widget": fields[n]["widget"]}
            out.append({"id": f"{bid}:slip_fix:{n}:{other}", "kind": "slip_fix", "box": n, "current": other,
                        "proposed": n, "spec": spec, "truth": "proposed"})
        else:
            out.append({"id": f"{bid}:slip_keep:{n}:{other}", "kind": "slip_keep", "box": n, "current": n,
                        "proposed": other, "spec": fields[n], "truth": "current"})
    for c in out:
        c.update(bid=bid, blank=str(blank), widget=fields[c["box"]]["widget"])
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("model")
    ap.add_argument("--forms", default=",".join(FORMS))
    ap.add_argument("--per-form", type=int, default=40)
    ap.add_argument("--gate", type=float, default=0.75)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.model.replace('/', '_')}.jsonl"
    done = {json.loads(l)["id"]: json.loads(l) for l in path.open()} if path.exists() else {}
    client = A._client(args.model)
    for i, bid in enumerate(args.forms.split(",")):
        cs = cases(bid, args.per_form)
        limits = widget_limits(Path(cs[0]["blank"])) if cs else {}
        for c in cs:
            if c["id"] in done:
                continue
            w = c["widget"]
            png = A.crop_png(Path(c["blank"]), w["page"], w["rect"])
            t0 = time.time()
            try:
                ans, usage = A.ask(client, args.model, png, field=c["current"], proposed=c["proposed"], reason=REASON,
                                   spec=c["spec"], publisher=A.publisher_text({"widget": w}, limits),
                                   page_no=w["page"], tag=f"adjudicate_test/{args.model}")
                err = None
            except Exception as e:
                ans, usage, err = {"verdict": "error"}, {}, f"{type(e).__name__}: {e}"[:300]
            rec = {"id": c["id"], "bid": bid, "kind": c["kind"], "truth": c["truth"], "verdict": ans.get("verdict"),
                   "right": ans.get("verdict") == c["truth"], "box_holds": ans.get("box_holds"),
                   "reason": (ans.get("reason") or "")[:200], "seconds": round(time.time() - t0, 1),
                   "tokens": [usage.get("input_tokens"), usage.get("output_tokens")], "error": err}
            done[c["id"]] = rec
            with path.open("a") as f:
                f.write(json.dumps(rec) + "\n")
        rows = [done[c["id"]] for c in cs if c["id"] in done]
        acc = sum(r["right"] for r in rows) / max(len(rows), 1)
        by = collections.Counter((r["kind"], r["right"]) for r in rows)
        kinds = {k: f"{by[(k, True)]}/{by[(k, True)] + by[(k, False)]}" for k in ("slip_keep", "slip_fix", "real")
                 if by[(k, True)] + by[(k, False)]}
        secs = sorted(r["seconds"] for r in rows)
        print(f"{args.model} {bid}: {acc:.0%} right of {len(rows)} {kinds} | unclear "
              f"{sum(r['verdict'] == 'unclear' for r in rows)} | errors {sum(bool(r['error']) for r in rows)} | "
              f"median {secs[len(secs) // 2] if secs else 0} s per case", flush=True)
        if i == 0 and acc < args.gate:
            print(f"{args.model}: under {args.gate:.0%} on the first form, stopping (the gate)", flush=True)
            return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
