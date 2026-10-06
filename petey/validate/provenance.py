"""What a run, a case set and a blueprint were built with, so a finder or classifier change is a versioned event.

Andrew (2026-10-01): do not regenerate the library when the finder changes; re-run the forms being addressed, and
record on every blueprint which finder it was built with, so "rebuild it with the current finder" is the first
step when a form misbehaves. The frozen case sets had no such record: their values are keyed by the finder's box
rects, their cache key did not carry the finder, and a finder change would have left them silently misaligned
(and set 1 of the five test forms may already have been read against a newer class map than the one it was drawn
from).

    case basis      `<finder version>|<classifier model>|<classifier prompt version>`: everything a bank case's
                    values depend on besides the blank and the case key. Bank cases are cached under it
                    (`validate._bank_cache_path`), set manifests record it, and a set whose basis is not the
                    current one refuses to load unless `--rebuild-set` is given.
    build record    the basis, spelled out, plus the generator, case set, run and time; written to the run's
                    `summary.json` and, by the loop, onto the blueprint as `x_petey_build`.
    code version    which code ran (`code_version`): the commit, and a hash plus list of any uncommitted changes. On
                    a machine without `.git` (the GCP runner, docs/RUNNER.md) it is read from CODE_VERSION.json,
                    which `scripts/runner_sync.sh` writes when it copies the working tree there.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import yaml

from petey.paths import RUNS
from petey.synth import classify
from petey.synth.boxes import FINDER_VERSION, finder_stamp

CLASSIFIER_MODEL = classify.MODEL
CLASSIFIER_PROMPT = classify.PROMPT_VERSION


def code_version() -> dict:
    """{commit, branch, dirty: [paths], diff_sha256, source}: the code a run used. From git when the repo has one,
    else from CODE_VERSION.json at the repo root (written by scripts/runner_sync.sh), else {"source": "unknown"}."""
    import hashlib
    import subprocess
    root = RUNS.parent
    vf = root / "CODE_VERSION.json"
    if not (root / ".git").exists() and vf.exists():
        return {**json.loads(vf.read_text(encoding="utf-8")), "source": "CODE_VERSION.json"}

    def git(*a: str) -> str:
        return subprocess.run(["git", *a], cwd=root, capture_output=True, text=True).stdout

    commit = git("rev-parse", "HEAD").strip()
    if not commit:
        return {"source": "unknown"}
    dirty = [ln[3:] for ln in git("status", "--porcelain").splitlines() if ln.strip()]
    diff = subprocess.run(["git", "diff", "HEAD"], cwd=root, capture_output=True).stdout
    return {"commit": commit, "branch": git("rev-parse", "--abbrev-ref", "HEAD").strip(), "dirty": dirty,
            "diff_sha256": hashlib.sha256(diff).hexdigest()[:16] if diff else None, "source": "git"}


def case_basis(finder: str = FINDER_VERSION, model: str = CLASSIFIER_MODEL, prompt: str = CLASSIFIER_PROMPT) -> str:
    return f"{finder}|{model}|{prompt}"


def basis_of_class_map(cmap: dict) -> Optional[str]:
    """The basis a class map was made under (it records finder, model and prompt_version)."""
    if cmap.get("finder") and cmap.get("model") and cmap.get("prompt_version"):
        return case_basis(cmap["finder"], cmap["model"], str(cmap["prompt_version"]))
    return None


def manifest_basis(manifest: dict) -> Optional[str]:
    """A set manifest's basis: recorded, or backfilled from the class map of its first run (sets made before
    2026-10-01 carry none). None when it cannot be told."""
    if manifest.get("basis"):
        return manifest["basis"]
    for run in manifest.get("runs") or []:
        for case in sorted((RUNS / run).glob("case_*_intact")):
            cp = case / "class_map.json"
            if cp.exists():
                try:
                    b = basis_of_class_map(json.loads(cp.read_text(encoding="utf-8")))
                except Exception:
                    b = None
                if b:
                    return b
    return None


def build_record(*, generator: Optional[str] = None, case_set: Optional[int] = None,
                 run: Optional[str] = None, bpt: Optional[Path] = None) -> dict:
    fs = finder_stamp()
    return {
        "basis": case_basis(),
        "finder": fs["version"], "finder_label": fs["label"], "finder_code_sha": fs["code_sha"], "finder_env": fs["env"],
        "classifier_model": CLASSIFIER_MODEL, "classifier_prompt": CLASSIFIER_PROMPT,
        "generator": generator, "case_set": case_set, "run": run,
        "blueprint": str(bpt) if bpt else None,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def stamp_blueprint(bp_path: Path, record: dict) -> None:
    """Write `x_petey_build` on the blueprint: the build of its latest validation (the loop calls this after every
    validate run). Field order and everything else in the file are kept."""
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8")) or {}
    bp["x_petey_build"] = {k: v for k, v in record.items() if v is not None}
    bp_path.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                       encoding="utf-8")


def build_of_run(run_dir: Path) -> Optional[dict]:
    sp = run_dir / "summary.json"
    if not sp.exists():
        return None
    try:
        return json.loads(sp.read_text(encoding="utf-8")).get("build")
    except Exception:
        return None
