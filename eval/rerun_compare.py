"""Old library blueprint vs the same form run from scratch through the current code (`scripts/rerun_library.sh`).

Per form: fields and page-check flags of the old blueprint, of the fresh label, and of the fresh blueprint after
the loop (from the run record when the form went through `form_run.py`, else from the older per-step files); what the loop did (`loop_compare.summarize`); and, where a person hand-reviewed the old blueprint, what
became of each field they flagged (followed by widget path into the fresh blueprint: its name there, and the
page check's verdict on it) and how many fields they accepted were named differently by the fresh label.

    PYTHONPATH=. venv/bin/python eval/rerun_compare.py runs/judge_eval/old_library_1.txt [--show-accepts]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from loop_compare import summarize                     # noqa: E402
from page_check_fixture import reviewed_version         # noqa: E402

from petey.paths import BLUEPRINTS, RUNS
from petey.validate import page_check

EVAL = RUNS / "judge_eval"
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _load(p: Path) -> dict:
    return yaml.load(p.read_text(encoding="utf-8"), Loader=_LOADER) or {}


def by_path(bp: dict) -> dict[str, str]:
    """{widget path: field name}, every option of a group under the group's name."""
    out = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        ws = [spec["widget"]] if spec.get("widget") else list((spec.get("widgets") or {}).values())
        for w in ws:
            if w.get("path"):
                out.setdefault(w["path"], name)
    return out


def flags_of(rec: dict) -> collections.Counter:
    return collections.Counter(f.get("problem") for f in (rec.get("fields") or {}).values() if f.get("verdict") == "flag")


def label_time(form: str) -> tuple[int | None, float]:
    """The page check on the fresh label, from the run log."""
    log = EVAL / f"{form}.log"
    if not log.exists():
        return None, 0.0
    m = re.search(rf"^{re.escape(form)}: (\d+) fields, (\d+) flagged(?:, \$([0-9.]+) live)?", log.read_text(), re.M)
    return (int(m.group(2)), float(m.group(3) or 0)) if m else (None, 0.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("list", type=Path, help="lines form|blank path")
    ap.add_argument("--show-accepts", action="store_true", help="list accepted fields the fresh label renamed")
    args = ap.parse_args()
    forms = [ln.split("|")[0] for ln in args.list.read_text().splitlines() if ln.strip()]

    print(f"{'form':22} {'old f':>5} {'old fl':>6} {'new f':>5} {'label fl':>8} {'loop fl':>7} "
          f"{'loop':>24} {'$ check':>7} {'$ loop':>6}")
    details = []
    for form in forms:
        old_p, new_p = BLUEPRINTS / f"{form}.bpt", EVAL / "blueprints" / f"{form}.bpt"
        old_rec_p = page_check.record_path(old_p)
        st = (_load(new_p).get("x_petey_page_check") or {}) if new_p.exists() else {}
        new_rec_p = RUNS.parent / st["record"] if st.get("record") else page_check.OUT / "missing.json"
        if not new_p.exists():
            print(f"{form:22} no fresh blueprint")
            continue
        old_rec = json.loads(old_rec_p.read_text()) if old_rec_p.exists() else {}
        run_rec = json.loads(new_rec_p.read_text()) if new_rec_p.exists() else {}
        if "rounds" in run_rec:                       # form_run.py: one record per run, verdicts round by round
            new_rec = {"fields": page_check.verdicts(_load(new_p))}
            r0 = run_rec["rounds"][0].get("page_check") or {}
            n_label = sum(1 for v in r0.values() if v.get("verdict") == "flag")
            c_label = sum((r.get("page_check_run") or {}).get("cost_usd", 0) or 0 for r in run_rec["rounds"])
            s = summarize({"status": (run_rec.get("result") or {}).get("status"),
                           "iterations": [r["loop"] for r in run_rec["rounds"] if r.get("loop")]})
        else:
            new_rec = run_rec
            n_label, c_label = label_time(form)
            lp = EVAL / f"{form}_loop.json"
            s = summarize(json.loads(lp.read_text())) if lp.exists() else {}
        loop_txt = (f"{s.get('status')} {s.get('detected_first')}->{s.get('detected_last')}" if s else "-")
        check_cost = c_label + old_rec.get("cost_usd", 0) + new_rec.get("cost_usd", 0)
        old_bp, new_bp = _load(old_p), _load(new_p)
        print(f"{form:22} {len(old_bp.get('fields') or {}):>5} {sum(flags_of(old_rec).values()) if old_rec else '-':>6} "
              f"{len(new_bp.get('fields') or {}):>5} {n_label if n_label is not None else '-':>8} "
              f"{sum(flags_of(new_rec).values()) if new_rec else '-':>7} {loop_txt[:24]:>24} {check_cost:>7.2f} "
              f"{(s.get('cost') or 0):>6.2f}")
        details.append((form, old_bp, new_bp, old_rec, new_rec, s))

    for form, old_bp, new_bp, old_rec, new_rec, s in details:
        print(f"\n== {form}")
        if old_rec:
            print(f"  old flags by problem: {dict(flags_of(old_rec))}")
        if new_rec:
            print(f"  new flags by problem: {dict(flags_of(new_rec))}")
            for n, f in new_rec["fields"].items():
                if f.get("verdict") == "flag":
                    prop = " ".join(x for x in (f.get("proposed_name"), f.get("proposed_type")) if x)
                    print(f"    {n:44} {f['problem']:13} {prop[:40]:40} {(f.get('reason') or '')[:90]}")
        if s:
            print(f"  loop: {s.get('iters')} iterations, applied {s.get('applied')}")
        hr = RUNS / "hand_review" / f"lib__{form}.json"
        if not hr.exists():
            continue
        rec = json.loads(hr.read_text())
        seen = reviewed_version(f"lib__{form}", rec)
        if seen is None:
            continue
        seen_bp = _load(seen)
        new_names = by_path(new_bp)
        new_v = new_rec.get("fields") or {}
        old_paths = {}
        for path, name in by_path(seen_bp).items():
            old_paths.setdefault(name, path)
        verdicts = rec.get("verdicts") or {}
        flagged = {n: v for n, v in verdicts.items() if v.get("verdict") == "flag"}
        print(f"  hand review of the old blueprint: {len(verdicts)} verdicts, {len(flagged)} flags")
        for n, v in flagged.items():
            path = old_paths.get(n)
            nn = new_names.get(path) if path else None
            pv = (new_v.get(nn) or {}).get("verdict") if nn else None
            print(f"    {n:40} note {v.get('note', '')[:44]!r:46} -> new: {nn or '(no field on that widget)'}"
                  f"{f'  [page check: {pv}]' if pv else ''}")
        renamed = [(n, new_names.get(old_paths.get(n))) for n, v in verdicts.items()
                   if v.get("verdict") == "accept" and old_paths.get(n) and new_names.get(old_paths[n]) not in (None, n)]
        print(f"  accepted fields the fresh label names differently: {len(renamed)} of "
              f"{sum(1 for v in verdicts.values() if v.get('verdict') == 'accept')}")
        if args.show_accepts:
            for a, b in renamed:
                print(f"    {a:40} -> {b}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
