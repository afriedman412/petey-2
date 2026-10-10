"""Read the printed caption beside each option box of the groups the page check flagged; report, do not write.

REVERTED 2026-10-07 (Andrew): applied once to T1 / T2 (671 option captions, 276 groups) and undone the same day.
It duplicates the labeler's caption cascade (`auto_label.caption_options`: the XFA's declared caption, then the
publisher's option value when it is a word, then page text), whose order is deliberate, and it overrode his choice
of no page-text captions when the group reviews were applied. A page-check `options` flag is a second reading, not
proof the cascade chose wrong. The pairs it found are in runs/judge_eval/caption_fix_reverted.json. Now report-only:
`--apply` is needed to write, and should not be used without Andrew's say-so.

The labeler takes an option's caption from nearby page text and often keeps a fragment ('applicable)',
'required)', 'd. ALLOWED'); the page check then flags the group (`options`). On T1 that was 117 of 211 flags, and
the loop cannot act on them (its reviewer renames and retypes only), so every one reached hand review (Andrew,
2026-10-07: fix them automatically, keep a record). For each option group whose current page-check verdict is an
`options` flag, this crops the blank around the group's boxes (outlined and lettered as the page check draws them),
asks a vision model for the caption printed beside each box, and writes the captions that differ into the
blueprint: per option `caption` (source `caption_fix`), and on the field `x_petey_caption_fix` {when, model, from,
to}. Names, types and membership are never touched. The run record (form_run) gets a `caption_fix` round, so
`form_run.state` still rebuilds the blueprint. A changed caption changes the field's definition, so the old flag no
longer applies; the new captions are not page-checked again here.

    PYTHONPATH=. venv/bin/python -m petey.validate.caption_fix runs/judge_eval/launch_t1.txt [--dry] [--model gemini-3.8-flash]
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import yaml

from petey.paths import RUNS
from petey.validate import page_check
from petey.validate.retype import resolve_blank

MODEL = "gemini-3.8-flash"
OUT = RUNS / "judge_eval" / "blueprints"
MARGIN_Y = 90                         # px above / below the group at the page check's ~200 dpi (~32 pt); full width,
                                      # since a caption can run far right of its box (a first try cut them at 150 pt)

SYSTEM = """You read checkbox and radio-button captions on a blank form. The image is part of the form; every box \
outlined in red is one option of the same question, labelled with a small red tag (1.a, 1.b, ...). For each \
labelled box, give the caption printed for that box: the words a filer reads to choose that option, exactly as \
printed beside it (usually just right of the box, sometimes left or below). Leave out the box's own item letter or \
number unless it is all there is, and leave out the question's heading. Use an empty string when nothing is \
printed for the box."""

SCHEMA = {"type": "object",
          "properties": {"captions": {"type": "array", "items": {
              "type": "object", "properties": {"box": {"type": "string"}, "caption": {"type": "string"}},
              "required": ["box", "caption"], "additionalProperties": False}}},
          "required": ["captions"], "additionalProperties": False}


def _norm(s: Optional[str]) -> str:
    """For comparing captions: case, spacing and punctuation do not count as a change."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def group_crop(blank: Path, name: str, spec: dict, page_no: int) -> tuple[bytes, dict[str, str]]:
    """The page around one group's boxes on `page_no`, only its boxes outlined and lettered. Returns (png,
    {label: on_state})."""
    from PIL import Image
    rows = page_check.numbered({"fields": {name: spec}})
    png, dpi, px = page_check.render(blank, page_no, rows)
    labels = {b["label"]: b["on_state"] for b in rows[0]["boxes"] if b["page"] == page_no}
    boxes = [px[lab] for lab in labels]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    im = Image.open(io.BytesIO(png))
    W, H = im.size
    crop = im.crop((0, max(0, y0 - MARGIN_Y), W, min(H, y1 + MARGIN_Y)))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue(), labels


def ask(client, model: str, png: bytes, labels: list[str]) -> dict[str, str]:
    resp = client.chat.completions.create(
        model=model, max_tokens=8000, reasoning_effort=page_check.REASONING_EFFORT,
        messages=[{"role": "system", "content": SYSTEM},
                  {"role": "user", "content": [
                      {"type": "image_url", "image_url": {"url": "data:image/png;base64,"
                                                          + base64.standard_b64encode(png).decode("ascii")}},
                      {"type": "text", "text": f"Boxes: {', '.join(labels)}. Return JSON."}]}],
        response_format={"type": "json_schema", "json_schema": {"name": "captions", "schema": SCHEMA}})
    try:
        return {c["box"]: c["caption"] for c in json.loads(resp.choices[0].message.content or "{}").get("captions") or []}
    except (json.JSONDecodeError, AttributeError, KeyError):
        return {}


def flagged_groups(bp: dict) -> list[str]:
    cur = page_check.verdicts(bp)
    return [n for n, v in cur.items() if v.get("verdict") == "flag" and v.get("problem") == "options"
            and (bp["fields"].get(n) or {}).get("widgets")]


def fix_form(form: str, *, model: str, client, dry: bool, log=print) -> dict:
    bpt = OUT / f"{form}.bpt"
    if not bpt.exists():
        return {"form": form, "skipped": "no blueprint"}
    bp = yaml.safe_load(bpt.read_text(encoding="utf-8")) or {}
    blank = resolve_blank(bp)
    names = flagged_groups(bp)
    if not names or blank is None:
        return {"form": form, "groups": 0}
    jobs = []
    for n in names:
        spec = bp["fields"][n]
        for pg in sorted({w["page"] for w in spec["widgets"].values() if w.get("page")}):
            png, labels = group_crop(blank, n, spec, pg)
            jobs.append((n, labels, png))
    with ThreadPoolExecutor(max_workers=8) as ex:
        answers = list(ex.map(lambda j: ask(client, model, j[2], list(j[1])), jobs))
    changed = {}
    for (n, labels, _), ans in zip(jobs, answers):
        spec = bp["fields"][n]
        for lab, on in labels.items():
            new = (ans.get(lab) or "").strip()
            old = spec["widgets"][on].get("caption")
            if new and _norm(new) != _norm(old):
                fix = changed.setdefault(n, {"from": {}, "to": {}})
                fix["from"][on], fix["to"][on] = old, new
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for n, fix in changed.items():
        log(f"  {form}.{n}: " + "; ".join(f"{fix['from'][o]!r} -> {fix['to'][o]!r}" for o in fix["to"]))
        if dry:
            continue
        spec = bp["fields"][n]
        for on, new in fix["to"].items():
            spec["widgets"][on]["caption"] = new
            spec["widgets"][on]["x_petey_caption_source"] = "caption_fix"
        spec["x_petey_caption_fix"] = {"when": now, "model": model, **fix}
    if changed and not dry:
        bpt.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                       encoding="utf-8")
        _record_round(bp, changed, now)
    return {"form": form, "groups": len(names), "fixed": len(changed),
            "options_changed": sum(len(f["to"]) for f in changed.values())}


def _record_round(bp: dict, changed: dict, now: str) -> None:
    """Append a `caption_fix` round to the form's run record, so `form_run.state` rebuilds the fixed blueprint."""
    run = (bp.get("x_petey_run") or {}).get("record")
    rp = RUNS.parent / run if run else None
    if rp is None or not rp.exists():
        return
    rec = json.loads(rp.read_text())
    rec["rounds"].append({"round": len(rec["rounds"]), "stage": "caption_fix", "when": now,
                          "changed": {n: bp["fields"][n] for n in changed}, "removed": [], "renamed": {}})
    rp.write_text(json.dumps(rec, indent=1, ensure_ascii=False, default=str))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("lists", type=Path, nargs="+", help="form lists (form|blank per line)")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--apply", action="store_true", help="write the captions (reverted 2026-10-07; ask Andrew first)")
    args = ap.parse_args()
    args.dry = not args.apply
    from petey.synth.generate import make_client
    client = make_client(args.model)
    forms = [ln.split("|")[0] for lst in args.lists for ln in lst.read_text().splitlines() if ln.strip()]
    tot = {"groups": 0, "fixed": 0, "options_changed": 0}
    for f in forms:
        r = fix_form(f, model=args.model, client=client, dry=args.dry)
        for k in tot:
            tot[k] += r.get(k, 0)
    print(f"{'(dry) ' if args.dry else ''}groups with a caption flag {tot['groups']}, groups changed {tot['fixed']}, "
          f"option captions changed {tot['options_changed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
