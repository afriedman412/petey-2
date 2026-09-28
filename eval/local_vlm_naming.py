"""Can a local VLM NAME a field from a crop of the page? (the untested Liquid branch)

The 2026-09-24 experiment showed LFM2.5-VL cannot enumerate fields but can
localize a supplied list; naming was left untested. Here the geometry is
supplied (the committed widget rect), and the model is asked only what the
box is for. Same yardstick as the caption measurement: MiniLM cosine between
the proposed name and the committed field name, with the nearest printed
caption as the baseline on the same widgets.

    PYTHONPATH=. venv/bin/python eval/local_vlm_naming.py --forms fw9,f1040,acord25 --per-form 25 \
        --model hf.co/LiquidAI/LFM2.5-VL-1.6B-GGUF:Q4_K_M

Runs against a local ollama (http://localhost:11434). No API key.
"""
from __future__ import annotations

import argparse
import base64
import collections
import glob
import json
import os
import random
import re
import time
import urllib.request
from pathlib import Path

import numpy as np
import pymupdf
import yaml

OLLAMA = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
PROMPT = (
    "This is a crop of a blank form. The red rectangle marks one fillable "
    "field. From the printed labels around it, say what belongs in that "
    "field. Answer with ONE short snake_case field name (2-5 words, "
    "lowercase, underscores), nothing else. Example answers: "
    "employer_identification_number, spouse_first_name, total_wages."
)


def lines_of(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = " ".join(s["text"] for s in l["spans"]).strip()
            if t and re.search(r"[A-Za-z]{2,}", t):
                out.append((pymupdf.Rect(l["bbox"]), t))
    return out


def caption_for(rect, lines):
    r = pymupdf.Rect(rect)
    best = None
    for lr, t in lines:
        if 0 <= r.x0 - lr.x1 <= 60 and min(r.y1, lr.y1) - max(r.y0, lr.y0) > 0.4 * min(r.height, lr.height):
            c = ("left", r.x0 - lr.x1, t)
        elif 0 <= r.y0 - lr.y1 <= 24 and min(r.x1, lr.x1) - max(r.x0, lr.x0) > 0:
            c = ("above", (r.y0 - lr.y1) + 5, t)
        elif lr in r or (r & lr).get_area() > 0.6 * lr.get_area():
            c = ("inside", 0.5, t)
        else:
            continue
        if best is None or c[1] < best[1]:
            best = c
    return best


def crop_png(page, rect, pad_x=220, pad_y=70, dpi=170) -> bytes:
    r = pymupdf.Rect(rect)
    clip = pymupdf.Rect(r.x0 - pad_x, r.y0 - pad_y, r.x1 + pad_x, r.y1 + pad_y) & page.rect
    shape = page.new_shape()
    shape.draw_rect(r)
    shape.finish(color=(1, 0, 0), width=1.2)
    shape.commit()
    pix = page.get_pixmap(dpi=dpi, clip=clip)
    return pix.tobytes("png")


def ask_openai_compat(endpoint: str, model: str, png: bytes, prompt: str = PROMPT,
                      timeout: int = 180) -> str:
    """llama-server / any OpenAI-compatible chat endpoint with an image."""
    body = json.dumps({
        "model": model, "temperature": 0, "max_tokens": 24,
        "messages": [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
                                                + base64.b64encode(png).decode()}},
            {"type": "text", "text": prompt},
        ]}],
    }).encode()
    req = urllib.request.Request(f"{endpoint.rstrip('/')}/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["choices"][0]["message"]["content"]


def ask_ollama(model: str, png: bytes, prompt: str = PROMPT, timeout: int = 120) -> str:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "images": [base64.b64encode(png).decode()],
        "options": {"temperature": 0, "num_predict": 24},
    }).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())["response"]


def slugify(s: str) -> str:
    s = s.strip().splitlines()[0] if s.strip() else ""
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:60]


def tokens(s: str) -> set[str]:
    return {t for t in re.split(r"[_\s]+", s.lower()) if len(t) > 1 and not t.isdigit()}


def overlap(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", default="fw9,f1040,acord25,i130,vba21526ez,cms1500_fillable")
    ap.add_argument("--per-form", type=int, default=25)
    ap.add_argument("--model", default="hf.co/LiquidAI/LFM2.5-VL-1.6B-GGUF:Q4_K_M")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", type=Path, default=Path("runs/local_vlm_naming.json"))
    ap.add_argument("--dump-crops", type=Path, default=None)
    ap.add_argument("--endpoint", default=None,
                    help="OpenAI-compatible server (e.g. llama-server http://localhost:8080) "
                         "instead of ollama")
    args = ap.parse_args()
    rng = random.Random(args.seed)
    pdf_by_name = {os.path.basename(p): p for p in glob.glob("source_pdfs/**/*.pdf", recursive=True)
                   if os.path.isfile(p)}
    rows = []
    for form in [f.strip() for f in args.forms.split(",") if f.strip()]:
        bp_path = Path("blueprints") / f"{form}.bpt"
        if not bp_path.exists():
            print(f"skip {form}: no blueprint")
            continue
        bp = yaml.safe_load(bp_path.read_text())
        src = pdf_by_name.get(bp.get("source_pdf") or "")
        if not src:
            print(f"skip {form}: no blank")
            continue
        fields = [(n, f) for n, f in bp["fields"].items()
                  if f.get("widget") and f["widget"].get("widget_type") == "text"]
        rng.shuffle(fields)
        doc = pymupdf.open(src)
        lines_cache = {}
        for name, f in fields[:args.per_form]:
            w = f["widget"]
            page = doc[w["page"] - 1]
            if w["page"] not in lines_cache:
                lines_cache[w["page"]] = lines_of(page)
            cap = caption_for(w["rect"], lines_cache[w["page"]])
            png = crop_png(page, w["rect"])
            if args.dump_crops:
                args.dump_crops.mkdir(parents=True, exist_ok=True)
                (args.dump_crops / f"{form}_{name}.png").write_bytes(png)
            t = time.time()
            try:
                raw = (ask_openai_compat(args.endpoint, args.model, png) if args.endpoint
                       else ask_ollama(args.model, png))
            except Exception as e:
                raw = f"ERROR {e}"
            rows.append({"form": form, "field": name, "proposed": slugify(raw), "raw": raw[:80],
                         "caption": cap[2] if cap else None, "seconds": round(time.time() - t, 1)})
            print(f"  {form:<14} {name[:34]:<34} -> {rows[-1]['proposed'][:34]:<34} ({rows[-1]['seconds']}s)", flush=True)
        doc.close()

    # Score: token overlap and MiniLM cosine, model vs committed and caption vs committed.
    from petey.label import retrieve
    import onnxruntime as ort

    class CpuEmbedder(retrieve.Embedder):
        def __init__(self):
            super().__init__()
            self.session = ort.InferenceSession(str(retrieve.MODEL_DIR / "onnx" / "model.onnx"),
                                                providers=["CPUExecutionProvider"])
    emb = CpuEmbedder()

    def enc(xs):
        out = []
        for i in range(0, len(xs), 64):
            out.append(np.asarray(emb.encode(xs[i:i + 64])))
        e = np.concatenate(out)
        return e / np.linalg.norm(e, axis=1, keepdims=True)
    names = [r["field"].replace("_", " ") for r in rows]
    props = [r["proposed"].replace("_", " ") or "none" for r in rows]
    caps = [r["caption"] or "none" for r in rows]
    En, Ep, Ec = enc(names), enc(props), enc(caps)
    cos_m = (En * Ep).sum(1)
    cos_c = (En * Ec).sum(1)
    for r, cm, cc in zip(rows, cos_m, cos_c):
        r["cos_model"] = float(cm)
        r["cos_caption"] = float(cc) if r["caption"] else None
        r["overlap_model"] = overlap(r["proposed"], r["field"])
        r["overlap_caption"] = overlap(r["caption"] or "", r["field"]) if r["caption"] else None
    n = len(rows)
    valid = sum(1 for r in rows if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)*", r["proposed"] or ""))
    summary = {
        "model": args.model, "widgets": n, "valid_slugs": valid,
        "model_cos>=0.60": float((cos_m >= 0.60).mean()), "model_cos>=0.85": float((cos_m >= 0.85).mean()),
        "model_overlap>=0.3": float(np.mean([r["overlap_model"] >= 0.3 for r in rows])),
        "caption_present": sum(1 for r in rows if r["caption"]),
        "caption_cos>=0.60_of_all": float(np.mean([(r["cos_caption"] or 0) >= 0.60 for r in rows])),
        "caption_overlap>=0.3_of_all": float(np.mean([(r["overlap_caption"] or 0) >= 0.3 for r in rows])),
        "median_seconds": float(np.median([r["seconds"] for r in rows])),
        "per_form": {},
    }
    by_form = collections.defaultdict(list)
    for r in rows:
        by_form[r["form"]].append(r)
    for form, rs in by_form.items():
        summary["per_form"][form] = {
            "n": len(rs),
            "model_cos>=0.60": float(np.mean([r["cos_model"] >= 0.60 for r in rs])),
            "caption_cos>=0.60": float(np.mean([(r["cos_caption"] or 0) >= 0.60 for r in rs])),
        }
    print(json.dumps(summary, indent=1))
    args.out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
