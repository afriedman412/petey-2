"""Each model's caption per box against the blueprint's (hand-reviewed) field name at that box, scored by the
text-match model: share of matched boxes whose caption describes the name (P >= 0.5)."""
import json, sys
from pathlib import Path
from petey.synth import classify
from petey.synth.boxes import match_rect
from petey.validate import witness as W
from petey.label import text_match as tm
models = sys.argv[1].split(",")
forms = sys.argv[2].split(",") if len(sys.argv) > 2 else ["dd1155", "614bb5b94bd72daedb5d730b_ia_1form", "osha_301"]
for stem in forms:
    bp = W._load(Path(f"blueprints/{stem}.bpt")); pdf = W.resolve_blank(bp).read_bytes()
    out = []
    for m in models:
        cp = classify.cache_path(pdf, m)
        if not cp.exists(): out.append(f"{m}: -"); continue
        boxes = json.loads(cp.read_text())["boxes"]
        by_page = {}
        for k, b in boxes.items(): by_page.setdefault(b["page"], []).append(b)
        pairs = []
        for n, s in bp["fields"].items():
            if not isinstance(s, dict) or s.get("widgets"): continue
            w = s.get("widget") or {}
            b = match_rect(w.get("rect"), by_page.get(w.get("page"), [])) if w.get("rect") else None
            if b and b.get("label"): pairs.append((b["label"], tm.name_words(n)))
        sc = tm.score_pairs(pairs) or []
        out.append(f"{m}: {sum(x >= .5 for x in sc)}/{len(sc)} = {sum(x >= .5 for x in sc) / max(len(sc), 1):.0%}")
    print(f"{stem:36} " + " | ".join(out))
