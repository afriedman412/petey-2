"""Blueprint defects detectable without running anything.

`risk_screen.py` established that no *statistical* signal predicts measured
defects, so VLM evaluation cannot be triaged to a risky subset. That result
stands. These are a different kind of thing: structural facts about a
blueprint that are wrong on their face, not correlates of wrongness. They
need no cases, no extraction, no model, and no API key.

Both were found by inspecting the batch-1 method-delta findings and then
generalised back across the library. See OBSERVATIONS classes 12 and 13.

## Class 12 — pushbutton widgets promoted to extraction fields

A blueprint field bound to an AcroForm pushbutton. Ground truth for it is
always `None` (there is nothing to fill), and a meaning-based reader
returns the button's caption as data: `print_form_btn` → `'PRINT FORM'`,
`item_j_prefix_txt` → `'j. Are you taking credit to reduce taxes due…'`.

The labeler had this information and dropped it — all 106 instances are
written as `widget_type: text` even though pymupdf reports
`field_type_string == 'Button'`. So the check must go back to the source
PDF rather than trusting the `.bpt`.

## Class 13 — sibling names carrying no distinguishing information

Two fields whose names differ only by a trailing dedup ordinal (`_2`) or
by a bare type suffix, with no `description` on either. Nothing in the
blueprint distinguishes them, so a reader navigating by meaning is
guessing and is wrong about half the time. Confirmed as reciprocal swaps
on cbp_form_3299_0, 92900_a and ao030.

Deliberately conservative: only *trailing* ordinals count. `line_1_amt` vs
`line_2_amt` carries a real distinction in the index and is not flagged —
the failure mode is specifically the suffix appended to break a collision,
which by construction says nothing about what the field is.

Usage:
    python structural_defects.py
    python structural_defects.py --form 01_114 --verbose
    python structural_defects.py --out runs/structural_defects.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from pathlib import Path

import pymupdf
import yaml

from petey.paths import REPO, BLUEPRINTS, SOURCE_PDFS
HERE = Path(__file__).resolve().parent
REPO = HERE.parent

# PDF field flag bit 17. Set on pushbuttons, which are controls rather
# than data entry — clicking them does something, they hold no value.
PUSHBUTTON_FLAG = 1 << 16

# Suffixes the labeler appends to record a field's shape. They occupy the
# slot where a discriminator would go without carrying one.
TYPE_SUFFIXES = ("_txt", "_nm", "_cd", "_amt", "_dt", "_ind", "_qty",
                 "_num", "_pct", "_id")

TRAILING_ORDINAL = re.compile(r"^(.*?)_([2-9])$")


def _source_pdfs() -> dict[str, Path]:
    return {p.name: p for p in (SOURCE_PDFS).rglob("*.pdf")}


def pushbutton_fields(bp: dict, pdf: Path) -> list[dict]:
    """Fields bound to a pushbutton widget in the source PDF."""
    try:
        doc = pymupdf.open(str(pdf))
    except Exception:
        return []
    buttons: dict[str, int] = {}
    try:
        for page in doc:
            for w in page.widgets():
                if (w.field_flags or 0) & PUSHBUTTON_FLAG:
                    buttons[w.field_name] = w.field_flags
    except Exception:
        pass
    finally:
        doc.close()
    if not buttons:
        return []

    out = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        path = (spec.get("widget") or {}).get("path")
        if path in buttons:
            out.append({
                "field": name,
                "path": path,
                "declared_widget_type": (spec.get("widget") or {}
                                         ).get("widget_type"),
            })
    return out


def undiscriminable_siblings(bp: dict) -> list[dict]:
    """Groups of fields distinguished only by an ordinal or a bare suffix.

    Two relations qualify, and only these two:

      X, X_2, X_3…   a trailing dedup ordinal. Says nothing about which
                     is which.
      X, X_txt       a type suffix where the unsuffixed name is ALSO a
                     field. The suffix records shape, not identity, so
                     the pair is undiscriminable.

    Explicitly NOT flagged: two different type suffixes on a shared stem.
    `taxpayer_nm` and `taxpayer_amt` differ by suffix, but a name and an
    amount are genuinely different concepts and the suffix is what says
    so. An earlier revision grouped these and reported 1,863 at-risk
    fields; the great majority were this false positive.
    """
    fields = bp.get("fields") or {}
    described = {
        n for n, s in fields.items()
        if isinstance(s, dict) and (s.get("description") or "").strip()
    }

    groups: dict[str, set[str]] = collections.defaultdict(set)
    reasons: dict[str, set[str]] = collections.defaultdict(set)

    for name in fields:
        m = TRAILING_ORDINAL.match(name)
        if m:
            stem = m.group(1)
            # Real only if some sibling shares the stem — either the
            # unsuffixed field or another ordinal.
            groups[stem].add(name)
            reasons[stem].add("trailing ordinal")
            if stem in fields:
                groups[stem].add(stem)
            continue
        for s in TYPE_SUFFIXES:
            base = name[: -len(s)]
            if name.endswith(s) and base in fields:
                groups[base].update((name, base))
                reasons[base].add(f"bare type suffix {s}")
                break

    # `_dedup.py` records every collision it resolved, so where the log is
    # present it says authoritatively which ordinals were manufactured to
    # break a tie rather than carrying real positional meaning. Name
    # pattern alone cannot distinguish the two, so the verdict is reported
    # either way rather than silently mixed.
    log = (bp.get("x_petey_dedup_log") or {}).get("collisions") or []
    from_dedup = {c.get("assigned_label") for c in log}

    out = []
    for stem, names in groups.items():
        if len(names) < 2:
            continue
        # Any member carrying prose is discriminable; the class is
        # specifically "nothing tells these apart".
        if any(n in described for n in names):
            continue
        out.append({
            "stem": stem,
            "fields": sorted(names),
            "distinguished_only_by": sorted(reasons[stem]),
            "source": ("dedup_log" if names & from_dedup else "name_pattern"),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--blueprints", type=Path, default=BLUEPRINTS)
    ap.add_argument("--form", help="substring match on blueprint stem")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    src = _source_pdfs()
    results, totals = [], collections.Counter()

    for bpt in sorted(args.blueprints.glob("*.bpt")):
        if args.form and args.form not in bpt.stem:
            continue
        try:
            bp = yaml.safe_load(bpt.read_text())
        except Exception:
            totals["unparseable"] += 1
            continue
        if not isinstance(bp, dict) or not bp.get("fields"):
            continue

        pdf = src.get(bp.get("source_pdf") or "")
        buttons = pushbutton_fields(bp, pdf) if pdf else []
        siblings = undiscriminable_siblings(bp)

        totals["blueprints"] += 1
        totals["fields"] += len(bp["fields"])
        totals["class12_pushbutton"] += len(buttons)
        totals["class13_sibling_groups"] += len(siblings)
        totals["class13_fields"] += sum(len(s["fields"]) for s in siblings)
        totals["class13_confirmed_by_dedup_log"] += sum(
            1 for s in siblings if s["source"] == "dedup_log")
        totals["class13_inferred_from_name"] += sum(
            1 for s in siblings if s["source"] == "name_pattern")
        if pdf is None:
            totals["source_pdf_not_found"] += 1
        if buttons or siblings:
            results.append({"blueprint": bpt.stem,
                            "class12_pushbutton": buttons,
                            "class13_siblings": siblings})

    print(f"{totals['blueprints']} blueprints, {totals['fields']} fields")
    print(f"  class 12  pushbutton-bound fields   "
          f"{totals['class12_pushbutton']}")
    print(f"  class 13  undiscriminable siblings  "
          f"{totals['class13_fields']} fields in "
          f"{totals['class13_sibling_groups']} groups "
          f"({totals['class13_confirmed_by_dedup_log']} confirmed by dedup "
          f"log, {totals['class13_inferred_from_name']} inferred from name)")
    if totals["source_pdf_not_found"]:
        print(f"  ({totals['source_pdf_not_found']} blueprints' source_pdf "
              f"not on disk — class 12 unchecked for those)")

    ranked = sorted(results, key=lambda r: -(len(r["class12_pushbutton"])
                                             + len(r["class13_siblings"])))
    print()
    for r in ranked[:20]:
        print(f"  {r['blueprint']:<28} "
              f"btn={len(r['class12_pushbutton']):<4} "
              f"sib={len(r['class13_siblings'])}")

    if args.verbose:
        for r in ranked:
            print(f"\n=== {r['blueprint']} ===")
            for b in r["class12_pushbutton"]:
                print(f"  [12] {b['field']:<38} path={b['path']} "
                      f"declared={b['declared_widget_type']}")
            for s in r["class13_siblings"]:
                print(f"  [13] {', '.join(s['fields'])}")
                print(f"       differ only by: "
                      f"{', '.join(s['distinguished_only_by'])}")

    if args.out:
        args.out.write_text(json.dumps(
            {"totals": dict(totals), "results": results}, indent=1))
        print(f"\nwrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
