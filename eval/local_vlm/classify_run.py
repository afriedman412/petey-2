"""Classify the four single-page test forms with one model; time each (runs/local_vlm/times.jsonl)."""
import json, sys, time
from pathlib import Path
from petey.synth.classify import classify_form
from petey.validate import witness as W
FORMS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["dd1155", "614bb5b94bd72daedb5d730b_ia_1form", "osha_301"]
model = sys.argv[1]
for stem in FORMS:
    blank = W.resolve_blank(W._load(Path(f"blueprints/{stem}.bpt")))
    t0 = time.time()
    try:
        cm = classify_form(blank, model=model, form_id=stem)
        n = len((cm or {}).get("boxes") or {})
        err = None
    except Exception as e:
        n, err = None, f"{type(e).__name__}: {e}"[:300]
    rec = {"model": model, "form": stem, "seconds": round(time.time() - t0, 1), "boxes": n, "error": err}
    print(json.dumps(rec), flush=True)
    with open("runs/local_vlm/times.jsonl", "a") as f:
        f.write(json.dumps(rec) + "\n")
