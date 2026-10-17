"""In-place repairs for blueprints already written — the patch, not the retrain.

Fixing a defect class in `auto_label` stops it being PRODUCED. It does
nothing for the 146 blueprints already on disk, and the only way to push an
upstream fix backwards is a full relabel, which is paid and rewrites most
field names (`acord25` agreed with its prior labeling on 31% of widgets). So
an upstream fix is a retrain: batched, periodic, global. This is the prompt
patch: targeted, cheap, reversible, applied now.

Caption widgets stopped being produced this session. 241 of them still sat in
31 blueprints an hour later.

## Permanent invariants, not transitional patches

Each rule is idempotent and re-applied after every regeneration, because a
freshly generated blueprint still carries every defect whose upstream fix has
not shipped. Running this is part of producing a blueprint, not a one-off
tidy.

**A rule that touches zero fields is PASSING, not finished.** An earlier
version of this docstring called that "graduated" and suggested retiring the
rule once its upstream fix landed. That is wrong. Zero occurrences says the
blueprints that exist today are clean; it says nothing about the 229 sources
still unlabeled, the forms that will arrive after them, or the other paths a
blueprint can be produced by — `vision_label`, a hand edit, an older
checkout. A new form can carry the defect through a variant the upstream fix
does not cover, and an `auto_label` regression would reintroduce it silently.

So these rules never retire. Zero is a green test, and nobody deletes a test
for passing.

## Rules are deterministic or they do not belong here

Every rule reads the source PDF's own widget flags or the publisher's naming.
Nothing here calls a model or guesses: a repair that might be wrong belongs
in `correct.py`, which grades its proposals against an independent oracle and
holds back the ones it cannot confirm.

## Dropping a field is an improvement the headline metric cannot see

Removing a field shrinks the denominator, so `agree` falls while the
blueprint gets strictly better. The success criterion for a drop is that
`differ` and `miss` fall while `agree` holds — those fields only ever
produced failures. `reextract_all.py` must be read that way for these rules,
or a correct fix reads as a regression.

Usage:
    python remediate.py                    # report, change nothing
    python remediate.py --apply
    python remediate.py --rule caption_field --apply
"""
from __future__ import annotations

import argparse
import collections
import re
import shutil
from pathlib import Path
from typing import Callable, Optional

import pymupdf
import yaml

from petey.validate import publisher_name
from petey import semantic_types
from petey.validate.defect_taxonomy import BY_NAME

from petey.paths import BLUEPRINTS
HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "source_pdfs"

READONLY_FLAG = 1 << 0
PUSHBUTTON_FLAG = 1 << 16


def _widget_facts(pdf: Path) -> dict[str, dict]:
    """Per-path flags and default value, straight from the source PDF."""
    out: dict[str, dict] = {}
    try:
        doc = pymupdf.open(str(pdf))
    except Exception:
        return out
    try:
        for page in doc:
            for w in (page.widgets() or []):
                out.setdefault(w.field_name, {
                    "flags": w.field_flags or 0,
                    "value": (w.field_value or "").strip(),
                    "type": w.field_type,
                    "tooltip": (w.field_label or "").strip(),
                })
    finally:
        doc.close()
    return out


# --- rules -----------------------------------------------------------------
# Each returns the field names to DROP. A rule that wants to modify rather
# than drop returns nothing and mutates in place; none do yet.

def rule_caption_field(bp: dict, facts: dict) -> list[str]:
    """A locked widget whose value IS the printed label (see taxonomy)."""
    out = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        w = spec.get("widget")
        if not isinstance(w, dict):
            continue
        f = facts.get(w.get("path"))
        if not f:
            continue
        if (f["flags"] & READONLY_FLAG) and f["value"] and \
                f["type"] not in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
            out.append(name)       # a checkbox's value is its state ('Off'), not a caption (acroform._STATE_TYPES)
    return out


def rule_pushbutton_field(bp: dict, facts: dict) -> list[str]:
    """A control, not a field: it fires an action and holds no value."""
    out = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        w = spec.get("widget")
        if not isinstance(w, dict):
            continue
        f = facts.get(w.get("path"))
        if not f:
            continue
        if (f["flags"] & PUSHBUTTON_FLAG) or \
                f["type"] == pymupdf.PDF_WIDGET_TYPE_BUTTON:
            out.append(name)
    return out


# --- edit rules ------------------------------------------------------------
# These MODIFY a field rather than dropping it, so they return edits:
#   (field_name, what, value)  where `what` is a spec key, or "rename".

Edit = tuple[str, str, object]


def rule_missing_semantic_type(bp: dict, facts: dict) -> list[Edit]:
    """Attach the semantic_type (and pattern) the registry resolves.

    Purely additive: it fills a null, never overwrites a value the labeler
    chose. Deliberately does NOT force a resolution -- `semantic_types.lookup`
    returns a hit for anything ending `_nm`, so appending a suffix to make a
    field resolve scores 100% "typed" while making slugs worse. Tried on all
    9,173 nameable fields it dropped library agreement from 153 to 136.
    """
    out: list[Edit] = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("semantic_type"):
            continue
        w = spec.get("widget")
        wt = w.get("widget_type") if isinstance(w, dict) else None
        st = semantic_types.lookup(str(name), widget_type=wt)
        if st is None:
            continue
        # The registry matches by CONTAINMENT, which is how
        # `state_license_action` resolves to state_abbr and would acquire
        # `^[A-Z]{2}$` -- truncating every extraction of it. Require the
        # match to land at the END of the slug, where our convention puts the
        # type marker. `employer_state_cd` still resolves; a field that
        # merely mentions a state no longer does.
        slug = str(name).lower()
        tail_ok = any(slug.endswith(m.lstrip("_")) for m in st.matches) or \
            any(slug == w.lower() for w in st.whole_names)
        if not tail_ok:
            continue
        out.append((name, "semantic_type", st.name))
        if st.pattern and not spec.get("pattern"):
            out.append((name, "pattern", st.pattern))
    return out


def rule_mistyped_field(bp: dict, facts: dict) -> list[Edit]:
    """Retype from the publisher's own assertion about the widget.

    The final word of an AcroForm name states what the field holds, and that
    assertion agrees with the declared type on 92.4% of the 4,994 fields
    carrying one -- a working oracle, unlike the 47% name oracle.

    Only fires where the widget's own name is PROSE. A field whose publisher
    name contradicts the declared type may be MISBOUND rather than mistyped,
    and the taxonomy's precedence is explicit that rebinding comes first:
    retyping patient_birth_dt to string makes it accept the surname and look
    fixed, so nothing ever finds the bad binding. This rule therefore skips
    any field the corrector has flagged, which is what `--suspects` supplies.
    """
    suspects = facts.get("_suspects") or set()
    out: list[Edit] = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or name in suspects:
            continue
        w = spec.get("widget")
        path = w.get("path") if isinstance(w, dict) else None
        if not path:
            continue
        want = publisher_name.asserted_type(path)
        if want and want != (spec.get("type") or "string"):
            out.append((name, "type", want))
    return out


def rule_block_renumbered(bp: dict, facts: dict) -> list[Edit]:
    """Renumber a repeating block's slugs from the publisher's own ordinal.

    Deterministic because the publisher numbered the block. Fires only where
    our sequence RESTARTS inside one of its blocks, which is the signature of
    two naming families for one table -- 2025-schedule-a names the
    publisher's brokers 3, 4, 5 as `1a`, `2a`, `3a`.

    NOT SAFE TO SWEEP. `RESTARTS` is a candidate signal and its false
    positive rate on the current library is 2 of 4 forms:

      2025-schedule-a  TRUE  one broker series split across a page break
      f5500sa          TRUE  the same, same form family
      form_1005        FALSE the publisher numbers CELLS across a grid
                             (base pay / overtime / commissions x 2 years)
      revised_c_148    FALSE the publisher's flat `Volume_1..12` spans two
                             SECTIONS, so our restart at 6 is correct

    The grid case is caught by `block_verdict`. The section case is not, and
    cannot be from names alone: stem-token overlap puts the true
    2025-schedule-a insbrokername block at 0.25 and the false revised_c_148
    volume block at 0.40, so no threshold separates them. Settling it needs
    the geometry -- identical blocks at a regular vertical pitch, which two
    different sections will not have.

    So this rule requires --form NAME. Renaming is also the most invasive
    edit here, because field names are the keys consumers read.
    """
    out: list[Edit] = []
    existing = set(bp.get("fields") or {})
    for stem, members in publisher_name.repeating_blocks(bp):
        if publisher_name.block_verdict(members) != "RESTARTS":
            continue
        # A block renumbers ATOMICALLY or not at all. Renaming only the
        # members whose target is free leaves 2025-schedule-a holding
        # 1a, 2a, 3a, 6a, 7a -- a state worse than the defect, and one that
        # the next run would try to "fix" again. That is the oscillation the
        # taxonomy's precedence exists to prevent, arriving from inside a
        # single rule.
        block: list[Edit] = []
        targets: set[str] = set()
        ok = True
        for pub_ord, name in members:
            ours = publisher_name._slug_ordinal(name)
            if ours is None or ours == pub_ord:
                continue
            new = re.sub(rf"_{ours}(?=[a-z]?(?:_|$))", f"_{pub_ord}",
                         str(name), count=1)
            if new == name or new in targets:
                ok = False
                break
            # A collision with a name that is ITSELF being renamed is fine;
            # one with a name that is staying put is not.
            moving = {n for _, n in members}
            if new in existing and new not in moving:
                ok = False
                break
            targets.add(new)
            block.append((name, "rename", new))
        if ok and block:
            out.extend(block)
    return out


RULES: dict[str, Callable[[dict, dict], list[str]]] = {
    "caption_field": rule_caption_field,
    "pushbutton_field": rule_pushbutton_field,
}

EDIT_RULES: dict[str, Callable[[dict, dict], list[Edit]]] = {
    "missing_semantic_type": rule_missing_semantic_type,
    "block_renumbered": rule_block_renumbered,
    "mistyped_field": rule_mistyped_field,
}

# Sequence is CODE, not dict-insertion luck. The taxonomy records which rules
# fight over a field and which wins (`defect_taxonomy.py --conflicts`); this
# is where that order is obeyed. Two rules that disagree and run in the wrong
# order oscillate: each undoes the other and both look right in isolation.
ORDER: tuple[str, ...] = (
    "caption_field",          # before orphan handling: drop furniture first
    "pushbutton_field",
    "missing_semantic_type",  # additive, cannot conflict
    "block_renumbered",       # RENUMBER BEFORE PERMUTING (vs correct.py)
    "mistyped_field",         # REBIND BEFORE RETYPING -> runs last
)

# Rules that rewrite names or types rather than removing a defect. A blanket
# --apply will not run these; they need --rule NAME, so the library is never
# renamed by a habit.
OPT_IN: frozenset[str] = frozenset({"block_renumbered", "mistyped_field"})

# Rules whose signal is a CANDIDATE, not a verdict. They refuse to run across
# the library and require --form, because a sweep would apply their false
# positives too. block_renumbered is 2-for-4 on the current library and I
# applied it library-wide once before adding this, renaming 10 fields on
# form_1005 that were already correct.
NEEDS_FORM: frozenset[str] = frozenset({"block_renumbered"})


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rule", default=None)
    ap.add_argument("--form", default=None,
                    help="restrict to one blueprint stem; required by the "
                         "rules in NEEDS_FORM")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--all", action="store_true",
                    help="include the opt-in rules in the REPORT (they still "
                         "need --rule to be applied)")
    args = ap.parse_args()

    known = set(RULES) | set(EDIT_RULES)
    if args.rule and args.rule not in known:
        print(f"no such rule. known: {', '.join(ORDER)}")
        return 1
    # ORDER, not dict order: the sequence encodes the conflict precedence in
    # `defect_taxonomy.py --conflicts`. Rules that rewrite names or types are
    # opt-in, so a blanket --apply cannot rename the library by habit.
    selected = [k for k in ORDER
                if (args.rule == k)
                or (not args.rule and (args.all or k not in OPT_IN))]
    if args.all and args.apply and not args.rule:
        print("[refused] --all --apply would rename and retype the library; "
              "pass --rule NAME for each opt-in rule instead")
        return 1
    rules = {k: RULES[k] for k in selected if k in RULES}
    edit_rules = {k: EDIT_RULES[k] for k in selected if k in EDIT_RULES}
    if args.rule and args.rule in OPT_IN and args.apply:
        print(f"[note] {args.rule} rewrites names or types — applying to "
              f"the library")

    counts: collections.Counter = collections.Counter()
    forms_hit: dict[str, set] = {k: set() for k in selected}
    samples: dict[str, list[str]] = {k: [] for k in selected}
    changed = 0

    needs = [k for k in selected if k in NEEDS_FORM]
    if needs and not args.form:
        print(f"[refused] {', '.join(needs)} is a candidate signal, not a "
              f"verdict — pass --form NAME after checking that form")
        return 1

    for bpf in sorted(BLUEPRINTS.glob("*.bpt")):
        if args.form and bpf.stem != args.form:
            continue
        try:
            bp = yaml.safe_load(bpf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(bp, dict) or not bp.get("fields"):
            continue
        hits = list(SRC.rglob(bp.get("source_pdf") or "\0"))
        if not hits:
            continue
        facts = _widget_facts(hits[0])
        if not facts:
            continue

        drop: dict[str, str] = {}
        for rname, fn in rules.items():
            for field in fn(bp, facts):
                drop.setdefault(field, rname)
                counts[rname] += 1
                forms_hit[rname].add(bpf.stem)

        edits: list[tuple[str, str, str, object]] = []
        for rname, efn in edit_rules.items():
            for field, what, value in efn(bp, facts):
                if field in drop:
                    continue            # dropped fields need no repair
                edits.append((rname, field, what, value))
                counts[rname] += 1
                forms_hit[rname].add(bpf.stem)
                if len(samples[rname]) < 6:
                    samples[rname].append(
                        f"{bpf.stem}:{field} {what} -> {value}")
        if not drop and not edits:
            continue
        if args.verbose:
            print(f"  {bpf.stem}: {len(drop)} fields")
            for f, r in sorted(drop.items())[:6]:
                print(f"      {r:18s} {f}")
        if args.apply:
            for f in drop:
                bp["fields"].pop(f, None)
            # Renames are a PERMUTATION -- 1a becomes 3a while 3a becomes 5a
            # -- so they must be applied simultaneously. Doing them one at a
            # time makes two keys collide and silently drops a field.
            renames = {f: str(v) for r, f, w, v in edits if w == "rename"}
            if renames:
                collisions = set(renames.values()) & (
                    set(bp["fields"]) - set(renames))
                if collisions:
                    print(f"  [{bpf.stem}] rename refused, target(s) "
                          f"occupied by fields that are not moving: "
                          f"{sorted(collisions)[:4]}")
                elif len(set(renames.values())) != len(renames):
                    print(f"  [{bpf.stem}] rename refused, two fields map "
                          f"to one name")
                else:
                    bp["fields"] = {renames.get(k, k): v
                                    for k, v in bp["fields"].items()}
            for rname, field, what, value in edits:
                if what == "rename":
                    continue
                spec = (bp.get("fields") or {}).get(field)
                if isinstance(spec, dict):
                    spec[what] = value
            shutil.copy2(bpf, bpf.with_suffix(".bpt.pre_remediate"))
            with open(bpf, "w") as fh:
                yaml.safe_dump(bp, fh, sort_keys=False, allow_unicode=True)
            changed += 1

    print("=" * 74)
    print("IN-PLACE REMEDIATION" + ("" if args.apply else "  (report only)"))
    print("=" * 74)
    for rname in selected:
        n = counts[rname]
        cls = BY_NAME.get(rname)
        print(f"  {rname:20s} {n:5d} fields  "
              f"{len(forms_hit[rname]):3d} blueprints")
        if cls and cls.inline_fix:
            print(f"      fix: {cls.inline_fix}")
        for line in samples.get(rname, []):
            print(f"        {line}")
        if n == 0:
            print("      PASS — no occurrences in the current library. The "
                  "rule stays live:")
            print("      new sources can reintroduce the defect, and this is "
                  "what would catch it.")
    print()
    if args.apply:
        print(f"  {changed} blueprints rewritten "
              f"(backups at *.bpt.pre_remediate)")
        print("  Re-run reextract_all.py --compare. For DROPS, success is "
              "differ and miss falling")
        print("  while agree holds — a smaller denominator makes agree fall "
              "on a correct fix.")
    else:
        print("  (report only — pass --apply to rewrite)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
