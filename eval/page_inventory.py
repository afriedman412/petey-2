"""Every page of every form on the review page, fingerprinted, to find duplicate forms and pages (Andrew, 2026-10-31:
"remove duplicate forms from library", "aggressive is fine"; "there are a bunch of duplicate *pages* across [forms],
maybe we can find a way to leverage that? also need to consider as much when doing our page inventory").

Each distinct blank (by its hash, else its path) is read once; for each page:

    words   the page's text layer, lower case, runs of letters and digits: their count, a hash of them in reading
            order, and the set of them (vocab; order varies with how the PDF was written)
    dhash   a 16 x 16 difference hash of the page drawn small and grey (256 bits, hex): pages that look alike
            are a few bits apart, a text layer or not

    runs/inventory/pages.jsonl    a line a blank: {"blank", "pdf", "pages": [{"page", "n_words", "words_sha",
                                  "vocab", "dhash"}]}
    runs/inventory/forms.json     {review id: blank}

    PYTHONPATH=. venv/bin/python eval/page_inventory.py [--procs 4]

Blanks already in pages.jsonl are skipped. `eval/page_dups.py` reads these.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "runs" / "inventory"
WORD = re.compile(r"[a-z0-9]+")


def dhash(page, n: int = 16) -> str:
    import pymupdf
    z = 64 / max(page.rect.width, page.rect.height)            # about 64 px on the long side, then n+1 x n
    pix = page.get_pixmap(matrix=pymupdf.Matrix(z, z), colorspace=pymupdf.csGRAY, alpha=False)
    w, h, s = pix.width, pix.height, pix.samples
    def at(x, y):                                              # nearest pixel of an (n+1) x n grid
        return s[min(h - 1, int(y * h / n)) * w + min(w - 1, int(x * w / (n + 1)))]
    bits = "".join("1" if at(x, y) > at(x + 1, y) else "0" for y in range(n) for x in range(n))
    return f"{int(bits, 2):0{n * n // 4}x}"


def read_blank(job: tuple[str, str]) -> dict:
    import pymupdf
    pymupdf.TOOLS.mupdf_display_errors(False)
    key, pdf = job
    out = {"blank": key, "pdf": pdf, "pages": []}
    try:
        with pymupdf.open(pdf) as doc:
            for i, page in enumerate(doc):
                words = WORD.findall(page.get_text().lower())
                out["pages"].append({"page": i + 1, "n_words": len(words),
                                     "words_sha": hashlib.sha1(" ".join(words).encode()).hexdigest()[:16],
                                     "vocab": sorted(set(words)), "dhash": dhash(page)})
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def main() -> int:
    import petey_dataset as D
    from petey.validate.retype import resolve_blank
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--procs", type=int, default=4)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    done = set()
    pj = OUT / "pages.jsonl"
    if pj.exists():
        done = {json.loads(ln)["blank"] for ln in pj.read_text().splitlines() if ln}
    forms, jobs, t = {}, {}, time.time()
    for bid, p in D.blueprint_paths().items():
        try:
            bp = D.load(p)
            pdf = resolve_blank(bp)
        except Exception:  # noqa: BLE001
            continue
        if not pdf:
            continue
        key = bp.get("source_pdf_hash") or str(pdf)
        forms[bid] = key
        if key not in done:
            jobs.setdefault(key, str(pdf))
    (OUT / "forms.json").write_text(json.dumps(forms, indent=1, sort_keys=True))
    print(f"{len(forms)} forms, {len(set(forms.values()))} blanks, {len(jobs)} to read ({time.time() - t:.0f}s)", flush=True)
    t, n = time.time(), 0
    with Pool(args.procs) as pool, pj.open("a") as f:
        for out in pool.imap_unordered(read_blank, list(jobs.items()), chunksize=4):
            f.write(json.dumps(out) + "\n")
            n += 1
            if n % 200 == 0:
                print(f"  {n} / {len(jobs)} blanks, {(time.time() - t) / n:.2f}s a blank", flush=True)
    print(f"done: {n} blanks in {time.time() - t:.0f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
