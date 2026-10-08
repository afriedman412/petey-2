"""Calibrate the flat path on forms whose truth is known (flat forms, step 4; 2026-10-05).

A flat form has no widget layer, so the finder makes both the blueprint and the cases, and a box it never saw
is invisible on both sides: the loop reports success over a hole. The error rate of that path is measured here,
where a reference exists, so it can be attached to real flat forms, where none does.

Two kinds of reference:

  * a test form baked flat (`step2flat.pipeline.flatten`, the finder's own flattening): the blank's widget layer
    is the structural truth and the committed blueprint is the truth about meaning;
  * a true flat copy with a fillable twin (`runs/twin_pairs.json`): the twin's widgets are the structural truth;
    there is no committed blueprint.

Per form the whole flat path runs on the flat copy as it would on a real flat form (finder, classifier,
labeler; `petey.label.flat_label`), then:

  structure   every widget of the reference against the flat blueprint's rects, size-aware as in
              `eval/finder_vs_widgets.py`: hit / in_region / part / miss, by widget kind; blueprint rects no
              widget backs are `unbacked`
  meaning     every flat field whose rect lands on a committed field: do the two agree on the type family
              (`class_check.blueprint_class`) and on the name (token overlap, `name_caption.tokens`)?
  classifier  the flat copy's class map against the blank's cached one, box by box (the same page twice)
  loop        with --validate: bank cases on the flat copy, read back by the native reader (ink for marks),
              scored by rect key; agree / differ / miss, no API

    PYTHONPATH=. venv/bin/python eval/flat_calibration.py --tier core --validate --json runs/flat_calibration/core.json
    PYTHONPATH=. venv/bin/python eval/flat_calibration.py --twins tx_rrc_ep_3,tx_rrc_w_3x --validate

Blueprints are written to runs/flat_calibration/<form>.bpt (side copies, never the library); flat copies to
source_pdfs/_flat_calibration/ so `resolve_blank` finds them. --cache-only never calls the API.
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from petey.paths import REPO, RUNS, SOURCE_PDFS  # noqa: E402
from petey.synth.boxes import match_rect, match_rect_scored  # noqa: E402
from petey.synth.classify import classify_form  # noqa: E402
from petey.validate.class_check import _family, blueprint_class  # noqa: E402
from petey.validate.inventory_check import _field_rects  # noqa: E402
from petey.validate.name_caption import tokens  # noqa: E402
from petey.validate.test_forms import by_stem, forms  # noqa: E402

sys.path.insert(0, str(REPO / "eval"))
from finder_vs_widgets import classify_match, widget_rects  # noqa: E402

OUT = RUNS / "flat_calibration"
FLAT_COPIES = SOURCE_PDFS / "_flat_calibration"


def flat_copy_of(blank: Path, stem: str) -> Path:
    """The blank baked flat, as the finder sees every form. Made once."""
    from step2flat.pipeline import flatten
    FLAT_COPIES.mkdir(parents=True, exist_ok=True)
    dst = FLAT_COPIES / f"{stem}_flat.pdf"
    if not dst.exists():
        flatten(str(blank), str(dst))
    return dst


def structure(widgets: list[dict], bpt: dict) -> dict:
    """The reference widgets against the blueprint's rects."""
    rects = _field_rects(bpt)
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for i, r in enumerate(rects):
        by_page[int(r["page"])].append({**r, "id": i})
    counts: collections.Counter = collections.Counter()
    used: set[int] = set()
    kind_swaps = 0
    missed = []
    for w in widgets:
        cls, b = classify_match(w, by_page.get(w["page"], []))
        counts[cls] += 1
        counts[f"{cls}_{w['kind']}"] += 1
        if b is not None:
            used.add(b["id"])
            if cls == "hit" and b["kind"] != w["kind"] and w["kind"] in ("text", "option"):
                kind_swaps += 1
        if cls == "miss":
            missed.append({"page": w["page"], "kind": w["kind"], "rect": w["rect"], "path": w["path"].split(".")[-1]})
    unbacked = [r for rows in by_page.values() for r in rows if r["id"] not in used]
    n_text = sum(1 for w in widgets if w["kind"] == "text")
    n_opt = sum(1 for w in widgets if w["kind"] == "option")
    return {
        "widgets": len(widgets), "n_text": n_text, "n_option": n_opt, "blueprint_rects": len(rects),
        "hit": counts["hit"], "in_region": counts["in_region"], "part": counts["part"], "miss": counts["miss"],
        "hit_text": counts["hit_text"], "hit_option": counts["hit_option"],
        "kind_swaps": kind_swaps,
        "unbacked": len(unbacked),
        "unbacked_by_kind": dict(collections.Counter(r["kind"] for r in unbacked)),
        "missed": missed,
    }


def _name_match(a: str, b: str) -> str:
    if a == b:
        return "exact"
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return "none"
    j = len(ta & tb) / len(ta | tb)
    if j >= 0.5:
        return "strong"
    return "weak" if ta & tb else "none"


def meaning(flat: dict, committed: dict) -> dict:
    """Flat fields landing on committed fields: type family and name agreement."""
    crects = _field_rects(committed)
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for r in crects:
        by_page[int(r["page"])].append(r)
    cfields = committed.get("fields") or {}
    ffields = flat.get("fields") or {}
    pairs = []
    unmatched = 0
    for fname, fspec in ffields.items():
        if fspec.get("widgets"):
            frects = [{"page": wb["page"], "rect": wb["rect"]} for wb in fspec["widgets"].values()]
        else:
            w = fspec.get("widget") or {}
            frects = [{"page": w.get("page"), "rect": w.get("rect")}] if w.get("rect") else []
        hits = collections.Counter()
        for fr in frects:
            m = match_rect(fr["rect"], by_page.get(int(fr["page"]), []))
            if m is not None:
                hits[m["field"]] += 1
        if not hits:
            unmatched += 1
            continue
        cname = hits.most_common(1)[0][0]
        cspec = cfields.get(cname) or {}
        fcls, _ = blueprint_class(fname, fspec)
        ccls, _ = blueprint_class(cname, cspec)
        if fcls is None and ccls is None:
            type_verdict = "both_untyped"
        elif fcls is None or ccls is None:
            type_verdict = "one_untyped"
        else:
            type_verdict = "agree" if _family(fcls) == _family(ccls) else "differ"
        shape = None
        if fspec.get("widgets") or cspec.get("widgets"):
            shape = "same" if len(fspec.get("widgets") or {}) == len(cspec.get("widgets") or {}) else "differs"
        pairs.append({"flat": fname, "committed": cname, "flat_class": fcls, "committed_class": ccls,
                      "type": type_verdict, "name": _name_match(fname, cname), "group_shape": shape,
                      "committed_fields_under": len(hits)})
    c = collections.Counter(p["type"] for p in pairs)
    n = collections.Counter(p["name"] for p in pairs)
    return {
        "flat_fields": len(ffields), "committed_fields": len(cfields), "paired": len(pairs), "unpaired": unmatched,
        "type_agree": c["agree"], "type_differ": c["differ"], "one_untyped": c["one_untyped"],
        "both_untyped": c["both_untyped"],
        "name_exact": n["exact"], "name_strong": n["strong"], "name_weak": n["weak"], "name_none": n["none"],
        "merged": sum(1 for p in pairs if p["committed_fields_under"] > 1),
        "group_shape_differs": sum(1 for p in pairs if p["group_shape"] == "differs"),
        "pairs": pairs,
    }


def latest_class_map(blank: Path) -> dict | None:
    """The newest cached class map for this blank under the current classifier model and prompt, whichever
    finder version it was read under (the blanks' maps are migrated to a new finder only when a case set is
    checked, so the current version's key may be empty while an older one holds the same boxes)."""
    import hashlib
    from petey.synth.classify import CACHE_DIR, MODEL, PROMPT_VERSION
    sha = hashlib.sha256(blank.read_bytes()).hexdigest()[:16]
    best, best_when = None, ""
    for f in CACHE_DIR.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("blank_sha") == sha and d.get("model") == MODEL and str(d.get("prompt_version")) == PROMPT_VERSION:
            if str(d.get("when", "")) >= best_when:
                best, best_when = d, str(d.get("when", ""))
    return best


def classifier_stability(blank: Path, flat_copy: Path) -> dict | None:
    """The same page classified twice (blank, flat copy): class agreement per box. None without both maps cached."""
    a = classify_form(blank, cache_only=True) or latest_class_map(blank)
    b = classify_form(flat_copy, cache_only=True)
    if a is None or b is None:
        return None
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for k, bx in a["boxes"].items():
        by_page[bx["page"]].append({**bx, "key": k})
    same = diff = none_diff = unmatched = 0
    for k, bx in b["boxes"].items():
        m = match_rect(bx["rect"], by_page.get(bx["page"], []), min_overlap=0.9)
        if m is None:
            unmatched += 1
            continue
        if m["class"] == bx["class"]:
            same += 1
        elif "none" in (m["class"], bx["class"]):
            none_diff += 1
        else:
            diff += 1
    return {"boxes_blank": len(a["boxes"]), "boxes_flat": len(b["boxes"]), "same": same, "differ": diff,
            "none_vs_class": none_diff, "unmatched": unmatched, "blank_finder": a.get("finder"),
            "flat_finder": b.get("finder")}


def run_validate(flat_copy: Path, bpt: Path, form_id: str, methods: str) -> dict | None:
    """Bank cases on the flat copy, native read-back, scored by rect key. Returns the intact verdicts."""
    cmd = [sys.executable, "-m", "petey.validate.validate", "--blank", str(flat_copy), "--bpt", str(bpt),
           "--form-id", form_id, "--gen-model", "bank", "--methods", methods, "--n-flat", "0", "--gen-cache-only"]
    r = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    run_dir = None
    for line in r.stdout.splitlines():
        if line.startswith("[validate] run_dir="):
            run_dir = Path(line.split("=", 1)[1].strip())
    if r.returncode != 0 or run_dir is None:
        print(r.stdout[-2000:], r.stderr[-2000:])
        return {"error": f"validate exited {r.returncode}"}
    summary = json.loads((run_dir / "summary.json").read_text())
    case = run_dir / "case_001_intact"
    out = {"run": run_dir.name, "intact": summary.get("intact")}
    fr = case / "fill_report.json"
    if fr.exists():
        rep = json.loads(fr.read_text())
        out["drawn"] = rep.get("drawn")
        out["unmatched"] = rep.get("n_unmatched")
    ex = case / "extract_native.json"
    if ex.exists():
        out["dispatch"] = (json.loads(ex.read_text()).get("_meta") or {}).get("dispatch_counts")
    return out


def calibrate_form(stem: str, blank: Path, widgets_from: Path, committed: Path | None, *, cache_only: bool,
                   validate: bool, methods: str, flat_copy: Path | None = None) -> dict:
    from petey.label.flat_label import build_flat_blueprint, write_blueprint
    t0 = time.time()
    flat = flat_copy or flat_copy_of(blank, stem)
    form_id = f"{stem}_flat" if flat_copy is None else stem
    bp = build_flat_blueprint(flat, form_id, cache_only=cache_only)
    rec: dict = {"form": stem, "flat_copy": str(flat), "form_id": form_id}
    if bp is None:
        rec["error"] = "not cached (--cache-only)"
        return rec
    OUT.mkdir(parents=True, exist_ok=True)
    bpt_path = OUT / f"{form_id}.bpt"
    write_blueprint(bp, bpt_path)
    rec["blueprint"] = str(bpt_path)
    rec["fields"] = len(bp["fields"])
    rec["structure"] = structure(widget_rects(widgets_from), bp)
    if committed is not None and committed.exists():
        rec["meaning"] = meaning(bp, yaml.safe_load(committed.read_text(encoding="utf-8")) or {})
    if flat_copy is None:
        rec["classifier"] = classifier_stability(blank, flat)
    if validate:
        rec["loop"] = run_validate(flat, bpt_path, form_id, methods)
    rec["seconds"] = round(time.time() - t0, 1)
    return rec


def _pct(a: int, b: int) -> str:
    return f"{100.0 * a / b:.0f}%" if b else "-"


def print_form(r: dict) -> None:
    if r.get("error"):
        print(f"{r['form']:16} {r['error']}")
        return
    s = r["structure"]
    print(f"{r['form']:16} fields {r['fields']:4}  widgets {s['widgets']:4}  hit {s['hit']:4} "
          f"(text {s['hit_text']}/{s['n_text']}, option {s['hit_option']}/{s['n_option']})  "
          f"in_region {s['in_region']:3}  part {s['part']:3}  miss {s['miss']:3}  "
          f"unbacked {s['unbacked']:3} {s['unbacked_by_kind']}  kind swaps {s['kind_swaps']}")
    m = r.get("meaning")
    if m:
        print(f"{'':16} meaning: {m['paired']}/{m['flat_fields']} flat fields land on a committed field "
              f"({m['unpaired']} on none, {m['merged']} over several); type agree {m['type_agree']} differ "
              f"{m['type_differ']} one-untyped {m['one_untyped']} both-untyped {m['both_untyped']}; "
              f"name exact {m['name_exact']} strong {m['name_strong']} weak {m['name_weak']} none {m['name_none']}; "
              f"group shape differs {m['group_shape_differs']}")
    c = r.get("classifier")
    if c:
        print(f"{'':16} classifier twice: {c['same']} same, {c['differ']} differ, {c['none_vs_class']} none-vs-class, "
              f"{c['unmatched']} boxes unmatched ({c['boxes_blank']} blank under {c['blank_finder']} / "
              f"{c['boxes_flat']} flat under {c['flat_finder']})")
    lp = r.get("loop")
    if lp:
        if lp.get("error"):
            print(f"{'':16} loop: {lp['error']}")
        else:
            v = (lp.get("intact") or {}).get("native") or {}
            print(f"{'':16} loop ({lp['run']}): drawn {lp.get('drawn')} unmatched {lp.get('unmatched')}; native "
                  f"agree {v.get('agree')} differ {v.get('differ')} miss {v.get('extract_miss')} "
                  f"not_generated {v.get('not_generated')}; dispatch {lp.get('dispatch')}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--tier", default=None, help="test forms of this tier (smoke|core|full), baked flat")
    ap.add_argument("--forms", default=None, help="comma-separated test form stems instead of a tier")
    ap.add_argument("--twins", default=None, help="comma-separated form ids from runs/twin_pairs.json (true flat copies)")
    ap.add_argument("--validate", action="store_true", help="also run the loop on each flat copy (local)")
    ap.add_argument("--methods", default="native", help="readers for --validate (judge:* is metered)")
    ap.add_argument("--cache-only", action="store_true", help="never call the API")
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--show-missed", type=int, default=5)
    ap.add_argument("--show-pairs", type=int, default=0, help="print this many meaning pairs that disagree")
    args = ap.parse_args()
    results = []
    if args.forms or args.tier:
        tfs = [by_stem(s) for s in args.forms.split(",")] if args.forms else forms(args.tier)
        for tf in tfs:
            r = calibrate_form(tf.stem, tf.blank_path, tf.blank_path, tf.blueprint(), cache_only=args.cache_only,
                               validate=args.validate, methods=args.methods)
            results.append(r)
            print_form(r)
            _show(r, args)
    if args.twins:
        pairs = {p[0]: p for p in json.load(open(RUNS / "twin_pairs.json"))}
        for fid in args.twins.split(","):
            if fid not in pairs:
                print(f"{fid}: not in twin_pairs.json")
                continue
            _, flat, twin = pairs[fid]
            r = calibrate_form(fid, REPO / flat, REPO / twin, None, cache_only=args.cache_only,
                               validate=args.validate, methods=args.methods, flat_copy=REPO / flat)
            results.append(r)
            print_form(r)
            _show(r, args)
    if len(results) > 1:
        tot: collections.Counter = collections.Counter()
        for r in results:
            for k in ("widgets", "n_text", "n_option", "hit", "hit_text", "hit_option", "in_region", "part", "miss",
                      "unbacked", "blueprint_rects"):
                tot[k] += (r.get("structure") or {}).get(k, 0)
            for k in ("paired", "flat_fields", "type_agree", "type_differ", "one_untyped", "both_untyped",
                      "name_exact", "name_strong", "name_weak", "name_none"):
                tot["m_" + k] += (r.get("meaning") or {}).get(k, 0)
        print(f"{'TOTAL':16} widgets {tot['widgets']}: hit {_pct(tot['hit'], tot['widgets'])} "
              f"(text {_pct(tot['hit_text'], tot['n_text'])}, option {_pct(tot['hit_option'], tot['n_option'])}), "
              f"in_region {tot['in_region']}, part {tot['part']}, miss {_pct(tot['miss'], tot['widgets'])}; "
              f"blueprint rects {tot['blueprint_rects']}, unbacked {_pct(tot['unbacked'], tot['blueprint_rects'])}")
        if tot["m_paired"]:
            typed = tot["m_type_agree"] + tot["m_type_differ"]
            print(f"{'':16} meaning over {tot['m_paired']} paired fields: type agree {_pct(tot['m_type_agree'], typed)} "
                  f"of {typed} typed on both sides; name exact+strong "
                  f"{_pct(tot['m_name_exact'] + tot['m_name_strong'], tot['m_paired'])}, weak "
                  f"{_pct(tot['m_name_weak'], tot['m_paired'])}, none {_pct(tot['m_name_none'], tot['m_paired'])}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "forms": results}, indent=1))
    return 0


def _show(r: dict, args) -> None:
    for m in (r.get("structure") or {}).get("missed", [])[:args.show_missed]:
        print(f"    missed p{m['page']} {m['kind']:6} {m['rect']} {m['path']}")
    if args.show_pairs:
        shown = 0
        for p in (r.get("meaning") or {}).get("pairs", []):
            if p["type"] == "differ" or p["name"] == "none":
                print(f"    {p['flat'][:40]:40} -> {p['committed'][:40]:40} type={p['type']} name={p['name']} "
                      f"({p['flat_class']} vs {p['committed_class']})")
                shown += 1
                if shown >= args.show_pairs:
                    break


if __name__ == "__main__":
    raise SystemExit(main())
