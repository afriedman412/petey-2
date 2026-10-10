"""Caption reachability: for every widget in the committed v1.1 blueprints, find the nearest printed caption
(left on the row, above with overlap, or inside) and score it against the committed field name.
Run from the repo root: PYTHONPATH=. python eval/caption_binding.py   (CPU MiniLM; a few minutes)"""
import yaml, pymupdf, os, glob, collections, numpy as np, re, json, sys
import onnxruntime as ort
from petey.label import retrieve
class CpuEmbedder(retrieve.Embedder):
    def __init__(self):
        super().__init__()
        self.session=ort.InferenceSession(str(retrieve.MODEL_DIR/"onnx"/"model.onnx"), providers=["CPUExecutionProvider"])
pdf_by_name={os.path.basename(p):p for p in glob.glob('source_pdfs/**/*.pdf', recursive=True) if os.path.isfile(p)}
emb=CpuEmbedder()
def lines_of(page):
    out=[]
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines",[]):
            t=" ".join(s["text"] for s in l["spans"]).strip()
            if t and re.search(r"[A-Za-z]{2,}", t): out.append((pymupdf.Rect(l["bbox"]), t))
    return out
def caption_for(rect, lines):
    r=pymupdf.Rect(rect); best=None
    for lr,t in lines:
        if 0 <= r.x0 - lr.x1 <= 60 and min(r.y1,lr.y1)-max(r.y0,lr.y0) > 0.4*min(r.height,lr.height): c=('left', r.x0-lr.x1, t)
        elif 0 <= r.y0 - lr.y1 <= 24 and min(r.x1,lr.x1)-max(r.x0,lr.x0) > 0: c=('above', (r.y0-lr.y1)+5, t)
        elif lr in r or (r & lr).get_area() > 0.6*lr.get_area(): c=('inside', 0.5, t)
        else: continue
        if best is None or c[1] < best[1]: best=c
    return best
rows=[]; per_form=collections.defaultdict(lambda:[0,0]); tooltips=0
for bp in sorted(glob.glob('blueprints/*.bpt')):
    b=yaml.safe_load(open(bp)); src=pdf_by_name.get(b.get('source_pdf') or '')
    if not src: continue
    try: doc=pymupdf.open(src)
    except Exception: continue
    cache={}; tips={}
    for pg in doc:
        for w in pg.widgets():
            if w.field_label: tips[w.field_name]=1
    for name,f in (b.get('fields') or {}).items():
        w=f.get('widget')
        if not w: continue
        pg=w['page']
        if pg not in cache: cache[pg]=lines_of(doc[pg-1])
        c=caption_for(w['rect'], cache[pg]); per_form[bp][0]+=1
        if w.get('path') in tips: tooltips+=1
        if c: per_form[bp][1]+=1; rows.append((os.path.basename(bp), name, c[0], c[2][:60], name.replace('_',' ')))
print(f"scanned {len(per_form)} blueprints, {len(rows)} captions; embedding...", flush=True)
caps=[r[3] for r in rows]; names=[r[4] for r in rows]
def enc(xs, bs=256):
    out=[]
    for i in range(0, len(xs), bs):
        out.append(np.asarray(emb.encode(xs[i:i+bs])))
        if (i//bs) % 10 == 0: print(f"  embedded {min(i+bs,len(xs))}/{len(xs)}", flush=True)
    return np.concatenate(out)
E1=enc(caps); E2=enc(names)
E1/=np.linalg.norm(E1,axis=1,keepdims=True); E2/=np.linalg.norm(E2,axis=1,keepdims=True); cos=(E1*E2).sum(1)
tot=sum(v[0] for v in per_form.values()); cov=sum(v[1] for v in per_form.values())
print(f"widgets: {tot} across {len(per_form)} blueprints | caption within geometric reach: {cov} ({cov/tot:.0%}) | widgets with a /TU tooltip: {tooltips} ({tooltips/tot:.0%})")
print(f"  caption side: {dict(collections.Counter(r[2] for r in rows))}")
print(f"caption vs committed name, MiniLM cosine: median {np.median(cos):.2f} | >=0.85: {(cos>=0.85).mean():.0%} | >=0.60: {(cos>=0.60).mean():.0%} | <0.30: {(cos<0.30).mean():.0%}")
pf=sorted(((v[1]/v[0], os.path.basename(k), v[0]) for k,v in per_form.items() if v[0]>=15))
print(f"\nper-form caption coverage: worst {[(f'{a:.0%}',n) for a,n,_ in pf[:5]]}\n                           best  {[(f'{a:.0%}',n) for a,n,_ in pf[-5:]]}")
idx=np.argsort(-cos)
print("\nexamples (cosine, side, caption -> committed name):")
for i in list(idx[:4])+list(idx[len(idx)//2:len(idx)//2+4])+list(idx[-4:]):
    print(f"  {cos[i]:.2f} {rows[i][2]:6s} {rows[i][3][:44]!r:46s} -> {rows[i][1]}")
json.dump(dict(total=tot, covered=cov, tooltips=tooltips, rows=[(r[0],r[1],r[2],r[3],float(c)) for r,c in zip(rows,cos)]), open('runs/caption_binding.json','w'))
