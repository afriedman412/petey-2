"""Ground-truth-free per-field features. Only structural signals from the page; no widget metadata."""
import math, re
from collections import Counter
from itertools import groupby
import pymupdf
from .geometry import iou

LINE_CUE = re.compile(r'[^\w\s]?[_.\u2026\u00b7\-]{3,}')   # typed underscores / dot leaders are line cues, not text;
# one leading sign allowed: `$___________` on B106I / B410 counted as text and sank 56 amount cells (2026-10-01)

# A checkbox square drawn as a text glyph: ZapfDingbats '\u25a0' (LA 7006), Wingdings2 0xF0A3 (TX RRC R-32), Wingdings
# 0xF071 / 0xF06F (B410, KS DO-41), or a box character. Not text for the features, and a candidate in its own right
# (lattice.lattice_fields): the raster reader erases recognised text before it looks for boxes, so these left no
# candidate; where the lattice had one, the glyph made it text_filled and header and it sank to 0.45 (2026-10-01).
GLYPH_CHARS = set('\u25a0\u25a1\u2610\u2611\u2612\u2751\u2752\u25a2\u25fb\u25fc\u25aa\u25ab')

def is_glyph(t):
    return len(t) == 1 and (t in GLYPH_CHARS or 0xE000 <= ord(t) <= 0xF8FF)

def glyph_rects(page):
    """Squares for the glyph checkboxes on a page: the character's advance width, centred on its bbox (the bbox is
    the font's line height, not the drawn square: with the full bbox DO-41's 7 pt radios sat in boxes over 3x their
    area)."""
    out = []
    for b in page.get_text('rawdict').get('blocks', []):
        for ln in b.get('lines', []):
            for sp in ln.get('spans', []):
                for c in sp.get('chars', []):
                    if not is_glyph(c['c']): continue
                    r = pymupdf.Rect(c['bbox'])
                    if not (4 <= r.width <= 20 and 4 <= r.height <= 20): continue
                    side = r.width; cy = (r.y0 + r.y1) / 2
                    out.append(pymupdf.Rect(r.x0, cy - side / 2, r.x0 + side, cy + side / 2))
    return out

def _page_info(pa):
    W = [(pymupdf.Rect(w[:4]), w[4]) for w in pa.get_text('words') if not LINE_CUE.fullmatch(w[4]) and not is_glyph(w[4])]
    fills = []
    for x in pa.get_drawings():
        f = x.get('fill')
        if f is None or len(f) < 3 or all(c > 0.97 for c in f): continue
        if x['rect'].width * x['rect'].height < 20: continue
        fills.append((x['rect'], f[:3]))
    bold = set()
    for b in pa.get_text('dict')['blocks']:
        for l in b.get('lines', []):
            for sp in l['spans']:
                if 'Bold' in sp['font'] or sp['size'] >= 11: bold.add(tuple(round(v) for v in sp['bbox']))
    # zebra striping: neutral-gray fills sharing a horizontal span, alternating with equal-height gaps (>=3 in a run)
    gr = sorted([(r, f) for r, f in fills if max(f) - min(f) <= 0.05 and sum(f) / 3 < 0.95],
                key=lambda z: (round(z[0].x0 / 3), round(z[0].x1 / 3), z[0].y0))
    zebra = set()
    for _, grp in groupby(gr, key=lambda z: (round(z[0].x0 / 3), round(z[0].x1 / 3))):
        g = [z[0] for z in grp]; run = [g[0]] if g else []
        for a, b in zip(g, g[1:]):
            gap = b.y0 - a.y1; hh = (a.height + b.height) / 2
            if 0.5 * hh <= gap <= 1.6 * hh and abs(a.height - b.height) <= 0.25 * hh: run.append(b)
            else:
                if len(run) >= 3: zebra.update(tuple(round(v, 1) for v in r) for r in run)
                run = [b]
        if len(run) >= 3: zebra.update(tuple(round(v, 1) for v in r) for r in run)
    return W, fills, bold, pa.rect, zebra

def compute(doc, P):
    """P: candidate fields, each with page, rect, kind, source, reader ('lat'|'fz'). Returns rows with src + features."""
    pages = {}
    info = lambda pg: pages.setdefault(pg, _page_info(doc[pg]))
    hc = Counter(round(p['rect'][3] - p['rect'][1]) for p in P); modes = [h for h, _ in hc.most_common(3)] or [0]
    rows = []
    for p in P:
        R = pymupdf.Rect(p['rect']); W, fills, bold, pr, zebra = info(p['page']); w, h = max(R.width, .1), max(R.height, .1)
        inside = [t for r, t in W if R.contains(pymupdf.Point((r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2))]
        tcov = sum((r & R).get_area() for r, t in W if r.intersects(R)) / (w * h)
        ctr = pymupdf.Point((R.x0 + R.x1) / 2, (R.y0 + R.y1) / 2)
        flr = [(r, f) for r, f in fills if r.contains(ctr) and r.width * r.height < 40000]
        zb = [r for r, f in flr if tuple(round(v, 1) for v in r) in zebra]
        gray = [f for r, f in flr if max(f) - min(f) <= 0.05 and sum(f) / 3 < 0.92 and tuple(round(v, 1) for v in r) not in zebra]
        colr = [f for r, f in flr if max(f) - min(f) > 0.05 and sum(f) / 3 > 0.75]
        other = [q for q in P if q['page'] == p['page'] and q['reader'] != p['reader']]
        rows.append(dict(page=p['page'], rect=p['rect'], kind=p['kind'], src=p['reader'] + ':' + p['source'],
            f=dict(logw=math.log(w), logh=math.log(h), aspect=math.log(w / h), hmode=min(abs(h - m) for m in modes),
                   nwords=len(inside), tcov=min(tcov, 1),
                   lab_left=any(abs((r.y0 + r.y1) / 2 - (R.y0 + R.y1) / 2) < max(h, 8) and 0 <= R.x0 - r.x1 < 40 for r, t in W),
                   lab_above=any(r.x0 < R.x1 and r.x1 > R.x0 and 0 <= R.y0 - r.y1 < 14 for r, t in W),
                   gray=bool(gray), zebra=bool(zb), color=bool(colr),
                   agree=max((iou(p['rect'], q['rect']) for q in other), default=0),
                   boldin=any(pymupdf.Rect(b).intersects(R) for b in bold),
                   square=float(abs(w - h) < 2.5 and w < 18), edge=float(R.x1 > pr.width - 30 or R.x0 < 30))))
    return rows
