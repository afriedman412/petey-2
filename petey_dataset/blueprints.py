"""The blueprints: where each section keeps them, a form's working copy, parsed loading, and what the dataset reads
off a blueprint without any model: the boxes with a page, the printed tag, the Split Field tags, the page sizes.
Lifted from the review page's `hand_review` and `draft` (2026-11-05), so the benchmark runner reads them without the
petey package."""
from __future__ import annotations

import collections
import hashlib
import json
import os
import pickle
import threading
from pathlib import Path
from typing import Optional

import yaml

from petey_dataset import BENCHMARK, BLUEPRINTS, DRAFTS, HAND_REVIEW, ROOT, RUNS, SOURCE_PDFS, split_types

_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)     # libyaml when present: 10x faster over 229 blueprints

# the sections, in the review page's order: the id of a blueprint is `<tag>__<file stem>`
SOURCES = {"lib": BLUEPRINTS, "je": RUNS / "judge_eval" / "blueprints", "rl": RUNS / "relabel" / "blueprints",
           "fl": RUNS / "flat" / "blueprints",      # flat forms: page-made blueprints, path-less widgets
           # the flat-structure benchmark's forms (Andrew, 2026-10-27: "can you load the benchmark pdfs under a new
           # section in the review app?"): the business-like corpus set, runs/acquisition/safedocs/business_set.json
           "bm": RUNS / "benchmark" / "blueprints",
           # forms Andrew downloaded by hand for the benchmark (source_pdfs/manual_grabs), their own section (Andrew,
           # 2026-10-28: "if so, can you put them in their own section?")
           "mg": RUNS / "manual_grabs" / "blueprints",
           # the finance forms scraped 2026-10-29 from banks', brokerages' and insurers' forms pages, their own section
           # (Andrew, 2026-10-29: "can you put the new downloads in their own section" ... "just today's batch")
           "fin": RUNS / "finance" / "blueprints",
           # private-sector forms (Andrew, 2026-11-02: "can you create a new section called 'private' in the review
           # app?"): the benchmark is about 78% government pages, and the goal is government at most 60-65%
           "pv": RUNS / "private" / "blueprints",
           # the forms added the evening of 2026-11-03 in one section (Andrew, 2026-11-04: "can you put all the forms
           # added last night (11/3 pm) in one section"): 26 hand-picked (source_pdfs/manual_dl_110326) and 129 big
           # publishers', moved from mg / bm; later stagings go to their usual sections
           "nov3": RUNS / "nov3" / "blueprints",
           # the library before the naming standard's renames, kept to check against (Andrew, 2026-10-24: "let's keep
           # the old copies around so I can do a little more validation against old versions before we let them slide")
           "old": RUNS / "naming_2026-10-24" / "before"}


def blueprint_paths() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for tag, d in SOURCES.items():
        if not d.exists():
            continue
        for p in sorted(d.glob("*.bpt")):
            if tag == "je" and p.stem.endswith(("_v0", "_run1", "_prev")):
                continue
            out[f"{tag}__{p.stem}"] = p
    return out


def launch_tiers() -> dict[str, str]:
    """{blank file name: launch tier} from registry/launch_ranking_v2.csv (the forms acquired for launch), read once."""
    if not hasattr(launch_tiers, "tiers"):
        import csv
        f = ROOT / "registry" / "launch_ranking_v2.csv"
        if not f.exists():
            launch_tiers.tiers = {}
        else:
            with f.open() as fh:
                launch_tiers.tiers = {r["file"]: r["tier"] for r in csv.DictReader(fh)}
    return launch_tiers.tiers


# ---- the working copy (the review page's draft, `petey.validate.draft`) ----

def draft_dir(bid: str) -> Path:
    return DRAFTS / bid


def draft_meta(bid: str) -> Optional[dict]:
    m = draft_dir(bid) / "draft.json"
    try:
        return json.loads(m.read_text(encoding="utf-8")) if m.exists() else None
    except (OSError, json.JSONDecodeError):
        return None


def working(bid: str, real: Path) -> Path:
    """The copy while one is open, else the blueprint itself."""
    m = draft_meta(bid)
    if m is None:
        return real
    p = draft_dir(bid) / Path(m["real"]).name
    return p if p.exists() else real


def working_path(bid: str, paths: Optional[dict] = None) -> Optional[Path]:
    """The file the review page reads and writes for a blueprint: its working copy while one is open, else the
    blueprint itself. Records keep the blueprint's own path (`blueprint_paths`)."""
    p = (paths if paths is not None else blueprint_paths()).get(bid)
    return working(bid, p) if p is not None else None


# ---- parsed blueprints kept on disk (Andrew, 2026-10-22: "can you look into if there's a way to speed up the
# reboot?"): the server parsed all 770 blueprints twice at startup, 78 MB of YAML, ~40 s; a parsed copy reloads in
# about a millisecond. A copy is used only while its file has the same modification time and size; files outside the
# dataset (tests' temporary ones) are not kept. 64 MB for the library. ----

PARSED = HAND_REVIEW / ".parsed"


def _parsed_path(p: Path) -> Optional[Path]:
    try:
        rp = p.resolve()
        rp.relative_to(ROOT)
    except (OSError, ValueError):
        return None
    return PARSED / (hashlib.sha1(str(rp).encode()).hexdigest() + ".pickle")


def load(p: Path) -> dict:
    """The blueprint parsed, from its kept copy when the file is unchanged."""
    cp, st = _parsed_path(Path(p)), Path(p).stat()
    stamp = (st.st_mtime_ns, st.st_size)
    if cp is not None:
        try:
            with open(cp, "rb") as f:
                kept, data = pickle.load(f)
            if kept == stamp:
                return data
        except (OSError, EOFError, pickle.UnpicklingError, ValueError, TypeError):
            pass
    data = yaml.load(Path(p).read_text(encoding="utf-8"), Loader=_LOADER) or {}
    if cp is not None and Path(p).stat().st_mtime_ns == stamp[0]:       # not rewritten while it was read
        try:
            PARSED.mkdir(parents=True, exist_ok=True)
            tmp = cp.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
            with open(tmp, "wb") as f:
                pickle.dump((stamp, data), f, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cp)
        except OSError:
            pass
    return data


def warm_parsed(paths: list) -> int:
    """Every blueprint's parsed copy brought up to date, parsed on all cores (startup: 770 files in ~3 s rather than
    ~20 s one by one); how many were parsed again."""
    from concurrent.futures import ProcessPoolExecutor
    todo = [str(p) for p in paths if stale(Path(p))]
    if len(todo) < 8:
        for p in todo:
            load(Path(p))
        return len(todo)
    with ProcessPoolExecutor(os.cpu_count() or 4) as ex:
        list(ex.map(_warm_one, todo, chunksize=4))
    return len(todo)


def _warm_one(p: str) -> None:
    load(Path(p))


def stale(p: Path) -> bool:
    cp = _parsed_path(p)
    if cp is None or not cp.exists():
        return cp is not None
    try:
        st = p.stat()
        with open(cp, "rb") as f:
            kept, _ = pickle.load(f)
        return kept != (st.st_mtime_ns, st.st_size)
    except Exception:
        return True


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:12]


# ---- the blank ----

def resolve_blank(bp: dict) -> Optional[Path]:
    """The blueprint's blank under source_pdfs/: at its `source_pdf` path, else the first file of that name."""
    src = bp.get("source_pdf")
    if not src:
        return None
    direct = SOURCE_PDFS / str(src)
    if direct.is_file():
        return direct
    hits = [h for h in SOURCE_PDFS.rglob(Path(str(src)).name)
            if "source_pdfs_old" not in h.parts and h.is_file()]
    return hits[0] if hits else None


# ---- what a blueprint holds, read without a model ----

def widgets(spec: dict) -> list[dict]:
    """A field's boxes: an option group's widgets, or its one widget."""
    if spec.get("widgets"):
        return [w for w in spec["widgets"].values() if isinstance(w, dict)]
    w = spec.get("widget") or {}
    return [w] if w else []


def reviewable(bp: dict) -> list[str]:
    """The fields the review page shows (those with a box on a page): what a verdict on every field means."""
    return [n for n, s in (bp.get("fields") or {}).items()
            if isinstance(s, dict) and any(w.get("rect") and w.get("page") for w in widgets(s))]


PRINTED_TAG = "x_petey_printed"
CHOICE = {"checkbox", "radio", "radiobutton", "combobox", "listbox"}
FIELD_TYPES = BENCHMARK / "field_types.json"              # the printed sheet's progress: {page id: {"when"}}
PRINTED_CANDIDATES = BENCHMARK / "printed" / "candidates.json"   # eval/benchmark_printed.py's proposals, a page at a time


def printed_record(record: Optional[Path] = None) -> dict:
    """The pages confirmed on the printed sheet."""
    record = record or FIELD_TYPES
    return json.loads(record.read_text()) if record.exists() else {}


def is_text(spec: dict) -> bool:
    """A field the benchmark counts as text: one box, not a choice."""
    w = spec.get("widget") if isinstance(spec, dict) else None
    return bool(w) and not spec.get("widgets") and w.get("widget_type") not in CHOICE and spec.get("type") != "boolean"


def is_printed(spec: dict) -> bool:
    """Expected to be hand-written (a signature, initials): the tag set on the printed sheet or the Review tab."""
    return isinstance(spec, dict) and bool(spec.get(PRINTED_TAG)) and is_text(spec)


ENTITY_TAG = "x_petey_entity"


def split_values(bp: dict, counted_only: bool = True) -> list[dict]:
    """The Split Fields tagged on the Groups tab: `[{kind, page, fields: [code, ...]}]`, each the text fields that
    hold one value (a date in three boxes), in reading order. `kind` is the entity type from the taxonomy
    (`split_types`), None when none was picked or "other"; `counted_only` keeps the kinds the benchmark scores."""
    by: dict[str, list] = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict) or spec.get("widgets") or spec.get("x_petey_id") is None:
            continue
        tag = spec.get(ENTITY_TAG)
        w = spec.get("widget") or {}
        if not (isinstance(tag, dict) and tag.get("name")) or spec.get("type") == "boolean":
            continue
        if w.get("widget_type") != "text" or not w.get("rect") or not w.get("page"):
            continue
        by.setdefault(tag["name"], []).append((str(spec["x_petey_id"]), int(w["page"]),
                                               [float(c) for c in w["rect"]], tag.get("entity_type")))
    out = []
    for ms in by.values():
        if len(ms) < 2:
            continue
        kind = next((m[3] for m in ms if m[3] in split_types.TYPES), None)
        if kind == "other":
            kind = None
        if counted_only and not split_types.counts(kind):
            continue
        ms.sort(key=lambda m: (round(m[2][1] / 3), m[2][0]))
        out.append({"kind": kind, "page": ms[0][1], "fields": [m[0] for m in ms]})
    return out


def page_sizes(bp: dict, blank: Optional[Path] = None) -> list[dict]:
    """Every page of the blank: its size, and how many fields have a box on it (a field counts on each page it has a
    box on). Every tab shows every page, those with no field drawn apart (Andrew, 2026-10-27: "instead of only showing
    the pages that have the relevant fields, can you show all the pages? and can you color the pages that have NO
    fields differently")."""
    blank = blank or resolve_blank(bp)
    if not (blank and blank.exists()):
        return []
    import pymupdf
    n: collections.Counter = collections.Counter()
    for spec in (bp.get("fields") or {}).values():
        if isinstance(spec, dict):
            n.update({w["page"] for w in widgets(spec) if w.get("page") and w.get("rect")})
    doc = pymupdf.open(str(blank))
    try:
        return [{"page": i, "w_pt": pg.rect.width, "h_pt": pg.rect.height, "fields": n[i]}
                for i, pg in enumerate(doc, start=1)]
    finally:
        doc.close()
