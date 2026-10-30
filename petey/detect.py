"""Which library blueprint does a filled PDF belong to? Two reads, no model.

    text      the share of the blank's printed word trigrams (3+ letter words, lower case, within one text line)
              found in the filled PDF. Filling adds words and removes none, so the blank is contained in its own
              filled copy; this reads flattened and printed-to-PDF fills as well as fillable ones. Trigrams stop at
              line ends because filled values land between label lines and would break trigrams that span them.
    widgets   the share of a blueprint's widget paths present among the PDF's field names. Used only for blanks
              with too little printed text to read (CMS-1500 draws its labels; OSHA 300A, K-1): on its own it
              cannot tell forms apart, since IRS forms share generic names (`f1_1[0]`), and an unrelated form
              matched a small blueprint's paths at 0.92.

Below both bars the PDF is not a library form and no blueprint is returned (extracting with the wrong one gives
confident garbage); the closest form is returned as `runner_up` so a near miss shows.

The library holds some forms twice (`f1099nec` and `1099_nec_blank`: one registry form, two blueprints). Those
tie, and the tie goes to the blueprint with the most hand-review accepts, then the most fields, so the one Andrew
has checked is the one used.

Measured 2026-10-07 on one or two filled cases per library form from runs/ (136 intact, 104 flattened) and 300
blanks with no library blueprint: the true form scored >= 0.994 on every case but DA-4187 (0.70: its blank is a
template whose sample text the fill replaces); the best unrelated form scored 0.915 (a tax booklet that contains
GA 500). Variants of a library form still match it: H-12P (0.997, H-12) and MCS-150B (0.989, MCS-150).

    PYTHONPATH=. venv/bin/python -m petey.detect filled.pdf [...]
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import pymupdf
import yaml

from petey.paths import BLUEPRINTS, REPO
from petey.validate.hand_review import load_verdicts
from petey.validate.retype import resolve_blank

TEXT_BAR = 0.95         # share of the blank's line trigrams found in the PDF
MIN_GRAMS = 40          # a blank with fewer line trigrams has too little text for the text read
WIDGET_BAR = 0.9        # share of a blueprint's widget paths among the PDF's field names
TIE = 0.02              # scores this close are the same form (duplicate blueprints)
WORD = re.compile(r"[a-z]{3,}")
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)     # libyaml: the index reads every blueprint


def _trigrams(doc: pymupdf.Document) -> set[str]:
    """Word trigrams within each text line; a line of one or two words is kept whole."""
    out = set()
    for page in doc:
        for line in page.get_text().lower().splitlines():
            ws = WORD.findall(line)
            n = min(3, len(ws))
            if n:
                out |= {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}
    return out


def _widget_paths(bp: dict) -> set[str]:
    out = set()
    for f in (bp.get("fields") or {}).values():
        if not isinstance(f, dict):
            continue
        for w in [f.get("widget")] + list((f.get("widgets") or {}).values()):
            if isinstance(w, dict) and w.get("path"):
                out.add(w["path"])
    return out


@dataclass
class Entry:
    stem: str
    path: Path
    form_id: Optional[str]
    title: Optional[str]
    fields: int
    accepted: int
    paths: set[str] = field(repr=False)
    trigrams: set[str] = field(repr=False)


def _label(form_id: str) -> str:
    """`schedule_se` -> `Schedule SE`: short tokens read as abbreviations."""
    return " ".join(w.upper() if len(w) <= 3 and not w.isdigit() else w.capitalize() for w in form_id.split("_"))


def _registry() -> tuple[dict[str, str], dict[str, str]]:
    """{blueprint stem: form_id} and {form_id: display title}. The title is the registry's when it has one (5 of
    138 library forms on 2026-10-07), else issuer and printed number from the identity (`IRS 1099-DIV`), else the
    form id spelled out."""
    db = REPO / "registry" / "registry.db"
    if not db.exists():
        return {}, {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        forms = {Path(p).stem: f for f, p in conn.execute(
            "SELECT form_id, path FROM artifacts WHERE kind IN ('bpt', 'draft')")}
        titles = {f: _label(f) for f in set(forms.values())}
        for f, issuer, number in conn.execute(
                "SELECT form_id, issuer, form_number FROM identities WHERE form_number IS NOT NULL AND form_number <> ''"):
            if f in titles:
                titles[f] = f"{issuer.upper()} {number.replace('_', '-').upper()}" if issuer else number
        titles.update({f: t for f, t in conn.execute("SELECT form_id, title FROM forms") if t and f in titles})
    finally:
        conn.close()
    return forms, titles


class Library:
    """The library blueprints, read once: widget paths, blank trigrams, registry form and title, review accepts."""

    def __init__(self, directory: Path = BLUEPRINTS) -> None:
        forms, titles = _registry()
        self.entries: list[Entry] = []
        for p in sorted(directory.glob("*.bpt")):
            bp = yaml.load(p.read_text(encoding="utf-8"), Loader=_LOADER) or {}
            blank = resolve_blank(bp)
            tri = set()
            if blank is not None:
                with pymupdf.open(str(blank)) as d:
                    tri = _trigrams(d)
            verdicts = (load_verdicts(f"lib__{p.stem}").get("verdicts") or {})
            fid = forms.get(p.stem)
            self.entries.append(Entry(
                stem=p.stem, path=p, form_id=fid, title=titles.get(fid) if fid else None,
                fields=len(bp.get("fields") or {}),
                accepted=sum(1 for v in verdicts.values() if v.get("verdict") == "accept"),
                paths=_widget_paths(bp), trigrams=tri))
        self.by_stem = {e.stem: e for e in self.entries}

    def detect(self, pdf: Path | str) -> dict:
        """{'blueprint', 'form_id', 'title', 'method', 'score', 'ties', 'runner_up'}; blueprint None when no read
        clears its bar. `runner_up` is the best other form, so a near miss shows."""
        with pymupdf.open(str(pdf)) as doc:
            names = {w.field_name for page in doc for w in (page.widgets() or []) if w.field_name}
            tri = _trigrams(doc)
        reads = []
        if tri:
            reads.append(("text", TEXT_BAR, {e.stem: len(tri & e.trigrams) / len(e.trigrams)
                                             for e in self.entries if len(e.trigrams) >= MIN_GRAMS}))
        if names:
            reads.append(("widgets", WIDGET_BAR, {e.stem: len(names & e.paths) / len(e.paths) for e in self.entries
                                                  if e.paths and (not tri or len(e.trigrams) < MIN_GRAMS)}))
        best_miss = None
        for method, bar, scores in reads:
            ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
            if not ranked:
                continue
            top = ranked[0][1]
            if top < bar:
                best_miss = best_miss or (method, ranked[0])
                continue
            tied = [self.by_stem[s] for s, v in ranked if top - v <= TIE]
            tied.sort(key=lambda e: (-e.accepted, -e.fields, e.stem))
            pick = tied[0]
            same = {e.stem for e in tied} | {e.stem for e in self.entries if pick.form_id and e.form_id == pick.form_id}
            other = next(((s, v) for s, v in ranked if s not in same), None)
            return {"blueprint": pick.stem, "form_id": pick.form_id, "title": pick.title, "method": method,
                    "score": round(top, 3), "ties": [e.stem for e in tied[1:]],
                    "runner_up": {"blueprint": other[0], "score": round(other[1], 3)} if other else None}
        out = {"blueprint": None, "form_id": None, "title": None, "method": None, "score": None, "ties": [],
               "runner_up": None}
        if best_miss:
            out["runner_up"] = {"blueprint": best_miss[1][0], "score": round(best_miss[1][1], 3),
                                "method": best_miss[0]}
        return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdfs", nargs="+", type=Path)
    args = ap.parse_args()
    t = time.time()
    lib = Library()
    print(f"[detect] {len(lib.entries)} blueprints read in {time.time() - t:.1f}s", file=sys.stderr)
    for p in args.pdfs:
        print(json.dumps({"pdf": str(p), **lib.detect(p)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
