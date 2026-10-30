"""Jev with the page image: can it stand in for the page check? (Andrew, 2026-10-15: Jev is far cheaper than the
models in use, so anything it can replace is worth a try; TypeSafe added images to System One, docs.typesafe.ai/images.)

The page check (`petey.validate.page_check`, Opus 5, ~7 cents a page) sees one page of the blank with every box
outlined in red and numbered, plus the field list, and flags fields. This sends Jev the same picture (rendered to
Jev's limit, 1568 px long edge, ~140 dpi on a letter page) and the same field list as `state`, and asks one Noul per
field: does the name say what a filer writes in the box tagged with its number? `--text` adds the text evidence
`jev_hand_check.states` gives text-only Jev (printed text at the box, column / row headers, publisher text,
neighbours) to each question.

Scored like the other screens by `eval/triage_score.py --jev-scores <saved file>`, on the before copies of the 19
validated forms (`belongs_to_fixture`), and here at the page check's own flag count: of the fields Jev doubts most,
as many as the page check flagged, how many are known errors.

    PYTHONPATH=. venv/bin/python eval/jev_page_check.py --save runs/jev/page_image_2026-10-15.json [--text] [--forms ID ...]

Price at writing: $0.042 per million input tokens, output free. Responses cached under runs/jev/cache by request hash.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

import httpx
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from belongs_to_fixture import BEFORE, is_known  # noqa: E402

from triage_score import NAME_PROBLEMS, page_verdicts  # noqa: E402

from petey.validate import page_check as pc  # noqa: E402
from petey.validate.jev_page import (FITS, LIMITS, MODEL, PER_REQUEST as PER_REQUEST_TEXT, QUESTION, _key,  # noqa: E402
                                     ask_split, image_ref, states)
from petey.validate.retype import resolve_blank  # noqa: E402

PER_REQUEST = 60               # image only: fields per request
PER_REQUEST_CROP = 5           # with a crop per question (12 went over the 64k-token request limit)
CROP_DPI = 300                 # the crops: the page at 300 dpi (the page check sees ~200), a window around the box
CROP_IN = (4.5, 2.5)           # window in inches (wide, tall) centred on the box, grown to hold the whole box
CROP_QUESTION = ("`crop` is a close-up of the same page at higher resolution around this field's box, which is "
                 "outlined in thick blue (the other boxes stay red and tagged). Judge from the close-up first.")

FITS = {
    "true": "The name describes the value a filer writes or marks in this box, and tells it apart from the "
            "neighbouring boxes.",
    "false": "The name describes a different box (a neighbour's caption, the row or column next to it, swapped with "
             "another field), is too vague to tell this box from the others, or nothing is written in this box.",
}
def _crops(blank: Path, page_no: int, rows: list[dict], items: list[dict]) -> dict[str, bytes]:
    """{field id: png} a CROP_IN window at CROP_DPI around each field's boxes, the field's own boxes in blue."""
    import io
    from PIL import Image, ImageDraw
    png, dpi, _px = pc.render(blank, page_no, rows, dpi=CROP_DPI)
    page = Image.open(io.BytesIO(png)).convert("RGB")
    k = dpi / 72
    W, H = page.size
    out = {}
    for it in items:
        r = _full_px(rows, it["id"], page_no, k)
        x0, y0 = min(b[0] for b in r), min(b[1] for b in r)
        x1, y1 = max(b[2] for b in r), max(b[3] for b in r)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        ww, hh = max(CROP_IN[0] * dpi, x1 - x0 + 0.6 * dpi), max(CROP_IN[1] * dpi, y1 - y0 + 0.6 * dpi)
        L, T = max(0, min(W - ww, cx - ww / 2)), max(0, min(H - hh, cy - hh / 2))
        im = page.crop((int(L), int(T), int(min(W, L + ww)), int(min(H, T + hh))))
        d = ImageDraw.Draw(im)
        for b in r:
            d.rectangle([b[0] - L - 3, b[1] - T - 3, b[2] - L + 3, b[3] - T + 3], outline=(0, 60, 255), width=5)
        s = min(1.0, 1568 / max(im.size))
        if s < 1:
            im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        out[it["id"]] = buf.getvalue()
    return out


def _full_px(rows: list[dict], fid: str, page_no: int, k: float) -> list[list[float]]:
    r = next(r for r in rows if r["id"] == fid)
    return [[v * k for v in b["rect"]] for b in r["boxes"] if b["page"] == page_no]


def jobs_for(bid: str, text: bool, crop: bool = False) -> list[tuple[str, int, dict, dict, dict]]:
    """(bid, page, body, {ref: png}, {question id: field name}) per request."""
    bpt = next((BEFORE / bid).glob("*.bpt"))
    bp = yaml.safe_load(bpt.read_text())
    blank = resolve_blank(bp)
    rows = pc.numbered(bp)
    ev = states(bpt) if text else {}
    out = []
    step = PER_REQUEST_CROP if crop else PER_REQUEST_TEXT if text else PER_REQUEST
    for page_no in sorted({b["page"] for r in rows for b in r["boxes"]}):
        png, _dpi, px = pc.render(blank, page_no, rows, limits=LIMITS)
        items = pc.field_list(rows, page_no, px)
        ref = image_ref(png)
        crops = _crops(blank, page_no, rows, items) if crop else {}
        for i in range(0, len(items), step):
            qs, names, imgs = {}, {}, {ref: png}
            for it in items[i:i + step]:
                q = {"field": {k: v for k, v in it.items() if k != "pixel_box"}, "question": QUESTION}
                if text and it["name"] in ev:
                    q["text_at_the_box"] = {k: v for k, v in ev[it["name"]].items() if k not in ("form", "field")}
                if crop:
                    cref = image_ref(crops[it["id"]], "crop")
                    imgs[cref] = crops[it["id"]]
                    q = {"crop": cref, "about_the_crop": CROP_QUESTION, **q}
                qs[f"f{it['id']}"] = {"type": "noul", "instructions": q, "criteria": FITS}
                names[f"f{it['id']}"] = it["name"]
            body = {"model": MODEL, "state": {"form": bp.get("name"), "page_number": page_no, "page": ref,
                                              "fields": items}, "questions": qs}
            out.append((bid, page_no, body, imgs, names))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--forms", nargs="*", help="default: the 19 validated in the 2026-10-13/14 round")
    ap.add_argument("--rows", default="runs/belongs_to/validated_2026-10-14.json")
    ap.add_argument("--text", action="store_true", help="add the text evidence to each question")
    ap.add_argument("--crop", action="store_true", help="a close-up around each field's box in its question")
    ap.add_argument("--limit", type=int, default=0, help="only the first N requests (a smoke test)")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--provider", default="jev",
                    help="jev | openai (OpenAI's Decisions API) | liquid (Liquid d1 direct, with the image) | dapi:<model> (decisions-api.dev, text only: "
                         "liquid/d1, upstage/solar-decide, jaredpalmer/kev-4b, togethercomputer/tev1-4b-experimental, "
                         "typesafe/jev-1.13); petey.validate.decisions_page")
    ap.add_argument("--save", required=True)
    args = ap.parse_args()
    if args.provider == "openai":
        from petey.validate import decisions_page as dp
        key, asker, price = dp._key(), dp.ask_split, dp.PRICE
    elif args.provider == "liquid":
        from petey.validate import decisions_page as dp
        key, asker, price = dp.liquid_key(), dp.liquid_ask, dp.LIQUID_PRICE
    elif args.provider.startswith("dapi:"):
        from petey.validate import decisions_page as dp
        key, asker, price = dp.dapi_key(), dp.dapi_ask(args.provider[5:]), 0.06    # 600 credits / M tokens
    else:
        key, asker, price = _key(), ask_split, 0.042
    if not key:
        raise SystemExit(f"no API key for {args.provider} (.env, petey-master/.env)")
    forms = args.forms or list(json.loads(Path("runs/belongs_to/validated_forms_2026-10-14.json").read_text())["forms"])
    jobs = [j for bid in forms for j in jobs_for(bid, args.text, args.crop)]
    if args.limit:
        jobs = jobs[:args.limit]
    pages = {(j[0], j[1]) for j in jobs}
    print(f"{len(jobs)} requests, {len(pages)} pages, {sum(len(j[4]) for j in jobs)} fields", file=sys.stderr)
    scores, tokens, t0 = {}, 0, time.time()
    with httpx.Client() as client, cf.ThreadPoolExecutor(args.workers) as ex:
        futs = {ex.submit(asker, client, key, j[2], j[3]): j for j in jobs}
        for k, f in enumerate(cf.as_completed(futs), 1):
            j = futs[f]
            res = f.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, name in j[4].items():
                v = ((res.get("answers") or {}).get(qid) or {}).get("noul")
                if v is not None:
                    scores[(j[0], name)] = v
            if k % 20 == 0:
                print(f"  {k}/{len(jobs)} requests, {time.time() - t0:.0f}s", file=sys.stderr)
    Path(args.save).parent.mkdir(parents=True, exist_ok=True)
    Path(args.save).write_text(json.dumps([[b, n, v] for (b, n), v in scores.items()]))
    print(f"input tokens {tokens:,} (~${tokens / 1e6 * price:.4f}; ${tokens / 1e6 * price / max(1, len(pages)):.5f}/page, "
          f"cached responses included)")

    # at the page check's own flag count, on the fields the fixture reviewed
    rows = [r for r in json.loads(Path(args.rows).read_text()) if r["bid"] in {j[0] for j in jobs}]
    to_now = {(r["bid"], r.get("before") or r["field"]): r["field"] for r in rows}
    known = {(r["bid"], r["field"]) for r in rows if is_known(r)}
    jev = sorted(((v, (k[0], to_now[k])) for k, v in scores.items() if k in to_now), key=lambda x: x[0])
    page = set()
    for bid in {r["bid"] for r in rows}:
        for n, x in page_verdicts(bid).items():
            if x.get("verdict") == "flag" and x.get("problem") in NAME_PROBLEMS and (bid, n) in to_now:
                page.add((bid, to_now[(bid, n)]))
    print(f"\n{len(rows)} reviewed fields, {len(known)} known name errors; page check name flags: {len(page)} fields, "
          f"{len(page & known)} caught")
    for n in (len(page), 2 * len(page), 4 * len(page)):
        top = {k for _, k in jev[:n]}
        print(f"  Jev's {n} most doubted fields: {len(top & known)} caught, cutoff name_fits {jev[min(n, len(jev)) - 1][0]:.2f}; "
              f"with the page check's flags: {len((top | page) & known)} caught at {len(top | page)} fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
