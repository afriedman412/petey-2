"""Adjudicator for contested renames: the taxonomy's tier 3, applied to the loop's own edits.

The loop's per-field before/after cannot judge a rename whose evidence all comes from one reading of the page.
MA LIC100 (2026-09-30): the classifier gave the box under "C5. State" the caption "B16. Name" two rows up; the
class, the bank value, the regex check and the judge all followed, the reviewer renamed the field `applicant_nm`,
and every flag built on that caption cleared, so the loop scored the wrong rename 'better'. The case chain
(`field_chain.py`) now withholds such captions from the reviewer, which stops that rename and also stops right
ones (SS-4 `ein` on the legal-name box, whose caption the geometry calls uncertain).

This is one step, independent of the classifier, between the reviewer's decisions (`review.ask`) and
`review.apply_decisions`:

    when      the reviewer proposes a rename on a field the chain does not settle: its caption is unverified
              (`verified` False or None), or the publisher's tooltip / path and the caption disagree (KS DO-10:
              widgets placed one row off, tooltip EIN/SSN/PTIN in the box captioned Area Code & Phone Number);
    input     a crop of the rendered BLANK page with the widget's own rect outlined (from the blueprint, not the
              finder or the classifier), wide enough to show the neighbouring captions and any table header above;
              the current name, the proposed name, the reviewer's reason, the tooltip / path, the description;
    question  what would a filer write in the outlined box; does the current or the proposed name describe it?
              `current` / `proposed` / `unclear` with a one-line reason;
    outcome   the rename lands only on `proposed`; `unclear` keeps the name and flags the field for a person
              (`x_petey_adjudication.needs_person`); the loop keeps an adjudicated rename it would otherwise
              restore as 'same' (`iterate.judge_review`), since its evidence is independent of the case.

One vision call per contested rename (batch 2: 11 renames over 20 forms). Tested before use on the fields checked
by eye on 2026-09-30 / 10-01: `eval/adjudicator_test.py`.

    python -m petey.validate.adjudicate --form do10 --field ein_ssn_ptin --proposed taxpayer_phone_number \
        [--bpt runs/judge_eval/blueprints/do10_v0.bpt] [--model claude-sonnet-4-6] [--crop out.png]
"""
from __future__ import annotations

import argparse
import base64
import collections
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml

from petey.validate.name_caption import tokens

MODEL = "claude-sonnet-4-6"
PRICES = {  # $ per million tokens, input / output (list price, 2026-06); same table as review.py
    "claude-opus-5": (5.0, 25.0), "claude-sonnet-5": (2.0, 10.0), "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0), "claude-fable-5-1": (10.0, 50.0),
}
DPI = 170
PAD_UP, PAD_DOWN = 130.0, 70.0     # points of page above / below the widget in the crop
HEADER_PT = 300.0                  # a table's column header may sit this far above its rows (TX DMV 1756)

SYSTEM = """You adjudicate one field name on a blank form. You see a crop of the page with ONE box \
outlined in red, and two candidate names for the field behind that box: the current name and a proposed \
rename. Nothing about the box is known for certain except where it is.

First read the page: what would a person filling in this form by hand write in the outlined box? Decide \
that from the captions printed for the box (inside it, or directly above, below or beside it as this form \
lays out its captions; a table's column header and row label count for a cell), not from the box's \
metadata. A filer writes by position: when the publisher's tooltip or field name disagrees with the caption \
printed at the box, the caption wins. Mind which caption belongs to THIS box and which to a neighbour: on a \
dense form the caption of the cell above or beside the box is often nearer than its own.

Then decide which name describes that value. Names are snake_case, IRS MeF style (_nm name, _dt date, _amt \
money, _cd code, _ind checkbox); judge the kind of value a name points at, not its style, suffix or copy \
number. Answer:
- "current" when the current name describes what a filer writes in the box;
- "proposed" when the proposed name describes it and the current name does not;
- "unclear" when the crop does not show what the box holds, or neither name fits.
Give what the box holds in a few words and a one-line reason that names the caption you relied on."""

SCHEMA = {
    "type": "object",
    "properties": {
        "box_holds": {"type": "string"},
        "verdict": {"type": "string", "enum": ["current", "proposed", "unclear"]},
        "reason": {"type": "string"},
    },
    "required": ["box_holds", "verdict", "reason"],
    "additionalProperties": False,
}


# ------------------------------------------------------------------ crop

def _lines(page) -> list[tuple[tuple, str]]:
    out = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            text = " ".join(s.get("text", "") for s in line.get("spans", [])).strip()
            if text and re.search(r"[A-Za-z0-9]", text):
                out.append((tuple(line["bbox"]), text))
    return out


def _header_top(rect, lines) -> Optional[float]:
    """Top of the nearest text line lined up above the widget within HEADER_PT: a table's column header,
    printed once over the first row, has to be in the crop for a cell fifteen rows down."""
    above = []
    for bb, _ in lines:
        if bb[3] <= rect[1] + 2 and rect[1] - bb[3] <= HEADER_PT:
            xo = max(0.0, min(rect[2], bb[2]) - max(rect[0], bb[0])) / max(min(rect[2] - rect[0], bb[2] - bb[0]), 1e-6)
            if xo >= 0.5:
                above.append((rect[1] - bb[3], bb[1]))
    return min(above)[1] if above else None


def crop_png(blank: Path, page_no: int, rect, *, dpi: int = DPI) -> bytes:
    """The rendered blank around the widget, full page width, the widget outlined in red. The crop reaches up to
    the nearest lined-up line above the widget (a column header) when that is farther than PAD_UP."""
    doc = pymupdf.open(str(blank))
    try:
        page = doc[page_no - 1]
        r = pymupdf.Rect(*rect)
        top = r.y0 - PAD_UP
        ht = _header_top(rect, _lines(page))
        if ht is not None and ht - 8 < top:
            top = ht - 8
        clip = pymupdf.Rect(page.rect.x0, max(page.rect.y0, top), page.rect.x1, min(page.rect.y1, r.y1 + PAD_DOWN))
        page.draw_rect(r, color=(1, 0, 0), width=1.4)
        return page.get_pixmap(dpi=dpi, clip=clip).tobytes("png")
    finally:
        doc.close()


# ---------------------------------------------------------------- contest

def publisher_text(spec: dict, limits: dict[str, dict]) -> str:
    """The publisher's words for the widget: the tooltip and the readable tail of the AcroForm path."""
    w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
    path = w.get("path") or ""
    tail = re.sub(r"\[\d+\]", "", path.split(".")[-1])
    tooltip = (limits.get(path) or {}).get("tooltip") or ""
    return f"{tooltip} {tail}".strip()


def contested_because(spec: dict, chain_rec: Optional[dict], limits: dict[str, dict]) -> Optional[str]:
    """Why a rename on this field needs the adjudicator, or None when the chain settles it."""
    rec = chain_rec or {}
    verified = rec.get("verified")
    if verified is False:
        return "the classifier's caption for the box is not the text at the widget"
    if verified is None:
        return "no caption could be verified at the widget"
    caption = rec.get("caption_classifier") or ""
    pub = publisher_text(spec, limits)
    pt, ct = tokens(pub), tokens(caption)
    if pt and ct and not (pt & ct):
        return f"the publisher's tooltip / path ({pub!r}) and the caption ({caption!r}) disagree"
    return None


# ------------------------------------------------------------------ model

def _client():
    from petey.synth.generate import make_client
    return make_client(MODEL)


def ask(client, model: str, png: bytes, *, field: str, proposed: str, reason: str, spec: dict,
        publisher: str, page_no: int, tag: str = "adjudicate") -> tuple[dict, dict]:
    """One call. Returns (answer, usage); on a refusal or a parse failure the answer is `unclear`."""
    facts = {
        "current_name": field, "proposed_name": proposed, "reviewer_reason": reason[:400],
        "publisher_tooltip_or_field_name": publisher or None,
        "current_description": (spec.get("description") or "")[:200] or None,
        "current_type": spec.get("type"), "page": page_no,
    }
    user = ("The box outlined in red is the field. Facts about it (the names are the two candidates; the "
            "reviewer's reason is an argument, not evidence):\n"
            + json.dumps({k: v for k, v in facts.items() if v is not None}, ensure_ascii=False)
            + "\n\nWhat would a filer write in the outlined box, and which name describes it? Return JSON.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                            "data": base64.standard_b64encode(png).decode("ascii")}},
               {"type": "text", "text": user}]
    kwargs: dict[str, Any] = dict(model=model, max_tokens=4000, system=SYSTEM,
                                  messages=[{"role": "user", "content": content}],
                                  output_config={"format": {"type": "json_schema", "schema": SCHEMA}})
    t0 = time.time()
    resp = client.messages.create(**kwargs)
    text = next((b.text for b in resp.content if getattr(b, "type", None) == "text"), "")
    usage = {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens,
             "stop_reason": resp.stop_reason, "model_served": resp.model}
    try:
        from petey.label import call_log
        call_log.record(f"{tag}/{model}", raw=text, finish_reason=resp.stop_reason,
                        request={"model": model, "field": field, "proposed": proposed},
                        usage={k: usage[k] for k in ("input_tokens", "output_tokens")}, elapsed=time.time() - t0)
    except Exception:
        pass
    try:
        ans = json.loads(text)
        if ans.get("verdict") not in ("current", "proposed", "unclear"):
            raise ValueError("bad verdict")
    except (json.JSONDecodeError, ValueError, AttributeError):
        ans = {"verdict": "unclear", "box_holds": None, "reason": f"no usable answer ({resp.stop_reason}): {text[:80]}"}
    return ans, usage


def adjudicate_decisions(bp: dict, blank: Path, decisions: list[dict], chain: dict[str, dict], *,
                         limits: dict[str, dict], model: str = MODEL, client=None, force: bool = False,
                         crop_dir: Optional[Path] = None, tag: str = "adjudicate") -> dict:
    """Judge every proposed rename the chain does not settle. Decisions are edited in place: a rename that is not
    upheld loses its `name` (the rest of the decision stands) and every adjudicated decision carries
    `adjudication` for `apply_decisions` to record. Returns the tally, usage and per-field records."""
    fields = bp.get("fields") or {}
    tally: collections.Counter = collections.Counter()
    usage_total: collections.Counter = collections.Counter()
    records = []
    for d in decisions:
        field, proposed = d.get("field"), d.get("name")
        if d.get("verdict") != "fix" or not proposed or proposed == field or field not in fields:
            continue
        spec = fields[field]
        why = contested_because(spec, chain.get(field), limits)
        if why is None and not force:
            tally["settled"] += 1
            continue
        w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
        if not (w.get("rect") and w.get("page")):
            tally["no_rect"] += 1
            continue
        if client is None:
            client = _client()
        png = crop_png(blank, w["page"], w["rect"])
        if crop_dir is not None:
            crop_dir.mkdir(parents=True, exist_ok=True)
            (crop_dir / f"{bp.get('name') or 'form'}__{field}.png").write_bytes(png)
        ans, usage = ask(client, model, png, field=field, proposed=proposed, reason=d.get("reason", ""),
                         spec=spec, publisher=publisher_text(spec, limits), page_no=w["page"], tag=tag)
        for k in ("input_tokens", "output_tokens"):
            usage_total[k] += usage.get(k, 0)
        usage_total["calls"] += 1
        verdict = ans["verdict"]
        tally[verdict] += 1
        d["adjudication"] = {"verdict": verdict, "box_holds": ans.get("box_holds"), "reason": ans.get("reason", "")[:300],
                             "proposed": proposed, "model": model, "contested": why or "forced"}
        if verdict != "proposed":
            d["name"] = None
        records.append({"field": field, "proposed": proposed, **d["adjudication"]})
    pin, pout = PRICES.get(model, (0.0, 0.0))
    cost = usage_total["input_tokens"] / 1e6 * pin + usage_total["output_tokens"] / 1e6 * pout
    return {"model": model, "tally": dict(tally), "usage": dict(usage_total), "cost_usd": round(cost, 4),
            "records": records}


# -------------------------------------------------------------------- cli

def main() -> int:
    from petey.paths import BLUEPRINTS, RUNS
    from petey.synth.local import widget_limits
    from petey.validate.retype import resolve_blank
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True)
    ap.add_argument("--field", required=True)
    ap.add_argument("--proposed", required=True)
    ap.add_argument("--reason", default="")
    ap.add_argument("--bpt", type=Path, default=None)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--crop", type=Path, default=None, help="also write the crop the model saw")
    args = ap.parse_args()
    bp_path = args.bpt or (BLUEPRINTS / f"{args.form}.bpt")
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
    blank = resolve_blank(bp)
    if blank is None:
        raise SystemExit(f"{args.form}: blank PDF not found")
    d = {"field": args.field, "verdict": "fix", "name": args.proposed, "reason": args.reason}
    res = adjudicate_decisions(bp, blank, [d], {}, limits=widget_limits(blank), model=args.model, force=True,
                               crop_dir=args.crop.parent if args.crop else None)
    if args.crop and res["records"]:
        src = (args.crop.parent / f"{bp.get('name') or 'form'}__{args.field}.png")
        if src.exists():
            src.replace(args.crop)
    print(json.dumps(res, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
