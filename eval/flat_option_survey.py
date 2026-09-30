"""What does the flat-form geometry finder see on the corpus's genuinely flat forms?

For every PDF without an AcroForm layer, run step2flat and count its box
candidates, then cluster same-size boxes that line up in a row or a column
with small spacing: the layout signature of an option group. This is the
observed side of the flat-form blind spot; eval/flat_radio_recall.py gives
the finder's recall on forms whose groups are known.

    PYTHONPATH=. venv/bin/python eval/flat_option_survey.py [--limit N]
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from step2flat import pipeline  # noqa: E402
from petey.paths import RUNS, SOURCE_PDFS  # noqa: E402


def clusters(boxes: list[dict], gap: float = 90.0) -> list[list[dict]]:
    """Groups of >= 2 boxes of about the same size on one page, aligned in a
    row (same y band) or a column (same x band), neighbours closer than `gap`."""
    out = []
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for b in boxes:
        by_page[int(b["page"])].append(b)
    for page, bs in by_page.items():
        used = set()
        for i, a in enumerate(bs):
            if i in used:
                continue
            ax0, ay0, ax1, ay1 = a["rect"]
            aw, ah = ax1 - ax0, ay1 - ay0
            row = [i]; col = [i]
            for j, b in enumerate(bs):
                if j == i or j in used:
                    continue
                bx0, by0, bx1, by1 = b["rect"]
                bw, bh = bx1 - bx0, by1 - by0
                if abs(bw - aw) > 2.5 or abs(bh - ah) > 2.5:
                    continue
                if abs(by0 - ay0) < 3 and abs(bx0 - ax0) < gap * 4:
                    row.append(j)
                elif abs(bx0 - ax0) < 3 and abs(by0 - ay0) < gap * 4:
                    col.append(j)
            best = row if len(row) >= len(col) else col
            if len(best) >= 2:
                # keep only members whose nearest neighbour in the run is within `gap`
                mem = sorted(best, key=lambda k: (bs[k]["rect"][0], bs[k]["rect"][1]))
                keep = [mem[0]]
                for k in mem[1:]:
                    p, q = bs[keep[-1]]["rect"], bs[k]["rect"]
                    d = min(abs(q[0] - p[0]), abs(q[1] - p[1])) if best is col else abs(q[0] - p[0])
                    d = abs(q[1] - p[1]) if best is col else abs(q[0] - p[0])
                    if d <= gap:
                        keep.append(k)
                if len(keep) >= 2:
                    used.update(keep)
                    out.append([bs[k] for k in keep])
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    survey = json.load(open(RUNS / "source_survey.json"))
    flat = [r["file"] for r in survey if not r.get("error") and r.get("widgets") == 0]
    if args.limit:
        flat = flat[: args.limit]
    rows = []
    for i, name in enumerate(flat):
        hits = list(SOURCE_PDFS.rglob(Path(name).name))
        if not hits:
            continue
        try:
            kept, scored = pipeline.run(str(hits[0]))
        except Exception as e:
            rows.append({"pdf": name, "error": str(e)[:80]}); continue
        boxes = [r for r in kept if r["kind"] in ("radio", "checkbox")]
        cl = clusters(boxes)
        rows.append({"pdf": name, "boxes": len(boxes), "ovals": sum(1 for b in boxes if b["kind"] == "radio"),
                     "clusters": len(cl), "cluster_sizes": sorted(collections.Counter(len(c) for c in cl).items()),
                     "boxes_in_clusters": sum(len(c) for c in cl), "text_fields": sum(1 for r in kept if r["kind"] in ("text", "comb"))})
        if i % 20 == 0:
            print(f"  {i}/{len(flat)}", flush=True)
    (RUNS / "flat_option_survey.json").write_text(json.dumps(rows, indent=1))
    ok = [r for r in rows if "boxes" in r]
    with_boxes = [r for r in ok if r["boxes"]]
    with_cl = [r for r in ok if r["clusters"]]
    print(f"\n{len(ok)} flat forms read ({len(rows) - len(ok)} errors); {len(with_boxes)} have box candidates, "
          f"{len(with_cl)} have aligned same-size runs (candidate option groups)")
    print(f"boxes {sum(r['boxes'] for r in ok)}, ovals {sum(r['ovals'] for r in ok)}, candidate groups {sum(r['clusters'] for r in ok)}, "
          f"boxes in them {sum(r['boxes_in_clusters'] for r in ok)}")
    sizes = collections.Counter()
    for r in ok:
        for s, n in r["cluster_sizes"]:
            sizes[s] += n
    print("group sizes:", dict(sorted(sizes.items())))
    for r in sorted(with_cl, key=lambda r: -r["clusters"])[:12]:
        print(f"  {r['pdf'][:40]:40s} boxes={r['boxes']:3d} groups={r['clusters']:3d} sizes={r['cluster_sizes']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
