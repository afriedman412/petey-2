"""Lattice v2: (1) contrast cells incl. white-on-tint, (2) closure only from long rules and never through text,
(3) character-box grouping, (4) writable-size limits."""
import pymupdf,numpy as np,cv2
Z=4
def segments(page):
    H=[];V=[];tint=[];whites=[]
    D=page.get_drawings()
    for x in D:
        f=x.get('fill'); r=x['rect']
        if f is not None and len(f)>=3 and not all(c>0.97 for c in f) and r.width*r.height>2000: tint.append(r)
    for x in D:
        stroked=x.get('color') is not None; f=x.get('fill')
        filled=f is not None and len(f)>=3 and not all(c>0.97 for c in f)
        white=f is not None and len(f)>=3 and all(c>0.97 for c in f)
        for it in x['items']:
            if it[0]=='l':
                a,b=it[1],it[2]
                if abs(a.y-b.y)<0.8 and abs(a.x-b.x)>3: H.append((min(a.x,b.x),max(a.x,b.x),(a.y+b.y)/2))
                elif abs(a.x-b.x)<0.8 and abs(a.y-b.y)>3: V.append(((a.x+b.x)/2,min(a.y,b.y),max(a.y,b.y)))
            elif it[0]=='re':
                r=pymupdf.Rect(it[1])
                if r.height<1.5 and r.width>3: H.append((r.x0,r.x1,(r.y0+r.y1)/2)); continue
                if r.width<1.5 and r.height>3: V.append(((r.x0+r.x1)/2,r.y0,r.y1)); continue
                c=pymupdf.Point((r.x0+r.x1)/2,(r.y0+r.y1)/2)
                on_tint=white and any(t.contains(c) and t.get_area()>r.get_area()*1.5 for t in tint)   # (1) white box cut out of a tinted panel
                if (stroked or filled or on_tint) and r.width>3 and r.height>3:
                    H+=[(r.x0,r.x1,r.y0),(r.x0,r.x1,r.y1)]; V+=[(r.x0,r.y0,r.y1),(r.x1,r.y0,r.y1)]
    return H,V
def crosses_text(line,words,horiz):
    for w in words:
        if horiz:
            x0,x1,y=line
            if w.y0+0.5<y<w.y1-0.5 and w.x1>x0 and w.x0<x1: return True
        else:
            x,y0,y1=line
            if w.x0+0.5<x<w.x1-0.5 and w.y1>y0 and w.y0<y1: return True
    return False
def virtual(H,V,words,tol=1.5,minrun=3,minlen=30):
    add_v=[];add_h=[]
    LH=[h for h in H if h[1]-h[0]>=minlen]; LV=[v for v in V if v[2]-v[1]>=minlen]   # (2) long rules only
    for side in (0,1):
        ends=sorted((h[side],h[2]) for h in LH); i=0
        while i<len(ends):
            j=i
            while j+1<len(ends) and ends[j+1][0]-ends[i][0]<=tol: j+=1
            grp=ends[i:j+1]
            if len(grp)>=minrun:
                x=float(np.median([g[0] for g in grp])); ys=sorted(g[1] for g in grp); run=[ys[0]]
                for y in ys[1:]+[1e9]:
                    if y-run[-1]<=60: run.append(y); continue
                    if len(run)>=minrun:
                        ln=(x,run[0],run[-1])
                        if not crosses_text(ln,words,False): add_v.append(ln)        # (2) never through printed text
                    run=[y]
            i=j+1
    for side in (1,2):
        ends=sorted((v[side],v[0]) for v in LV); i=0
        while i<len(ends):
            j=i
            while j+1<len(ends) and ends[j+1][0]-ends[i][0]<=tol: j+=1
            grp=ends[i:j+1]
            if len(grp)>=minrun:
                y=float(np.median([g[0] for g in grp])); xs=sorted(g[1] for g in grp); ln=(xs[0],xs[-1],y)
                if xs[-1]-xs[0]>5 and not crosses_text(ln,words,True): add_h.append(ln)
            i=j+1
    return add_h,add_v
def group_charboxes(cells,maxw=25,gap=3.5,minrun=3):
    cells=sorted(cells,key=lambda c:(round(c.y0),c.x0)); used=set(); out=[]
    for i,c in enumerate(cells):
        if i in used: continue
        if c.width>maxw: out.append(c); continue
        run=[i]; last=c
        for j in range(i+1,len(cells)):
            d=cells[j]
            if j in used or abs(d.y0-c.y0)>1.5 or abs(d.y1-c.y1)>1.5: continue
            if abs(d.width-c.width)<=2.5 and 0<=d.x0-last.x1<=gap: run.append(j); last=d
        if len(run)>=minrun:
            used.update(run); r=pymupdf.Rect(cells[run[0]]);
            for j in run[1:]: r|=cells[j]
            out.append(r)
        else: out.append(c)
    return out
def cells(page):
    Wd,Hd=int(page.rect.width*Z)+2,int(page.rect.height*Z)+2
    words=[pymupdf.Rect(w[:4]) for w in page.get_text('words')]
    H,V=segments(page); ah,av=virtual(H,V,words); H=H+ah; V=V+av
    m=np.zeros((Hd,Wd),np.uint8)
    for x0,x1,y in H: cv2.line(m,(int(x0*Z),int(y*Z)),(int(x1*Z),int(y*Z)),255,2)
    for x,y0,y1 in V: cv2.line(m,(int(x*Z),int(y0*Z)),(int(x*Z),int(y1*Z)),255,2)
    m=cv2.dilate(m,np.ones((3,3),np.uint8))
    n,lab,st,_=cv2.connectedComponentsWithStats((m==0).astype(np.uint8),connectivity=4); out=[]
    for i in range(1,n):
        x,y,w,h,a=st[i]
        if x<=1 or y<=1 or x+w>=Wd-1 or y+h>=Hd-1 or a<0.8*w*h: continue
        r=pymupdf.Rect(x/Z,y/Z,(x+w)/Z,(y+h)/Z)
        sq=abs(r.width-r.height)<3 and 5<=r.width<=16
        if not sq and (r.height<6 or r.width<6 or r.height>40): continue               # (4) writable size
        out.append(r)
    return group_charboxes(out)                                                        # (3)

def refine(cell,words,t):
    """Cell -> entry area using label position (label along the top -> field below it; label at left -> field to its right)."""
    ws=[w for w in words if pymupdf.Rect(w[:4]).intersects(cell) and (pymupdf.Rect(w[:4])&cell).get_area()>=0.5*pymupdf.Rect(w[:4]).get_area()]
    if not ws or t in('CheckBox','RadioButton'): return cell,'empty' if not ws else 'box'
    lb=pymupdf.Rect(ws[0][:4])
    for w in ws[1:]: lb|=pymupdf.Rect(w[:4])
    top_space=cell.y1-lb.y1; right_space=cell.x1-lb.x1
    if lb.y0-cell.y0<cell.height*0.4 and top_space>=6: return pymupdf.Rect(cell.x0,lb.y1,cell.x1,cell.y1),'label_top'
    if right_space>=12: return pymupdf.Rect(lb.x1+1,cell.y0,cell.x1,cell.y1),'label_left'
    left_space=lb.x0-cell.x0
    if left_space>=12: return pymupdf.Rect(cell.x0,cell.y0,lb.x0-1,cell.y1),'suffix_right'   # ".00", "%", units printed at the right end
    return cell,'label_fills'

def lattice_fields(doc):
    """All lattice-derived candidate fields for a (flat) document."""
    P=[]
    for pg in range(len(doc)):
        words=doc[pg].get_text('words')
        for c in cells(doc[pg]):
            sq=c.width<=16 and c.height<=16 and abs(c.width-c.height)<3
            fld,how=refine(c,words,'CheckBox' if sq else 'Text')
            if how=='label_fills': continue          # a cell that is all label is not an entry area
            P.append(dict(page=pg,rect=list(fld),kind='checkbox' if sq else 'text',source='lattice:'+how,caption=''))
    return P
