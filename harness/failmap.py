import json,sys,pymupdf; sys.path.insert(0,'.'); from score import score,iou
from collections import Counter
def inter(a,b): return max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
tag=sys.argv[1]
for f in sys.argv[2:]:
    p=json.load(open(f'out/{f}.{tag}.json')); g=json.load(open(f'sealed/{f}.json'))
    r=score(p,g,True); P=p['fields']; doc=pymupdf.open(f'flat/{f}.pdf')
    cats=Counter(); ex={}
    for u in r['unmatched_gt']:
        R=u['rect']; A=(R[2]-R[0])*(R[3]-R[1])
        cont=[q for q in P if q['page']==u['page'] and inter(q['rect'],R)>=0.8*A]
        if u['best_iou']>=0.3: c='extent(0.3-0.5)'
        elif cont and any((q['rect'][3]-q['rect'][1])>1.8*(R[3]-R[1]) for q in cont): c='merged/split'
        elif u['best_iou']>0: c='overlap<0.3'
        else: c='not_found'
        c=c+'/'+u['type']; cats[c]+=1
        ctx=doc[u['page']].get_textbox(pymupdf.Rect(R[0]-60,R[1]-14,R[2],R[3])).replace('\n',' ')[:50]
        ex.setdefault(c,[]).append((u['page'],[round(x) for x in R],ctx))
    print('==',f,dict(cats))
    for c,v in ex.items():
        if 'not_found' in c or 'overlap' in c:
            for e in v[:6]: print('  ',c,e)
    print('  FP by source',Counter((u['src'],u['kind']) for u in r['unmatched_pred']))
