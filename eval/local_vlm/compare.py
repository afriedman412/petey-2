"""Page-classifier test: a local model against Sonnet 4.6 box by box, and both against the blueprint.

    PYTHONPATH=. venv/bin/python eval/local_vlm/compare.py local-underdog-iq2-q8vision [form,form,...]
Boxes are keyed by page + rect (same finder, same keys). Class: same class / same family (class_check._family).
Caption: same words, case and punctuation aside, or at least half shared. Group: the box's fellow options are the
same set. Blueprint: class_check.compare's tier-1 contradictions (a captioned box whose class family differs from
the blueprint's type), fewer is closer.
"""
import json, re, sys, collections
from pathlib import Path
from petey.synth import classify
from petey.validate import witness as W
from petey.validate.class_check import _family, compare

BASE = "claude-sonnet-4-6"
model = sys.argv[1]
forms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["dd1155", "614bb5b94bd72daedb5d730b_ia_1form", "osha_301"]
words = lambda s: set(re.findall(r"[a-z0-9]+", (s or "").lower()))
def same_caption(a, b):
    wa, wb = words(a), words(b)
    if not wa and not wb: return True
    return bool(wa and wb) and (wa == wb or len(wa & wb) / max(len(wa | wb), 1) >= 0.5)
def groups(boxes):
    by = collections.defaultdict(set)
    for k, b in boxes.items():
        if b.get("group"): by[(b["page"], str(b["group"]).lower())].add(k)
    return {k: frozenset(by[(b["page"], str(b["group"]).lower())]) for k, b in boxes.items() if b.get("group")}
tot = collections.Counter()
for stem in forms:
    bp = W._load(Path(f"blueprints/{stem}.bpt")); blank = W.resolve_blank(bp); pdf = blank.read_bytes()
    maps = {}
    for m in (BASE, model):
        cp = classify.cache_path(pdf, m)
        maps[m] = json.loads(cp.read_text()) if cp.exists() else None
    if maps[model] is None:
        print(f"{stem}: no {model} result"); continue
    a, b = maps[BASE]["boxes"], maps[model]["boxes"]
    keys = sorted(set(a) & set(b))
    c = collections.Counter(boxes=len(keys), only_sonnet=len(set(a) - set(b)), only_local=len(set(b) - set(a)))
    ga, gb = groups(a), groups(b)
    for k in keys:
        x, y = a[k], b[k]
        c["class"] += x.get("class") == y.get("class")
        c["family"] += _family(x.get("class")) == _family(y.get("class"))
        c["caption"] += same_caption(x.get("label"), y.get("label"))
        c["entity"] += (x.get("entity") or "").lower() == (y.get("entity") or "").lower()
        if k in ga or k in gb:
            c["grouped"] += 1
            c["group_same"] += ga.get(k) == gb.get(k)
    bpc = {m: sum(1 for r in compare(bp, maps[m]) if r["tier"] == 1) for m in (BASE, model)}
    n = max(c["boxes"], 1)
    print(f"{stem}: {c['boxes']} boxes both read (+{c['only_sonnet']} Sonnet only, +{c['only_local']} local only)")
    print(f"   agrees with Sonnet: class {c['class']/n:.0%}, class family {c['family']/n:.0%}, caption {c['caption']/n:.0%}, "
          f"entity {c['entity']/n:.0%}, option groups {c['group_same']}/{c['grouped']}")
    print(f"   contradicts the blueprint's type (tier 1): Sonnet {bpc[BASE]}, local {bpc[model]}")
    tot.update(c); tot["bp_sonnet"] += bpc[BASE]; tot["bp_local"] += bpc[model]
n = max(tot["boxes"], 1)
print(f"\nall: {tot['boxes']} boxes | class {tot['class']/n:.0%}, family {tot['family']/n:.0%}, caption {tot['caption']/n:.0%}, "
      f"entity {tot['entity']/n:.0%}, groups {tot['group_same']}/{tot['grouped']} | blueprint contradictions Sonnet {tot['bp_sonnet']}, local {tot['bp_local']}")
