"""Duplicate pages and duplicate forms from the page inventory (`eval/page_inventory.py`; Andrew, 2026-10-31:
"remove duplicate forms from library", "aggressive is fine"; "a bunch of duplicate *pages* across [forms]").

Two pages are the same page when

    their words are the same (20 words or more), or
    they look alike (image hashes at most HAM bits apart of 256) and share most words (Jaccard of their word sets at
    least JAC), or
    they look the same (HAM_IMAGE bits or fewer apart) with about as many words (within a tenth), whatever the
    words are (the text layer may be garbled); never for a page with little drawn on it (fewer than INK of the
    hash's bits set), as near-empty pages all look alike.

Pairs to compare come from the image hash cut in 8 bands (a pair shares a band exactly) and from equal text.
Two forms are the same form when they have as many pages and each page is the same as the other's page there; the
same blank file is the same form too. Groups are closed over pairs (a ~ b, b ~ c: one group).

    runs/inventory/dups.json    {"forms": [[review id, ...], ...], "pages": [[[review id, page], ...], ...]}
                                pages: groups across two or more forms not in one form group

    PYTHONPATH=. venv/bin/python eval/page_dups.py
"""
from __future__ import annotations

import collections
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "runs" / "inventory"
HAM, JAC, HAM_IMAGE, MIN_WORDS, INK = 40, 0.85, 12, 20, 24


def ham(a: str, b: str) -> int:
    return bin(int(a, 16) ^ int(b, 16)).count("1")


def jac(a: list, b: list) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def same_page(p: dict, q: dict) -> bool:
    if p["n_words"] >= MIN_WORDS and p["words_sha"] == q["words_sha"]:
        return True
    d = ham(p["dhash"], q["dhash"])
    if d <= HAM_IMAGE and min(ink(p), ink(q)) >= INK and abs(p["n_words"] - q["n_words"]) <= max(p["n_words"], q["n_words"]) / 10:
        return True
    return d <= HAM and p["n_words"] >= MIN_WORDS and q["n_words"] >= MIN_WORDS and jac(p["vocab"], q["vocab"]) >= JAC


def ink(p: dict) -> int:
    return bin(int(p["dhash"], 16)).count("1")


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def join(self, a, b):
        self.p[self.find(a)] = self.find(b)

    def groups(self):
        g = collections.defaultdict(list)
        for x in self.p:
            g[self.find(x)].append(x)
        return [sorted(v) for v in g.values() if len(v) > 1]


def page_pairs(blanks: dict) -> set:
    """{((blank, page), (blank, page))} the same page on two different blanks."""
    pages = {(k, p["page"]): p for k, b in blanks.items() for p in b["pages"]}
    cand = collections.defaultdict(set)
    for key, p in pages.items():
        h = f"{int(p['dhash'], 16):064x}"
        for i in range(8):
            cand[("band", i, h[i * 8:(i + 1) * 8])].add(key)
        if p["n_words"] >= MIN_WORDS:
            cand[("text", p["words_sha"])].add(key)
    seen, out = set(), set()
    for keys in cand.values():
        if len(keys) < 2 or len(keys) > 400:          # a band every blank page shares says nothing
            continue
        for a, b in itertools.combinations(sorted(keys), 2):
            if a[0] == b[0] or (a, b) in seen:
                continue
            seen.add((a, b))
            if same_page(pages[a], pages[b]):
                out.add((a, b))
    return out


def find(inv: Path = INV) -> dict:
    blanks = {b["blank"]: b for b in map(json.loads, (inv / "pages.jsonl").read_text().splitlines()) if b.get("pages")}
    forms = json.loads((inv / "forms.json").read_text())
    pairs = page_pairs(blanks)
    same = collections.defaultdict(set)                 # (blank a, blank b) -> pages of a matched at the same page
    for (ka, pa), (kb, pb) in pairs:
        if pa == pb:
            same[(ka, kb)].add(pa)
    bu = UF()
    for (ka, kb), pgs in same.items():
        if len(blanks[ka]["pages"]) == len(blanks[kb]["pages"]) == len(pgs):
            bu.join(ka, kb)
    of_blank = collections.defaultdict(list)
    for bid, k in forms.items():
        of_blank[k].append(bid)
    fu = UF()
    for bids in of_blank.values():                     # the same blank file
        for b in bids[1:]:
            fu.join(bids[0], b)
    for g in bu.groups():
        ids = [b for k in g for b in of_blank.get(k, [])]
        for b in ids[1:]:
            fu.join(ids[0], b)
    form_groups = fu.groups()
    grp = {b: i for i, g in enumerate(form_groups) for b in g}
    pu = UF()
    for (ka, pa), (kb, pb) in pairs:
        pu.join((ka, pa), (kb, pb))
    page_groups = []
    for g in pu.groups():
        refs = [[b, pg] for k, pg in g for b in of_blank.get(k, [])[:1]]
        if len({grp.get(b, b) for b, _ in refs}) > 1:   # across forms that are not one form
            page_groups.append(sorted(refs))
    out = {"forms": sorted(form_groups), "pages": sorted(page_groups)}
    (inv / "dups.json").write_text(json.dumps(out, indent=1))
    return out


def main() -> int:
    out = find()
    print(f"{len(out['forms'])} duplicate form groups ({sum(map(len, out['forms']))} forms), "
          f"{len(out['pages'])} pages shared across other forms ({sum(map(len, out['pages']))} copies)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
