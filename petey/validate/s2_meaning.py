"""S2 — does the blueprint's field NAME describe the widget it points at?

S1 checks shape, so it is blind to the errors that matter most: `wages_amt`
and `tips_amt` are both MONEY, both agree, and a blueprint that swaps them
scores perfectly. The deterministic loop cannot see it either — the
generator writes by AcroForm path and `extract.py` reads back by AcroForm
path, so a wrong name cancels on both sides and reports `agree`.

S2 breaks that symmetry by introducing a reader that navigates by MEANING.
It is shown a filled page and the blueprint's field names, and nothing
about geometry — no rects, no AcroForm paths, no widget block. To answer,
it must find each field on the page from its name alone. Then:

    deterministic (by position)  agrees with ground truth
    semantic      (by meaning)   disagrees
    ------------------------------------------------------
    => the name does not describe the widget it is bound to

That intersection is the output. Two accuracy numbers are not; either one
alone conflates blueprint defects with extraction defects.

## The measuring instrument is not the product

Petey's shipped extraction path stays model-free — that is the whole point
of the widget layer. The model here is a reference instrument used to
calibrate a cheap one, the way you would check a tape measure against a
gauge block. It never runs at extraction time.

## Reading a disagreement

A `differ` has two causes and S2 cannot separate them alone:
  1. the name is WRONG — the blueprint says `employer_ein` about the wages box
  2. the name is RIGHT but UNDER-SPECIFIED — only 6% of fields carry a
     `description`, so the reader may simply have too little to go on
Cluster the output against S1 and the misalignment report to triage: a
field that BOTH S1 and S2 flag is very likely genuinely mislabeled.

Filled PDFs are re-rendered locally from stored ground truth (pymupdf, no
API), so any form with a ground-truth case can be measured. Responses are
cached by (blueprint, pdf, model, field-set) hash; a re-run costs nothing.

Usage:
    python s2_meaning.py --form fw9
    python s2_meaning.py --forms fw9,f1040,acord25 --out runs/s2.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from petey.extract import extract, load_blueprint          # noqa: E402
from petey.validate.shape_agree import index_by_path, normalize_value  # noqa: E402

from petey.paths import REPO, RUNS, BLUEPRINTS, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

DEFAULT_MODEL = "claude-sonnet-4-6"
CACHE = RUNS / "_s2_cache"
MAX_FIELDS_PER_CALL = 120
# Pages rendered per form. Fields outside these pages are not tested at
# all rather than being asked about blind.
MAX_PAGES = 8


SYSTEM = """You read filled forms. You are given page images of a COMPLETED \
form and a list of field names. Return the value that appears on the page \
for each field.

You are given NO coordinates and NO widget information. Locate each field \
yourself, using its name and the printed labels visible on the page.

Rules:
- Return the value EXACTLY as printed on the page. Do not reformat, \
normalise, or correct it.
- If a field's name does not correspond to anything you can find on the \
page, return null for it. Do NOT guess, and do NOT return a value from a \
different field because it seems close.
- For checkbox-style fields return true if marked, false if visibly \
unmarked, null if you cannot tell.
- GROUND EVERY ANSWER IN THESE IMAGES. You may recognise this form; do not \
answer from that recollection. Revisions move and renumber fields. If your \
memory of the form conflicts with the page shown, the page wins.

Return JSON only: {"values": {"<field_name>": <value>, ...}}"""


def _client():
    import anthropic
    return anthropic.Anthropic()


def render_pages(pdf: Path, pages: list[int], dpi: int = 150) -> list[bytes]:
    doc = pymupdf.open(str(pdf))
    try:
        return [doc[p - 1].get_pixmap(dpi=dpi).tobytes("png")
                for p in pages if 0 < p <= len(doc)]
    finally:
        doc.close()


def ask(pngs: list[bytes], fields: list[str], model: str) -> dict:
    key = hashlib.sha256(
        b"".join(pngs) + model.encode() + json.dumps(fields).encode()
    ).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{key}.json"
    if cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))

    content: list[dict] = [
        {"type": "image", "source": {"type": "base64",
                                     "media_type": "image/png",
                                     "data": base64.b64encode(p).decode()}}
        for p in pngs
    ]
    content.append({"type": "text", "text":
                    "Fields to read:\n" + "\n".join(f"- {f}" for f in fields)})
    resp = _client().messages.create(
        model=model, max_tokens=8192, system=SYSTEM,
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in resp.content
                   if getattr(b, "type", None) == "text")
    m = re.search(r"\{.*\}", text, re.DOTALL)
    out = {}
    if m:
        try:
            out = (json.loads(m.group(0)) or {}).get("values") or {}
        except json.JSONDecodeError:
            out = {}
    cached.write_text(json.dumps(out, indent=2, default=str))
    return out


def _as_date(v: Any) -> Optional[str]:
    """ISO form of a date-looking value, else None."""
    s = str(v).strip()
    if not re.search(r"\d", s) or len(s) > 24:
        return None
    if not re.fullmatch(r"[\d/\-.\s]{6,24}", s):
        return None
    try:
        from dateutil import parser as dp
        return dp.parse(s, dayfirst=False).date().isoformat()
    except Exception:
        return None


def _as_number(v: Any) -> Optional[float]:
    """Numeric value of a money/quantity-looking value, else None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    s = re.sub(r"[,$\s]", "", str(v).strip())
    try:
        return float(s)
    except ValueError:
        return None


def same(a: Any, b: Any) -> bool:
    """Loose equality — S2 asks WHICH FIELD a value belongs to, not how it
    is formatted, so both sides must go through the same coercion.

    This bit once already: `extract.py` correctly canonicalises
    `03/14/24` to `2024-03-14` per the `iso_date` pattern, and a
    strip-punctuation comparison scored that as a miss on every date in
    the corpus. It is not a cosmetic bug — `suspect` requires
    `det_agrees`, so each falsely-failed comparison SUPPRESSED a suspect
    and the check silently under-reported.
    """
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return bool(a) == bool(b)

    da, db = _as_date(a), _as_date(b)
    if da and db:
        return da == db
    na_, nb_ = _as_number(a), _as_number(b)
    if na_ is not None and nb_ is not None:
        return abs(na_ - nb_) < 0.005

    na = re.sub(r"[^a-z0-9]", "", str(normalize_value(a)).lower())
    nb = re.sub(r"[^a-z0-9]", "", str(normalize_value(b)).lower())
    if not na or not nb:
        return na == nb
    return na == nb or na in nb or nb in na


def run_form(form: str, model: str) -> Optional[dict]:
    bp_path = BLUEPRINTS / f"{form}.bpt"
    if not bp_path.exists():
        return None
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
    blank_name = bp.get("source_pdf")
    blank = SOURCE_PDFS / str(blank_name)
    if not blank.exists():
        return None

    gts = sorted((RUNS).glob(f"{form}_*/case_*/ground_truth.json"))
    if not gts:
        return None
    gt_path = max(gts, key=lambda p: len(p.read_text()))
    gt = json.loads(gt_path.read_text(encoding="utf-8"))

    # Re-render the filled PDF locally — free, and most run dirs no longer
    # carry theirs.
    from petey.synth import render_pdf
    filled = CACHE / f"{form}_filled.pdf"
    CACHE.mkdir(parents=True, exist_ok=True)
    try:
        render_pdf(gt, blank_pdf=blank, out=filled)
    except Exception as e:
        return {"form": form, "error": f"fill failed: {str(e)[:120]}"}

    idx = index_by_path(bp)
    # Deterministic read, by position.
    det = extract(load_blueprint(bp_path), filled)
    det = {k: v for k, v in det.items() if not k.startswith("_")}

    all_pages = sorted({(spec.get("widget") or {}).get("page")
                        for _, spec in idx.values()
                        if (spec.get("widget") or {}).get("page")})
    shown = all_pages[:MAX_PAGES]

    # Only fields with a ground-truth value AND a widget on a page we
    # actually render are testable.
    #
    # This was originally "any field with a value", which silently asked
    # the reader about fields it could not see: cms855a spans 72 pages,
    # its tested fields sat on pages 7-21, and only 8 pages were rendered.
    # Every one of its 63 "unlocatable" fields was on an unrendered page.
    # The check reported a 52% vocabulary mismatch for a blueprint that
    # may be fine. Measure only what is shown.
    testable = {}
    for path, (fname, spec) in idx.items():
        if path not in gt or gt[path] in (None, "", False):
            continue
        pg = (spec.get("widget") or {}).get("page")
        if pg in shown:
            testable[fname] = gt[path]
    if not testable:
        return {"form": form, "error": "no filled fields on rendered pages"}

    pngs = render_pages(filled, shown)
    if not pngs:
        return {"form": form, "error": "no pages"}

    names = list(testable)[:MAX_FIELDS_PER_CALL]
    sem = ask(pngs, names, model)

    rows = []
    for name in names:
        truth = testable[name]
        d = det.get(name)
        s = sem.get(name)
        det_ok = same(d, truth)
        sem_ok = same(s, truth)
        rows.append({
            "field": name, "truth": truth,
            "deterministic": d, "semantic": s,
            "det_agrees": det_ok, "sem_agrees": sem_ok,
            # `suspect` = the name is bound to the wrong widget.
            "suspect": bool(det_ok and not sem_ok and s is not None),
            # `unlocatable` = the reader could not find this field on the
            # page AT ALL. Originally treated as "not measured", which was
            # wrong: it is the strongest signal in the whole check. A
            # blueprint whose names are unlocatable is unusable by Petey's
            # LLM path, which navigates by name. cms1500 returned null for
            # all 36 fields because the labeler had put capital-gains
            # vocabulary (`date_acquired_1_mo`, `gross_proceeds_1_amt`) on
            # an insurance claim form — the single worst defect in the
            # corpus, and silently discarded until this was separated out.
            "unlocatable": bool(s is None and truth is not None),
        })
    n_unloc = sum(1 for r in rows if r["unlocatable"])
    return {"form": form, "n_tested": len(rows), "rows": rows,
            "pages_shown": shown, "pages_total": len(all_pages),
            "n_unlocatable": n_unloc,
            "unlocatable_rate": (n_unloc / len(rows)) if rows else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", type=str)
    ap.add_argument("--forms", type=str)
    ap.add_argument("--model", type=str, default=DEFAULT_MODEL)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    forms = ([args.form] if args.form
             else [f.strip() for f in (args.forms or "").split(",") if f.strip()])
    if not forms:
        print("give --form or --forms")
        return 1

    results = []
    for f in forms:
        r = run_form(f, args.model)
        if r is None:
            print(f"  {f:<14} skipped (no blueprint / blank / ground truth)")
            continue
        if "error" in r:
            print(f"  {f:<14} {r['error']}")
            continue
        results.append(r)
        rows = r["rows"]
        susp = [x for x in rows if x["suspect"]]
        det_n = sum(1 for x in rows if x["det_agrees"])
        sem_n = sum(1 for x in rows if x["sem_agrees"])
        ur = r["unlocatable_rate"]
        flag = "  <-- VOCABULARY MISMATCH" if ur >= 0.5 else ""
        print(f"  {f:<14} tested={len(rows):<4} "
              f"deterministic={det_n:<4} semantic={sem_n:<4} "
              f"suspect={len(susp):<4} unlocatable={ur:>5.0%}{flag}")

    print()
    print("=" * 74)
    print("S2 — deterministic agrees, semantic disagrees")
    print("   (the name does not describe the widget it is bound to)")
    print("=" * 74)
    total = 0
    for r in results:
        susp = [x for x in r["rows"] if x["suspect"]]
        if not susp:
            continue
        print(f"\n  {r['form']}  ({len(susp)} of {r['n_tested']})")
        for x in susp[:15]:
            print(f"     {x['field'][:40]:<40}")
            print(f"        in widget : {x['truth']!r}")
            print(f"        by meaning: {x['semantic']!r}")
        total += len(susp)
    print(f"\n  total suspect fields: {total}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2, default=str))
        print(f"[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
