"""Cross-PDF layout clustering plus identity evidence, for the source corpus.

Two questions about a pile of 481 source PDFs, answered in one pass because
they need the same read of each file:

**How many distinct layouts are actually in here?** The registry dedups on
`sha256`, which found 2 duplicates in 481 — the weak form of the check. Two
agency PDFs of the same form differing only by a revision stamp hash
differently and are structurally the same document. Labeling costs one LLM
call per page, so paying it 84 times for one layout buys one structural
sample and 83 copies of it.

**What form is this?** 365 of the 481 are unidentified. Nothing here
identifies a form — it extracts the evidence a human or a model needs to:
OMB number, printed form number, title, revision. `omb` in particular is a
near-unique key assigned by an agency, so where it is present the
identification is close to free.

## Similarity

Layout signature is widget geometry, reusing `_page_signature.py` so both
dedup paths share one definition: a page is the set of
`(x, y, w, h, widget_type)` tuples, compared by Jaccard. That module asks
it of pages within one PDF (1099-R Copy A/B/C); this asks it of PDFs.

Documents are compared page-for-page in order, since revisions rarely
reorder pages, and the mean is scaled by the page-count ratio so a form
with an appendix does not match its own shorter edition for free.

Two exact bounds make all-pairs cheap enough to skip any index: Jaccard
cannot exceed the ratio of set sizes, so a pair whose widget counts differ
by more than the threshold cannot match, and neither can a pair whose page
counts do.

## Scope

Widget geometry, so this sees AcroForm PDFs — 348 of the 481. Flat scans
cluster on nothing here and are reported as `no_widgets` rather than
silently collapsed into one giant group.

Read-only: emits JSON for the registry to import, writes nothing itself.

Usage:
    python form_fingerprint.py
    python form_fingerprint.py --min-cluster 2 --verbose
    python form_fingerprint.py --out runs/fingerprints.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import pymupdf

from petey.label.page_signature import _jaccard, _widget_sig

from petey.paths import REPO, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# Same default as `_page_signature.py`. Looser than exact match, tighter
# than "any overlap" — and deliberately identical so a layout judged the
# same form here is judged the same form there.
DEFAULT_THRESHOLD = 0.85

# Identity evidence is printed near the top of page 1 on essentially every
# government form. Reading the whole page invites picking up instruction
# prose that happens to name another form.
IDENTITY_HEAD_CHARS = 1800

# A title span shorter than this is a stray label, not a form title.
MIN_TITLE_CHARS = 8

OMB_RE = re.compile(r"OMB\s*(?:No\.?|Number|Control\s*No\.?)\s*[:.]?\s*"
                    r"(\d{4}\s*-\s*\d{4})", re.I)
FORM_RE = re.compile(r"\bForm\s+((?:[A-Z]{1,4}[- ]?)?\d{1,5}[A-Z\-]{0,6}"
                     r"|W-\d[A-Z\-]*|I-\d{2,4}|SS-\d)\b")
SCHEDULE_RE = re.compile(r"\bSCHEDULE\s+([A-Z0-9][A-Z0-9\-]{0,3})\b")
REV_RE = re.compile(r"\(\s*Rev\.?\s*([A-Za-z]+\.?\s*\d{4}|\d{1,2}[-/]\d{4})"
                    r"\s*\)", re.I)


def identity_evidence(page) -> dict:
    """Printed identifiers from the top of a page. Evidence, not a verdict."""
    head = page.get_text()[:IDENTITY_HEAD_CHARS]
    flat = " ".join(head.split())

    omb = OMB_RE.search(flat)
    form = FORM_RE.search(flat)
    sched = SCHEDULE_RE.search(flat)
    rev = REV_RE.search(flat)

    # Title: the largest type on the page, which is what a form uses for
    # its own name. Ties broken by reading order.
    title, best_size = None, 0.0
    try:
        for block in page.get_text("dict").get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = " ".join(span.get("text", "").split())
                    if len(txt) < MIN_TITLE_CHARS:
                        continue
                    if span.get("size", 0) > best_size:
                        best_size, title = span["size"], txt
    except Exception:
        pass

    return {
        "omb": re.sub(r"\s", "", omb.group(1)) if omb else None,
        "form_no": form.group(1).strip() if form else None,
        "schedule": sched.group(1) if sched else None,
        "revision": " ".join(rev.group(1).split()) if rev else None,
        "title": title,
    }


def fingerprint(path: Path) -> dict:
    try:
        doc = pymupdf.open(str(path))
    except Exception as e:
        return {"path": str(path), "error": f"{type(e).__name__}: {e}"[:90]}
    sigs: list[set] = []
    ident: dict = {}
    try:
        for i, page in enumerate(doc):
            ws = [{"rect": tuple(w.rect), "widget_type": w.field_type_string}
                  for w in page.widgets()]
            sigs.append({_widget_sig(w) for w in ws})
            if i == 0:
                ident = identity_evidence(page)
    except Exception as e:
        doc.close()
        return {"path": str(path), "error": f"{type(e).__name__}: {e}"[:90]}
    doc.close()

    return {
        "path": str(path),
        "file": path.name,
        "vertical": path.parent.name,
        "pages": len(sigs),
        "widgets": sum(len(s) for s in sigs),
        "identity": ident,
        "_sigs": sigs,
    }


def layout_similarity(a: list[set], b: list[set], threshold: float) -> float:
    """Page-aligned mean Jaccard, scaled by page-count agreement."""
    n, m = min(len(a), len(b)), max(len(a), len(b))
    if m == 0 or n / m < threshold:
        return 0.0
    total = sum(_jaccard(a[i], b[i]) for i in range(n))
    return (total / n) * (n / m)


def cluster(records: list[dict], threshold: float) -> None:
    """Assign `cluster` to each record in place, by union-find."""
    parent = list(range(len(records)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i, a in enumerate(records):
        for j in range(i + 1, len(records)):
            b = records[j]
            # Jaccard cannot exceed the ratio of set sizes, so a large
            # disparity in widget count rules the pair out exactly.
            lo, hi = sorted((a["widgets"], b["widgets"]))
            if hi == 0 or lo / hi < threshold:
                continue
            if find(i) == find(j):
                continue
            if layout_similarity(a["_sigs"], b["_sigs"], threshold) >= threshold:
                union(i, j)

    labels: dict[int, int] = {}
    for i, r in enumerate(records):
        root = find(i)
        r["cluster"] = labels.setdefault(root, len(labels))


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", type=Path, default=SOURCE_PDFS)
    ap.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ap.add_argument("--min-cluster", type=int, default=2,
                    help="only list clusters at least this large")
    ap.add_argument("--verbose", action="store_true",
                    help="list every member of each listed cluster")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    pdfs = sorted(args.src.rglob("*.pdf"))
    if not pdfs:
        print(f"no PDFs under {args.src}", file=sys.stderr)
        return 1

    all_recs = [fingerprint(p) for p in pdfs]
    errors = [r for r in all_recs if r.get("error")]
    flat = [r for r in all_recs if not r.get("error") and r["widgets"] == 0]
    recs = [r for r in all_recs if not r.get("error") and r["widgets"] > 0]

    cluster(recs, args.threshold)

    groups = collections.defaultdict(list)
    for r in recs:
        groups[r["cluster"]].append(r)
    dupes = {k: v for k, v in groups.items() if len(v) >= args.min_cluster}

    print(f"{len(all_recs)} PDFs — {len(recs)} with widgets, "
          f"{len(flat)} flat, {len(errors)} unreadable")
    print(f"{len(groups)} distinct layouts at threshold {args.threshold}")
    collapsed = len(recs) - len(groups)
    print(f"{collapsed} PDFs are near-duplicates of another "
          f"({collapsed / max(len(recs), 1):.0%} of the fillable corpus)")

    ident = [r for r in recs if r["identity"].get("omb")
             or r["identity"].get("form_no")]
    omb = [r for r in recs if r["identity"].get("omb")]
    print(f"\nidentity evidence: {len(omb)} carry an OMB number, "
          f"{len(ident)} carry OMB or a form number "
          f"({len(ident) / max(len(recs), 1):.0%})")

    if dupes:
        print(f"\nclusters of {args.min_cluster}+ "
              f"({sum(len(v) for v in dupes.values())} PDFs):")
        for k, v in sorted(dupes.items(), key=lambda kv: -len(kv[1])):
            head = v[0]["identity"]
            name = head.get("form_no") or head.get("title") or v[0]["file"]
            verts = ",".join(sorted({r["vertical"] for r in v}))
            print(f"  [{len(v):>3}] {str(name)[:44]:<44} {verts}")
            if args.verbose:
                for r in v:
                    print(f"        {r['file']}")

    by_vert = collections.Counter(r["vertical"] for r in recs)
    uniq_vert = collections.Counter()
    for v in groups.values():
        uniq_vert[v[0]["vertical"]] += 1
    print(f"\n{'vertical':<16}{'pdfs':>6}{'layouts':>9}")
    for vert, n in by_vert.most_common():
        print(f"{vert:<16}{n:>6}{uniq_vert.get(vert, 0):>9}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        for r in all_recs:
            r.pop("_sigs", None)
        args.out.write_text(json.dumps(all_recs, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
