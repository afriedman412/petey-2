"""Vocabulary loader for retrieval-based labeling.

Sources ranked highest-to-lowest confidence:
  1. Sensible config field IDs (per petey-eval/sensible_mapping.yaml)
  2. Union of field slugs across existing widget-mapper/blueprints/*.bpt

Both sources are humanized (snake_case -> spaces) and expanded via a
short acronym-alias table so MiniLM can bridge things like "SSN" <->
"Social Security Number".

Returns `list[(canonical_id, [alias_strings])]` — the shape
`retrieve.match_labels_to_widgets()` expects.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

# Sensible's checked-in JSON configs use JSONC conventions — trailing
# commas before `]`/`}` are common. Strict json.loads chokes. Strip
# them before parsing.

from petey.paths import BLUEPRINTS, SENSIBLE_DIR
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def _load_jsonc(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(_TRAILING_COMMA_RE.sub(r"\1", text))


BPT_DIR = BLUEPRINTS
SENSIBLE_MAPPING = Path(__file__).with_name("sensible_mapping.yaml")

MEF_SUFFIXES = ("_nm", "_ind", "_dt", "_cd", "_txt", "_amt",
                "_pct", "_cnt", "_qty")

EXPANSIONS = {
    "ssn":     "social security number",
    "ein":     "employer identification number",
    "tin":     "taxpayer identification number",
    "zip":     "zip code postal code",
    "llc":     "limited liability company",
    "dob":     "date of birth",
    "npi":     "national provider identifier",
    "vin":     "vehicle identification number",
    "cpt":     "current procedural terminology code",
    "icd":     "international classification of diseases",
    "poa":     "power of attorney",
    "name":    "name of entity or individual full name",
    "date":    "date signed",
    "address": "address street city state zip",
}


def strip_mef_suffix(name: str) -> str:
    for suf in MEF_SUFFIXES:
        if name.endswith(suf):
            return name[:-len(suf)]
    return name


def id_to_display(fid: str) -> str:
    """Convert a slug or dotted id (e.g. `payer.name_nm`) to display text."""
    last = fid.rsplit(".", 1)[-1]
    return strip_mef_suffix(last).replace("_", " ").strip()


def expand_aliases(display: str) -> list[str]:
    aliases = [display]
    for tok in display.split():
        tl = tok.lower()
        if tl in EXPANSIONS:
            aliases.append(EXPANSIONS[tl])
            aliases.append(display.lower().replace(tl, EXPANSIONS[tl]))
    return list(dict.fromkeys(aliases))


def load_sensible_labels(form_id: str) -> list[tuple[str, list[str]]]:
    """Return Sensible field IDs (as canonical_ids) for a form, humanized."""
    if not SENSIBLE_MAPPING.exists():
        return []
    mapping = yaml.safe_load(SENSIBLE_MAPPING.read_text()) or {}
    cfg_paths = mapping.get(form_id) or []
    if isinstance(cfg_paths, str):
        cfg_paths = [cfg_paths]
    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for rel in cfg_paths:
        p = SENSIBLE_DIR / rel
        if not p.exists():
            continue
        try:
            cfg = _load_jsonc(p.read_text())
        except Exception as e:
            print(f"[_vocab] failed to parse Sensible config "
                  f"{rel}: {e}")
            continue
        for f in cfg.get("fields", []) or []:
            fid = f.get("id", "")
            if not fid or fid in seen:
                continue
            display = id_to_display(fid)
            if not display:
                continue
            out.append((fid, expand_aliases(display)))
            seen.add(fid)
    return out


def load_bpt_vocab(exclude_form: str | None = None
                   ) -> list[tuple[str, list[str]]]:
    """Return the union of field slugs across all existing bpts.

    `exclude_form` — bpt stem to skip (avoids self-reference when
    re-labeling a form we already have a bpt for).
    """
    out: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    if not BPT_DIR.exists():
        return out
    for bpt_path in sorted(BPT_DIR.glob("*.bpt")):
        if exclude_form and bpt_path.stem == exclude_form:
            continue
        try:
            bpt = yaml.safe_load(bpt_path.read_text()) or {}
        except Exception:
            continue
        for name in (bpt.get("fields") or {}).keys():
            if name in seen:
                continue
            display = id_to_display(name)
            if not display:
                continue
            out.append((name, expand_aliases(display)))
            seen.add(name)
    return out


def load_form_vocab(form_id: str, *,
                    include_bpt_union: bool = False
                    ) -> list[tuple[str, list[str]]]:
    """Combined vocab for a form. Sensible first (per-form, high-signal),
    optionally supplemented by the union of every other bpt's slugs.

    Each canonical_id appears at most once — Sensible wins on collision.

    `include_bpt_union` defaults to False because dumping ~20k slugs
    from unrelated forms into the label pool lets Hungarian assignment
    pick semantically-close-but-wrong labels (e.g. matching a W-9
    widget to `applicant_ssn` from an insurance form instead of `ssn`).
    Turn on when a form has no Sensible mapping and the risk is
    acceptable.
    """
    labels: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    for cid, aliases in load_sensible_labels(form_id):
        if cid not in seen:
            labels.append((cid, aliases))
            seen.add(cid)
    if include_bpt_union:
        for cid, aliases in load_bpt_vocab(exclude_form=form_id):
            if cid not in seen:
                labels.append((cid, aliases))
                seen.add(cid)
    return labels


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("form_id")
    args = ap.parse_args()
    labels = load_form_vocab(args.form_id)
    sensible_ct = len(load_sensible_labels(args.form_id))
    print(f"form_id: {args.form_id}")
    print(f"  sensible labels: {sensible_ct}")
    print(f"  total labels:    {len(labels)}")
    for i, (cid, aliases) in enumerate(labels[:20]):
        print(f"  [{i}] {cid} -> {aliases[0]!r} "
              f"({len(aliases)} alias(es))")
    if len(labels) > 20:
        print(f"  ... {len(labels) - 20} more")
