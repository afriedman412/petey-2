"""The text-match model and Jev on the same held-out pairs (`runs/text_match/test.jsonl`, forms never trained on).

Names: each publisher text or readable path of a test field is a group, its own field name against the names a
swap could involve (`text_match_data.name_pairs`); right when the own name scores highest. Captions: each option
with a trusted caption is a group, its true caption against its siblings' captions and the other lines printed
near its box; right when the true caption scores highest. Both scorers answer the same question for every pair:
does this text describe this field?

Jev (TypeSafe System One, `eval/jev_hand_check.py`) is asked one pair per call, cached under runs/jev/cache by
request hash. It runs on a seeded sample of groups (`--name-groups`, `--caption-groups`); the local model runs on
the same sample and on every group.

    PYTHONPATH=. venv/bin/python eval/text_match_eval.py [--name-groups 300] [--caption-groups 200] [--no-jev]
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import hashlib
import json
import random
from pathlib import Path

from petey.label import text_match as tm
from petey.paths import RUNS

TEST = RUNS / "text_match" / "test.jsonl"
URL = "https://api.typesafe.ai/v1/systemone"
MODEL = "jev-1.13.0"
CACHE = RUNS / "jev" / "cache"
ENV = Path("/Users/user/Documents/code/petey-2/.env")     # the main tree's; the worktree has none

DESCRIBES = {
    "type": "noul",
    "instructions": (
        "`text` is something a PDF form says about one of its boxes: the box's tooltip, a label printed next to "
        "it, or the box's internal name. `field` is a field of the form written out in words; for a checkbox "
        "option it is 'question: option', sometimes followed by '|' and the option's own tooltip. Does `text` "
        "describe `field`?"),
    "criteria": {
        "true": ("The text is about the same item as the field, possibly in other words, abbreviated or "
                 "misspelt (street ~ address, M ~ male, 'Parient' ~ patient), or it is the printed label of that "
                 "option."),
        "false": ("The text is about a different item (a neighbouring box, another row or column, another "
                  "option of the same question), or says nothing about this field."),
    },
}


def groups(kind_prefix: str) -> list[dict]:
    """Name groups `{text, true, others}` keyed by (copy, text, own field); caption groups straight from the file."""
    out, by = [], collections.OrderedDict()
    for line in TEST.open():
        r = json.loads(line)
        if kind_prefix == "caption" and r["kind"] == "caption" and r["wrong"]:
            out.append({"text_options": [r["caption"]] + r["wrong"], "field": r["option"], "form": r["form"]})
        elif kind_prefix == "name" and r["kind"].startswith("name"):
            own = r["name"] if r["label"] == 1 else r["of"]
            g = by.setdefault((r["copy"], r["text"], own), {"text": r["text"], "true": None, "others": [],
                                                              "form": r["form"], "kind": r["kind"]})
            (g.__setitem__("true", r["field"]) if r["label"] == 1 else g["others"].append(r["field"]))
    if kind_prefix == "name":
        out = [g for g in by.values() if g["true"] and g["others"]]
    return out


def jev(pairs: list[tuple[str, str]], workers: int = 8) -> list[float | None]:
    import httpx
    from dotenv import dotenv_values
    key = dotenv_values(ENV).get("TYPESAFE_API_KEY")

    def one(p):
        body = {"model": MODEL, "state": {"text": p[0], "field": p[1]}, "questions": {"describes": DESCRIBES}}
        h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        cp = CACHE / f"{h}.json"
        if cp.exists():
            res = json.loads(cp.read_text())
        else:
            with httpx.Client() as c:
                for attempt in range(4):
                    r = c.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=60)
                    if r.status_code == 429 and attempt < 3:
                        import time
                        time.sleep(float(r.headers.get("retry-after") or 2 ** attempt))
                        continue
                    r.raise_for_status()
                    break
            res = r.json()
            CACHE.mkdir(parents=True, exist_ok=True)
            cp.write_text(json.dumps(res))
        return res.get("answers", {}).get("describes", {}).get("noul"), res.get("usage", {}).get("input_tokens", 0)

    with cf.ThreadPoolExecutor(workers) as ex:
        got = list(ex.map(one, pairs))
    jev.tokens = getattr(jev, "tokens", 0) + sum(t for _, t in got)
    return [s for s, _ in got]


def top1(scores_by_group: list[list[float | None]]) -> tuple[int, int]:
    """Groups where the first (true) option scores strictly highest; a tie or a missing score is wrong."""
    right = sum(1 for s in scores_by_group if None not in s and s[0] > max(s[1:]))
    return right, len(scores_by_group)


def name_pairs_of(g):
    return [(g["text"], g["true"])] + [(g["text"], o) for o in g["others"]]


def caption_pairs_of(g):
    return [(t, g["field"]) for t in g["text_options"]]


def score_groups(gs, pairs_of, scorer) -> list[list[float | None]]:
    flat, spans = [], []
    for g in gs:
        ps = pairs_of(g)
        spans.append((len(flat), len(ps)))
        flat += ps
    s = scorer(flat)
    return [s[a:a + n] for a, n in spans]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--name-groups", type=int, default=300)
    ap.add_argument("--caption-groups", type=int, default=200)
    ap.add_argument("--no-jev", action="store_true")
    ap.add_argument("--show", type=int, default=10, help="disagreements to print per task")
    args = ap.parse_args()
    if not tm.available():
        raise SystemExit(f"no model at {tm.MODEL_DIR}")
    rng = random.Random(11)
    for task, pairs_of, n in (("name", name_pairs_of, args.name_groups),
                              ("caption", caption_pairs_of, args.caption_groups)):
        gs = groups(task)
        local_all = score_groups(gs, pairs_of, tm.score_pairs)
        r, t = top1(local_all)
        chance = sum(1 / len(pairs_of(g)) for g in gs) / max(len(gs), 1)
        print(f"\n{task}: {t} test groups (chance {chance:.0%})")
        print(f"  local model, all groups      {r}/{t} = {r / t:.1%}")
        if task == "name":
            for kind in ("name_publisher", "name_path"):
                sub = [s for g, s in zip(gs, local_all) if g["kind"] == kind]
                r2, t2 = top1(sub)
                print(f"    {kind:26} {r2}/{t2} = {r2 / max(t2, 1):.1%}")
        idx = sorted(rng.sample(range(len(gs)), min(n, len(gs))))
        sample = [gs[i] for i in idx]
        loc = [local_all[i] for i in idx]
        r, t = top1(loc)
        print(f"  local model, sample          {r}/{t} = {r / t:.1%}")
        if args.no_jev:
            continue
        jv = score_groups(sample, pairs_of, jev)
        r, t = top1(jv)
        print(f"  Jev, sample                  {r}/{t} = {r / t:.1%}")
        both = sum(1 for a, b in zip(loc, jv) if None not in b and a[0] > max(a[1:]) and b[0] > max(b[1:]))
        agree = sum(1 for a, b in zip(loc, jv) if None not in b
                    and max(range(len(a)), key=a.__getitem__) == max(range(len(b)), key=b.__getitem__))
        agree_right = sum(1 for a, b in zip(loc, jv) if None not in b
                          and max(range(len(a)), key=a.__getitem__) == max(range(len(b)), key=b.__getitem__) == 0)
        print(f"  both right                   {both}/{t}")
        print(f"  they pick the same option    {agree}/{t}, of which right {agree_right} "
              f"({agree_right / max(agree, 1):.1%}): the gate's precision")
        shown = 0
        for g, a, b in zip(sample, loc, jv):
            if None in b:
                continue
            ia, ib = max(range(len(a)), key=a.__getitem__), max(range(len(b)), key=b.__getitem__)
            if ia != ib and shown < args.show:
                ps = pairs_of(g)
                print(f"    [{g['form']}] {'local' if ia == 0 else 'JEV  ' if ib == 0 else 'neither'} right: "
                      f"text {ps[0][0][:60]!r} | true {ps[0][1][:40]!r} | local {ps[ia][0 if task == 'caption' else 1][:35]!r} "
                      f"| jev {ps[ib][0 if task == 'caption' else 1][:35]!r}")
                shown += 1
    if not args.no_jev:
        print(f"\nJev input tokens this run (new calls only): {getattr(jev, 'tokens', 0)} "
              f"(~${getattr(jev, 'tokens', 0) / 1e6 * 0.042:.4f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
