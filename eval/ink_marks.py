"""Ink-mark detection: is petey/validate/ink.py robust to the shape, size, colour, stroke and placement of a mark?

For each sample page (AcroForm forms, so every option box's rectangle is
known), 60% of the boxes get a synthetic mark drawn with a random variant
and 40% stay empty. A second pass marks boxes the PDF's own way (the widget
appearance glyph). The detector's ink delta is computed for every box; the
report sweeps the threshold and gives precision / recall overall and per
variant dimension at the chosen threshold. Overlays go to runs/ink/.

    PYTHONPATH=. venv/bin/python eval/ink_marks.py
"""
from __future__ import annotations

import collections
import json
import random
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.paths import RUNS, SOURCE_PDFS  # noqa: E402
from petey.validate import ink  # noqa: E402
from petey.synth.render import _unescape_pdf_name  # noqa: E402


def flattened(src: Path, out: Path) -> Path:
    """Bake widget appearances into the page content: a hand mark on a printed
    form sits on top of the printed box, so the mark must be drawn over the
    baked appearance, not under the live widget (which hides it)."""
    doc = pymupdf.open(src)
    try:
        doc.bake()
    except Exception:
        for page in doc:
            for w in list(page.widgets() or []):
                pass
    doc.save(out); doc.close()
    return out

PAGES = [("BldgForm1-2_Fillable_l3tFiXs.pdf", 1), ("chubb-uk-accident_and_illness_claims form.pdf", 3),
         ("cms1500_fillable.pdf", 1), ("DA FORM 4187 - Locally Assigned Status template.pdf", 1),
         ("form-12s.pdf", 9), ("Form400-070620.pdf", 1), ("FORMS_BINGO_830_f.pdf", 1),
         ("mortgage/Form 1004.pdf", 1), ("mortgage/URLA-2019-Borrower-v28.pdf", 1), ("nurse1.pdf", 1),
         ("pdf_GR_en_claim_form_injury.pdf", 2), ("PIT-RSS_2025-01_PaperInteractiveIPM.pdf", 1)]
SHAPES = ["check", "x", "dot", "square", "tick", "scribble"]
SIZES = [0.45, 0.7, 0.95, 1.25]              # of the box's smaller side; 1.25 overflows
COLORS = {"black": (0, 0, 0), "blue": (0.05, 0.1, 0.6), "red": (0.8, 0.05, 0.05), "grey": (0.55, 0.55, 0.55),
          "pencil": (0.72, 0.72, 0.72)}
STROKES = [0.5, 1.0, 1.8, 3.0]               # pt
OFFSETS = [0.0, 0.25, 0.45]                  # of the box, diagonal shift
OUT = RUNS / "ink"


def find(name: str) -> Path:
    p = SOURCE_PDFS / name
    if p.exists():
        return p
    hits = [h for h in SOURCE_PDFS.rglob(Path(name).name) if "source_pdfs_old" not in h.parts]
    return hits[0]


def draw_mark(page: pymupdf.Page, rect: pymupdf.Rect, v: dict) -> None:
    s = min(rect.width, rect.height) * v["size"]
    cx = rect.x0 + rect.width / 2 + v["offset"] * rect.width
    cy = rect.y0 + rect.height / 2 + v["offset"] * rect.height
    color = COLORS[v["color"]]
    w = v["stroke"]
    sh = page.new_shape()
    h = s / 2
    if v["shape"] == "check":
        sh.draw_polyline([(cx - h, cy), (cx - h * 0.3, cy + h * 0.8), (cx + h, cy - h * 0.8)])
        sh.finish(color=color, width=w)
    elif v["shape"] == "x":
        sh.draw_line((cx - h, cy - h), (cx + h, cy + h)); sh.finish(color=color, width=w)
        sh.draw_line((cx - h, cy + h), (cx + h, cy - h)); sh.finish(color=color, width=w)
    elif v["shape"] == "dot":
        sh.draw_circle((cx, cy), h * 0.6); sh.finish(color=color, fill=color, width=0)
    elif v["shape"] == "square":
        sh.draw_rect(pymupdf.Rect(cx - h * 0.7, cy - h * 0.7, cx + h * 0.7, cy + h * 0.7)); sh.finish(color=color, fill=color, width=0)
    elif v["shape"] == "tick":
        sh.draw_polyline([(cx - h * 0.4, cy + h * 0.1), (cx - h * 0.05, cy + h * 0.6), (cx + h * 0.7, cy - h * 0.6)])
        sh.finish(color=color, width=w)
    elif v["shape"] == "scribble":
        pts = [(cx - h + i * s / 6, cy + (h * 0.6 if i % 2 else -h * 0.6)) for i in range(7)]
        sh.draw_polyline(pts); sh.finish(color=color, width=w)
    sh.commit()


def main() -> int:
    rng = random.Random(7)
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, pno in PAGES:
        src = find(name)
        live = pymupdf.open(src)
        boxes = [(w.field_name, pymupdf.Rect(w.rect), w.field_type_string) for w in live[pno - 1].widgets()
                 if w.field_type_string in ("CheckBox", "RadioButton") and w.rect.width >= 4 and w.rect.height >= 4]
        live.close()
        flat_blank = flattened(src, OUT / "_tmp_blank_flat.pdf")
        blank = pymupdf.open(flat_blank)
        # pass 1: synthetic marks, drawn over the baked page
        doc = pymupdf.open(flat_blank)
        page = doc[pno - 1]
        plan = []
        for i, (path, rect, kind) in enumerate(boxes):
            if rng.random() < 0.6:
                v = {"shape": rng.choice(SHAPES), "size": rng.choice(SIZES), "color": rng.choice(list(COLORS)),
                     "stroke": rng.choice(STROKES), "offset": rng.choice(OFFSETS)}
                draw_mark(page, rect, v)
                plan.append((i, True, v))
            else:
                plan.append((i, False, None))
        for i, marked, v in plan:
            path, rect, kind = boxes[i]
            d = ink.ink_delta(page, blank[pno - 1], list(rect))
            rows.append({"page": f"{Path(name).name}:{pno}", "pass": "drawn", "box": path[-30:], "kind": kind,
                         "w": round(rect.width, 1), "marked": marked, "delta": round(d, 4), **(v or {})})
        page.get_pixmap(dpi=72).save(OUT / f"{Path(name).stem[:30]}_p{pno}_drawn.png")
        doc.close()
        # pass 2: the PDF's own appearance (fill the widget)
        doc = pymupdf.open(src)
        page = doc[pno - 1]
        for w in page.widgets():
            if w.field_type_string in ("CheckBox", "RadioButton") and rng.random() < 0.5:
                try:
                    on = _unescape_pdf_name(w.on_state())
                    if on:
                        w.field_value = on; w.update()
                except Exception:
                    pass
        doc.save(OUT / "_tmp_filled_live.pdf"); doc.close()
        # truth = what the PDF now shows (a sibling kid of a filled field shows the mark too)
        live2 = pymupdf.open(OUT / "_tmp_filled_live.pdf")
        marked_paths = {(w.field_name, tuple(round(c, 1) for c in w.rect)) for w in live2[pno - 1].widgets()
                        if w.field_type_string in ("CheckBox", "RadioButton") and w.field_value not in (None, "", "Off")}
        live2.close()
        flattened(OUT / "_tmp_filled_live.pdf", OUT / "_tmp_filled.pdf")
        filled = pymupdf.open(OUT / "_tmp_filled.pdf")
        fpage = filled[pno - 1]
        for path, rect, kind in boxes:
            m = (path, tuple(round(c, 1) for c in rect)) in marked_paths
            d = ink.ink_delta(fpage, blank[pno - 1], list(rect))
            rows.append({"page": f"{Path(name).name}:{pno}", "pass": "appearance", "box": path[-30:], "kind": kind,
                         "w": round(rect.width, 1), "marked": m, "delta": round(d, 4)})
        filled.close(); blank.close()
    (OUT / "ink_marks.json").write_text(json.dumps(rows, indent=1))

    def pr(rs, t):
        tp = sum(1 for r in rs if r["marked"] and r["delta"] >= t); fp = sum(1 for r in rs if not r["marked"] and r["delta"] >= t)
        fn = sum(1 for r in rs if r["marked"] and r["delta"] < t)
        return tp / max(tp + fp, 1), tp / max(tp + fn, 1)
    print(f"{len(rows)} box readings on {len(PAGES)} pages")
    print("\nthreshold sweep (all readings): threshold | precision | recall")
    for t in (0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12):
        p, r = pr(rows, t); print(f"  {t:.3f} | {p:.3f} | {r:.3f}")
    t = ink.THRESHOLD
    for pss in ("drawn", "appearance"):
        p, r = pr([x for x in rows if x["pass"] == pss], t); print(f"\n{pss}: precision {p:.3f} recall {r:.3f} at {t}")
    print("\nrecall by variant at", t)
    drawn = [x for x in rows if x["pass"] == "drawn" and x["marked"]]
    for dim in ("shape", "size", "color", "stroke", "offset"):
        parts = []
        for val in sorted({x[dim] for x in drawn}, key=str):
            xs = [x for x in drawn if x[dim] == val]; parts.append(f"{val}: {sum(1 for x in xs if x['delta'] >= t)}/{len(xs)}")
        print(f"  {dim:7s} " + " | ".join(parts))
    print("\nfalse positives by page at", t)
    for pg in sorted({x["page"] for x in rows}):
        xs = [x for x in rows if x["page"] == pg and not x["marked"]]
        fp = [x for x in xs if x["delta"] >= t]
        print(f"  {pg[:52]:52s} {len(fp)}/{len(xs)} " + (f"max delta {max(x['delta'] for x in fp):.3f}" if fp else ""))
    print("\nmissed marks (delta < threshold):")
    for x in sorted((x for x in rows if x["marked"] and x["delta"] < t), key=lambda x: x["delta"])[:15]:
        print(f"  {x['page'][:30]:30s} {x['pass']:10s} {x.get('shape','')!s:8} size={x.get('size','')} {x.get('color','')!s:6} stroke={x.get('stroke','')} off={x.get('offset','')} box={x['w']}pt delta={x['delta']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
