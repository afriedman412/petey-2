"""A blueprint for a blank with no form layer, from the page alone (flat forms, 2026-10-05).

The structure comes from the class map (`petey.synth.classify`): the finder's boxes on the rendered page, the
classifier's verdict per box (fillable or not, text or mark, which marks answer one question, the caption it
read, whose value it is). That map already exists for every form that has been through the loop, because the
bank draws cases from it. The names come from a second model reading the page's printed words beside each box
(`auto_label.label_page_via_llm`, the labeler the AcroForm path uses, given rects and words and nothing else).
Two models on purpose: the class check and the classifier witness compare the blueprint's typing with the
class map, and a blueprint typed by the classifier would agree with itself.

What a flat field carries (spec 5.9.1: `path: null`, derivation recorded):

    widget: {page, rect, widget_type, path: null}      the finder's box; the rect is an estimate
    x_petey_geometry: {source: finder, finder, kind, confidence}
    x_petey_page_class / x_petey_caption / x_petey_entity   the classifier's reading, for the eye
    label_source: llm | classifier_caption | placeholder

Types come from the name through the semantic-type registry, as on AcroForm forms; the classifier's class is
recorded, not applied. An option group is one `category` field, one option per box keyed by a slug of its
caption, with the caption on the option; a lone option box is a boolean. Scoring, reading back and the witness
tiers key such fields by page and rect (`boxes.widget_key`); the native reader reads marks as ink against the
blank (`extract._ink_marked`).

    python -m petey.label.flat_label --blank source_pdfs/rrc_raw/formp15p.pdf --output blueprints/p_15.bpt
    python -m petey.label.flat_label --blank ... --dry-run DIR     # the labeler's payload, no API

Labels are cached under runs/_gen_cache/flat_labels/ by blank, finder, class map basis and name model, so a
re-emit costs nothing; the class map is cached by `classify_form`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml

from petey.bpt_version import stamp_version
from petey.validate import field_ids
from petey.label import auto_label
from petey.label.dedup import DedupState
from petey.paths import RUNS, SOURCE_PDFS
from petey.semantic_types import enrich_field
from petey.synth import classify
from petey.synth.boxes import FINDER_VERSION, finder_stamp

NAME_MODEL = "claude-opus-5"          # not the classifier's model (classify.MODEL): two readings of the page
LABELS_PROMPT_VERSION = "1"           # bump when the payload the labeler sees changes
CACHE_DIR = RUNS / "_gen_cache" / "flat_labels"


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def _union(rects: list[list[float]]) -> list[float]:
    return [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]


def labeler_entries(cmap: dict) -> tuple[list[dict], dict[int, dict]]:
    """What the labeler is asked to name, one entry per field-to-be: every text box, every option group (one
    entry, the union rect, the options' captions) and every lone option box. Returns the entries and, by entry
    id, the boxes behind each. Boxes the classifier called `none` are dropped here."""
    boxes = [{"key": k, **b} for k, b in cmap["boxes"].items() if b.get("class") != "none"]
    boxes.sort(key=lambda b: int(b["box"]))
    entries: list[dict] = []
    behind: dict[int, dict] = {}
    groups: dict[tuple, list[dict]] = {}
    for b in boxes:
        if b["class"] == "option" and b.get("group"):
            groups.setdefault((b["page"], b["group"]), []).append(b)
    grouped_keys = {m["key"] for ms in groups.values() if len(ms) >= 2 for m in ms}
    for b in boxes:
        if b["key"] in grouped_keys:
            continue
        eid = int(b["box"])
        if b["class"] == "option":
            entries.append({"id": eid, "page": b["page"], "rect": b["rect"], "widget_type": "checkbox"})
            behind[eid] = {"kind": "option", "boxes": [b]}
        else:
            entries.append({"id": eid, "page": b["page"], "rect": b["rect"], "widget_type": "text"})
            behind[eid] = {"kind": "text", "boxes": [b]}
    for (page, question), ms in groups.items():
        if len(ms) < 2:
            continue
        eid = int(ms[0]["box"])
        entries.append({"id": eid, "page": page, "rect": _union([m["rect"] for m in ms]),
                        "widget_type": "radiobutton",
                        "options": [m.get("label") or f"option {m['box']}" for m in ms]})
        behind[eid] = {"kind": "group", "boxes": ms, "question": question}
    entries.sort(key=lambda e: (e["page"], e["id"]))
    return entries, behind


def _words(doc: pymupdf.Document, page_no: int) -> list[dict]:
    return auto_label._words_from_page(doc[page_no - 1])


def labels_cache_path(pdf_bytes: bytes, cmap: dict, name_model: str) -> Path:
    h = hashlib.sha256()
    for part in (pdf_bytes, b"\x00flat_labels\x00", FINDER_VERSION.encode(), b"\x00",
                 str(cmap.get("model")).encode(), b"\x00", str(cmap.get("prompt_version")).encode(), b"\x00",
                 name_model.encode(), b"\x00", LABELS_PROMPT_VERSION.encode()):
        h.update(part)
    return CACHE_DIR / f"{h.hexdigest()}.json"


def name_entries(blank_pdf: Path, entries: list[dict], cmap: dict, *, name_model: str, form_id: str,
                 cache_only: bool = False) -> Optional[dict[int, str]]:
    """`{entry id: slug}` from the labeler, one call per page, cached. None under `cache_only` with no cache."""
    cp = labels_cache_path(blank_pdf.read_bytes(), cmap, name_model)
    if cp.exists():
        return {int(k): v for k, v in json.loads(cp.read_text(encoding="utf-8"))["labels"].items()}
    if cache_only:
        return None
    auto_label.CALL_TAG = f"flat_label/{form_id}"
    out: dict[int, str] = {}
    doc = pymupdf.open(str(blank_pdf))
    try:
        for page_no in sorted({e["page"] for e in entries}):
            on_page = [e for e in entries if e["page"] == page_no]
            words = _words(doc, page_no)
            if not words:
                print(f"  [page {page_no}] no text layer: {len(on_page)} entries get placeholder names")
                continue
            got = auto_label.label_page_via_llm(on_page, words, model=name_model)
            out.update(got)
            print(f"  [page {page_no}] {len(on_page)} entries, {sum(1 for e in on_page if got.get(e['id']))} named")
    finally:
        doc.close()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps({"form": form_id, "blank": str(blank_pdf), "model": name_model,
                              "finder": FINDER_VERSION, "classifier": {"model": cmap.get("model"),
                                                                       "prompt_version": cmap.get("prompt_version")},
                              "when": time.strftime("%Y-%m-%d %H:%M:%S"),
                              "labels": {str(k): v for k, v in out.items()}}, indent=1))
    return out


def _widget_block(b: dict, widget_type: str) -> dict:
    return {"page": int(b["page"]), "rect": [float(c) for c in b["rect"]], "widget_type": widget_type, "path": None}


def _geometry(b: dict) -> dict:
    return {"source": "finder", "finder": FINDER_VERSION, "kind": b.get("kind"), "confidence": b.get("conf")}


def _option_type(b: dict) -> str:
    return "radiobutton" if b.get("kind") == "radio" else "checkbox"


def build_fields(entries: list[dict], behind: dict[int, dict], labels: dict[int, str]) -> tuple[dict, dict]:
    """The blueprint's `fields` from the labeler's slugs and the boxes behind each entry. Returns the fields and
    a count of where each name came from."""
    dedup = DedupState()
    fields: dict[str, dict] = {}
    sources = {"llm": 0, "classifier_caption": 0, "placeholder": 0}

    def _name(e: dict, fallback_caption: Optional[str], kind: str) -> tuple[str, str]:
        lbl = (labels.get(e["id"]) or "").strip().replace(".", "_")
        lbl = _slug(lbl)
        if lbl:
            return lbl, "llm"
        cap = _slug(fallback_caption or "")
        if cap:
            return (cap + ("_ind" if kind == "option" else ""), "classifier_caption")
        return f"p{e['page']}_{kind}_{e['id']:03d}", "placeholder"

    for e in entries:
        info = behind[e["id"]]
        kind, boxes = info["kind"], info["boxes"]
        if kind == "text":
            b = boxes[0]
            label, src = _name(e, b.get("label"), "text")
            name = dedup.assign(label, page=e["page"], rect=e["rect"])
            spec = enrich_field(label, "text")
            spec["widget"] = _widget_block(b, "text")
            spec["label_source"] = src
            spec["x_petey_geometry"] = _geometry(b)
            spec["x_petey_page_class"] = b.get("class")
            if b.get("label"):
                spec["x_petey_caption"] = b["label"]
            if b.get("entity"):
                spec["x_petey_entity"] = b["entity"]
            if src == "placeholder":
                spec["needs_review"] = True
            fields[name] = spec
        elif kind == "option":
            b = boxes[0]
            label, src = _name(e, b.get("label"), "option")
            name = dedup.assign(label, page=e["page"], rect=e["rect"])
            spec = {"type": "boolean", "semantic_type": "indicator", "widget": _widget_block(b, _option_type(b)),
                    "label_source": src, "x_petey_geometry": _geometry(b)}
            if b.get("label"):
                spec["x_petey_caption"] = b["label"]
            if src == "placeholder":
                spec["needs_review"] = True
            fields[name] = spec
        else:
            label, src = _name(e, info.get("question"), "group")
            name = dedup.assign(label, page=e["page"], rect=e["rect"])
            widgets: dict[str, dict] = {}
            for m in boxes:
                opt = _slug(m.get("label") or "") or f"option_{m['box']}"
                if opt[0].isdigit():
                    opt = "opt_" + opt
                base, n = opt, 2
                while opt in widgets:
                    opt = f"{base}_{n}"
                    n += 1
                wb = _widget_block(m, _option_type(m))
                if m.get("label"):
                    wb["caption"] = m["label"]
                widgets[opt] = wb
            spec = {"type": "category", "values": list(widgets), "widgets": widgets, "label_source": src,
                    "x_petey_geometry": {"source": "finder", "finder": FINDER_VERSION,
                                         "kinds": sorted({m.get("kind") for m in boxes if m.get("kind")}),
                                         "confidence": min((m.get("conf") or 0) for m in boxes)},
                    "x_petey_page_group": info.get("question")}
            if src == "placeholder":
                spec["needs_review"] = True
            fields[name] = spec
        sources[src] += 1
    return fields, {"sources": sources, "dedup": dedup}


def _source_pdf(blank_pdf: Path) -> str:
    """The blueprint's `source_pdf`: relative to source_pdfs/ when the blank lives there (so `resolve_blank` finds
    it directly), else the file name."""
    try:
        return str(blank_pdf.resolve().relative_to(SOURCE_PDFS.resolve()))
    except ValueError:
        return blank_pdf.name


def build_flat_blueprint(blank_pdf: Path, form_id: str, *, name_model: str = NAME_MODEL,
                         classify_model: str = classify.MODEL, cache_only: bool = False,
                         form_version: Optional[str] = None) -> Optional[dict]:
    """The blueprint, or None under `cache_only` when the class map or the labels are not cached."""
    blank_pdf = Path(blank_pdf)
    cmap = classify.classify_form(blank_pdf, model=classify_model, form_id=form_id, cache_only=cache_only)
    if cmap is None:
        print(f"[flat_label] no cached classification for {blank_pdf} (--cache-only)")
        return None
    entries, behind = labeler_entries(cmap)
    print(f"[flat_label] class map: {cmap['n_boxes']} boxes, {cmap['n_none']} none, {cmap['n_option']} option "
          f"in {cmap['n_option_groups']} groups; {len(entries)} entries to name")
    labels = name_entries(blank_pdf, entries, cmap, name_model=name_model, form_id=form_id, cache_only=cache_only)
    if labels is None:
        print(f"[flat_label] no cached labels for {blank_pdf} (--cache-only)")
        return None
    fields, info = build_fields(entries, behind, labels)
    src = info["sources"]
    n_groups = sum(1 for s in fields.values() if s.get("widgets"))
    n_bool = sum(1 for s in fields.values() if s.get("type") == "boolean")
    print(f"[flat_label] {len(fields)} fields: {len(fields) - n_groups - n_bool} text, {n_groups} option groups, "
          f"{n_bool} lone options; names llm={src['llm']} caption={src['classifier_caption']} "
          f"placeholder={src['placeholder']}")
    fs = finder_stamp()
    bp: dict[str, Any] = {
        "bpt_version": "1.1",
        "name": form_id,
        "form_version": form_version,
        "source_pdf": _source_pdf(blank_pdf),
        "source_pdf_hash": auto_label._sha1(blank_pdf),
        "source_pages": sorted({e["page"] for e in entries}),
        "description": "",
        "instructions": "",
        "authoring": {
            "method": "flat_label",
            "geometry": "finder",
            "finder": fs["version"],
            "classifier": {"model": cmap.get("model"), "prompt_version": cmap.get("prompt_version")},
            "labeler": {"model": name_model, "prompt": "auto_label.LABEL_SYSTEM", "payload_version": LABELS_PROMPT_VERSION},
            "labels": "llm",
            "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "fields": fields,
    }
    dedup = info["dedup"]
    if dedup.collisions:
        bp["x_petey_dedup_log"] = dedup.summary()
    field_ids.assign(bp)                    # a fixed id per field, for referring to it (x_petey_id)
    return stamp_version(bp)


def write_blueprint(bp: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False),
                   encoding="utf-8")


def dry_run(blank_pdf: Path, out_dir: Path, form_id: str) -> dict:
    """The labeler's payload per page (entries and words), from the cached class map; no API."""
    cmap = classify.classify_form(blank_pdf, form_id=form_id, cache_only=True)
    if cmap is None:
        raise SystemExit(f"no cached classification for {blank_pdf}; run the classifier first")
    entries, behind = labeler_entries(cmap)
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(blank_pdf))
    try:
        for page_no in sorted({e["page"] for e in entries}):
            (out_dir / f"page_{page_no:02d}.json").write_text(json.dumps(
                {"entries": [e for e in entries if e["page"] == page_no], "words": _words(doc, page_no)}, indent=1))
    finally:
        doc.close()
    return {"entries": len(entries), "pages": len({e["page"] for e in entries}), "out": str(out_dir)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--blank", required=True, type=Path)
    ap.add_argument("--output", type=Path, default=None, help="the .bpt to write (default blueprints/<form-id>.bpt)")
    ap.add_argument("--form-id", default=None, help="default: the --output stem, else the blank's stem")
    ap.add_argument("--form-version", default=None)
    ap.add_argument("--name-model", default=NAME_MODEL)
    ap.add_argument("--classify-model", default=classify.MODEL)
    ap.add_argument("--cache-only", action="store_true", help="never call the API; fail when a step is not cached")
    ap.add_argument("--dry-run", type=Path, metavar="DIR", help="write the labeler's payload to DIR and stop")
    args = ap.parse_args()
    if not args.blank.exists():
        raise SystemExit(f"blank not found: {args.blank}")
    form_id = args.form_id or (args.output.stem if args.output else args.blank.stem)
    if args.dry_run:
        print(dry_run(args.blank, args.dry_run, form_id))
        return 0
    bp = build_flat_blueprint(args.blank, form_id, name_model=args.name_model, classify_model=args.classify_model,
                              cache_only=args.cache_only, form_version=args.form_version)
    if bp is None:
        return 1
    from petey.paths import BLUEPRINTS
    out = args.output or BLUEPRINTS / f"{form_id}.bpt"
    write_blueprint(bp, out)
    print(f"[ok] wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
