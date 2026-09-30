"""Survey: how are option groups (radio buttons, checkbox clusters) encoded across the corpus?

Written before changing the emitter to per-option entries (2026-09-29): the
encoding must cover what the 646 PDFs actually do, not what one form does.

Per PDF, every button widget is grouped by its AcroForm field name; each
group is classified by kid count, on-state pattern and page spread. Output:
runs/radio_survey.json (per-group records) and a printed census.

    PYTHONPATH=. venv/bin/python eval/radio_survey.py [--limit N]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import pymupdf

from petey.paths import RUNS, SOURCE_PDFS

BTN = {"RadioButton", "CheckBox"}


def _onstate_pattern(states: list[str]) -> str:
    s = [x for x in states if x is not None]
    if not s:
        return "none"
    if len(set(s)) < len(s):
        return "duplicated" if len(set(s)) > 1 else "all_same"
    if all(re.fullmatch(r"\d+", x) for x in s):
        seq = sorted(int(x) for x in s)
        return "indices_0" if seq == list(range(len(seq))) else ("indices_1" if seq == list(range(1, len(seq) + 1)) else "numeric")
    if all(x.lower() in ("yes", "no", "y", "n", "true", "false") for x in s):
        return "yes_no_words"
    if all(x == "On" for x in s):
        return "all_On"
    return "words"


def survey_pdf(path: Path) -> list[dict]:
    try:
        doc = pymupdf.open(path)
    except Exception as e:  # unreadable file: record and move on
        return [{"pdf": path.name, "error": str(e)[:80]}]
    groups: dict[str, list] = collections.defaultdict(list)
    for pno in range(len(doc)):
        page = doc[pno]  # keep the page alive: widgets of a dropped page lose their on-state
        try:
            widgets = list(page.widgets())
        except Exception:
            continue
        for w in widgets:
            if w.field_type_string not in BTN:
                continue
            try:
                on = w.on_state()
            except Exception:
                on = None
            groups[w.field_name].append({
                "page": pno + 1, "type": w.field_type_string, "on": on,
                "flags": w.field_flags, "rect": [round(x, 1) for x in w.rect],
                "value": w.field_value,
            })
    out = []
    for name, kids in groups.items():
        states = [k["on"] for k in kids]
        types = sorted({k["type"] for k in kids})
        out.append({
            "pdf": path.name, "field": name, "n_kids": len(kids), "types": types,
            "pages": sorted({k["page"] for k in kids}),
            "on_states": states[:12], "pattern": _onstate_pattern(states),
            "radio_flag": bool(kids[0]["flags"] & (1 << 15)),
            "in_unison": bool(kids[0]["flags"] & (1 << 25)),
            "no_toggle_off": bool(kids[0]["flags"] & (1 << 14)),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    pdfs = sorted(SOURCE_PDFS.rglob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    recs: list[dict] = []
    for i, p in enumerate(pdfs):
        recs.extend(survey_pdf(p))
        if i % 100 == 0:
            print(f"  {i}/{len(pdfs)}", flush=True)
    (RUNS / "radio_survey.json").write_text(json.dumps(recs, indent=1))

    groups = [r for r in recs if "field" in r]
    multi = [r for r in groups if r["n_kids"] > 1]
    print(f"\n{len(pdfs)} PDFs, {len(groups)} button fields, {len(multi)} with more than one widget "
          f"({len({r['pdf'] for r in multi})} PDFs)")
    c = collections.Counter()
    for r in multi:
        kind = "radio" if r["radio_flag"] else "checkbox"
        c[(kind, r["pattern"], "multi_page" if len(r["pages"]) > 1 else "one_page")] += 1
    print("\nmulti-widget fields by (field kind, on-state pattern, page spread):")
    for k, v in c.most_common():
        print(f"  {v:5d}  {k}")
    single_radio = [r for r in groups if r["n_kids"] == 1 and r["radio_flag"]]
    print(f"\nradio-flagged fields with ONE widget: {len(single_radio)} in {len({r['pdf'] for r in single_radio})} PDFs")
    sizes = collections.Counter(r["n_kids"] for r in multi)
    print("kid counts:", dict(sorted(sizes.items())[:15]))
    odd = [r for r in multi if r["pattern"] in ("duplicated", "all_same", "all_On", "none")]
    print(f"\nodd on-state patterns: {len(odd)}; examples:")
    for r in odd[:12]:
        print(f"  {r['pdf'][:40]:40s} {r['field'][-40:]:40s} kids={r['n_kids']} {r['types']} {r['on_states'][:6]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
