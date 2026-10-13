"""Each model's option groups against the blueprint's (Andrew's groupings): per blueprint group, whether the model
put exactly its boxes together; and pairwise, of box pairs the blueprint groups together, how many the model does
(recall), and of pairs the model groups, how many the blueprint does (precision)."""
import json, sys, itertools, collections
from pathlib import Path
from petey.synth import classify
from petey.synth.boxes import match_rect
from petey.validate import witness as W
models = sys.argv[1].split(",")
forms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["dd1155", "614bb5b94bd72daedb5d730b_ia_1form", "osha_301"]
for stem in forms:
    bp = W._load(Path(f"blueprints/{stem}.bpt")); pdf = W.resolve_blank(bp).read_bytes()
    print(stem)
    for m in models:
        boxes = json.loads(classify.cache_path(pdf, m).read_text())["boxes"]
        by_page = {}
        for k, b in boxes.items(): by_page.setdefault(b["page"], []).append({**b, "key": k})
        grp = {k: (b["page"], str(b["group"]).lower()) for k, b in boxes.items() if b.get("group")}
        bp_groups, exact = [], 0
        for n, s in bp["fields"].items():
            ws = (s or {}).get("widgets") if isinstance(s, dict) else None
            if not isinstance(ws, dict) or len(ws) < 2: continue
            keys = [match_rect(w.get("rect"), by_page.get(w.get("page"), [])) for w in ws.values()]
            keys = [x["key"] for x in keys if x]
            bp_groups.append(set(keys))
            g = {grp.get(k) for k in keys}
            members = {k for k, v in grp.items() if v in g} if len(g) == 1 and None not in g else None
            exact += members == set(keys)
        bp_pairs = {frozenset(p) for G in bp_groups for p in itertools.combinations(sorted(G), 2)}
        by = collections.defaultdict(set)
        for k, v in grp.items(): by[v].add(k)
        m_pairs = {frozenset(p) for G in by.values() for p in itertools.combinations(sorted(G), 2)}
        rec = len(bp_pairs & m_pairs) / max(len(bp_pairs), 1); prec = len(bp_pairs & m_pairs) / max(len(m_pairs), 1)
        print(f"   {m:38} groups exactly right {exact}/{len(bp_groups)} | pairs: recall {rec:.0%}, precision {prec:.0%} ({len(m_pairs)} pairs)")
