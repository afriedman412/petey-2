"""Compare the benchmark key and the tuning set with their copies from before a rebuild (the update-key skill).

    venv/bin/python .claude/skills/update-key/scripts/key_diff.py --before DIR [--key DIR] [--dev DIR] [--prune]

`--before` holds the copies made before the build: DIR/key/ and DIR/dev_key/, each with its index.json and page
JSONs. The live sets default to runs/benchmark/key and runs/benchmark/dev_key. For each set it prints forms and pages
before -> after, the forms and pages that came in, the pages that went out (none unless a page was ignored on the
review page since), the pages still there whose fields changed, and the totals of fields, option groups, printed
fields and split values; then the page files in the live set that its index no longer lists (`--prune` removes
them; they are rebuilt from the blueprints, nothing is lost). Read-only otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def load(d: Path) -> dict[str, dict]:
    """{page id: page key} for a set's index."""
    ix = d / "index.json"
    if not ix.exists():
        return {}
    return {x["page_id"]: json.loads((d / f"{x['page_id']}.json").read_text()) for x in json.loads(ix.read_text())}


def shape(page: dict) -> tuple:
    """What the scorer sees of a page: boxes with kinds, groups by box, ignored areas."""
    rect = {f["id"]: tuple(f["rect"]) for f in page["fields"]}
    fields = sorted((rect[f["id"]], f["kind"]) for f in page["fields"])
    groups = sorted(sorted(rect[i] for i in g if i in rect) for g in page.get("groups", []))
    return fields, groups, sorted(tuple(r) for r in page.get("ignored", []))


def totals(pages: dict[str, dict]) -> dict:
    t = {"fields": 0, "option groups": 0, "printed": 0, "split values": 0}
    for p in pages.values():
        kind = {f["id"]: f["kind"] for f in p["fields"]}
        t["fields"] += len(p["fields"])
        t["printed"] += sum(k == "printed" for k in kind.values())
        for g in p.get("groups", []):
            t["split values" if all(kind.get(i) != "choice" for i in g) else "option groups"] += 1
    return t


def stale(d: Path, pages: dict[str, dict]) -> list[Path]:
    """Page JSONs and page PDFs in the live set that its index no longer lists."""
    out = [p for p in d.glob("*.json") if p.name != "index.json" and p.stem not in pages]
    out += [p for p in (d / "pages").glob("*.pdf") if p.stem not in pages]
    return sorted(out)


def report(name: str, before: dict, after: dict) -> list[str]:
    form = lambda ids: {i.rsplit("__p", 1)[0] for i in ids}  # noqa: E731
    fb, fa = form(before), form(after)
    new_pages, gone = sorted(set(after) - set(before)), sorted(set(before) - set(after))
    changed = sorted(p for p in set(before) & set(after) if shape(before[p]) != shape(after[p]))
    tb, ta = totals(before), totals(after)
    out = [f"{name}: forms {len(fb)} -> {len(fa)}, pages {len(before)} -> {len(after)}",
           f"  forms in: {len(fa - fb)}" + (f" ({', '.join(sorted(fa - fb)[:12])}{', ...' if len(fa - fb) > 12 else ''})"
                                          if fa - fb else ""),
           f"  pages in: {len(new_pages)}; pages out: {len(gone)}" + (f" ({', '.join(gone[:12])})" if gone else ""),
           f"  pages kept whose fields changed: {len(changed)}" + (
               f" ({', '.join(f'{p} {len(before[p]['fields'])}->{len(after[p]['fields'])}' for p in changed[:8])})"
               if changed else "")]
    for k in tb:
        out.append(f"  {k}: {tb[k]} -> {ta[k]}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--before", type=Path, required=True, help="the copies made before the build (key/, dev_key/)")
    ap.add_argument("--key", type=Path, default=ROOT / "runs" / "benchmark" / "key")
    ap.add_argument("--dev", type=Path, default=ROOT / "runs" / "benchmark" / "dev_key")
    ap.add_argument("--prune", action="store_true", help="remove page files the index no longer lists")
    args = ap.parse_args(argv)
    for name, old, live in (("benchmark key", args.before / "key", args.key), ("tuning set", args.before / "dev_key", args.dev)):
        after = load(live)
        print("\n".join(report(name, load(old), after)))
        left = stale(live, after)
        if left:
            print(f"  {len(left)} page files not in the index any more" + (": removed" if args.prune else " (--prune removes them)"))
            for p in left if args.prune else []:
                p.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
