"""`petey.label.caption_choice` against what a person or the publisher decided. No API.

1. Flagged: the option groups Andrew flagged 'captions are wrong' (2026-10-07), truth read from the page.
2. Hand corrections: every option caption a person wrote (`x_petey_hand_edit` in a blueprint, or an unapplied
   edit in runs/hand_review), chosen from the caption it replaced: does the chooser land on the person's caption?
3. Declared: options whose caption the XFA declares, on forms the model never trained on, chosen as if the
   caption were missing: right / wrong / no pick.
4. Sentences: option captions that are a whole tooltip sentence (group apply copied them); how many get a short
   proposal, with a sample.

    PYTHONPATH=. venv/bin/python eval/caption_choice_eval.py [--sample 25]
"""
from __future__ import annotations

import argparse
import collections
import copy
import json
import random
import re
from pathlib import Path

from petey.label import caption_choice as cc
from petey.paths import BLUEPRINTS, RUNS
from petey.validate import witness as W

JE = RUNS / "judge_eval" / "blueprints"
FLAGGED = {   # (blueprint, group): {key: printed caption}, read off the page and the tooltips
    (JE / "ca_courts_dv_130.bpt", "restrained_person_gender"): {"male": "M", "female": "F", "nonbinary": "Nonbinary"},
    (JE / "ca_courts_dv_130.bpt", "insurance_person"): {"1": "in 1", "2": "in 2"},
    (JE / "cbp_form_3461.bpt", "line_a_zone_status"): {"p": "P", "n": "N"},
    (JE / "cbp_form_3461.bpt", "line_c_zone_status"): {"p": "P", "n": "N"},
    (JE / "ca_courts_dv_110.bpt", "order_type"): {"original": "Original Order", "amended": "Amended Order"},
    (JE / "acord_140.bpt", "secondary_heat_boiler_ind"): {"boiler": "BOILER", "solid_fuel": "SOLID FUEL"},
}


def same(a, b) -> bool:
    na, nb = cc._norm(a), cc._norm(b)
    return bool(na) and bool(nb) and (na == nb or na in nb or nb in na)


_CTX: dict = {}


def ctx(bpt: Path):
    if bpt not in _CTX:
        bp = W._load(bpt)
        blank = W.resolve_blank(bp)
        _CTX[bpt] = (bp, cc.page_context(blank), W.publisher_words(blank))
    return _CTX[bpt]


def hand_cases() -> list[tuple[Path, str, str, str, str]]:
    """(blueprint, group, key, caption it replaced, person's caption)."""
    out = []
    for d in (BLUEPRINTS, JE):
        for p in sorted(d.glob("*.bpt")):
            if re.search(r"_(v\d+|run\d+|prev)$", p.stem):
                continue
            bp = W._load(p)
            for g, s in (bp.get("fields") or {}).items():
                he = (s or {}).get("x_petey_hand_edit") if isinstance(s, dict) else None
                if not he or not isinstance(s.get("widgets"), dict):
                    continue
                before = ((he.get("from") or {}).get("options")) or {}
                after = ((he.get("to") or {}).get("options")) or {}
                for k, o in after.items():
                    capt = (o or {}).get("caption") if isinstance(o, dict) else None
                    if capt and k in s["widgets"]:
                        out.append((p, g, k, before.get(k), capt))
    return out


def run_group(bpt: Path, group: str, overrides: dict[str, str | None] | None = None) -> dict[str, dict]:
    bp, (words, lines), tips = ctx(bpt)
    spec = copy.deepcopy(bp["fields"][group])
    for k, c in (overrides or {}).items():                  # the state before the person's edit
        w = spec["widgets"][k]
        w.pop("x_petey_caption_source", None)
        if c:
            w["caption"] = c
        else:
            w.pop("caption", None)
    return cc.choose(group, spec, words, lines, tips)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sample", type=int, default=25)
    args = ap.parse_args()

    print("1. flagged groups")
    right = total = 0
    for (bpt, g), truth in FLAGGED.items():
        if not bpt.exists() or g not in (W._load(bpt).get("fields") or {}):
            print(f"   (missing) {bpt.stem} {g}")
            continue
        res = run_group(bpt, g, {k: (W._load(bpt)["fields"][g]["widgets"][k].get("caption")
                                     if W._load(bpt)["fields"][g]["widgets"][k].get("x_petey_caption_source") != "hand"
                                     else None) for k in truth})
        for k, t in truth.items():
            r = res.get(k) or {}
            ok = same(r.get("best"), t)
            right += ok
            total += 1
            print(f"   {'ok ' if ok else 'NO '} {bpt.stem[:22]:22} {g[:26]:26} {k:10} {str(r.get('current'))[:28]!r:30} -> "
                  f"{r.get('best')!r} (truth {t!r})")
    print(f"   {right}/{total} right")

    print("\n2. hand corrections")
    cases = hand_cases()
    by_group = collections.defaultdict(dict)
    for p, g, k, before, after in cases:
        by_group[(p, g)][k] = (before, after)
    right = wrong = none = 0
    misses = []
    for (p, g), ks in by_group.items():
        res = run_group(p, g, {k: b for k, (b, a) in ks.items()})
        for k, (b, a) in ks.items():
            r = res.get(k) or {}
            if same(r.get("best"), a):
                right += 1
            elif not r.get("best"):
                none += 1
            else:
                wrong += 1
                misses.append((p.stem, g, k, b, a, r.get("best")))
    print(f"   {len(cases)} captions a person wrote: chooser right {right}, wrong {wrong}, no pick {none}")
    for m in misses[:12]:
        print(f"     {m[0][:20]:20} {m[1][:26]:26} {m[2][:14]:14} was {str(m[3])[:22]!r} person {m[4]!r} chooser {m[5]!r}")

    print("\n3. XFA-declared captions on held-out forms, chosen as if missing")
    test_forms = {json.loads(l)["copy"] for l in open(RUNS / "text_match" / "test.jsonl") if '"caption"' in l}
    c = collections.Counter()
    bad = []
    for cp in sorted(test_forms):
        src, stem = cp.split("__", 1)
        p = (BLUEPRINTS if src == "lib" else JE) / f"{stem}.bpt"
        if not p.exists():
            continue
        bp = W._load(p)
        for g, s in (bp.get("fields") or {}).items():
            decl = ((s or {}).get("x_petey_xfa") or {}).get("choices") if isinstance(s, dict) else None
            ws = s.get("widgets") if isinstance(s, dict) else None
            if not decl or not isinstance(ws, dict):
                continue
            ks = [k for k in ws if decl.get(k) and cc._short(decl[k])]
            if not ks:
                continue
            res = run_group(p, g, {k: None for k in ks})
            for k in ks:
                b = (res.get(k) or {}).get("best")
                v = "right" if same(b, decl[k]) else ("no pick" if not b else "wrong")
                c[v] += 1
                if v == "wrong" and len(bad) < 10:
                    bad.append((stem, g, k, decl[k], b))
    n = sum(c.values())
    print(f"   {n} options: right {c['right']} ({c['right'] / max(n, 1):.0%}), wrong {c['wrong']}, no pick {c['no pick']}")
    for x in bad:
        print(f"     {x[0][:20]:20} {x[1][:26]:26} {x[2][:12]:12} declared {x[3]!r} chooser {x[4]!r}")

    print("\n4. sentence captions (whole tooltips)")
    found, proposed, samples = 0, 0, []
    for d in (BLUEPRINTS, JE):
        for p in sorted(d.glob("*.bpt")):
            if re.search(r"_(v\d+|run\d+|prev)$", p.stem):
                continue
            bp = W._load(p)
            groups = [g for g, s in (bp.get("fields") or {}).items() if isinstance(s, dict) and isinstance(s.get("widgets"), dict)
                      and any(len((w.get("caption") or "").split()) > cc._MAX_WORDS and w.get("x_petey_caption_source") == "tooltip"
                              for w in s["widgets"].values())]
            for g in groups:
                res = run_group(p, g)
                for k, r in res.items():
                    if len((r["current"] or "").split()) > cc._MAX_WORDS and not r["trusted"]:
                        found += 1
                        proposed += r["propose"]
                        samples.append((p.stem, k, r["current"], r["best"], r["score"], r["propose"]))
    print(f"   {found} sentence captions; a short caption proposed for {proposed} ({proposed / max(found, 1):.0%})")
    random.seed(5)
    for s in random.sample(samples, min(args.sample, len(samples))):
        print(f"     {'PROPOSE' if s[5] else 'keep   '} {s[0][:16]:16} {s[1][:30]:30} -> {s[3]!r} ({s[4]:.2f})   was {s[2][:55]!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
