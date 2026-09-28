"""Label the next N unlabeled source PDFs, spread across verticals.

The cascade costs one LLM call per page and the ready corpus is 338 forms
at 1,207 widgeted pages, so the whole thing is ~$12 — cheap enough that
the reason to run it in batches is not money. It is that **each batch is
supposed to teach us something**, and a batch drawn from one vertical
teaches us about that vertical's house style rather than about the
labeler.

So selection is round-robin across verticals rather than alphabetical.
EVAL_STATE's finding is that failure classes track structure, not subject
matter — ten more IRS forms produced zero new wrong values — and the
verticals outside tax/ACORD are where the unmeasured structure lives.

Eligibility is `source_survey.py`'s verdict, not a judgment made here:
`ready` only. `needs_ocr` forms have widgets but no text layer and
`auto_label` correctly refuses them; `no_widgets` forms belong to
`vision_label.py`.

Usage:
    python batch_label.py --n 10 --dry-run
    python batch_label.py --n 10
    python batch_label.py --n 10 --vertical okcc
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess

import pymupdf
import sys
import time
from pathlib import Path

from petey.paths import REPO, RUNS, BLUEPRINTS, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SURVEY = RUNS / "source_survey_full.json"
FINGERPRINTS = RUNS / "fingerprints.json"


# Non-AcroForm renderings of forms already held in fillable form. They
# carry no widgets the labeler can use and duplicate coverage we have.
SKIP_VERTICALS = {"rrc_raw"}

# Widgets per widgeted page above which one labeling call cannot fit its
# response in MAX_TOKENS. A label line costs 15-20 tokens of JSON, so ~200
# widgets is where an 8192-token budget runs out — nj1040's 302-widget page
# truncated mid-JSON at widget 160 and took the whole form down, since a
# truncated response is invalid JSON and nothing partial survives.
# auto_label now batches within a page (LABEL_BATCH), but that path is
# unexercised, so dense forms are held back rather than risked in bulk.
# 14 of the 229 unlabeled forms are over this line.
MAX_WIDGETS_PER_PAGE = 200


def _max_widgets_on_a_page(pdf_name: str) -> int:
    """Widgets on the densest single page of a source PDF.

    Opened per candidate rather than read from the survey, because
    `source_survey.py` records only totals and page counts — the per-page
    distribution is exactly what the average destroys.
    """
    hits = list((SOURCE_PDFS).rglob(pdf_name))
    if not hits:
        return 0
    try:
        doc = pymupdf.open(str(hits[0]))
    except Exception:
        return 0
    try:
        return max((len(list(pg.widgets() or [])) for pg in doc), default=0)
    except Exception:
        return 0
    finally:
        doc.close()


def slug_for(pdf_name: str) -> str:
    """Blueprint stem for a source PDF, matching existing convention."""
    return pdf_name[:-4].lower().replace("-", "_").replace(" ", "_")


def already_labeled() -> set[str]:
    """Source PDFs that some blueprint already covers.

    Name matching does not work here and should not be attempted: the
    source is `ACORD-125.pdf` where the blueprint is `acord125.bpt`, and
    `cbp_form_7501.pdf` where it is `cbp7501.bpt` — separator-insensitive
    comparison fixes the first and not the second. Every `.bpt` records
    the `source_pdf` it was labeled from, which is the exact join.

    Only the header is read; blueprints run to ~150KB and the field block
    is irrelevant here.
    """
    covered: set[str] = set()
    for bpt in BLUEPRINTS.glob("*.bpt"):
        try:
            with bpt.open() as fh:
                for _ in range(12):
                    line = fh.readline()
                    if not line:
                        break
                    if line.startswith("source_pdf:"):
                        covered.add(line.split(":", 1)[1].strip())
                        break
        except OSError:
            continue
    return covered


def load_candidates() -> list[dict]:
    survey = {r["file"]: r for r in json.loads(SURVEY.read_text())}
    prints = [r for r in json.loads(FINGERPRINTS.read_text())
              if not r.get("error") and r.get("widgets")]
    covered = already_labeled()

    out = []
    for r in prints:
        s = survey.get(r["file"])
        if not s or s.get("verdict") != "ready":
            continue
        if r["vertical"] in SKIP_VERTICALS:
            continue
        if r["file"] in covered:
            continue
        pages = s.get("widgeted_pages") or r["pages"] or 1
        # The AVERAGE hides the page that breaks. Form 1025 carries 887
        # widgets over 5 widgeted pages — 177 on average, under any
        # threshold — while page 3 alone holds 291. Averaging let it through
        # and it failed. Use the worst page.
        if _max_widgets_on_a_page(r["file"]) > MAX_WIDGETS_PER_PAGE:
            continue
        slug = slug_for(r["file"])
        out.append({**r, "slug": slug, "pages": pages})
    return out


def round_robin(cands: list[dict], n: int) -> list[dict]:
    """Take from each vertical in turn, rarest vertical first.

    Rarest-first matters because the small verticals (immigration,
    mortgage, nm_ocd) would otherwise never surface ahead of okcc's 78.
    """
    by_vert: dict[str, list[dict]] = collections.defaultdict(list)
    for c in sorted(cands, key=lambda c: c["file"]):
        by_vert[c["vertical"]].append(c)
    order = sorted(by_vert, key=lambda v: len(by_vert[v]))

    picked: list[dict] = []
    while len(picked) < n and any(by_vert.values()):
        for v in order:
            if by_vert[v] and len(picked) < n:
                picked.append(by_vert[v].pop(0))
    return picked


def label_one(rec: dict, model: str | None) -> dict:
    out = BLUEPRINTS / f"{rec['slug']}.bpt"
    cmd = [sys.executable, "-m", "petey.label.auto_label",
           "--blank", rec["path"], "--output", str(out)]
    if model:
        cmd += ["--model", model]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    ok = p.returncode == 0 and out.exists()

    # Keep the WHOLE tail on failure, and drop the ONNX/CoreML provider
    # warnings the detector emits on every run — truncating to 400 chars
    # once captured nothing but those warnings and lost the exception.
    err = None
    if not ok:
        noise = ("onnxruntime", "coreml", "W:onnxruntime")
        lines = [ln for ln in (p.stderr + "\n" + p.stdout).splitlines()
                 if ln.strip() and not any(n in ln.lower() for n in noise)]
        err = "\n".join(lines[-40:])

    return {
        "slug": rec["slug"], "file": rec["file"], "vertical": rec["vertical"],
        "pages": rec["pages"], "widgets": rec["widgets"],
        "ok": ok, "returncode": p.returncode, "wrote": out.exists(),
        "model": model,
        "seconds": round(time.time() - t0, 1), "error": err,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--vertical", help="restrict to one vertical")
    ap.add_argument("--model", help="override auto_label's default model")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log", type=Path,
                    default=RUNS / "batch_label_log.jsonl")
    args = ap.parse_args()

    if not SURVEY.exists() or not FINGERPRINTS.exists():
        print("run source_survey.py and form_fingerprint.py first",
              file=sys.stderr)
        return 1

    cands = load_candidates()
    if args.vertical:
        cands = [c for c in cands if c["vertical"] == args.vertical]
    batch = round_robin(cands, args.n)

    print(f"{len(cands)} ready and unlabeled; taking {len(batch)}")
    for c in batch:
        print(f"  {c['vertical']:<14} {c['slug']:<34} "
              f"{c['pages']}pp {c['widgets']}w")
    if args.dry_run:
        return 0

    results = []
    for i, c in enumerate(batch, 1):
        r = label_one(c, args.model)
        results.append(r)
        mark = "ok " if r["ok"] else "FAIL"
        print(f"[{i}/{len(batch)}] {mark} {r['slug']:<34} {r['seconds']}s")
        if not r["ok"]:
            print(f"      rc={r['returncode']} wrote={r['wrote']}")
            for ln in (r["error"] or "").splitlines()[-8:]:
                print(f"      {ln}")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("a") as fh:
        for r in results:
            fh.write(json.dumps(r) + "\n")

    ok = sum(1 for r in results if r["ok"])
    print(f"\n{ok}/{len(results)} labeled; appended to {args.log}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
