"""Collapse S1's per-field disagreements into per-block findings.

S1 reports one row per field. But blueprint defects are rarely per-field: on
`acord25`, the labeler named a producer-name widget `producer_address_line_1_txt`
and every field below it inherited the slip, so ONE mistake produced six
mismatch rows. Itemising those six invites six shallow, uncoordinated fixes.

This pass groups disagreements into runs of vertically adjacent widgets and
reports each run once, with the evidence needed to judge it.

## Division of labour

Deterministic here:
  - grouping fields into spatial chains (exact, repeatable, diffable)
  - the offset arithmetic — does value[i] fit field[i-k] better than field[i]?

Left to a human or an agent:
  - which side actually slipped, the labeler or the generator
  - what the fields should be renamed to

That split is deliberate. Counting hypothesis fits across a run is precisely
what a language model does unreliably and code does exactly; naming what a
value *is* is the reverse. It also keeps the eval a regression test: relabel a
form, re-run, and any diff in the cluster list is attributable to the
blueprint rather than to judge variance.

## Cluster, don't filter

Every disagreement reaches the output. A run with no offset that explains it
is reported as `cause unknown`, not dropped — `OBSERVATIONS` lists failure
classes (per-cell grouping, Class 3 partial identifiers) that are not shifts,
and this pass must not silently relabel them as such. The offset test is an
annotation on a cluster, never a filter over them.

Usage:
    python cluster_misalignment.py
    python cluster_misalignment.py --form acord25 --verbose
    python cluster_misalignment.py --out runs/clusters.json
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import statistics
from pathlib import Path
from typing import Any, Optional

import yaml

from petey.validate.shape_agree import (
    EXPECTED, TEXT_EXPECTED_CLASSES, TEXT_SEMANTICS, TYPE_EXPECTED,
    index_by_path, observed_classes, primary_class,
)

from petey.paths import RUNS, BLUEPRINTS
HERE = Path(__file__).resolve().parent

# --- adjacency parameters -------------------------------------------------
# Two widgets are in the same column when their x-ranges overlap by at least
# this fraction of the narrower one. Forms put unrelated content side by side
# (acord25 has columns at x=22 and x=346); without this they interleave and
# every chain is shredded.
X_OVERLAP_MIN = 0.30
# A vertical gap larger than this multiple of the median widget height ends a
# chain — beyond it, "the widget below" is a different part of the form.
Y_GAP_MAX_MULT = 4.0
# Runs shorter than this are coincidence, not structure.
MIN_RUN = 3
# Offsets tested. +1 means "this value belongs to the field above".
OFFSETS = (1, -1, 2, -2)


def fits(sem: Optional[str], ftype: Any, value: Any) -> Optional[bool]:
    """Does `value` agree with a field declaring `sem`/`ftype`?

    None when the field constrains nothing, so unconstrained fields neither
    support nor contradict a shift hypothesis.
    """
    classes = observed_classes(value)
    if "EMPTY" in classes:
        return None
    if sem in TEXT_SEMANTICS:
        return bool(classes & TEXT_EXPECTED_CLASSES)
    allowed = EXPECTED.get(sem) if sem else None
    if allowed is None:
        allowed = TYPE_EXPECTED.get(str(ftype))
    if allowed is None:
        return None
    return bool(classes & allowed)


# --------------------------------------------------------------------------
# Named failure classes
# --------------------------------------------------------------------------
# A generic "is this block shifted?" test does not discriminate: the
# permissive TEXT class absorbs most of a chain, so the in-place and shifted
# readings score within a field of each other. Naming the classes we have
# actually observed works better, and each name maps to a DIFFERENT fix —
# extend the registry, re-label the widget, split it, or repair the
# generator. Anything unrecognised stays `unclassified` and is still
# reported.

_STATE_NAMES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada", "ohio",
    "oklahoma", "oregon", "pennsylvania", "tennessee", "texas", "utah",
    "vermont", "virginia", "washington", "wisconsin", "wyoming",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "rhode island", "south carolina",
    "south dakota", "west virginia", "district of columbia",
}

# Tokens that redefine the field they follow: `zip_ext_cd` is not a ZIP,
# `phone_area_cd` is not a phone number.
_QUALIFIERS = ("ext", "extension", "area", "prefix", "suffix", "type")

_DATE_PARTS = ("_mo", "_dy", "_da", "_yr", "_year", "_month", "_day")

_IRS_SEMANTICS = {"ssn", "ein", "itin", "tin"}


def _semantic_tokens(slug: str) -> list[str]:
    """Distinct registry concepts named anywhere in a slug."""
    from petey.semantic_types import REGISTRY
    n = "_" + slug.lower().replace("-", "_").replace(".", "_") + "_"
    hits = []
    for st in REGISTRY:
        for m in st.matches:
            if ("_" + m.lower().lstrip("_") + "_") in n:
                if st.name not in hits:
                    hits.append(st.name)
                break
    return hits


_ROW_INDEX = re.compile(r"(_row_?\d+|_line_?\d+|_col_[a-z0-9]+|_\d+)+$")


def base_slug(field: str) -> str:
    """Slug with trailing row/column indices removed.

    Line-item forms replicate one widget down a table: cbp7501 carries
    `line_htsus_ad_cvd_irc_visa_rate` through `_8`. Those are one labeling
    decision repeated, not eight defects, and collapsing them is the
    difference between a worklist and a pile.
    """
    prev = None
    out = field.lower()
    while prev != out:
        prev = out
        out = _ROW_INDEX.sub("", out)
    return out or field.lower()


def classify_issue(field: str, sem: Optional[str], value: Any,
                   form: str) -> str:
    """Name the failure class for one disagreeing field."""
    slug = field.lower()
    s = str(value).strip()
    classes = observed_classes(value)

    # The generator wrote the printed caption instead of a value.
    if re.search(r"\(mm|dd/yyyy|yyyy\)|^[A-Z][a-z]+ [A-Z][a-z]+ \(", s):
        return "generator_echoed_label"

    # A widget whose slug names several concepts at once. The matcher picks
    # one arbitrarily, and the widget really holds one line of a block.
    if len(_semantic_tokens(field)) >= 2:
        return "compound_widget"

    # `_area_cd` / `_ext` after the semantic token.
    for q in _QUALIFIERS:
        if re.search(rf"_{q}(_|$)", slug):
            return "qualifier_modified_token"

    # Class 3 — a date component typed as a whole date.
    if sem in {"iso_date", "birth_date", "service_date"}:
        if slug.endswith(_DATE_PARTS) or "YEAR" in classes:
            return "partial_date_component"
        if re.fullmatch(r"\d{1,2}", s):
            return "partial_date_component"

    # Spelled out where an abbreviation was declared.
    if sem == "state_abbr" and s.lower() in _STATE_NAMES:
        return "value_not_abbreviated"

    # Class 8b — an IRS-family semantic on a non-IRS document.
    if sem in _IRS_SEMANTICS and not re.match(r"^(f\d|fw|i?r?s)", form):
        return "cross_family_semantic"

    if sem in TEXT_SEMANTICS:
        return "free_text_mismatch"
    return "unclassified"


def detect_swaps(records: list[dict]) -> dict[int, dict]:
    """Find pairs of fields each holding what the other declares.

    On cbp7501 `broker_filer_zip_cd` holds `'CA'` while
    `ultimate_consignee_state_abbreviation_cd` holds `'90745'`. Neither is
    explicable alone, and the earlier offset test could not see it — the
    two fields are in different blocks, and the margin-based scoring it
    used was mushy anyway.

    A reciprocal pair is a much stronger signal than an offset, because it
    demands an EXACT double fit rather than beating a threshold: value A
    must fit field B's declared semantic *and* value B must fit field A's.
    Two independently-wrong fields almost never satisfy both directions by
    chance, so this needs no tuning parameter at all.

    Searched form-wide rather than within a chain: the reciprocal partner
    is frequently in another block entirely.
    """
    bad = [r for r in records if r["fits"] is False]
    out: dict[int, dict] = {}
    for i, a in enumerate(bad):
        if a["idx"] in out:
            continue
        for b in bad[i + 1:]:
            if b["idx"] in out or a["semantic_type"] == b["semantic_type"]:
                continue
            a_into_b = fits(b["semantic_type"], b["type"], a["value"])
            b_into_a = fits(a["semantic_type"], a["type"], b["value"])
            if a_into_b and b_into_a:
                out[a["idx"]] = {"partner": b["field"],
                                 "partner_value": b["value"]}
                out[b["idx"]] = {"partner": a["field"],
                                 "partner_value": a["value"]}
                break
    return out


def build_chains(records: list[dict]) -> list[list[dict]]:
    """Link each widget to the one directly below it in the same column.

    Deliberately avoids defining a global reading order: a page-wide sort
    interleaves parallel columns and destroys the runs we are looking for.
    Local adjacency needs no column detection.
    """
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for r in records:
        by_page[r["page"]].append(r)

    heights = [r["rect"][3] - r["rect"][1] for r in records
               if r["rect"][3] > r["rect"][1]]
    med_h = statistics.median(heights) if heights else 12.0
    max_gap = med_h * Y_GAP_MAX_MULT

    successor: dict[int, int] = {}
    claimed: set[int] = set()
    for page_records in by_page.values():
        page_records.sort(key=lambda r: (r["rect"][1], r["rect"][0]))
        for i, a in enumerate(page_records):
            ax0, ay0, ax1, ay1 = a["rect"]
            best = None
            best_gap = None
            for b in page_records[i + 1:]:
                bx0, by0, bx1, by1 = b["rect"]
                gap = by0 - ay1
                if gap < -med_h:          # still on the same visual row
                    continue
                if gap > max_gap:
                    break                  # sorted by y: nothing closer later
                overlap = min(ax1, bx1) - max(ax0, bx0)
                narrower = min(ax1 - ax0, bx1 - bx0) or 1.0
                if overlap / narrower < X_OVERLAP_MIN:
                    continue
                if best_gap is None or gap < best_gap:
                    best, best_gap = b, gap
            if best is not None and best["idx"] not in claimed:
                successor[a["idx"]] = best["idx"]
                claimed.add(best["idx"])

    by_idx = {r["idx"]: r for r in records}
    heads = [r for r in records if r["idx"] not in claimed]
    chains: list[list[dict]] = []
    for h in heads:
        chain, cur, guard = [], h["idx"], 0
        while cur is not None and guard < 500:
            chain.append(by_idx[cur])
            cur = successor.get(cur)
            guard += 1
        if len(chain) >= 2:
            chains.append(chain)
    return chains


def diagnose(run: list[dict]) -> dict:
    """Score the in-place reading of a run against shifted alternatives."""
    def score(offset: int) -> tuple[int, int]:
        ok = testable = 0
        for i, rec in enumerate(run):
            j = i - offset
            if not (0 <= j < len(run)):
                continue
            v = fits(run[j]["semantic_type"], run[j]["type"], rec["value"])
            if v is None:
                continue
            testable += 1
            ok += bool(v)
        return ok, testable

    in_ok, in_n = score(0)
    best = None
    for k in OFFSETS:
        ok, n = score(k)
        if n < MIN_RUN:
            continue
        # Require a real margin, measured on comparable denominators.
        if ok - (in_ok * n / in_n if in_n else 0) >= 2:
            cand = {"offset": k, "shifted_ok": ok, "shifted_testable": n}
            if best is None or ok > best["shifted_ok"]:
                best = cand
    out = {"in_place_ok": in_ok, "in_place_testable": in_n}
    if best:
        out.update(best)
        out["diagnosis"] = (
            f"values appear shifted by {best['offset']:+d} widget(s)"
        )
    else:
        out["diagnosis"] = "cause unknown"
    return out


def analyse_form(form: str, bp: dict, gt: dict) -> list[dict]:
    idx = index_by_path(bp)
    records: list[dict] = []
    for path, (fname, spec) in idx.items():
        w = spec.get("widget") or {}
        rect = w.get("rect")
        if not rect or w.get("page") is None:
            continue
        if path not in gt:
            continue
        records.append({
            "idx": len(records), "field": fname, "path": path,
            "page": int(w["page"]), "rect": [float(x) for x in rect],
            "semantic_type": spec.get("semantic_type"),
            "type": spec.get("type"), "value": gt.get(path),
        })
    if not records:
        return []

    for r in records:
        r["fits"] = fits(r["semantic_type"], r["type"], r["value"])
        r["failure_class"] = (
            classify_issue(r["field"], r["semantic_type"], r["value"], form)
            if r["fits"] is False else None
        )

    swaps = detect_swaps(records)
    for r in records:
        sw = swaps.get(r["idx"])
        if sw:
            r["swap_partner"] = sw["partner"]
            if r["failure_class"] in ("unclassified", "free_text_mismatch"):
                r["failure_class"] = "reciprocal_swap"
        else:
            r["swap_partner"] = None

    clusters: list[dict] = []
    for chain in build_chains(records):
        bad = [i for i, r in enumerate(chain) if r["fits"] is False]
        if not bad:
            continue
        # The whole chain is the unit, not a run of consecutive failures.
        # A shifted block leaves its disagreements SEPARATED, because the
        # permissive TEXT class absorbs the intermediate fields: on acord25
        # `producer_contact_nm` holds "Columbus" and passes as a person
        # name. Requiring adjacent failures therefore misses exactly the
        # case this pass exists for. Chains are already bounded by column
        # and vertical gap, so they stay readable.
        lo = max(0, bad[0] - 1)
        hi = min(len(chain), bad[-1] + 2)
        ctx = chain[lo:hi]
        clusters.append({
            "form": form,
            "page": ctx[0]["page"],
            "n_fields": len(ctx),
            "n_disagreeing": len(bad),
            "classes": sorted({chain[i]["failure_class"] for i in bad}),
            **diagnose(ctx),
            "fields": [{
                "field": r["field"],
                "semantic_type": r["semantic_type"],
                "value": r["value"],
                "observed": primary_class(observed_classes(r["value"])),
                "agrees": r["fits"],
                "failure_class": r["failure_class"],
                "swap_partner": r.get("swap_partner"),
            } for r in ctx],
        })

    # Cluster, don't filter. A widget with no column neighbour — the
    # `*_phone_area_cd` boxes on acord25 sit alone in their column — forms
    # no chain and would otherwise vanish from the report entirely. Emit it
    # as its own single-field cluster so every disagreement S1 found is
    # still accounted for downstream.
    covered = {
        f["field"] for c in clusters for f in c["fields"]
    }
    for r in records:
        if r["fits"] is False and r["field"] not in covered:
            clusters.append({
                "form": form, "page": r["page"],
                "n_fields": 1, "n_disagreeing": 1,
                "classes": [r["failure_class"]],
                "in_place_ok": 0, "in_place_testable": 1,
                "diagnosis": "isolated field, no column neighbours",
                "fields": [{
                    "field": r["field"],
                    "semantic_type": r["semantic_type"],
                    "value": r["value"],
                    "observed": primary_class(
                        observed_classes(r["value"])),
                    "agrees": False,
                    "failure_class": r["failure_class"],
                    "swap_partner": r.get("swap_partner"),
                }],
            })
    return clusters


def pick_case(form: str) -> Optional[Path]:
    """The case with the most filled widgets — the most evidence per form."""
    best, best_n = None, -1
    for p in (RUNS).glob(f"{form}_*/case_*/ground_truth.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        n = sum(1 for v in d.values() if v not in (None, "", False))
        if n > best_n:
            best, best_n = p, n
    return best


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--form", type=str, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--verbose", action="store_true",
                    help="print every field in every cluster")
    ap.add_argument("--top", type=int, default=20)
    args = ap.parse_args()

    forms = sorted({
        re.sub(r"_\d{8}_\d{6}$", "", p.parent.parent.name)
        for p in (RUNS).glob("*/case_*/ground_truth.json")
    })
    if args.form:
        forms = [f for f in forms if f == args.form]

    all_clusters: list[dict] = []
    for form in forms:
        bp_path = BLUEPRINTS / f"{form}.bpt"
        case = pick_case(form)
        if not bp_path.exists() or case is None:
            continue
        bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
        gt = json.loads(case.read_text(encoding="utf-8"))
        all_clusters.extend(analyse_form(form, bp, gt))

    total_fields = sum(c["n_disagreeing"] for c in all_clusters)
    diag = collections.Counter(
        f"shift {c['offset']:+d}" if c.get("offset") is not None
        else c["diagnosis"] for c in all_clusters
    )

    print("=" * 74)
    print("MISALIGNMENT CLUSTERS")
    print("=" * 74)
    print(f"forms: {len(forms)}   clusters: {len(all_clusters)}   "
          f"disagreeing fields inside them: {total_fields}")
    print()
    by_class = collections.Counter()
    for c in all_clusters:
        for f in c["fields"]:
            if f.get("failure_class"):
                by_class[f["failure_class"]] += 1
    print("  disagreeing fields by failure class:")
    for k, n in by_class.most_common():
        print(f"    {n:>5}  {k}")
    print("\n  clusters by shift diagnosis:")
    for k, c in diag.most_common():
        print(f"    {c:>5}  {k}")

    # The count that matters: distinct labeling decisions, with row
    # replicas and repeated cases collapsed.
    defects = collections.Counter()
    for c in all_clusters:
        for f in c["fields"]:
            if f.get("failure_class"):
                defects[(c["form"], base_slug(f["field"]),
                         f["failure_class"])] += 1
    print()
    print(f"  disagreeing fields          : "
          f"{sum(defects.values())}")
    print(f"  DISTINCT DEFECTS (row-collapsed): {len(defects)}")
    top = defects.most_common(8)
    print("  most-replicated:")
    for (form, base, cls), n in top:
        if n > 1:
            print(f"    x{n:<3} {form}:{base[:44]:<44} {cls}")

    ranked = sorted(all_clusters, key=lambda c: -c["n_disagreeing"])
    show = ranked if args.verbose else ranked[:args.top]
    print()
    print("-" * 74)
    print(f"WORKLIST — {'all' if args.verbose else f'top {args.top}'} "
          f"clusters by size")
    print("-" * 74)
    for c in show:
        print(f"\n  {c['form']} p{c['page']}  "
              f"{c['n_disagreeing']}/{c['n_fields']} fields disagree  "
              f"— {c['diagnosis']}")
        if "offset" in c:
            print(f"     in-place fit {c['in_place_ok']}/"
                  f"{c['in_place_testable']}   "
                  f"shifted fit {c['shifted_ok']}/{c['shifted_testable']}")
        for f in c["fields"]:
            mark = {True: "ok ", False: "BAD", None: "-- "}[f["agrees"]]
            sem = f["semantic_type"] or "-"
            cls = f.get("failure_class") or ""
            print(f"     {mark} {f['field'][:40]:<40} {sem:<16} "
                  f"{cls:<20} {f['value']!r}")
            if f.get("swap_partner"):
                print(f"         ^ value belongs to "
                      f"{f['swap_partner']}")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(all_clusters, indent=2, default=str))
        print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
