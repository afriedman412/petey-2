"""Score step2flat on TRUE flat copies: forms the corpus holds both flat and fillable.

The fillable twin's AcroForm widgets are exact ground truth for the flat
copy, without self-flattening. Pairs come from the registry (same form,
same page count) gated on layout identity (same page size, page-1 word
Jaccard >= 0.8), as written by `runs/twin_pairs.json`.

Usage: python eval/twins.py [--pairs runs/twin_pairs.json]
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'harness'))
import pymupdf
from score import score
from petey.locate.programmatic import enumerate_fields

PUSHBUTTON = 1 << 16
KIND = {'text': 'text', 'checkbox': 'checkbox'}

def gt_widgets(twin):
    doc = pymupdf.open(twin); G = []
    for pno, pg in enumerate(doc, start=1):
        for w in pg.widgets():
            if (w.field_flags or 0) & PUSHBUTTON: continue
            G.append(dict(page=pno, rect=list(w.rect), type=w.field_type_string))
    return G

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--pairs', default=os.path.join(REPO, 'runs', 'twin_pairs.json'))
    a = ap.parse_args(); pairs = json.load(open(a.pairs))
    agg = [0, 0, 0, 0]
    print(f"{'form':18s}{'flat copy':30s}{'gt':>5s}{'pred':>6s}{'R50':>7s}{'P50':>7s}{'R30':>7s}{'ctr':>6s}")
    for form, flat, twin in pairs:
        G = gt_widgets(twin)
        widgets, _ = enumerate_fields(flat)
        P = dict(fields=[dict(page=w['page'], rect=w['rect'], kind=KIND.get(w['widget_type'], 'text')) for w in widgets])
        r = score(P, dict(widgets=G))
        agg[0] += r['R50'] * r['n_gt']; agg[1] += r['n_gt']; agg[2] += r['P50'] * r['n_pred']; agg[3] += r['n_pred']
        print(f"{form[:18]:18s}{os.path.basename(flat)[:30]:30s}{r['n_gt']:5d}{r['n_pred']:6d}{r['R50']:7.2f}{r['P50']:7.2f}{r['R30']:7.2f}{r['center_in_R']:6.2f}")
    print(f"\nmicro R50 {agg[0]/max(agg[1],1):.2f}  P50 {agg[2]/max(agg[3],1):.2f}  over {len(pairs)} true flat copies, {agg[1]} GT widgets")

if __name__ == '__main__':
    main()
