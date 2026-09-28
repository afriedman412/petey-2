"""Import previously generated synthetic ground truth into this repo's cache.

Ground truth is data, not code: cases generated elsewhere (the old
widget-mapper runs) are `{acroform_path: value}` for a blank PDF, and they
are worth keeping because each one cost a multimodal call. This writes them
into `runs/_gen_cache` under the key `validate` computes today, so
`validate --gen-model <model>` hits the cache and only fills, extracts and
scores locally. A manifest records where each entry came from and that it
was generated with the FULL inventory (paths visible to the model), not in
blind mode — it is older data, reused as is.

    python -m petey.validate.import_ground_truth --from <runs dir> [--model claude-sonnet-4-6]

The cache key is sha256(pdf bytes, model, "<form>_intact_001", "0", blind)
— see `synth.generate.generate_from_pdf`. One entry per form: the most
recent old run's intact case. Flat cases in this repo reuse the intact
ground truth (`validate --fresh-flat-gt` to generate fresh ones).
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from petey.paths import BLUEPRINTS, RUNS, SOURCE_PDFS

DEFAULT_MODEL = "claude-sonnet-4-6"


def cache_key(pdf_bytes: bytes, model: str, prefix: str, index: int = 0,
              blind: bool = True) -> str:
    h = hashlib.sha256()
    h.update(pdf_bytes)
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    if blind:
        h.update(b"\x00blind")
    h.update(b"\x00")
    h.update(prefix.encode("utf-8"))
    h.update(b"\x00")
    h.update(str(index).encode("utf-8"))
    return h.hexdigest()


def resolve_blank(bpt_path: Path) -> Path | None:
    bp = yaml.safe_load(bpt_path.read_text(encoding="utf-8")) or {}
    src = bp.get("source_pdf")
    if not src:
        return None
    direct = SOURCE_PDFS / str(src)
    if direct.exists():
        return direct
    hits = [h for h in SOURCE_PDFS.rglob(Path(str(src)).name)
            if "source_pdfs_old" not in h.parts and h.is_file()]
    return hits[0] if hits else None


def old_runs(src: Path) -> dict[str, Path]:
    """form -> most recent old run dir carrying an intact ground truth."""
    latest: dict[str, Path] = {}
    for d in sorted(src.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        if not (d / "case_001_intact" / "ground_truth.json").exists():
            continue
        latest[d.name.rsplit("_", 2)[0]] = d   # sorted: later stamp wins
    return latest


def import_all(src: Path, model: str, cache_dir: Path,
               dry_run: bool = False) -> dict:
    runs = old_runs(src)
    cache_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = cache_dir / "imported.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    stats = {"old_runs": len(runs), "imported": 0, "no_blueprint": 0,
             "no_blank": 0, "already": 0, "empty": 0}
    for form, d in sorted(runs.items()):
        bpt_path = BLUEPRINTS / f"{form}.bpt"
        if not bpt_path.exists():
            stats["no_blueprint"] += 1
            continue
        blank = resolve_blank(bpt_path)
        if blank is None:
            stats["no_blank"] += 1
            continue
        gt = json.loads((d / "case_001_intact" / "ground_truth.json").read_text())
        if not gt:
            stats["empty"] += 1
            continue
        key = cache_key(blank.read_bytes(), model, f"{form}_intact_001", 0)
        target = cache_dir / f"{key}.json"
        if target.exists() and key in manifest:
            stats["already"] += 1
            continue
        if not dry_run:
            target.write_text(json.dumps(gt, indent=2))
            manifest[key] = {
                "form": form, "blank": str(blank.relative_to(SOURCE_PDFS.parent)),
                "source_run": str(d), "n_values": len(gt),
                "generated_blind": False, "cached_under_model": model,
            }
        stats["imported"] += 1
    if not dry_run:
        manifest_path.write_text(json.dumps(manifest, indent=1))
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="src", required=True, type=Path,
                    help="directory of old run dirs (<form>_<stamp>/case_001_intact/ground_truth.json)")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="model name to cache under (what validate will ask for)")
    ap.add_argument("--cache-dir", type=Path, default=RUNS / "_gen_cache")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = import_all(args.src, args.model, args.cache_dir, dry_run=args.dry_run)
    print(json.dumps(stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
