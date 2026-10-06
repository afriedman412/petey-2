"""One form from its blank through the current code, kept as one JSON per run; the `.bpt` is written when it is stable.

Andrew, 2026-10-06: keep the JSON before every loop round; when the form is stable, turn it into a bpt. The run
record (`runs/judge_eval/form_runs/<form>.json`) holds

    round 0     the fresh label in full (every field's definition and the blueprint's top level) with the page
                check's verdict on every field;
    round k     the state after loop round k, i.e. before round k+1: only the fields that round added, changed
                (a definition hash differs), renamed (same widget, new name) or removed, with the loop's record
                for the round (detections, rule fixes, rebinds, reviewer edits, edits restored), and a spot check:
                the page check on just the definitions the round introduced (only their pages are sent). Its
                verdicts reach the next round's reviewer; a name / type flag on a field the reviewer already
                judged reopens it (Andrew: the page check runs in full after ingestion, then the loop spot-checks
                until stable);
    final       anything left unchecked (normally nothing), and the result: status, why the loop stopped,
                review rounds, stable or not.

Any round's blueprint can be rebuilt from the record (`state`). The loop works on a scratch copy
(`runs/judge_eval/work/<form>.bpt`, the validate runs need a file); the blueprint is written to
`runs/judge_eval/blueprints/<form>.bpt` once, when the loop stops. Stable = the loop stopped on its own (nothing
detected, every flagged field reviewed as it stands, nothing left to change); a form that hits the review cap or
the round limit still gets its `.bpt`, stamped `stable: false` with the reason, so it shows in the review page.
The blueprint's `x_petey_page_check` stamp points at the run record, so the witness and the loop's reviewer read
the verdicts from it (`page_check.verdicts`). The library blueprint of the same name is page-checked for
comparison (record only; the library is never written). A previous run record is kept as `<form>__<when>.json`.

    PYTHONPATH=. venv/bin/python -m petey.validate.form_run --form 5021 --blank source_pdfs/workers_comp/5021.pdf
    PYTHONPATH=. venv/bin/python -m petey.validate.form_run --form 5021 --blank ... --reloop   # from the last run's round 0
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

from petey.paths import BLUEPRINTS, RUNS
from petey.synth.boxes import widget_key
from petey.validate import page_check

E = RUNS / "judge_eval"
WORK, OUT, RECORDS = E / "work", E / "blueprints", E / "form_runs"
UNSTABLE = ("review cap", "max iterations")


def _now() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _dump(bp: dict, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")


def _rel(p: Path) -> str:
    return str(p.resolve().relative_to(RUNS.parent.resolve()))


def _wkey(spec: dict) -> Optional[str]:
    if spec.get("widgets"):
        return "group:" + "|".join(sorted(str(widget_key(w)) for w in spec["widgets"].values()))
    return widget_key(spec.get("widget") or {})


# ------------------------------------------------------------------ record

class Record:
    def __init__(self, form: str, blank: Path, library: Optional[Path]) -> None:
        self.path = RECORDS / f"{form}.json"
        self.data = {"form": form, "blank": str(blank), "library_blueprint": str(library) if library else None,
                     "started": _now(), "rounds": []}
        self.fields: dict[str, dict] = {}            # the state the last round left

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1, ensure_ascii=False, default=str))

    def archive_previous(self) -> Optional[dict]:
        if not self.path.exists():
            return None
        prev = json.loads(self.path.read_text())
        stamp = (prev.get("started") or _now()).replace(" ", "_").replace(":", "")
        self.path.rename(self.path.with_name(f"{self.path.stem}__{stamp}.json"))
        return prev

    def round0(self, bp: dict, verdicts: dict, check: dict, stage: str) -> None:
        self.fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
        self.data["rounds"] = [{"round": 0, "stage": stage, "when": _now(),
                                "top": {k: v for k, v in bp.items() if k != "fields"},
                                "fields": self.fields, "page_check": verdicts, "page_check_run": check}]
        self.save()

    def add_round(self, bp: dict, loop_rec: Optional[dict] = None, **extra) -> dict:
        now = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
        h = page_check.spec_hash
        changed = {n: s for n, s in now.items() if n not in self.fields or h(s) != h(self.fields[n])}
        removed = [n for n in self.fields if n not in now]
        by_key = {_wkey(self.fields[n]): n for n in removed}
        renamed = {n: by_key[_wkey(s)] for n, s in changed.items() if n not in self.fields and _wkey(s) in by_key}
        r = {"round": len(self.data["rounds"]), "stage": "loop" if loop_rec is not None else extra.pop("stage", "?"),
             "when": _now(), "changed": changed, "removed": removed, "renamed": renamed, **extra}
        if loop_rec is not None:
            r["loop"] = loop_rec
        self.data["rounds"].append(r)
        self.fields = now
        self.save()
        return r


def state(rec: dict, upto: Optional[int] = None) -> dict:
    """The blueprint as it stood after round `upto` (default: the last), rebuilt from a run record."""
    rounds = rec["rounds"] if upto is None else rec["rounds"][:upto + 1]
    bp = dict(rounds[0]["top"])
    fields = dict(rounds[0]["fields"])
    for r in rounds[1:]:
        for n in r.get("removed") or []:
            fields.pop(n, None)
        fields.update(r.get("changed") or {})
    bp["fields"] = fields
    return bp


# --------------------------------------------------------------------- run

def spot_check(bp: dict, bp_path: Path, rec: Record, model: str, log) -> tuple[dict, Optional[dict]]:
    """Page-check the fields whose current definition no verdict in the record covers, sending only the pages that
    hold them. Returns ({field: verdict}, the check's cost record or None)."""
    table = page_check.verdict_table(rec.data)
    todo = {n for n, s in (bp.get("fields") or {}).items()
            if isinstance(s, dict) and (n, page_check.spec_hash(s)) not in table}
    if not todo:
        return {}, None
    pages = {b["page"] for r in page_check.numbered(bp) if r["name"] in todo for b in r["boxes"]}
    res = page_check.check(bp_path, model=model, pages=pages, log=log)
    return ({n: v for n, v in res["fields"].items() if n in todo},
            {k: res[k] for k in ("model", "prompt", "pages", "usage", "cost_usd", "when")})


def _stamp_record(bp: dict, rec_path: Path, model: str) -> None:
    bp["x_petey_page_check"] = {"record": _rel(rec_path), "model": model, "prompt": page_check.PROMPT_VERSION,
                                "when": _now()}


def run(form: str, blank: Path, *, reloop: bool = False, library: bool = True, model: str = page_check.MODEL,
        log=print) -> dict:
    lib = BLUEPRINTS / f"{form}.bpt"
    rec = Record(form, blank, lib if lib.exists() else None)
    prev = rec.archive_previous()
    work = WORK / f"{form}.bpt"

    # round 0: the fresh label (or, re-running the loop, the last run's round 0) and its page check
    if reloop:
        if not prev:
            raise SystemExit(f"{form}: no previous run record to re-loop from")
        bp0 = state(prev, 0)
        verdicts0, check0, stage = prev["rounds"][0]["page_check"], prev["rounds"][0].get("page_check_run"), "label (reloop)"
        log(f"[run] {form}: re-loop from round 0 of the run started {prev.get('started')}")
    else:
        work.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([sys.executable, "-u", "-m", "petey.label.auto_label", "--blank", str(blank), "--output",
                            str(work), "--name", form, "--no-register", "--no-retrieval"])
        if r.returncode or not work.exists():
            raise SystemExit(f"{form}: label failed (exit {r.returncode})")
        bp0 = yaml.safe_load(work.read_text(encoding="utf-8")) or {}
        res = page_check.check(work, model=model, log=log)
        verdicts0 = res["fields"]
        check0 = {k: res[k] for k in ("model", "prompt", "pages", "usage", "cost_usd", "when")}
        stage = "label"
    bp0.pop("x_petey_page_check", None)
    rec.round0(bp0, verdicts0, check0, stage)
    _stamp_record(bp0, rec.path, model)
    _dump(bp0, work)
    log(f"[run] {form}: round 0, {len(rec.fields)} fields, "
        f"{sum(1 for v in verdicts0.values() if v.get('verdict') == 'flag')} flagged")

    if not reloop:
        r = subprocess.run([sys.executable, "-u", "-m", "petey.validate.validate", "--blank", str(blank), "--form-id",
                            form, "--bpt", str(work), "--gen-model", "bank", "--case-set", "1", "--n-flat", "0",
                            "--methods", "native,judge:pymupdf"])
        log(f"[run] {form}: validate exit {r.returncode}")

    # the loop, recorded round by round
    from petey.validate.iterate import iterate

    def on_round(loop_rec: dict, bp_path: Path) -> set:
        """Record the round, then spot-check the definitions it introduced (the pages that hold them). The
        verdicts go into the round, where the next round's reviewer finds them; a name / type flag on a field
        the reviewer already judged reopens it."""
        bpr = yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {}
        spot, info = spot_check(bpr, bp_path, rec, model, log)
        r = rec.add_round(bpr, loop_rec, page_check=spot, page_check_run=info)
        flagged = {n for n, v in spot.items() if v.get("verdict") == "flag"}
        log(f"[run] {form}: round {r['round']} recorded: {len(r['changed'])} changed, {len(r['removed'])} removed, "
            f"{len(r['renamed'])} renamed; spot check {len(spot)} fields, {len(flagged)} flagged")
        return {n for n in flagged if spot[n].get("problem") in ("wrong_name", "wrong_type")}

    result = iterate(form, blank, gen_model="bank", methods="native,judge:pymupdf", n_flat=0, gen_cache_only=False,
                     label_model=None, gen_key=None, max_iter=8, describe=True, apply_correct=True,
                     review="flagged", allow_dirty=True, case_set=1, bpt=work, on_round=on_round)

    # final: anything the last round left unchecked (normally nothing: every round spot-checks its changes)
    bp = yaml.safe_load(work.read_text(encoding="utf-8")) or {}
    final, run_info = spot_check(bp, work, rec, model, log)
    stop = result.get("stop") or ""
    stable = not result["status"].startswith("blocked") and not stop.startswith(UNSTABLE)
    rec.add_round(bp, None, stage="final", page_check=final, page_check_run=run_info)
    current = page_check.verdicts(bp)
    rec.data["result"] = {"status": result["status"], "stop": stop, "stable": stable,
                          "review_rounds": result.get("review_rounds"), "residue": result.get("residue"),
                          "finished": _now(), "bpt": _rel(OUT / f"{form}.bpt")}
    rec.save()

    # the blueprint, once
    bp["x_petey_page_check"] = {**(bp.get("x_petey_page_check") or {}), "when": _now(),
                                "fields": len(bp.get("fields") or {}), "checked": len(current),
                                "flagged": sum(1 for v in current.values() if v.get("verdict") == "flag")}
    bp["x_petey_run"] = {"record": _rel(rec.path), "status": result["status"], "stop": stop, "stable": stable,
                         "rounds": len(rec.data["rounds"]) - 1, "review_rounds": result.get("review_rounds"),
                         "when": _now()}
    _dump(bp, OUT / f"{form}.bpt")
    log(f"[run] {form}: {result['status']} ({stop}); {'stable' if stable else 'NOT stable'}; "
        f"{bp['x_petey_page_check']['flagged']} page-check flags; wrote {OUT / f'{form}.bpt'}")

    if library and lib.exists():
        res = page_check.check(lib, model=model, log=log)
        page_check.save(res, lib, stamp=False)
        log(f"[run] {form}: library blueprint {sum(1 for v in res['fields'].values() if v.get('verdict') == 'flag')} "
            f"page-check flags")
    return rec.data


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", required=True)
    ap.add_argument("--blank", required=True, type=Path)
    ap.add_argument("--reloop", action="store_true", help="re-run the loop from the last run's round 0 (no label)")
    ap.add_argument("--no-library", action="store_true", help="skip the library blueprint's comparison check")
    args = ap.parse_args()
    run(args.form, args.blank, reloop=args.reloop, library=not args.no_library)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
