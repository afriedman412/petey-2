"""Flat form -> candidate fields with confidence. Ground-truth free.
Usage: python -m step2flat.pipeline form.pdf -o fields.json [--keep-all]"""
import argparse, json, os, subprocess, sys, tempfile
import pymupdf
from . import lattice, features, confidence

READER = os.path.join(os.path.dirname(__file__), 'frozen_reader.py')

def flatten(src, dst):
    """Print-equivalent flattening: bake widget appearances into the page, then strip widgets/annots."""
    doc = pymupdf.open(src)
    if any(True for p in doc for _ in p.widgets()) or any(True for p in doc for _ in p.annots()):
        doc.bake(annots=False, widgets=True)
        for p in doc:
            for w in list(p.widgets()): p.delete_widget(w)
            for a in list(p.annots()): p.delete_annot(a)
    doc.save(dst, garbage=3)

def run(pdf, reader_json=None):
    with tempfile.TemporaryDirectory() as td:
        flat = os.path.join(td, 'flat.pdf'); flatten(pdf, flat)
        if reader_json is None:
            reader_json = os.path.join(td, 'reader.json')
            subprocess.run([sys.executable, READER, flat, '-o', reader_json], check=True, stderr=subprocess.DEVNULL)
        F = json.load(open(reader_json))['fields']
        doc = pymupdf.open(flat)
        L = lattice.lattice_fields(doc)
        P = [dict(p, reader='lat') for p in L] + [dict(p, reader='fz') for p in F]
        rows = features.compute(doc, P)
    kept, scored = confidence.resolve(rows)
    return kept, scored

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('pdf'); ap.add_argument('-o', '--out'); ap.add_argument('--reader-json')
    ap.add_argument('--keep-all', action='store_true', help='also emit sub-threshold candidates (for the validation loop)')
    a = ap.parse_args()
    kept, scored = run(a.pdf, a.reader_json)
    out = dict(fields=[dict(page=r['page'], rect=r['rect'], kind=r['kind'], source=r['src'], conf=round(r['conf'], 3), why=r['why']) for r in kept])
    if a.keep_all:
        kid = {id(r) for r in kept}
        out['candidates'] = [dict(page=r['page'], rect=r['rect'], kind=r['kind'], source=r['src'], conf=round(r['conf'], 3), why=r['why']) for r in scored if id(r) not in kid]
    json.dump(out, open(a.out, 'w') if a.out else sys.stdout, indent=1)

if __name__ == '__main__': main()
