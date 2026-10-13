"""Iterate a blueprint to completion: validate -> detect -> fix -> validate again.

One pass of the loop finds defects and applies the mechanical fixes; this
repeats it until a fix pass changes nothing, and then says what is left and
which taxonomy class it belongs to. The blueprint on disk
(`blueprints/<form>.bpt`) is the state that advances; every validate run
copies it, so each iteration is scored against its own snapshot.

    python -m petey.validate.iterate --form fw9 --gen-model local
    python -m petey.validate.iterate --form va_form_10_10ez --blank "source_pdfs/VA Form 10-10EZ.pdf" \\
        --label-model none --gen-model local           # no blueprint yet: label first, no API
    python -m petey.validate.iterate --form vba21526ez --gen-model claude-sonnet-4-6 --gen-cache-only \\
        --methods native,judge:pymupdf --apply-correct  # with the judge arm and cycle rebinds

Per iteration:
  1. validate  — `petey.validate.validate` (label if the blueprint is missing;
                 generate; fill; extract with each method; score).
  2. detect    — from the intact case: verdicts, `gt_shape_mismatch` by reason,
                 rule violations; if a meaning-arm score exists, `method_delta`
                 findings by cause and `correct.analyse_run` cycles.
  3. fix       — `retype` rules + descriptions on the blueprint; with
                 `--apply-correct`, closed cycles whose every rebind the
                 oracle graded `confirmed`.
With `--review`, the LLM reviewer runs after step 3 for as long as some
flagged field has not been reviewed in its current form (its name and its
definition, widget included): new flags, fields a rebind moved, fields an
edit changed that are still flagged. A field the reviewer has seen as it
stands, before or after its edit (a restored edit leaves it in the form it
was reviewed in), is not reviewed again. Up to `--review-rounds` rounds
(default 4); each round's edits are judged field by field by the next
validation, worse ones restored (2026-10-06, Andrew: keep going until no
errors; "no errors" means none the reviewer has not yet seen, since part of
the residue is the reader's or the generator's and no edit clears it).
Stops when step 3 and the reviewer change nothing (`clean` if nothing was
detected, `converged_with_residue` otherwise) or at `--max-iter`; `stop`
records why. The residue is
reported by detector reason and mapped to `defect_taxonomy` class names, so
what remains is a decision list, not a mystery.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

from petey.label import xfa as xfa_mod
from petey.paths import BLUEPRINTS, RUNS
from petey.synth.local import widget_limits
from petey.validate import correct as correct_mod
from petey.validate import method_delta
from petey.validate import provenance
from petey.validate.retype import describe_blueprint, resolve_blank, retype_blueprint

# detector reason -> taxonomy classes it can be (the class that applies is a
# per-field question; the loop reports the reason and the candidates)
CLASS_OF = {
    "pattern_vs_value": ("part_typed_as_whole", "short_shape_on_wide_box", "value_overflows_box"),
    "date_type_vs_value": ("part_typed_as_whole", "approximate_date_month_year"),
    "number_type_vs_value": ("nonnumeric_in_numeric_field",),
    "name_vs_value": ("name_slide",),
    "value_not_in_values": ("yn_column",),
    "rule_violation": ("rule_violation",),
    "defect": ("name_rotation", "name_slide", "repeated_section_ambiguity"),
    "unlocatable": ("missing_description", "repeated_section_ambiguity"),
    "substring": ("value_overflows_box", "compound_widget"),
    "boolean": ("yn_column",),
    "phantom": ("phantom",),
}


def run_validate(form: str, blank: Optional[Path], *, gen_model: str, methods: str,
                 n_flat: int, gen_cache_only: bool, label_model: Optional[str],
                 gen_key: Optional[str], case_set: Optional[int] = None,
                 n_cases: Optional[int] = None, bpt: Optional[Path] = None,
                 rebuild_set: bool = False) -> Path:
    if blank is None:
        bp = yaml.safe_load((bpt or BLUEPRINTS / f"{form}.bpt").read_text(encoding="utf-8"))
        blank = resolve_blank(bp)
        if blank is None:
            raise SystemExit(f"{form}: no blank PDF found for source_pdf={bp.get('source_pdf')!r}")
    cmd = [sys.executable, "-m", "petey.validate.validate", "--blank", str(blank),
           "--form-id", form, "--n-flat", str(n_flat), "--methods", methods,
           "--gen-model", gen_model]
    if gen_cache_only:
        cmd.append("--gen-cache-only")
    if label_model:
        cmd += ["--label-model", label_model]
    if gen_key:
        cmd += ["--gen-key", gen_key]
    if case_set is not None:
        cmd += ["--case-set", str(case_set)]
    if n_cases:
        cmd += ["--n-cases", str(n_cases)]
    if bpt is not None:
        cmd += ["--bpt", str(bpt)]
    if rebuild_set:
        cmd.append("--rebuild-set")
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    m = re.search(r"run_dir=(\S+)", proc.stdout or "")
    if proc.returncode != 0 or not m:
        raise RuntimeError(f"validate failed for {form}:\n{(proc.stdout or '')[-800:]}\n{(proc.stderr or '')[-800:]}")
    return Path(m.group(1))


def intact_dirs(run_dir: Path) -> list[Path]:
    """Every intact case of a run: one, or the members of a case set."""
    return sorted(d for d in run_dir.glob("case_*_intact") if d.is_dir())


def detect(form: str, run_dir: Path) -> dict:
    """What the run detected. Over a case set the verdict counts are summed
    across cases, a shape contradiction or rule violation counts once per
    field (any case), so one bad draw cannot be outvoted by clean ones."""
    intact = run_dir / "case_001_intact"
    out: dict = {"run": run_dir.name, "verdicts": {}, "shape": {}, "rule_violations": 0,
                 "delta": {}, "confirmed_cycles": [], "generation": None,
                 "n_cases": len(intact_dirs(run_dir))}
    score_path = intact / "score_native.json"
    if not score_path.exists():
        summary = json.loads((run_dir / "summary.json").read_text()) if (run_dir / "summary.json").exists() else {}
        out["generation"] = "no_ground_truth" if not summary.get("intact", {}).get("native") else "no_score"
        return out
    verdicts: collections.Counter = collections.Counter()
    shape_fields: dict[str, str] = {}
    rule_fields: set[str] = set()
    for d in intact_dirs(run_dir):
        sp = d / "score_native.json"
        if not sp.exists():
            continue
        r = json.loads(sp.read_text())
        verdicts.update(r.get("verdicts", {}))
        shape_fields.update(r.get("gt_shape_mismatches") or {})
        for rv in r.get("rule_violations") or []:
            rule_fields.add(json.dumps(rv, sort_keys=True, default=str))
    out["verdicts"] = dict(verdicts)
    out["shape"] = dict(collections.Counter(shape_fields.values()))
    out["rule_violations"] = len(rule_fields)
    cd = intact / "class_disagreements.json"
    if cd.exists():
        rows = json.loads(cd.read_text())
        out["class_disagree"] = sum(1 for r in rows if r.get("tier") == 1)
        out["class_suggest"] = sum(1 for r in rows if r.get("tier") == 2)
        out["class_uncaptioned"] = sum(1 for r in rows if r.get("tier") == 3)
    if method_delta.judge_scores(intact):
        res = method_delta.compare_run(run_dir, "auto")
        # method_delta rows carry `verdict` (differ / extract_miss) AND `cause`
        # (defect / unlocatable / substring / ...); the loop judges by cause.
        out["delta"] = dict(collections.Counter(f.get("cause") or f["verdict"] for f in res["findings"]
                                                if not f.get("flat_only")))
        ana = correct_mod.analyse_run(form, run_dir)
        if ana:
            for c in ana["cycles"]:
                if c["rebinds"] and all(rb.get("grade") == "confirmed" for rb in c["rebinds"]):
                    out["confirmed_cycles"].append(c)
    out["total"] = (sum(out["shape"].values()) + out["rule_violations"]
                    + sum(v for k, v in out["delta"].items() if k in ("defect", "unlocatable"))
                    + out["verdicts"].get("differ", 0) + out["verdicts"].get("extract_miss", 0)
                    + out.get("class_disagree", 0))
    # Witness flags (a widget's text belongs to another field; `witness.against_flags`) open a review round but
    # stay out of `total`: they come from the blank, not the case, so they cannot judge a round, and counting
    # them would let a rename made to satisfy them score itself 'better'. The adjudicator judges those renames.
    try:
        from petey.validate.witness import against_flags
        out["witness"] = len(against_flags(run_dir))
    except Exception as e:
        out["witness_error"] = f"{type(e).__name__}: {e}"
    return out


def starting_state(bp_path: Path) -> dict:
    """Where the loop starts: the blueprint's last commit, whether the file on
    disk differs from it, and how many fields already carry review changes.
    Recorded in the output so a before/after is never read against the wrong
    starting point."""
    rel = str(bp_path.resolve().relative_to(BLUEPRINTS.resolve().parent))
    state: dict = {"path": rel}
    try:
        state["commit"] = subprocess.run(["git", "log", "-1", "--format=%h", "--", rel],
                                         capture_output=True, text=True, cwd=BLUEPRINTS.parent).stdout.strip() or None
        state["uncommitted"] = subprocess.run(["git", "diff", "--quiet", "--", rel],
                                              cwd=BLUEPRINTS.parent).returncode != 0
    except Exception:
        pass
    if bp_path.exists():
        fields = (yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {}).get("fields") or {}
        state["reviewed_fields"] = sum(1 for f in fields.values() if isinstance(f, dict) and f.get("x_petey_review"))
    return state


_RANK = {"agree": 0, "substring": 1, "numeric": 1, "phantom": 1, "punctuation": 1,
         "boolean": 1, "date_format": 1, "unlocatable": 2, "defect": 3}


def field_status(run_dir: Path) -> dict[str, int]:
    """Per-field badness after a validation: 0 = fine. Shape contradiction
    adds 1; the name-based reader's cause adds its rank (wrong value worse
    than not found, not found worse than a format quibble)."""
    status: dict[str, int] = collections.defaultdict(int)
    from petey.validate.field_chain import chain_for_run
    for intact in intact_dirs(run_dir):
        per_case: dict[str, int] = collections.defaultdict(int)
        native = json.loads((intact / "score_native.json").read_text())
        # The case was built box -> class -> value. A field whose box failed, or whose caption the classifier
        # took from a neighbouring box, has a case that says nothing about the blueprint: its class, regex and
        # judge signals are one misreading, not evidence (MA LIC100, 2026-09-30: a right field renamed from a
        # misread caption scored 'better' because the flags built on that caption cleared).
        held = {f for f, r in chain_for_run(run_dir, intact.name).items() if r.get("stage") in ("box", "class")}
        disagree = set(native.get("gt_shape_mismatches") or {})
        cd = intact / "class_disagreements.json"
        if cd.exists():
            disagree |= {row["field"] for row in json.loads(cd.read_text()) if row.get("tier") == 1}
        for f in disagree - held:          # class and regex disagreement on a bank case: one signal, counted once
            per_case[f] += 1
        arm = method_delta.preferred_judge(intact)
        if arm:
            for r in method_delta.compare_case(intact, arm):
                if r["field"] not in held:
                    per_case[r["field"]] += _RANK.get(r.get("cause") or "", 2)
        for f, v in per_case.items():
            status[f] = max(status[f], v)
    return status


def judge_review(bp_path: Path, snapshot: str, before: dict[str, int], after: dict[str, int]) -> dict:
    """Keep each reviewed field's change only if the loop says it helped.

    A field is identified across the rename by `x_petey_review.old_name`.
    better -> keep; worse -> restore the old spec and name; same -> keep a
    declaration change (type / pattern / description: harmless to the reader
    and judged by shape) but restore a rename, which has shown nothing,
    unless the adjudicator upheld it from the page (`adjudicated: proposed`):
    that evidence is independent of the case, and a class-stage field's
    before and after are both zero by construction."""
    cur = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
    old = yaml.safe_load(snapshot)
    fields = cur["fields"]
    verdict = collections.Counter()
    restore: dict[str, tuple[str, dict]] = {}
    outcomes: dict[str, dict] = {}   # old_name -> what the loop decided
    for name, spec in list(fields.items()):
        rv = spec.get("x_petey_review")
        if not rv or rv.get("judged"):
            continue
        old_name = rv.get("old_name", name)
        b, a = before.get(old_name, 0), after.get(name, 0)
        renamed = "name" in rv.get("changed", [])
        if a < b:
            verdict["better"] += 1
            rv["judged"] = f"kept: {b} -> {a}"
            outcomes[old_name] = {"outcome": "kept_better", "before": b, "after": a, "new_name": name}
        elif a > b or (renamed and rv.get("adjudicated") != "proposed"):
            verdict["worse" if a > b else "same_rename"] += 1
            if old_name in old["fields"]:
                restore[name] = (old_name, old["fields"][old_name])
            outcomes[old_name] = {"outcome": "restored_worse" if a > b else "restored_no_effect",
                                  "before": b, "after": a, "new_name": name}
        else:
            verdict["same_kept"] += 1
            rv["judged"] = f"kept: {b} -> {a}"
            outcomes[old_name] = {"outcome": "kept_same", "before": b, "after": a, "new_name": name}
    if restore:
        rebuilt = {}
        for k, v in fields.items():
            if k in restore:
                old_name, old_spec = restore[k]
                rebuilt[old_name] = old_spec
            else:
                rebuilt[k] = v
        cur["fields"] = rebuilt
        for rule in cur.get("x_petey_rules") or []:
            if "mutex" in rule:
                rule["mutex"] = [restore[m][0] if m in restore else m for m in rule["mutex"]]
    bp_path.write_text(yaml.safe_dump(cur, sort_keys=False, allow_unicode=True,
                                      default_flow_style=False), encoding="utf-8")
    verdict["restored"] = len(restore)
    out = dict(verdict)
    out["outcomes"] = outcomes
    return out


PAIRS = RUNS / "review_pairs.jsonl"


def record_pairs(form: str, run_dir: Path, pending: dict, outcomes: dict) -> int:
    """Training data as a side effect: every reviewed field's evidence, the
    model's decision, and what the loop decided about it. "ok" verdicts are
    recorded too — a field the model correctly left alone is a pair."""
    n = 0
    with PAIRS.open("a", encoding="utf-8") as fh:
        for d in pending.get("decisions", []):
            field = d.get("field")
            ev = pending.get("evidence", {}).get(field)
            if ev is None:
                continue
            rec = {"form": form, "run": run_dir.name, "model": pending.get("model"),
                   "field": field, "evidence": ev, "decision": d,
                   "loop": outcomes.get(field, {"outcome": "ok_not_applied" if d.get("verdict") == "ok"
                                                else "not_applied"}),
                   "recorded": time.strftime("%Y-%m-%dT%H:%M:%S")}
            fh.write(json.dumps(rec, default=str) + "\n")
            n += 1
    return n


def fix(form: str, detection: dict, *, describe: bool, apply_correct: bool,
        bpt: Optional[Path] = None, rebound: Optional[set] = None) -> collections.Counter:
    """Rule fixes and, with `apply_correct`, confirmed rebind cycles. The names of fields whose widget a rebind
    moved are added to `rebound`: this round's evidence about them describes the old binding."""
    bp_path = bpt or BLUEPRINTS / f"{form}.bpt"
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
    blank = resolve_blank(bp)
    limits = widget_limits(blank) if blank else {}
    changes = retype_blueprint(bp, limits)
    if describe and blank:
        try:
            tpl = xfa_mod.parse(blank)
        except Exception:
            tpl = None
        changes.update(describe_blueprint(bp, limits, tpl))
    if changes:
        bp_path.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True,
                                          default_flow_style=False), encoding="utf-8")
    if apply_correct:
        for c in detection.get("confirmed_cycles") or []:
            n = correct_mod.apply_rebinds(bp_path, c["rebinds"])
            if n:
                changes[f"rebind_cycle:{len(c['names'])}"] += n
                if rebound is not None:
                    rebound.update(r["field"] for r in c["rebinds"] if r.get("field"))
    return changes


def residue(detection: dict) -> list[tuple[str, int, tuple[str, ...]]]:
    rows = []
    for reason, n in detection.get("shape", {}).items():
        rows.append((reason, n, CLASS_OF.get(reason, ())))
    if detection.get("rule_violations"):
        rows.append(("rule_violation", detection["rule_violations"], CLASS_OF["rule_violation"]))
    for cause, n in detection.get("delta", {}).items():
        if cause in ("defect", "unlocatable", "substring", "boolean", "phantom"):
            rows.append((f"delta:{cause}", n, CLASS_OF.get(cause, ())))
    v = detection.get("verdicts", {})
    for k in ("differ", "extract_miss"):
        if v.get(k):
            rows.append((f"native:{k}", v[k], ("extraction mechanics",)))
    return sorted(rows, key=lambda t: -t[1])


def _defs(bp: dict) -> dict[str, str]:
    from petey.validate.page_check import spec_hash
    return {n: spec_hash(s) for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}


def already_seen(bp_path: Path, seen: set[tuple[str, str]]) -> set[str]:
    """Fields whose name and current definition the reviewer has already judged."""
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {}
    return {n for n, h in _defs(bp).items() if (n, h) in seen}


def _reopen(seen: set[tuple[str, str]], bp_path: Path, names) -> None:
    """Forget that the reviewer judged these fields as they now stand."""
    if names:
        now = _defs(yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {})
        seen -= {(n, now[n]) for n in names if n in now}


def reviewed_pairs(snapshot: str, bp_path: Path, res: dict) -> set[tuple[str, str]]:
    """(name, definition) of every field the review looked at, as it was before the round and as the round left
    it (a rename under its new name): either form, seen again, needs no second review."""
    before = _defs(yaml.safe_load(snapshot) or {})
    after = _defs(yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {})
    renamed = {d.get("field"): d.get("name") for d in res.get("decisions") or [] if d.get("name")}
    out = set()
    for e in res.get("evidence") or []:
        f = e.get("field")
        if f in before:
            out.add((f, before[f]))
        for n in (f, renamed.get(f)):
            if n and n in after:
                out.add((n, after[n]))
    return out


def iterate(form: str, blank: Optional[Path], *, gen_model: str, methods: str, n_flat: int,
            gen_cache_only: bool, label_model: Optional[str], gen_key: Optional[str],
            max_iter: int, describe: bool, apply_correct: bool,
            review: str = "none", review_model: Optional[str] = None,
            review_effort: str = "medium", review_rounds: int = 4,
            allow_dirty: bool = False, case_set: Optional[int] = None,
            n_cases: Optional[int] = None, bpt: Optional[Path] = None,
            adjudicate: bool = True, adjudicator_model: Optional[str] = None,
            rebuild_set: bool = False, on_round=None) -> dict:
    """See the module docstring. With `review` != "none", after the rule
    fixes the LLM reviewer (`review.py`) looks at the flagged fields and its
    fixes are applied; the NEXT validation judges them. If detections did
    not go down, the blueprint is restored to its pre-review state — the
    model never grades its own work. `on_round(rec, bp_path)`, when given, is called after every round with the
    round's record, once the blueprint on disk is the state the next round starts from (`form_run.py` keeps that
    state round by round and spot-checks the fields the round changed). It may return field names to reopen: new
    evidence (a spot-check flag) on a definition the reviewer already judged, so the next round reviews it again."""
    if review_model is None:
        from petey.validate.review import DEFAULT_MODEL as review_model     # PETEY_MODEL_REVIEWER
    history = []
    status = "max_iter"
    bp_path = bpt or BLUEPRINTS / f"{form}.bpt"   # a side copy (validate --bpt) runs the loop outside the library
    pending: Optional[dict] = None   # a review awaiting the loop's verdict
    rounds_done = 0
    seen: set[tuple[str, str]] = set()   # (field name, definition hash) the reviewer has judged
    stop = None
    start = starting_state(bp_path)
    if start.get("reviewed_fields") and start.get("uncommitted") and review != "none" and not allow_dirty:
        raise SystemExit(
            f"{form}: the blueprint on disk has {start['reviewed_fields']} fields with uncommitted "
            f"review changes; a review run would measure a second pass. Commit or restore it "
            f"(git checkout -- {start['path']}), or pass --allow-dirty.")
    if start.get("uncommitted"):
        print(f"[{form}] note: starting from an uncommitted blueprint ({start})")
    for i in range(1, max_iter + 1):
        t0 = time.time()
        stop = None                       # why the loop ends, if it ends this round
        run_dir = run_validate(form, blank, gen_model=gen_model, methods=methods, n_flat=n_flat,
                               gen_cache_only=gen_cache_only, label_model=label_model, gen_key=gen_key,
                               case_set=case_set, n_cases=n_cases, bpt=bpt, rebuild_set=rebuild_set and i == 1)
        build = provenance.build_of_run(run_dir)
        if build:
            # the blueprint carries the build of its latest validation (finder, classifier, set, run): "rebuild it
            # with the current finder" is the first step when a form misbehaves (Andrew, 2026-10-01)
            provenance.stamp_blueprint(bp_path, build)
        det = detect(form, run_dir)
        if det.get("generation"):
            history.append({"iteration": i, "run": run_dir.name, "blocked": det["generation"]})
            status = "blocked:" + det["generation"]
            print(f"[{form}] iter {i}: {status}")
            break
        judged = None
        if pending is not None:
            after = field_status(run_dir)
            judged = judge_review(bp_path, pending["snapshot"], pending["status"], after)
            outcomes = judged.pop("outcomes", {})
            record_pairs(form, run_dir, pending, outcomes)
            judged.update({"detected_before": pending["detected"], "detected_after": det["total"],
                           "cost_usd": pending["cost_usd"]})
            print(f"[{form}] review judged field by field: {judged}")
            pending = None
            if judged.get("restored"):
                # Restored fields change the blueprint: validate once more so
                # the final numbers describe what is on disk.
                history.append({"iteration": i, "run": run_dir.name, "detected": det["total"],
                                "verdicts": det["verdicts"], "shape": det["shape"], "delta": det["delta"],
                                "rule_violations": det["rule_violations"], "review": judged,
                                "fixed": {"review_restored": judged["restored"]}})
                print(f"[{form}] iter {i}: detected={det['total']} delta={det['delta']} "
                      f"-> restored {judged['restored']} reviewed fields")
                if on_round:
                    _reopen(seen, bp_path, on_round(history[-1], bp_path))
                continue
        rebound: set = set()
        changes = fix(form, det, describe=describe, apply_correct=apply_correct, bpt=bpt, rebound=rebound)
        review_rec = None
        if review != "none" and rounds_done >= review_rounds and (det["total"] > 0 or det.get("witness")):
            stop = f"review cap ({review_rounds} rounds)"
        if review != "none" and rounds_done < review_rounds and (det["total"] > 0 or det.get("witness")):
            from petey.validate.review import review as run_review
            snapshot = bp_path.read_text(encoding="utf-8")
            # A field a rebind just moved is not reviewed this round: the run's flags and the reviewer's evidence
            # describe its old widget, so an edit made for that box lands on the field now bound elsewhere (1014r,
            # 2026-10-06: City / State / E-Mail rebound, and the reviewer's e-mail type went onto the City box).
            # The next round validates the new binding and reviews it then.
            res = run_review(form, run_dir=run_dir, scope=review, model=review_model,
                             effort=review_effort, apply=True, bpt_path=bpt, adjudicate=adjudicate,
                             adjudicator_model=adjudicator_model, skip=rebound | already_seen(bp_path, seen))
            if res["fields_reviewed"]:
                rounds_done += 1
                seen |= reviewed_pairs(snapshot, bp_path, res)
            else:
                stop = "every flagged field already reviewed as it stands"
            applied = {k: v for k, v in res["applied"].items() if k != "ok" and not k.startswith("rejected")}
            review_rec = {k: res[k] for k in ("fields_reviewed", "verdicts", "applied", "usage", "cost_usd")}
            if res.get("adjudicated"):
                review_rec["adjudicated"] = {k: res["adjudicated"][k] for k in ("model", "tally", "cost_usd", "records")}
            print(f"[{form}] review round {rounds_done} ({review_model}, {review_effort}): {res['fields_reviewed']} fields, "
                  f"{res['verdicts']} -> applied {res['applied']} (${res['cost_usd']})")
            if applied:
                pending = {"snapshot": snapshot, "detected": det["total"], "applied": applied,
                           "cost_usd": res["cost_usd"], "status": field_status(run_dir),
                           "model": review_model, "decisions": res.get("decisions", []),
                           "evidence": {e["field"]: e for e in res.get("evidence", [])}}
                for k, v in applied.items():
                    changes[f"review:{k}"] += v
        rec = {"iteration": i, "run": run_dir.name, "seconds": round(time.time() - t0, 1),
               "verdicts": det["verdicts"], "shape": det["shape"], "delta": det["delta"],
               "rule_violations": det["rule_violations"], "detected": det["total"],
               "witness": det.get("witness"), "fixed": dict(changes)}
        if review_rec:
            rec["review_run"] = review_rec
        if judged:
            rec["review"] = judged
        history.append(rec)
        print(f"[{form}] iter {i}: detected={det['total']} verdicts={det['verdicts']} "
              f"shape={det['shape']} delta={det['delta']} -> fixed={dict(changes)} ({rec['seconds']}s)")
        if on_round:
            _reopen(seen, bp_path, on_round(rec, bp_path))
        if not changes:
            status = "clean" if det["total"] == 0 else "converged_with_residue"
            stop = stop or ("nothing detected" if det["total"] == 0 else "no rule fix and no review edit")
            break
    if status == "max_iter":
        stop = f"max iterations ({max_iter})"
    if stop:
        print(f"[{form}] stopped: {stop}; {rounds_done} review round(s)")
    result = {"form": form, "status": status, "stop": stop, "review_rounds": rounds_done,
              "start": start, "iterations": history,
              "residue": residue(history[-1] if history and "detected" in history[-1] else {})}
    if result["residue"]:
        print(f"[{form}] {status}; residue by detector reason -> taxonomy classes:")
        for reason, n, classes in result["residue"]:
            print(f"    {n:>5}  {reason:<26} {' / '.join(classes)}")
    else:
        print(f"[{form}] {status}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--form", default=None, help="blueprint stem (created by labeling if missing)")
    ap.add_argument("--forms", default=None, help="comma-separated stems")
    ap.add_argument("--all", action="store_true", help="every ready blueprint (run_all's target set)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--blank", type=Path, default=None, help="blank PDF (needed when the blueprint does not exist)")
    ap.add_argument("--gen-model", default="local", help="'local' (no API) or a model id")
    ap.add_argument("--gen-cache-only", action="store_true")
    ap.add_argument("--gen-key", default=None)
    ap.add_argument("--bpt", type=Path, default=None,
                    help="blueprint to run instead of blueprints/<form>.bpt (a side copy, e.g. the 10-10EZ relabel)")
    ap.add_argument("--case-set", type=int, default=None, help="versioned case set id (validate --case-set)")
    ap.add_argument("--n-cases", type=int, default=None, help="intact cases in the set (default 3)")
    ap.add_argument("--methods", default="native")
    ap.add_argument("--n-flat", type=int, default=1)
    ap.add_argument("--label-model", default=None, help="'none' labels without an API when the blueprint is missing")
    ap.add_argument("--max-iter", type=int, default=8)
    ap.add_argument("--no-describe", action="store_true")
    ap.add_argument("--apply-correct", action="store_true",
                    help="also apply closed cycles graded confirmed by correct.py")
    ap.add_argument("--review", choices=["none", "flagged", "all"], default="none",
                    help="LLM reviewer on flagged (or all) fields after the rule fixes; "
                         "kept only if the next validation detects less")
    ap.add_argument("--review-model", default=None, help="default: review.DEFAULT_MODEL (PETEY_MODEL_REVIEWER)")
    ap.add_argument("--review-effort", default="medium")
    ap.add_argument("--review-rounds", type=int, default=4,
                    help="cap on review rounds; a round runs only while some flagged field is unreviewed as it stands")
    ap.add_argument("--allow-dirty", action="store_true",
                    help="allow a review run on a blueprint with uncommitted review changes")
    ap.add_argument("--no-adjudicate", action="store_true",
                    help="land the reviewer's contested renames without the page adjudicator")
    ap.add_argument("--adjudicator-model", default=None, help="vision model for contested renames (adjudicate.MODEL)")
    ap.add_argument("--rebuild-set", action="store_true",
                    help="first validate passes --rebuild-set: draw the case set again under the current basis")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    rv = dict(review=args.review, review_model=args.review_model,
              review_effort=args.review_effort, review_rounds=args.review_rounds, case_set=args.case_set, n_cases=args.n_cases, bpt=args.bpt,
              allow_dirty=args.allow_dirty, adjudicate=not args.no_adjudicate,
              adjudicator_model=args.adjudicator_model, rebuild_set=args.rebuild_set)
    if args.all or args.forms:
        from petey.validate.run_all import ready_targets
        targets = ready_targets()
        if args.forms:
            wanted = {f.strip() for f in args.forms.split(",") if f.strip()}
            targets = [t for t in targets if t[0] in wanted]
        if args.limit:
            targets = targets[:args.limit]
        out = args.out or (RUNS / "iterate_all.json")
        results = []
        t0 = time.time()
        for i, (form, blank) in enumerate(targets, 1):
            try:
                res = iterate(form, blank, gen_model=args.gen_model, methods=args.methods,
                              n_flat=args.n_flat, gen_cache_only=args.gen_cache_only,
                              label_model=args.label_model, gen_key=args.gen_key,
                              max_iter=args.max_iter, describe=not args.no_describe,
                              apply_correct=args.apply_correct, **rv)
            except Exception as e:  # one form must not stop the library
                res = {"form": form, "status": f"error: {str(e)[:200]}", "iterations": [], "residue": []}
                print(f"[{form}] {res['status']}")
            results.append(res)
            out.write_text(json.dumps(results, indent=1, default=str))
            print(f"  [{i}/{len(targets)}] {form:<24} {res['status']}", flush=True)
        c = collections.Counter(r["status"].split(":")[0] for r in results)
        print(f"[iterate] {len(results)} forms in {(time.time() - t0) / 60:.1f} min: {dict(c)} -> {out}")
        return 0
    if not args.form:
        ap.error("--form, --forms or --all is required")
    res = iterate(args.form, args.blank, gen_model=args.gen_model, methods=args.methods,
                  n_flat=args.n_flat, gen_cache_only=args.gen_cache_only,
                  label_model=args.label_model, gen_key=args.gen_key, max_iter=args.max_iter,
                  describe=not args.no_describe, apply_correct=args.apply_correct, **rv)
    out = args.out or (RUNS / f"iterate_{args.form}.json")
    out.write_text(json.dumps(res, indent=1, default=str))
    print(f"[ok] {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
