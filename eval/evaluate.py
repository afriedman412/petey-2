"""Evaluate on fillable PDFs: seal widget GT -> flatten -> frozen reader -> pipeline -> score both.
Usage: python eval/evaluate.py <dir-of-fillable-pdfs> --tag NAME"""
import sys, os, json, subprocess, glob
HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO); sys.path.insert(0, os.path.join(REPO, 'harness'))
from score import score
from step2flat import pipeline
src = sys.argv[1]; tag = sys.argv[sys.argv.index('--tag') + 1] if '--tag' in sys.argv else 'eval'
subprocess.run([sys.executable, os.path.join(REPO, 'harness', 'blind_run.py'), src, '--tag', tag], check=True)
run = os.path.join(REPO, 'runs', tag); agg = {}
print(f"\n{'form':28}{'gt':>5}{'frozen R/P':>14}{'pipeline R/P':>15}")
for s in sorted(glob.glob(f'{run}/sealed/*.json')):
    k = os.path.basename(s)[:-5]; g = json.load(open(s))
    if not g['widgets']: continue
    kept, _ = pipeline.run(f'{run}/flat/{k}.pdf', reader_json=f'{run}/out/{k}.json')
    json.dump(dict(fields=[dict(page=r['page'], rect=r['rect'], kind=r['kind'], source=r['src'], conf=r['conf']) for r in kept]), open(f'{run}/out/{k}.pipeline.json', 'w'))
    res = {'frozen': score(json.load(open(f'{run}/out/{k}.json')), g),
           'pipeline': score(dict(fields=[dict(page=r['page'], rect=r['rect'], kind=r['kind'], source=r['src'], caption='') for r in kept]), g)}
    for n, r in res.items():
        t = agg.setdefault(n, [0, 0, 0, 0]); t[0] += r['R50'] * r['n_gt']; t[1] += r['n_gt']; t[2] += r['P50'] * r['n_pred']; t[3] += r['n_pred']
    a, b = res['frozen'], res['pipeline']; print(f"{k[:28]:28}{a['n_gt']:>5}{a['R50']:>8.2f}/{a['P50']:.2f}{b['R50']:>9.2f}/{b['P50']:.2f}")
for n, t in agg.items(): print(f"micro {n:9} R50 {t[0]/t[1]:.2f}  P50 {t[2]/max(t[3],1):.2f}")
