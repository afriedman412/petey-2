"""Programmatic confidence: a tier per cue type plus named, structurally-justified adjustments. No training.
Each constant is a knob with a reason; change one at a time and re-run the eval."""
import numpy as np
from .geometry import iou

TIER = {                          # how reliable each cue type is as evidence of an entry area
    'fz:enclosed_small': 0.80,    # closed small box (checkbox) found by the raster reader
    'fz:cell': 0.70,              # closed cell found by the raster reader
    'fz:comb': 0.60,              # per-character boxes
    'lat:lattice:empty': 0.60,    # empty lattice cell
    'lat:lattice:label_top': 0.55,
    'lat:lattice:label_left': 0.45,
    'fz:underline': 0.35,         # underline; mostly cell borders when inside the lattice
    'lat:lattice:box': 0.30,
}
TEXT_FILLED = 0.30      # mostly printed text -> label/instruction, not an entry area
BLOCKED_GRAY = 0.30     # neutral gray that is not zebra striping -> "don't enter" (IRS convention)
HEADER = 0.15           # bold/large text inside -> header cell
HEIGHT_MATCH = 0.10     # height matches one of the form's dominant heights
OUTLIER_UNDERLINE = 0.25  # underline outside every lattice cell = the genuine outlier field
THRESHOLD = 0.50
OVERLAP_IOU = 0.30

def mark_outside(rows):
    lat = [r for r in rows if r['src'].startswith('lat')]
    for r in rows:
        if r['src'] != 'fz:underline': continue
        R = r['rect']; cx, cy = (R[0] + R[2]) / 2, (R[1] + R[3]) / 2
        r['outside'] = not any(q['page'] == r['page'] and q['rect'][0] <= cx <= q['rect'][2] and q['rect'][1] - 2 <= cy <= q['rect'][3] + 2 for q in lat)

def score_field(r):
    f = r['f']; s = TIER.get(r['src'], 0.3); why = [r['src']]
    if f['tcov'] > 0.3 or f['nwords'] > 6: s -= TEXT_FILLED; why.append('text_filled')
    if f['gray']: s -= BLOCKED_GRAY; why.append('blocked_gray')
    if f['boldin'] and f['nwords'] > 0: s -= HEADER; why.append('header')
    if f['hmode'] <= 1.5: s += HEIGHT_MATCH; why.append('height_match')
    if r['src'] == 'fz:underline' and r.get('outside'): s += OUTLIER_UNDERLINE; why.append('outlier_underline')
    return s, why

def resolve(rows, threshold=THRESHOLD, overlap=OVERLAP_IOU):
    """Keep fields in confidence order; drop any overlapping an already-kept field. Returns (kept, all rows scored)."""
    mark_outside(rows)
    for r in rows: r['conf'], r['why'] = score_field(r)
    kept = []
    for r in sorted(rows, key=lambda r: -r['conf']):
        if r['conf'] < threshold: break
        if any(q['page'] == r['page'] and iou(q['rect'], r['rect']) >= overlap for q in kept): continue
        kept.append(r)
    return kept, rows
