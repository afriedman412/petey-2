#!/usr/bin/env python3
"""blind_run.py <dir-of-fillable-pdfs> [--tag NAME] [--style STYLE]
Seal GT (never printed) -> flatten -> verify -> run FROZEN reader cold -> score.
Refuses to run if the frozen reader's hash changed.

Style tags: optional <dir>/styles.json {"<stem>": "<style>"}; --style sets the default.
GT exclusions (sealed under "excluded", never scored): barcode widgets, hidden/NoView widgets, push buttons,
widgets on neutral-gray shaded cells (--shade-delta, default 25 levels below the page's paper; 0 disables).
Flattening BAKES widget appearances first: anything visible on a real printed form is fair input.
Read-only widgets are KEPT (signatures, computed totals, auto-filled fields are visible and extractable)."""
import sys, os, re, json, hashlib, subprocess, pymupdf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from score import score
ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
READER = f"{REPO}/step2flat/frozen_reader.py"
want = open(f"{REPO}/step2flat/FROZEN_SHA256").read().split()[0]
if hashlib.sha256(open(READER, "rb").read()).hexdigest() != want:
    sys.exit("frozen reader modified; refusing blind run")
arg = lambda k, d: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else d
src = sys.argv[1]; tag = arg("--tag", "blind"); default_style = arg("--style", "untagged")
styles = json.load(open(f"{src}/styles.json")) if os.path.exists(f"{src}/styles.json") else {}
BARCODE = re.compile(r"barcode|pdf417|qr_?code|datamatrix", re.I)

def exclusion(doc, w):
    if BARCODE.search(w.field_name or ""): return "barcode"
    if w.field_type_string == "Button": return "pushbutton"   # print/reset/nav/caption controls
    F = doc.xref_get_key(w.xref, "F")
    if F[0] == "int" and int(F[1]) & (2 | 32): return "hidden"   # annot Hidden / NoView
    return None

SHADE_DELTA = float(arg("--shade-delta", "25"))   # gray levels darker than the page's paper; <=0 disables

def shaded_gt(doc, gt, delta):
    """Indices of GT widgets whose interior is NEUTRAL gray at least `delta` levels darker than that page's paper.
    Coloured tints (T1 blue-green, DS-11 tan, CMS-1500 pink) are entry areas, not shading, so they never count."""
    if delta <= 0: return set()
    import numpy as np
    out, cache = set(), {}
    for i, w in enumerate(gt):
        if w.get("type", "Text") != "Text": continue       # gray-filled checkboxes (e.g. P-5) are controls, not shading
        pg = w["page"]
        if pg not in cache:
            pix = doc[pg].get_pixmap(dpi=72, annots=False)   # printed page only, no field highlights
            a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[..., :3].astype(int)
            g = a.mean(axis=2); hist = np.bincount(g.astype(int).ravel(), minlength=256)
            cache[pg] = (a, g, int(np.argmax(hist[128:])) + 128)
        a, g, paper = cache[pg]
        x0, y0, x1, y1 = [int(round(v)) for v in w["rect"]]
        if x1 - x0 < 6 or y1 - y0 < 6: continue
        rgb = a[y0 + 2:y1 - 2, x0 + 2:x1 - 2].reshape(-1, 3); gray = g[y0 + 2:y1 - 2, x0 + 2:x1 - 2]
        if rgb.size == 0: continue
        med = np.median(rgb, axis=0); neutral = med.max() - med.min() <= 12
        if neutral and np.median(gray) <= paper - delta: out.add(i)
    return out

def drawing_props(doc):
    """Objective drawing tags, computed on the flattened page content."""
    n = faint = 0; boxes = []; raster = False
    for p in doc:
        area = p.rect.width * p.rect.height
        if any((i["bbox"][2]-i["bbox"][0])*(i["bbox"][3]-i["bbox"][1]) > 0.5*area for i in p.get_image_info()): raster = True
        for x in p.get_drawings():
            c = x.get("color")
            if c is not None and x["type"] in ("s", "fs"):
                n += 1; faint += (sum(c)/len(c) if len(c) else 0) > 0.75
            r = x["rect"]
            if 4 <= r.width <= 16 and 4 <= r.height <= 16 and abs(r.width - r.height) < 2: boxes.append(max(r.width, r.height))
    boxes.sort()
    return dict(raster_bg=raster, faint_stroke_share=round(faint/n, 2) if n else None,
                small_box_median_pt=round(boxes[len(boxes)//2], 1) if boxes else None, n_small_boxes=len(boxes))

OUT = arg("--runs", f"{REPO}/runs")
for d in ("sealed", "flat", "out"): os.makedirs(f"{OUT}/{tag}/{d}", exist_ok=True)
rows = []
for fn in sorted(os.listdir(src)):
    if not fn.lower().endswith(".pdf"): continue
    k = os.path.splitext(fn)[0]; style = styles.get(k, default_style)
    doc = pymupdf.open(os.path.join(src, fn))
    gt, excl = [], []
    for p in doc:
        for w in p.widgets():
            rec = dict(page=p.number, rect=list(w.rect), type=w.field_type_string, name=w.field_name, tip=w.field_label)
            why = exclusion(doc, w)
            (excl.append(dict(rec, reason=why)) if why else gt.append(rec))
    shaded = shaded_gt(doc, gt, SHADE_DELTA)                       # measured on the printed page, before baking
    gt, excl = [w for i, w in enumerate(gt) if i not in shaded], excl + [dict(w, reason="shaded") for i, w in enumerate(gt) if i in shaded]
    json.dump(dict(pages=[list(p.rect) for p in doc], widgets=gt, excluded=excl, style=style, shade_delta=SHADE_DELTA),
              open(f"{OUT}/{tag}/sealed/{k}.json", "w"))
    doc.bake(annots=False, widgets=True)       # guideline: anything visible on a real printed form is fair input
    for p in doc:
        for w in list(p.widgets()): p.delete_widget(w)
        for a in list(p.annots()): p.delete_annot(a)
    doc.save(f"{OUT}/{tag}/flat/{k}.pdf", garbage=3)
    props = drawing_props(pymupdf.open(f"{OUT}/{tag}/flat/{k}.pdf"))
    left = sum(len(list(p.widgets())) + len(list(p.annots())) for p in pymupdf.open(f"{OUT}/{tag}/flat/{k}.pdf"))
    if left: rows.append((k, style, "FLATTEN FAILED")); continue
    subprocess.run([sys.executable, READER, f"{OUT}/{tag}/flat/{k}.pdf", "-o", f"{OUT}/{tag}/out/{k}.json"],
                   check=True, stderr=subprocess.DEVNULL)
    if not gt: rows.append((k, style, f"no widgets (truly flat) - predictions only {props}")); continue
    r = score(json.load(open(f"{OUT}/{tag}/out/{k}.json")), json.load(open(f"{OUT}/{tag}/sealed/{k}.json")))
    r["style"] = style; r["n_excluded"] = len(excl); r["drawing"] = props
    rows.append((k, style, r))

print(f"{'form':26}{'style':14}{'pred':>5}{'gt':>5}{'exc':>4}{'P50':>6}{'R50':>6}{'Pm2o':>6}{'Rm2o':>6}{'R30':>6}{'mIoU':>6}")
for k, s, r in rows:
    if isinstance(r, str): print(f"{k:26}{s:14}  {r}"); continue
    print(f"{k:26}{s:14}{r['n_pred']:>5}{r['n_gt']:>5}{r['n_excluded']:>4}{r['P50']:>6.2f}{r['R50']:>6.2f}"
          f"{r['P_m2o']:>6.2f}{r['R_m2o']:>6.2f}{r['R30']:>6.2f}{r['mIoU']:>6.2f}")
by = {}
for k, s, r in rows:
    if isinstance(r, dict): by.setdefault(s, []).append(r)
if len(by) > 1 or any(len(v) > 1 for v in by.values()):
    print("\nby style (micro-avg over GT/pred counts)")
    for s, rs in sorted(by.items()):
        G = sum(r["n_gt"] for r in rs); P = sum(r["n_pred"] for r in rs)
        tp = sum(r["R50"] * r["n_gt"] for r in rs); gm = sum(r["R_m2o"] * r["n_gt"] for r in rs)
        print(f"  {s:14} n={len(rs)}  R50 {tp/G:.2f}  Rm2o {gm/G:.2f}  P50 {sum(r['P50']*r['n_pred'] for r in rs)/P:.2f}")
json.dump({k: r for k, s, r in rows}, open(f"{OUT}/{tag}/scores.json", "w"), indent=1)
