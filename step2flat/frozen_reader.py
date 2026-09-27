#!/usr/bin/env python3
"""step2_reader.py -- Petey step-2 flat-page field finder.

Geometry from code only. Primary path: render -> binarize -> white connected
components ("enclosed regions") = cells/boxes/ovals; long-line opening = underlines.
Captions from tesseract (raster) or, with --captions textlayer, from the PDF text
layer (comparison only). No filename branches, no per-form constants.
"""
import argparse, json, re, sys
import numpy as np, cv2, pymupdf, pytesseract

DPI = 150
S = DPI / 72.0                      # px per pt
P = lambda pt: int(round(pt * S))   # pt -> px

# ---------------------------------------------------------------- inputs
def load_pages(path, raster_page_size=None):
    """Yields (page_no, gray uint8 image, page_w_pt, page_h_pt, text_words_px|None, assumed)."""
    if path.lower().endswith(".pdf"):
        doc = pymupdf.open(path)
        for pg in doc:
            pix = pg.get_pixmap(dpi=DPI, colorspace=pymupdf.csGRAY)
            img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w).copy()
            words = [(w[0]*S, w[1]*S, w[2]*S, w[3]*S, w[4]) for w in pg.get_text("words")]
            yield pg.number, img, pg.rect.width, pg.rect.height, words, False
    else:
        img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        h, w = img.shape
        pw, ph = raster_page_size or (w / S, h / S)   # assumption: rendered at DPI
        yield 0, img, pw, ph, None, True

# ---------------------------------------------------------------- preprocessing
def binarize(gray):
    hist = np.bincount(gray.ravel(), minlength=256)
    bg = int(np.argmax(hist[128:])) + 128           # paper level
    thr = min(225, bg - 22)                          # keeps light-tint rules
    ink = (gray < thr).astype(np.uint8)
    # drop speckle / halftone dots / dot leaders
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    small = (st[:, cv2.CC_STAT_AREA] < 14) & (np.maximum(st[:, 2], st[:, 3]) < 6)
    small[0] = False
    ink[small[lab]] = 0
    return ink

def ocr_tokens(gray):
    d = pytesseract.image_to_data(gray, config="--psm 11", output_type=pytesseract.Output.DICT)
    out = []
    for i, t in enumerate(d["text"]):
        t = t.strip()
        if not t or float(d["conf"][i]) <= 30:
            continue
        x, y, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        out.append(dict(t=t, x0=x, y0=y, x1=x + w, y1=y + h))
    return out

def words_to_tokens(words):
    return [dict(t=w[4], x0=w[0], y0=w[1], x1=w[2], y1=w[3]) for w in words if w[4].strip()]

def erase_text(ink, toks):
    """Fill each word box with the majority colour of its surrounding ring
    (handles black-on-white and white-on-black), so text can't fragment regions."""
    out = ink.copy()
    H, W = ink.shape
    for t in toks:
        if not re.search(r"[A-Za-z0-9]", t["t"]) or "_" in t["t"]:
            continue
        x0, y0, x1, y1 = map(int, (t["x0"], t["y0"], t["x1"], t["y1"]))
        if (x1 - x0) > P(250) or (y1 - y0) > P(30):
            continue
        a0, b0, a1, b1 = max(x0-2, 0), max(y0-2, 0), min(x1+2, W), min(y1+2, H)
        ring = np.concatenate([ink[b0, a0:a1], ink[b1-1, a0:a1], ink[b0:b1, a0], ink[b0:b1, a1-1]])
        out[y0:y1, x0:x1] = 1 if ring.mean() > 0.5 else 0
    return out

def rule_masks(ink):
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1)))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 18)))
    return h, v

# ---------------------------------------------------------------- regions
def border_thickness(ink, x, y, w, h):
    """Median run of ink outward from the region's bbox edge (px)."""
    H, W = ink.shape
    runs = []
    for (cx, cy, dx, dy) in [(x + w//2, y - 1, 0, -1), (x + w//2, y + h, 0, 1),
                             (x - 1, y + h//2, -1, 0), (x + w, y + h//2, 1, 0)]:
        r = 0
        while 0 <= cx < W and 0 <= cy < H and ink[cy, cx] and r < 12:
            r += 1; cx += dx; cy += dy
        runs.append(r)
    return float(np.median(runs))

def regions(ink_cells, ink_raw):
    white = (ink_cells == 0).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(white, connectivity=4)
    H, W = white.shape
    out = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if x == 0 or y == 0 or x + w >= W or y + h >= H:
            continue                                  # page background
        if w < P(5) or h < P(5):
            continue
        rect = a / float(w * h)
        wp, hp = w / S, h / S
        asp = w / float(h)
        kind = None
        if max(wp, hp) <= 22 and min(wp, hp) >= 5:
            bt = border_thickness(ink_raw, x, y, w, h)
            if rect >= 0.86 and 0.55 <= asp <= 1.8:
                kind = "box"
            elif 0.6 <= rect < 0.86 and 0.8 <= asp <= 2.8 and bt <= 3:
                kind = "oval"
            elif rect >= 0.86:
                kind = "smallcell"
        if kind is None:
            if rect < 0.75:
                continue                              # open / L-shaped region
            kind = "cell"
        out.append(dict(id=i, kind=kind, x0=x, y0=y, x1=x + w, y1=y + h, rect=rect))
    return out, lab

def group_combs(regs):
    """Runs of >=2 equal-size, edge-sharing small boxes/cells on one baseline -> one comb field."""
    cand = [r for r in regs if r["kind"] in ("box", "smallcell", "cell") and (r["x1"]-r["x0"]) <= P(26)
            and (r["y1"]-r["y0"]) <= P(26)]
    cand.sort(key=lambda r: (r["y0"], r["x0"]))
    used, combs = set(), []
    for r in cand:
        if r["id"] in used:
            continue
        run = [r]
        while True:
            last = run[-1]
            nxt = [c for c in cand if c["id"] not in used and c is not last
                   and abs(c["y0"] - last["y0"]) <= P(2) and abs(c["y1"] - last["y1"]) <= P(2)
                   and 0 <= c["x0"] - last["x1"] <= P(3.5)]
            if not nxt:
                break
            run.append(min(nxt, key=lambda c: c["x0"]))
        if len(run) >= 2:
            ws = [c["x1"] - c["x0"] for c in run]
            if max(ws) <= 1.6 * min(ws):
                for c in run: used.add(c["id"])
                combs.append(run)
    return combs, used

# ---------------------------------------------------------------- captions
def inside(t, r, pad=0):
    cx, cy = (t["x0"] + t["x1"]) / 2, (t["y0"] + t["y1"]) / 2
    return r["x0"] - pad <= cx <= r["x1"] + pad and r["y0"] - pad <= cy <= r["y1"] + pad

def lines_of(toks):
    toks = sorted(toks, key=lambda t: (t["y0"] + t["y1"]) / 2)
    lines = []
    for t in toks:
        cy = (t["y0"] + t["y1"]) / 2
        if lines and abs(cy - lines[-1]["cy"]) <= 0.5 * max(t["y1"] - t["y0"], lines[-1]["h"]):
            L = lines[-1]; L["toks"].append(t)
            L["y0"] = min(L["y0"], t["y0"]); L["y1"] = max(L["y1"], t["y1"])
        else:
            lines.append(dict(toks=[t], cy=cy, y0=t["y0"], y1=t["y1"], h=t["y1"] - t["y0"]))
    for L in lines:
        L["toks"].sort(key=lambda t: t["x0"])
        L["x0"] = L["toks"][0]["x0"]; L["x1"] = max(t["x1"] for t in L["toks"])
        L["text"] = " ".join(t["t"] for t in L["toks"])
    return lines

def box_labels(boxes, toks):
    """Label = run of tokens starting just right of the box on its row (else just left)."""
    claimed = {}
    for b in boxes:
        row = [t for t in toks if b["y0"] - P(3) <= (t["y0"] + t["y1"]) / 2 <= b["y1"] + P(3)]
        right = sorted([t for t in row if 0 <= t["x0"] - b["x1"] <= P(15)] and
                       [t for t in row if t["x0"] >= b["x1"] - 1], key=lambda t: t["x0"])
        seq = []
        for t in right:
            if not seq and t["x0"] - b["x1"] > P(15): break
            if seq and t["x0"] - seq[-1]["x1"] > P(8): break
            seq.append(t)
        if not seq:
            left = sorted([t for t in row if t["x1"] <= b["x0"] + 1 and b["x0"] - t["x1"] <= P(15)],
                          key=lambda t: -t["x1"])
            for t in left:
                if seq and seq[-1]["x0"] - t["x1"] > P(8): break
                seq.append(t)
            seq.reverse()
        b["label"] = " ".join(t["t"] for t in seq)
        for t in seq: claimed[id(t)] = b
    return claimed

# ---------------------------------------------------------------- main per page
def read_page(img, toks, erase=True):
    ink_raw = binarize(img)
    ink = erase_text(ink_raw, toks) if erase else ink_raw
    hmask, vmask = rule_masks(ink_raw)
    # bridge small gaps in scanned rules before region labelling
    ink_cells = ink | cv2.dilate(hmask, np.ones((1, 7), np.uint8)) | cv2.dilate(vmask, np.ones((7, 1), np.uint8))
    regs, lab = regions(ink_cells, ink_raw)

    combs, comb_ids = group_combs(regs)
    boxes = [r for r in regs if r["kind"] in ("box", "oval") and r["id"] not in comb_ids]
    cells = [r for r in regs if r["kind"] in ("cell", "smallcell") and r["id"] not in comb_ids]
    claimed = box_labels(boxes, toks)
    fields = []

    for b in boxes:
        fields.append(dict(kind="radio" if b["kind"] == "oval" else "checkbox",
                           px=(b["x0"], b["y0"], b["x1"], b["y1"]), caption=b.get("label", ""),
                           source="enclosed_small"))
    for run in combs:
        fields.append(dict(kind="comb", px=(run[0]["x0"], min(c["y0"] for c in run), run[-1]["x1"],
                           max(c["y1"] for c in run)), caption="", cells=len(run), source="comb"))

    # cells
    cell_info = []
    for c in cells:
        crop = img[c["y0"]:c["y1"], c["x0"]:c["x1"]]
        if crop.mean() < 110:
            continue                                   # solid band / section header
        if any(b["x0"] >= c["x0"] and b["x1"] <= c["x1"] and b["y0"] >= c["y0"] and b["y1"] <= c["y1"]
               for b in boxes):
            continue                                   # region hosting boxes = option group, not text entry
        ct = [t for t in toks if inside(t, c)]
        L = lines_of(ct)
        info = dict(c=c, lines=L, entry=None, caption="", header=False)
        if not L:
            info["entry"] = [c["x0"] + 1, c["y0"] + 1, c["x1"] - 1, c["y1"] - 1]
        else:
            cap = [L[0]]
            if L[0]["y0"] - c["y0"] <= 0.55 * (c["y1"] - c["y0"]):
                for l in L[1:]:
                    if l["y0"] - cap[-1]["y1"] <= 0.8 * cap[-1]["h"]:
                        cap.append(l)
                    else:
                        break
            capt = [t for l in cap for t in l["toks"]]
            info["caption"] = " ".join(l["text"] for l in cap)
            if capt and all(id(t) in claimed for t in capt):
                continue                               # text is a box's label
            cap_y1 = max(l["y1"] for l in cap)
            if c["y1"] - cap_y1 >= P(7):
                e = [c["x0"] + 1, cap_y1 + P(1), c["x1"] - 1, c["y1"] - 1]
            else:
                cx1 = max(l["x1"] for l in cap if l["y0"] <= cap[0]["y1"])
                e = [cx1 + P(2), c["y0"] + 1, c["x1"] - 1, c["y1"] - 1]
                if e[2] - e[0] < P(20):
                    info["header"] = True
                    cell_info.append(info); continue
            # printed prefix / suffix tokens (units, $, %) inside the entry band
            rest = [t for t in ct if t not in capt and inside(t, dict(x0=e[0], y0=e[1], x1=e[2], y1=e[3]))]
            for t in rest:
                if len(t["t"]) <= 4 and not re.fullmatch(r"\d{2,}", t["t"]):
                    if t["x0"] - e[0] <= P(6):
                        e[0] = max(e[0], t["x1"] + P(1))
                    elif e[2] - t["x1"] <= P(6):
                        e[2] = min(e[2], t["x0"] - P(1))
            info["entry"] = e
        cell_info.append(info)

    # header rows: caption-only cell whose column-mate directly below is captionless
    for i, a in enumerate(cell_info):
        if a["entry"] is None and not a["header"]:
            continue
        ca = a["c"]
        below = [b for b in cell_info if b is not a and abs(b["c"]["y0"] - ca["y1"]) <= P(4)
                 and abs(b["c"]["x0"] - ca["x0"]) <= P(4) and abs(b["c"]["x1"] - ca["x1"]) <= P(4)]
        if below and not below[0]["lines"] and a["lines"] and \
                (a["c"]["y1"] - max(l["y1"] for l in a["lines"])) < P(9):
            a["header"] = True
            below[0]["caption"] = below[0]["caption"] or a["caption"]
    for a in cell_info:
        if a["header"] or a["entry"] is None:
            continue
        e = a["entry"]
        if e[2] - e[0] < P(4) or e[3] - e[1] < P(4):
            continue
        k = "signature" if re.search(r"signature", a["caption"], re.I) else "text"
        fields.append(dict(kind=k, px=tuple(e), caption=a["caption"], source="cell"))

    # underlines: long horizontal rules that do not separate two regions
    n, llab, st, _ = cv2.connectedComponentsWithStats(hmask, connectivity=8)
    H, W = hmask.shape
    for i in range(1, n):
        x, y, w, h, _ = st[i]
        if w < P(25) or h > P(3):
            continue
        yc = y + h // 2
        same = 0
        for fx in (0.2, 0.5, 0.8):
            xx = int(x + fx * w)
            up = lab[max(yc - P(2) - h, 0), xx]; dn = lab[min(yc + P(2) + h, H - 1), xx]
            same += (up == dn)
        if same < 2:
            continue
        top = yc - P(14)
        above = [t for t in toks if t["x1"] > x and t["x0"] < x + w and top < t["y1"] <= yc - 1]
        # text sitting on the rule splits it; keep the widest free stretch
        segs = [(x, x + w)]
        for t in above:
            if t["y1"] >= yc - P(4):
                segs = [s for a0, a1 in segs for s in ((a0, min(a1, int(t["x0"]) - 1)), (max(a0, int(t["x1"]) + 1), a1)) if s[1] - s[0] > 0]
            else:
                top = max(top, int(t["y1"]) + 1)
        for a0, a1 in segs:
            if a1 - a0 >= P(20):
                fields.append(dict(kind="text", px=(a0, top, a1, yc), caption="", source="underline"))
    return fields

def near_caption(f, toks):
    """Nearest line of text left of / above an uncaptioned field (for naming only)."""
    x0, y0, x1, y1 = f["px"]
    best, bd = "", 1e9
    for L in lines_of(toks):
        if L["x1"] <= x0 + 2 and L["y0"] < y1 and L["y1"] > y0:
            d = x0 - L["x1"]
        elif L["y1"] <= y0 + 2 and L["x0"] < x1 and L["x1"] > x0:
            d = (y0 - L["y1"]) * 1.5
        else:
            continue
        if 0 <= d < bd and d < P(80):
            best, bd = L["text"], d
    return best

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("-o", "--out")
    ap.add_argument("--captions", choices=["ocr", "textlayer"], default="ocr")
    ap.add_argument("--raster-page-size", nargs=2, type=float, default=None)
    a = ap.parse_args()
    fields, assumed_any = [], False
    for pno, img, pw, ph, words, assumed in load_pages(a.src, a.raster_page_size):
        assumed_any |= assumed
        toks = words_to_tokens(words) if (a.captions == "textlayer" and words) else ocr_tokens(img)
        for f in read_page(img, toks):
            if not f["caption"]:
                f["caption"] = near_caption(f, toks)
            x0, y0, x1, y1 = f.pop("px")
            f.update(page=pno, rect=[round(x0 / S, 2), round(y0 / S, 2), round(x1 / S, 2), round(y1 / S, 2)])
            fields.append(f)
    out = dict(authoring=dict(method=f"step2_flat_reader/raster+{a.captions}", dpi=DPI,
                              page_size_assumed=assumed_any), fields=fields)
    json.dump(out, open(a.out, "w") if a.out else sys.stdout, indent=1)

if __name__ == "__main__":
    main()
