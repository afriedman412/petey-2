"""Results table for docs/RELABEL_PLAN_v1.md: committed vs relabeled blueprint, judged by the loop.

Reads the iterate outputs under runs/relabel/ (and, for a form whose committed
side was run earlier, any iterate json passed with --committed-json), the two
blueprints, and the labeler call log, and prints one markdown table.

    venv/bin/python eval/relabel_compare.py
    venv/bin/python eval/relabel_compare.py --forms fw9,acord25

Labeling cost: calls tagged `auto_label/<form>_relabel/<model>` are summed
directly. Calls made before the tag carried the form name (dir
`auto_label/<model>`) are attributed by matching each call's `request.widgets`
against the per-page widget counts in the form's label log, in time order.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

from petey.paths import BLUEPRINTS, RUNS

REL = RUNS / "relabel"
CALLS = RUNS / "_calls" / "auto_label"
PRICE = {"claude-sonnet-4-6": (3.0, 15.0), "claude-sonnet-5": (2.0, 10.0),
         "claude-haiku-4-5": (1.0, 5.0), "claude-opus-5": (5.0, 25.0)}  # $/M in, out

FORMS = ["fw9", "acord25", "i765", "vba21526ez", "va_form_10_10ez"]
COMMITTED_JSON = {  # committed side run outside runs/relabel (last iteration is the baseline)
    "vba21526ez": RUNS / "iterate_vba21526ez_review5.json",
}


def _load(p: Path):
    return json.load(open(p)) if p.exists() else None


def _bp(stem: str):
    # side copies live in blueprints/ while a test runs and move to runs/relabel/blueprints/ once recorded
    for p in (BLUEPRINTS / f"{stem}.bpt", REL / "blueprints" / f"{stem}.bpt"):
        if p.exists():
            return yaml.safe_load(open(p))
    return None


def _by_path(bp) -> dict[str, str]:
    out = {}
    for name, spec in (bp or {}).get("fields", {}).items():
        w = spec.get("widget")
        if w and w.get("path"):
            out[w["path"]] = name
        for v, wb in (spec.get("widgets") or {}).items():
            out[wb["path"]] = name
    return out


def _tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[_\W]+", name.lower()) if t and t not in {"txt", "nbr", "cd", "nm", "ind", "dt", "amt"}}


def name_overlap(rel, com) -> str:
    r, c = _by_path(rel), _by_path(com)
    shared = set(r) & set(c)
    if not shared:
        return "-"
    same = sum(1 for p in shared if r[p] == c[p])
    jac = sum(len(_tokens(r[p]) & _tokens(c[p])) / max(1, len(_tokens(r[p]) | _tokens(c[p]))) for p in shared) / len(shared)
    return f"{same}/{len(shared)} identical, token jaccard {jac:.2f}"


def reader_row(it: dict) -> dict:
    """Numbers for one iteration of an iterate json."""
    run = RUNS / it["run"]
    summ = _load(run / "summary.json") or {}
    methods = [m for m in summ.get("methods", []) if m != "native"]
    reader = summ.get("intact", {}).get(methods[0], {}) if methods else {}
    delta = it.get("delta", {})
    return {
        "shape": sum(it.get("shape", {}).values()),
        "shape_by": it.get("shape", {}),
        "native_miss": it.get("verdicts", {}).get("extract_miss", 0),
        "agree": reader.get("agree"), "differ": reader.get("differ"), "miss": reader.get("extract_miss"),
        "defect": delta.get("defect", 0), "delta": delta, "detected": it.get("detected"),
        "seconds": it.get("seconds"),
    }


def review_row(d: dict | None) -> str:
    if not d:
        return "-"
    its = d.get("iterations", [])
    rr = its[0].get("review_run") if its else None
    if not rr:
        return "no flags"
    v = rr.get("verdicts", {})
    s = f"{rr['fields_reviewed']} flagged, {v.get('fix', 0)} fixes"
    if len(its) > 1 and its[1].get("review"):
        j = its[1]["review"]
        s += f": {j.get('better', 0)} better / {j.get('worse', 0)} worse / {j.get('restored', 0)} restored"
    s += f", ${rr.get('cost_usd', 0):.2f}"
    return s


def _page_counts(form: str) -> list[int]:
    log = REL / f"label_{form}.log"
    if not log.exists():
        return []
    return [int(m) for m in re.findall(r"\[page \d+\] retrieval=\d+ llm=(\d+)", log.read_text())]


def label_cost(form: str, untagged: list[dict]) -> tuple[int, int, float, float]:
    """(input_tokens, output_tokens, dollars, seconds) for one form's labeler calls."""
    calls = []
    tagged = CALLS / f"{form}_relabel"
    if tagged.exists():
        for f in sorted(tagged.rglob("*.json")):
            calls.append(json.load(open(f)))
    else:
        want = _page_counts(form)
        i = 0
        for c in untagged:  # time order; batches of one page sum to the page count
            if i >= len(want):
                break
            w = (c.get("request") or {}).get("widgets")
            if c.get("_taken") or w is None:
                continue
            if w == want[i]:
                c["_taken"] = True; calls.append(c); i += 1
            elif w < want[i]:
                # a dense page split into batches: consume until the sum matches
                acc, grp = 0, []
                for c2 in untagged:
                    if c2.get("_taken"):
                        continue
                    w2 = (c2.get("request") or {}).get("widgets") or 0
                    acc += w2; grp.append(c2)
                    if acc >= want[i]:
                        break
                if acc == want[i]:
                    for c2 in grp:
                        c2["_taken"] = True
                    calls.extend(grp); i += 1
    ti = sum((c.get("usage") or {}).get("input_tokens") or 0 for c in calls)
    to = sum((c.get("usage") or {}).get("output_tokens") or 0 for c in calls)
    secs = sum(c.get("elapsed_s") or 0 for c in calls)
    model = next((c["tag"].split("/")[-1] for c in calls if c.get("tag")), "claude-sonnet-4-6")
    pi, po = PRICE.get(model, PRICE["claude-sonnet-4-6"])
    return ti, to, (ti * pi + to * po) / 1e6, secs


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--forms", default=",".join(FORMS))
    args = ap.parse_args()

    untagged = []
    for d in sorted(CALLS.glob("claude-*")):
        for f in sorted(d.glob("*.json")):
            untagged.append(json.load(open(f)))
    untagged.sort(key=lambda c: c.get("when", ""))

    rows = []
    for form in args.forms.split(","):
        rel_bp, com_bp = _bp(f"{form}_relabel"), _bp(form)
        rel = _load(REL / f"iterate_{form}_relabel.json")
        com = _load(REL / f"iterate_{form}_committed.json") or _load(COMMITTED_JSON.get(form, Path("/nonexistent")))
        rev = _load(REL / f"iterate_{form}_relabel_review.json")
        ti, to, usd, secs = label_cost(form, untagged)
        pages = len(_page_counts(form)) or len((rel_bp or {}).get("source_pages", []))
        com_tag = "committed" + (" (after review)" if form in COMMITTED_JSON else "")
        for tag, bp, d, pick in ((com_tag, com_bp, com, -1), ("relabel", rel_bp, rel, 0)):
            if not bp or not d or not d.get("iterations"):
                rows.append((form, tag, "(not run)", "", "", "", "", "", "", ""))
                continue
            it = d["iterations"][pick]
            r = reader_row(it)
            n = len(bp["fields"])
            reader = f"{r['agree']}/{n} agree, {r['differ']} differ, {r['miss']} miss" if r["agree"] is not None else "-"
            fixes = ", ".join(f"{k} {v}" for k, v in (bp.get("x_petey_emit_fixes") or {}).items()) or ("none" if tag == "relabel" else "")
            cost = f"{ti:,} in / {to:,} out, ${usd:.2f}, {usd / max(pages, 1) * 100:.0f}c/page" if tag == "relabel" and (ti or to) else ""
            rows.append((form, tag, len(bp["fields"]), fixes, f"{r['shape']} {dict(r['shape_by']) if r['shape_by'] else ''}".strip(),
                         reader, r["defect"], review_row(rev) if tag == "relabel" else "", cost,
                         name_overlap(rel_bp, com_bp) if tag == "relabel" and com_bp else ""))
    hdr = ("form", "version", "fields", "emit fixes", "shape contradictions", "name-based reader", "name defects", "Haiku review (relabel)", "labeling (Sonnet 4.6)", "names vs committed")
    print("| " + " | ".join(hdr) + " |")
    print("|" + "---|" * len(hdr))
    for row in rows:
        print("| " + " | ".join(str(x) for x in row) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
