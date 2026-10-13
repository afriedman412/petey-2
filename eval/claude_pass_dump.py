"""A form's fields as one reading-order file, for a model to review names and types against what the form says
(2026-10-13, Andrew: 'go through the forms and fix fields as you know them'; the proposals are applied by
eval/claude_pass_apply.py and checked by Andrew on the review page).

One line per field, in page and reading order: name, type / semantic type / pattern, the publisher's tooltip, the
text printed at the box, the description, what the name check says, and Andrew's own verdict and note. Option
groups list their options (key and caption).

    PYTHONPATH=. venv/bin/python eval/claude_pass_dump.py lib__faa8710 [more ids]   # -> runs/claude_pass/<id>.txt
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from petey.paths import RUNS
from petey.validate import witness as W

OUT = RUNS / "claude_pass"


def dump(bid: str) -> Path:
    v = json.loads((RUNS / "hand_review" / f"{bid}.json").read_text())
    bpt = Path(v["blueprint"])
    bp = W._load(bpt)
    res = W.witnesses(bpt, use_run=False)
    blank = W.resolve_blank(bp)
    words = W.publisher_words(blank)
    lines = W._page_lines(str(blank))
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}

    def where(s):
        w = s.get("widget") or next(iter((s.get("widgets") or {}).values()), {})
        r = w.get("rect") or [0, 0, 0, 0]
        return (w.get("page") or 0, round(r[1] / 6), r[0])

    out = [f"# {bid}  ({bpt.name}, {len(fields)} fields; form: {bp.get('name') or ''})", ""]
    for n in sorted(fields, key=lambda n: where(fields[n])):
        s = fields[n]
        p, _, _ = where(s)
        typ = "/".join(str(x) for x in (s.get("type"), s.get("semantic_type"), s.get("pattern")) if x)
        tip = " | ".join(W.publisher_texts(s, words))[:220]
        printed = " | ".join(W.page_texts(s, lines))[:160]
        flag = ""
        pub = (res["fields"].get(n) or {}).get("witnesses", {}).get("publisher")
        if pub and pub[0] is False:
            flag = pub[1][-120:]
        rec = (v.get("verdicts") or {}).get(n) or {}
        andrew = ""
        if rec and not (rec.get("note") or "").startswith(("auto:", "bulk")):
            andrew = f"{rec.get('verdict')}{': ' + rec['note'][:120] if rec.get('note') else ''}"
        row = [f"p{p} {n}", f"type={typ}", f"tooltip={tip!r}" if tip else "", f"printed={printed!r}" if printed else "",
               f"desc={(s.get('description') or '')[:120]!r}" if s.get("description") else "",
               f"CHECK={flag!r}" if flag else "", f"ANDREW={andrew!r}" if andrew else ""]
        if s.get("widgets"):
            declared = ((s.get("x_petey_xfa") or {}).get("choices")) or {}
            opts = "; ".join(f"{k}={(w.get('caption') or '')[:50]!r}"
                             + ("(LOCKED: xfa)" if k in declared or w.get("x_petey_caption_source") == "xfa" else
                                "(LOCKED: hand)" if w.get("x_petey_caption_source") == "hand" else "")
                             + (f"<tooltip {(words.get(w.get('path') or '') or [''])[0][:70]!r}>" if words.get(w.get("path") or "") else "")
                             for k, w in s["widgets"].items())
            row.append(f"options=[{opts[:900]}]")
        out.append("  ".join(x for x in row if x))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{bid}.txt"
    path.write_text("\n".join(out) + "\n")
    return path


if __name__ == "__main__":
    for bid in sys.argv[1:]:
        print(dump(bid), file=sys.stderr)
