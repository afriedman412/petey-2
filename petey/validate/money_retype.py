"""Amounts typed `money_whole_dollar` become plain `money` unless the form asks for whole dollars (Andrew, 2026-10-07).

The labeler's slug rule gave every `_amt` / `_amount` field `money_whole_dollar`; the spec registers plain `money`
too, and most amounts take cents. A field keeps `money_whole_dollar` when whole dollars are asked for: its own text
(description or tooltip) says so, a cents box (a text box named or described as cents) sits right beside it, or its
page tells the filer to round to whole dollars ("may round" does not count). Every other one becomes type `number`,
semantic type `money`, with `money` added to `x_petey_retype`.

The file changes, so the review records that matched it are moved to the new sha (as `field_ids` does), and the page
check's verdicts on the retyped fields are re-keyed to the new definitions (its verdicts are tied to the definition
hash; money vs whole dollars changes no verdict).

    PYTHONPATH=. venv/bin/python -m petey.validate.money_retype            # what would change
    PYTHONPATH=. venv/bin/python -m petey.validate.money_retype --write
"""
from __future__ import annotations

import argparse
import collections
import json
import re

import yaml

from petey.paths import RUNS
from petey.validate import field_ids, hand_review
from petey.validate.retype import resolve_blank

WHOLE = re.compile(r"whole[- ]dollar|nearest (whole )?dollar|round(ed|ing| off)?\b[^.]{0,40}dollar|omit cents|no cents|"
                   r"without cents|dollars only|drop(ping)? cents", re.I)
MAY = re.compile(r"\bmay\b[^.]{0,30}round", re.I)
CENTS = re.compile(r"cent|\bcts\b|_cts\b", re.I)


def keep_reason(name: str, spec: dict, fields: dict, tooltips: dict, page_text) -> str:
    """Why this field stays `money_whole_dollar`, or '' when it becomes `money`."""
    w = spec.get("widget") or {}
    own = " ".join(str(x) for x in (spec.get("description"), (tooltips.get(w.get("path") or "") or {}).get("tooltip")) if x)
    if WHOLE.search(own):
        return "field text: " + WHOLE.search(own).group(0)
    r, pg = w.get("rect"), w.get("page")
    if r and pg:
        for m, t in fields.items():
            tw = (t.get("widget") or {}) if isinstance(t, dict) else {}
            tr = tw.get("rect")
            if (m != name and tw.get("page") == pg and tw.get("widget_type") == "text" and tr and 0 <= tr[0] - r[2] <= 8
                    and abs((tr[1] + tr[3]) / 2 - (r[1] + r[3]) / 2) < 4 and (tr[2] - tr[0]) < 30
                    and (CENTS.search(m) or CENTS.search((tooltips.get(tw.get("path") or "") or {}).get("tooltip") or ""))):
                return "cents box: " + m
        t = page_text(pg)
        if t and WHOLE.search(t) and not MAY.search(t):
            return "page: " + WHOLE.search(t).group(0)
    return ""


def _rekey(bp: dict, moved: dict[str, tuple[str, str]]) -> int:
    """Re-key the page check's verdicts on the retyped fields from the old definition hash to the new one."""
    st = bp.get("x_petey_page_check") or {}
    rp = RUNS.parent / st["record"] if st.get("record") else None
    if rp is None or not rp.exists() or not moved:
        return 0
    rec = json.loads(rp.read_text(encoding="utf-8"))
    blocks = [r.get("page_check") or {} for r in rec.get("rounds") or []] if "rounds" in rec else [rec.get("fields") or {}]
    n = 0
    for block in blocks:
        for name, (old, new) in moved.items():
            v = block.get(name)
            if isinstance(v, dict) and v.get("spec") == old:
                v["spec"] = new
                n += 1
    if n:
        rp.write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    return n


def run(write: bool) -> dict:
    import pymupdf
    from petey.synth.local import widget_limits
    from petey.validate.page_check import spec_hash
    out = collections.Counter()
    kept = collections.Counter()
    for bid, p in hand_review.blueprint_paths().items():
        bp = hand_review._load(p)
        fields = bp.get("fields") or {}
        hits = [n for n, s in fields.items() if isinstance(s, dict) and s.get("semantic_type") == "money_whole_dollar"]
        if not hits:
            continue
        blank = resolve_blank(bp)
        doc = pymupdf.open(str(blank)) if blank and blank.exists() else None
        tips = widget_limits(blank) if doc else {}
        pages: dict[int, str] = {}

        def page_text(pg):
            if doc is None or not (1 <= pg <= len(doc)):
                return ""
            if pg not in pages:
                pages[pg] = doc[pg - 1].get_text()
            return pages[pg]

        moved = {}
        for n in hits:
            why = keep_reason(n, fields[n], fields, tips, page_text)
            if why:
                kept[why.split(":")[0]] += 1
                continue
            old = spec_hash(fields[n])
            s = fields[n]
            s["type"], s["semantic_type"] = "number", "money"
            s["x_petey_retype"] = list(s.get("x_petey_retype") or []) + ["money"]
            moved[n] = (old, spec_hash(s))
        if doc is not None:
            doc.close()
        out["fields"] += len(moved)
        out["blueprints"] += bool(moved)
        if write and moved:
            sha = hand_review._sha(p)
            p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
            for t in field_ids._rehash(bid, sha, hand_review._sha(p)):
                out[f"records rehashed: {t}"] += 1
            out["page-check verdicts re-keyed"] += _rekey(bp, moved)
    return {"changed": dict(out), "kept as whole dollars": dict(kept)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--write", action="store_true")
    print(json.dumps(run(ap.parse_args().write), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
