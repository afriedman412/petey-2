"""A flat form's structure without a frontier model, named by position (Andrew, 2026-10-26: "if we can create an
accurate blueprint with dummy labels (p5 g1 r5c6) that's great"; "I'm ok with jev at this point").

From the raw (flat) PDF alone:

  1. boxes      the finder (`boxes.find_boxes`, cached); its kind says text or mark
  2. screen     Jev, one Noul per box on the numbered page (`jev_is_field`'s question): keep >= KEEP
  3. groups     Yes / No pairs and checkbox rows by layout (`yes_no_groups`, `cell_groups`), plus Jev's joins of
                neighbouring marks over `cheap_groups.CUT`
  4. structure  tables (geometry) and repeated blocks (geometry + printed captions), `structure.find` as the
                labeler uses it
  5. names      by position, in reading order: a table cell p1_g1_r5c6, a block slot p2_b1_c3_s4 (block 1, copy 3,
                slot 4), any other field p1_f12; a group in one table row p1_g1_r3 (options c4, c5), in one block copy
                p2_b1_c3 (options s1, s2), else p1_o2 (options opt1, opt2)

Scored against the fillable twin (`runs/twin_pairs.json`-style pairs, given here as --pairs):

  boxes      every twin widget hit / in_region / part / miss against the blueprint's rects, and blueprint rects no
             widget backs (`flat_calibration.structure`); before and after the screen
  groups     on twins with a validated blueprint (--truth): box pairs grouped alike, groups rebuilt exactly
  tables     the same table and block finder run on the twin's widget rects as the reference: box pairs in the same
             table row / column, the same block copy / slot, on both sides
  alignment  the share of the raw page's words printed at the same place on the twin (another revision scores low)

Costs and times per field (twin widgets), not per page. Blueprints go to runs/flat/blueprints/<id>.bpt, which the
review page lists as fl__<id>.

    PYTHONPATH=. venv/bin/python eval/flat_light.py --pairs cf1=source_pdfs/rrc_raw/cf-1-06-09-14-final.pdf:source_pdfs/rrc_fillable/cf-1-fillable.pdf:cf_1_fillable ...
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures as cf
import json
import sys
import time
from pathlib import Path

import httpx
import pymupdf
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cheap_groups  # noqa: E402
from finder_vs_widgets import classify_match, widget_rects  # noqa: E402
from flat_calibration import structure as box_structure  # noqa: E402

from petey.label import structure as S  # noqa: E402
from petey.paths import BLUEPRINTS, REPO, RUNS  # noqa: E402
from petey.synth import boxes as B  # noqa: E402
from petey.validate import page_check as pc  # noqa: E402
from petey.validate.jev_is_field import CRITERIA, PER_REQUEST, QUESTION  # noqa: E402
from petey.validate.jev_page import LIMITS, MODEL, PRICE, _key, ask_split, image_ref  # noqa: E402

KEEP = 0.6           # Jev's is-it-a-field score kept (2026-10-15, non-IRS set: 96% of real boxes, 34% of false)
BOX_CACHE = None     # a scratch finder cache when a finder_experiment patch is on (`--patch`), so the library's
                     # caches under runs/_gen_cache/boxes never see patched boxes
OUT = RUNS / "flat" / "blueprints"
MARK = {"checkbox", "radio"}
PATCH = None         # the finder_experiment patch the boxes were found under


def _ask_all(jobs: list, workers: int) -> tuple[dict, int]:
    """{(page, qid): noul} over the jobs (page, body, imgs, names) and the input tokens (cached answers included)."""
    key = _key()
    if not key:
        raise SystemExit("TYPESAFE_API_KEY not in .env")
    got, tokens = {}, 0
    with httpx.Client() as client, cf.ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(ask_split, client, key, j[1], j[2]): j for j in jobs}
        for f in cf.as_completed(futs):
            j = futs[f]
            res = f.result()
            tokens += (res.get("usage") or {}).get("input_tokens", 0)
            for qid, what in j[3].items():
                v = ((res.get("answers") or {}).get(qid) or {}).get("noul")
                if v is not None:
                    got[what] = v
    return got, tokens


def screen(raw: Path, boxes: list[dict], workers: int) -> tuple[dict[str, float], int]:
    """{box id: Jev's is-it-a-field score}, input tokens."""
    jobs = []
    for page_no in sorted({b["page"] for b in boxes}):
        on = [b for b in boxes if b["page"] == page_no]
        rows = [{"boxes": [{"page": page_no, "rect": b["rect"], "label": b["id"]}]} for b in on]
        png, _dpi, px = pc.render(raw, page_no, rows, limits=LIMITS)
        ref = image_ref(png)
        items = [{"id": b["id"], "kind": b["kind"], "pixel_box": [round(v) for v in px[b["id"]]]}
                 for b in on if b["id"] in px]
        for i in range(0, len(items), PER_REQUEST):
            qs, names = {}, {}
            for it in items[i:i + PER_REQUEST]:
                qs[f"b{it['id']}"] = {"type": "noul", "instructions": {"box": it, "question": QUESTION},
                                      "criteria": CRITERIA}
                names[f"b{it['id']}"] = it["id"]
            body = {"model": MODEL, "state": {"form": raw.stem, "page_number": page_no, "page": ref, "boxes": items},
                    "questions": qs}
            jobs.append((page_no, body, {ref: png}, names))
    return _ask_all(jobs, workers)


def _stub(raw: Path, kept: list[dict]) -> dict:
    """One field per kept box, f<id>, with its id; marks as loose booleans (what the grouping rules take)."""
    fields = {}
    for b in kept:
        mark = b["kind"] in MARK
        fields[f"f{b['id']}"] = {"type": "boolean" if mark else "string", "x_petey_id": b["id"],
                                 "widget": {"page": b["page"], "rect": b["rect"],
                                            "widget_type": ("radiobutton" if b["kind"] == "radio" else "checkbox")
                                            if mark else "text", "path": None}}
    return {"source_pdf": str(raw.resolve()), "fields": fields}


def groups(raw: Path, stub: dict, workers: int, preset: list[set[str]] = ()) -> tuple[list[set[str]], int]:
    """Option groups among the kept marks, as sets of stub field names: code rules plus Jev's joins, joined with any
    `preset` groups (a fillable PDF's own radio groups)."""
    marks = sorted(n for n, s in stub["fields"].items() if s["type"] == "boolean")
    if len(marks) < 2:
        return [], 0
    code = cheap_groups.code_groups(stub, raw, marks)
    jobs = [(j[1], j[2], j[3], {q: pair for q, pair in j[4].items()})
            for j in cheap_groups.jev_jobs(raw.stem, stub, raw, marks)]
    # jev_jobs names each question by the two fields' names
    p, tokens = _ask_all(jobs, workers)
    joins = [pair for pair, v in p.items() if v > cheap_groups.CUT]
    pairs = joins + [(a, b) for g in code for a, b in zip(sorted(g), sorted(g)[1:])]
    if not preset:
        return cheap_groups.union(pairs, marks), tokens
    return _union_keeping(preset, pairs, marks), tokens


def _union_keeping(preset: list[set[str]], pairs: list[tuple[str, str]], marks: list[str]) -> list[set[str]]:
    """Groups from `pairs` on top of the `preset` ones, never joining two preset groups (a fillable PDF's radio groups
    are the publisher's own: the pregnancy intake pack's 46 became 40 when code and Jev joins chained them,
    2026-10-26). A loose box may join a preset group."""
    parent = {m: m for m in marks}
    owner: dict[str, int] = {}                     # root -> the preset group it holds

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for i, g in enumerate(preset):
        ms = [m for m in g if m in parent]
        for m in ms[1:]:
            parent[find(m)] = find(ms[0])
        if ms:
            owner[find(ms[0])] = i
    for a, b in pairs:
        if a not in parent or b not in parent:
            continue
        ra, rb = find(a), find(b)
        if ra == rb or (ra in owner and rb in owner):
            continue
        parent[ra] = rb
        if ra in owner:
            owner[rb] = owner.pop(ra)
    g = collections.defaultdict(set)
    for m in marks:
        g[find(m)].add(m)
    return [s for s in g.values() if len(s) > 1]


STACKED = 0.8        # IoU at which two fields on one page are one printed box with two widgets on it


def _iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    i = ix * iy
    u = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - i
    return i / u if u > 0 else 0.0


def collapse_stacked(bp: dict, keep: set[str] = frozenset()) -> list[dict]:
    """One field for a printed box that carries two stacked widgets (2026-10-27: 13 of 427 benchmark forms, 69 pairs;
    bm__sd_1474805 p2's employment blocks went unfound because the duplicates sat in different places in each copy).
    Of each pair of single-widget fields of one kind on one page overlapping by `STACKED`, the one whose x_petey_id is in
    `keep` (a saved block type's), else the lower id, stays; the other is removed and logged under
    x_petey_dropped_widgets. Returns the removed fields."""
    rows = []
    for n, s in (bp.get("fields") or {}).items():
        w = s.get("widget") if isinstance(s, dict) else None
        if w and w.get("rect") and not s.get("widgets"):
            rows.append((n, str(s.get("x_petey_id")), w))
    gone: set[str] = set()
    dropped = []
    for i, (na, ca, wa) in enumerate(rows):
        for nb, cb, wb in rows[i + 1:]:
            if na in gone or nb in gone or wa["page"] != wb["page"] or wa.get("widget_type") != wb.get("widget_type"):
                continue
            if _iou(wa["rect"], wb["rect"]) < STACKED:
                continue
            def rank(c):
                return (c not in keep, int(c) if c.isdigit() else 1 << 30)
            (kn, kc, _), (dn, dc, dw) = sorted([(na, ca, wa), (nb, cb, wb)], key=lambda r: rank(r[1]))
            gone.add(dn)
            dropped.append({"name": dn, "x_petey_id": dc, "page": dw["page"], "rect": dw["rect"],
                            "reason": f"stacked on {kn} ({kc}): one printed box"})
    for d in dropped:
        del bp["fields"][d["name"]]
    if dropped:
        log = bp.setdefault("x_petey_dropped_widgets", {"count": 0, "widgets": []})
        log["widgets"] = list(log.get("widgets") or []) + dropped
        log["count"] = len(log["widgets"])
    return dropped


def _order(rect) -> tuple:
    return (round(rect[1] / 4), rect[0])


def build(raw: Path, form_id: str, *, workers: int = 6, boxes: list[dict] | None = None,
          preset_groups: list[set[str]] = ()) -> tuple[dict, dict]:
    """(blueprint, info) for the raw PDF. `boxes` given (a fillable PDF's own widgets, for an answer-key starting point;
    2026-10-26) skips the finder and the screen; `preset_groups` (stub names f<id>) are kept as groups."""
    t0 = time.time()
    given = boxes is not None
    if not given:
        boxes = B.find_boxes(raw, BOX_CACHE) if BOX_CACHE else B.find_boxes(raw)
    t_find = time.time() - t0
    if given:
        score, tok_screen, kept = {}, 0, boxes
    else:
        score, tok_screen = screen(raw, boxes, workers)
        kept = [b for b in boxes if score.get(b["id"], 0) >= KEEP]
    t_screen = time.time() - t0 - t_find
    stub = _stub(raw, kept)
    grps, tok_groups = groups(raw, stub, workers, preset_groups)
    t_groups = time.time() - t0 - t_find - t_screen
    entries = [{"id": int(b["id"]), "page": b["page"], "rect": b["rect"], "path": None,
                "widget_type": stub["fields"][f"f{b['id']}"]["widget"]["widget_type"]} for b in kept]
    struct = S.find(raw, entries)
    # each kept box's place: ("g", page, table k, row, col) or ("b", page, block k, copy, slot)
    place: dict[str, tuple] = {}
    for page, st in struct.items():
        for k, t in enumerate(st["tables"], 1):
            for c in t["cells"]:
                place.setdefault(f"f{c['id']}", ("g", page, k, c["row"] + 1, c["col"] + 1))
        for k, bl in enumerate(st["blocks"], 1):
            for c in bl["cells"]:
                place.setdefault(f"f{c['id']}", ("b", page, k, c["block"] + 1, c["slot"] + 1))
    sf = stub["fields"]
    in_group = {n: i for i, g in enumerate(grps) for n in g}
    units = []                                    # (page, order key, kind, members)
    for i, g in enumerate(grps):
        ms = sorted(g, key=lambda n: (sf[n]["widget"]["page"], _order(sf[n]["widget"]["rect"])))
        units.append((sf[ms[0]]["widget"]["page"], _order(sf[ms[0]]["widget"]["rect"]), "group", ms))
    for n, s in sf.items():
        if n not in in_group:
            units.append((s["widget"]["page"], _order(s["widget"]["rect"]), "one", [n]))
    units.sort(key=lambda u: (u[0], u[1]))
    fields: dict[str, dict] = {}
    count = collections.Counter()
    for page, _o, kind, ms in units:
        if kind == "one":
            n = ms[0]
            pl = place.get(n)
            if pl and pl[0] == "g":
                name = f"p{page}_g{pl[2]}_r{pl[3]}c{pl[4]}"
            elif pl:
                name = f"p{page}_b{pl[2]}_c{pl[3]}_s{pl[4]}"
            else:
                count[page] += 1
                name = f"p{page}_f{count[page]}"
            w = dict(sf[n]["widget"])
            spec = {"type": sf[n]["type"], "widget": w}
            if spec["type"] == "boolean":
                spec["semantic_type"] = "indicator"
            spec["x_petey_geometry"] = ({"source": "widget"} if given else
                                        {"source": "finder", "finder": B.FINDER_VERSION,
                                         "jev_is_field": round(score.get(n[1:], 0), 2)})
            fields[name] = spec
            continue
        pls = [place.get(m) for m in ms]
        if all(pls) and len({p[:4] for p in pls}) == 1 and pls[0][0] == "g":
            p0 = pls[0]
            name, keys = f"p{page}_g{p0[2]}_r{p0[3]}", [f"c{p[4]}" for p in pls]
        elif all(pls) and len({p[:4] for p in pls}) == 1:
            p0 = pls[0]
            name, keys = f"p{page}_b{p0[2]}_c{p0[3]}", [f"s{p[4]}" for p in pls]
        else:
            count[("o", page)] += 1
            name, keys = f"p{page}_o{count[('o', page)]}", [f"opt{k}" for k in range(1, len(ms) + 1)]
        if len(set(keys)) < len(keys):
            keys = [f"opt{k}" for k in range(1, len(ms) + 1)]
        widgets = {k: dict(sf[m]["widget"]) for k, m in zip(keys, ms)}
        fields[name] = {"type": "category", "values": keys, "widgets": widgets,
                        "x_petey_geometry": ({"source": "widget"} if given else
                                             {"source": "finder", "finder": B.FINDER_VERSION,
                                              "jev_is_field": [round(score.get(m[1:], 0), 2) for m in ms]})}
    for i, (n, s) in enumerate(fields.items(), 1):
        s["x_petey_id"] = str(i)
    try:
        src = str(raw.resolve().relative_to((REPO / "source_pdfs").resolve()))
    except ValueError:
        src = raw.name
    bp = {"bpt_version": "1.1", "name": form_id, "source_pdf": src,
          "source_pages": sorted({b["page"] for b in boxes}), "description": "", "instructions": "",
          "authoring": {"method": "flat_light", "geometry": "widgets" if given else "finder",
                        "finder": None if given else B.FINDER_VERSION, "finder_patch": None if given else PATCH,
                        "screen": {"model": MODEL, "keep": KEEP}, "groups": "yes_no + cell_groups + Jev joins",
                        "names": "position", "when": time.strftime("%Y-%m-%d %H:%M:%S")},
          "fields": fields}
    info = {"finder_boxes": len(boxes), "kept": len(kept), "groups": len(grps),
            "tables": sum(len(st["tables"]) for st in struct.values()),
            "blocks": sum(len(st["blocks"]) for st in struct.values()),
            "tokens": tok_screen + tok_groups, "tokens_screen": tok_screen, "tokens_groups": tok_groups,
            "seconds": {"finder": round(t_find, 1), "screen": round(t_screen, 1), "groups": round(t_groups, 1),
                        "total": round(time.time() - t0, 1)},
            "struct": struct, "boxes": boxes, "kept_ids": [b["id"] for b in kept], "score": score}
    return bp, info


# ---------------------------------------------------------------------------------------------------- scoring

def alignment(raw: Path, twin: Path) -> float:
    """The share of the raw form's words printed at the same place (within 2 pt) on the twin."""
    a, b = pymupdf.open(str(raw)), pymupdf.open(str(twin))
    try:
        same = n = 0
        for i in range(min(len(a), len(b))):
            tw = collections.defaultdict(list)
            for w in b[i].get_text("words"):
                tw[w[4]].append(w)
            for w in a[i].get_text("words"):
                n += 1
                same += any(abs(w[0] - x[0]) <= 2 and abs(w[1] - x[1]) <= 2 for x in tw.get(w[4], ()))
        return same / n if n else 0.0
    finally:
        a.close()
        b.close()


def _boxes_bp(boxes: list[dict]) -> dict:
    """A blueprint of bare boxes, for scoring the finder before the screen."""
    return {"fields": {f"f{b['id']}": {"widget": {"page": b["page"], "rect": b["rect"],
                                                  "widget_type": "checkbox" if b["kind"] in MARK else "text"}}
                       for b in boxes}}


def _to_twin(rect_items: list[tuple[str, int, list]], widgets: list[dict]) -> dict[str, int]:
    """{item: twin widget index} for items whose rect hits a widget (comparable size)."""
    by_page = collections.defaultdict(list)
    for i, w in enumerate(widgets):
        by_page[w["page"]].append({**w, "i": i})
    out = {}
    for name, page, rect in rect_items:
        cls, b = classify_match({"rect": rect, "page": page}, by_page.get(page, []))
        if cls == "hit":
            out[name] = b["i"]
    return out


def score_groups(bp: dict, truth: dict) -> dict:
    """Box pairs grouped alike, against the validated blueprint's option groups. Only the blueprint's mark boxes that
    hit a validated option box count."""
    t_items = []                                   # (validated group or None, page, rect)
    for n, s in (truth.get("fields") or {}).items():
        if s.get("widgets"):
            for w in s["widgets"].values():
                if w.get("rect"):
                    t_items.append((n, int(w["page"]), w["rect"]))
        elif (s.get("type") == "boolean" or (s.get("widget") or {}).get("widget_type") in ("checkbox", "radiobutton")) \
                and (s.get("widget") or {}).get("rect"):
            t_items.append((None, int(s["widget"]["page"]), s["widget"]["rect"]))
    tw = [{"page": p, "rect": r, "kind": "option", "path": str(i)} for i, (_g, p, r) in enumerate(t_items)]
    ours = []                                      # (our group or None, page, rect)
    for n, s in bp["fields"].items():
        if s.get("widgets"):
            ours += [(n, w["page"], w["rect"]) for w in s["widgets"].values()]
        elif s["type"] == "boolean":
            ours.append((None, s["widget"]["page"], s["widget"]["rect"]))
    m = _to_twin([(str(k), p, r) for k, (_g, p, r) in enumerate(ours)], tw)
    pairs = [(int(k), i) for k, i in m.items()]
    tp = fp = fn = 0
    for (a, ia), (b, ib) in ((x, y) for x in pairs for y in pairs if x[0] < y[0]):
        ga, gb = ours[a][0], ours[b][0]
        ta, tb = t_items[ia][0], t_items[ib][0]
        we = ga is not None and ga == gb
        they = ta is not None and ta == tb
        tp += we and they
        fp += we and not they
        fn += they and not we
    # a validated group rebuilt exactly: every box found, all in one of our groups holding nothing else
    by_t = collections.defaultdict(set)
    for k, i in m.items():
        by_t[t_items[i][0]].add(int(k))
    tgroups = {g for g, *_ in t_items if g is not None}
    exact = 0
    for g in tgroups:
        n_boxes = sum(1 for x in t_items if x[0] == g)
        ks = by_t.get(g, set())
        if len(ks) != n_boxes:
            continue
        ogs = {ours[k][0] for k in ks}
        if len(ogs) == 1 and None not in ogs:
            og = ogs.pop()
            if sum(1 for x in ours if x[0] == og) == n_boxes:
                exact += 1
    return {"truth_marks": len(t_items), "matched": len(m), "truth_groups": len(tgroups), "exact": exact,
            "tp": tp, "fp": fp, "fn": fn}


def _relations(struct: dict, key_of) -> dict[str, set]:
    """{'row': {pairs}, 'col': {...}, 'copy': {...}, 'slot': {...}} of twin widget indices, from a structure.find
    result whose cell ids map through key_of (None when the cell has no twin widget)."""
    rel = {"row": set(), "col": set(), "copy": set(), "slot": set()}
    for page, st in struct.items():
        for k, t in enumerate(st["tables"]):
            for a in t["cells"]:
                for b in t["cells"]:
                    ia, ib = key_of(a["id"]), key_of(b["id"])
                    if ia is None or ib is None or ia >= ib:
                        continue
                    if a["row"] == b["row"]:
                        rel["row"].add((ia, ib))
                    if a["col"] == b["col"]:
                        rel["col"].add((ia, ib))
        for k, bl in enumerate(st["blocks"]):
            for a in bl["cells"]:
                for b in bl["cells"]:
                    ia, ib = key_of(a["id"]), key_of(b["id"])
                    if ia is None or ib is None or ia >= ib:
                        continue
                    if a["block"] == b["block"]:
                        rel["copy"].add((ia, ib))
                    if a["slot"] == b["slot"]:
                        rel["slot"].add((ia, ib))
    return rel


def score_tables(raw: Path, twin: Path, info: dict, widgets: list[dict]) -> dict:
    """Our tables and blocks against the same finder run on the twin's widgets, as pairs of twin widgets."""
    entries = [{"id": i, "page": w["page"], "rect": w["rect"], "path": None,
                "widget_type": "checkbox" if w["kind"] == "option" else "text"} for i, w in enumerate(widgets)]
    ref = S.find(twin, entries)
    kept = {b["id"]: b for b in info["boxes"] if b["id"] in set(info["kept_ids"])}
    m = _to_twin([(i, b["page"], b["rect"]) for i, b in kept.items()], widgets)
    ours = _relations(info["struct"], lambda c: m.get(str(c)))
    theirs = _relations(ref, lambda c: c)
    found = set(m.values())
    out = {"ref_tables": sum(len(st["tables"]) for st in ref.values()),
           "ref_blocks": sum(len(st["blocks"]) for st in ref.values())}
    for r in ("row", "col", "copy", "slot"):
        th = {p for p in theirs[r] if p[0] in found and p[1] in found}   # only pairs we could have seen
        out[r] = {"ours": len(ours[r]), "ref": len(th), "both": len(ours[r] & th)}
    return out


def _pct(a, b) -> str:
    return f"{100 * a / b:.0f}%" if b else "-"


def run_pair(fid: str, raw: Path, twin: Path, truth: Path | None, workers: int) -> dict:
    bp, info = build(raw, fid, workers=workers)
    OUT.mkdir(parents=True, exist_ok=True)
    out = OUT / f"{fid}.bpt"
    out.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    widgets = widget_rects(twin)
    rec = {"form": fid, "raw": str(raw), "twin": str(twin), "blueprint": str(out),
           "alignment": round(alignment(raw, twin), 3), "fields": len(bp["fields"]),
           **{k: info[k] for k in ("finder_boxes", "kept", "groups", "tables", "blocks", "tokens", "seconds")},
           "boxes_before": box_structure(widgets, _boxes_bp(info["boxes"])),
           "boxes_after": box_structure(widgets, bp),
           "tables_vs_twin": score_tables(raw, twin, info, widgets)}
    if truth is not None:
        rec["groups_vs_validated"] = score_groups(bp, yaml.safe_load(truth.read_text(encoding="utf-8")) or {})
    return rec


def show(r: dict) -> None:
    w = r["boxes_after"]["widgets"]
    a, b = r["boxes_after"], r["boxes_before"]
    print(f"\n{r['form']}  twin widgets {w}  (raw / twin words aligned {r['alignment']:.0%})  -> {r['fields']} fields, "
          f"{r['groups']} groups, {r['tables']} tables, {r['blocks']} blocks")
    print(f"  finder {r['finder_boxes']} boxes: hit {_pct(b['hit'], w)}, miss {b['miss']}, unbacked {b['unbacked']}")
    print(f"  kept {r['kept']}:        hit {_pct(a['hit'], w)} (text {a['hit_text']}/{a['n_text']}, mark "
          f"{a['hit_option']}/{a['n_option']}), in_region {a['in_region']}, part {a['part']}, miss {a['miss']}; "
          f"unbacked {a['unbacked']} {a['unbacked_by_kind']}; kind swaps {a['kind_swaps']}")
    t = r["tables_vs_twin"]
    print(f"  tables / blocks vs the finder on the twin's widgets ({t['ref_tables']} tables, {t['ref_blocks']} "
          f"blocks there): " + "; ".join(f"same {k} {v['both']} of {v['ref']} found, {v['ours'] - v['both']} extra"
                                         for k, v in t.items() if isinstance(v, dict)))
    g = r.get("groups_vs_validated")
    if g:
        print(f"  groups vs validated: {g['exact']} of {g['truth_groups']} rebuilt exactly; pairs precision "
              f"{_pct(g['tp'], g['tp'] + g['fp'])} recall {_pct(g['tp'], g['tp'] + g['fn'])} "
              f"({g['matched']} of {g['truth_marks']} validated marks found)")
    s = r["seconds"]
    print(f"  Jev {r['tokens']:,} input tokens = ${r['tokens'] / 1e6 * PRICE:.4f}, "
          f"${r['tokens'] / 1e6 * PRICE / max(w, 1) * 1000:.3f} per 1000 fields; {s['total']} s "
          f"({s['total'] / max(w, 1):.2f} s a field; finder {s['finder']}, screen {s['screen']}, groups {s['groups']})")


def main() -> int:
    global KEEP, BOX_CACHE, PATCH
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--pairs", nargs="+", required=True, help="id=raw.pdf:twin.pdf[:validated blueprint stem]")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--keep", type=float, default=KEEP, help="Jev is-it-a-field score kept")
    ap.add_argument("--patch", default=None, help="a finder_experiment.PATCHES name, boxes in a scratch cache")
    ap.add_argument("--save", type=Path, default=RUNS / "flat" / "light_scores.json")
    args = ap.parse_args()
    KEEP = args.keep
    if args.patch:
        import finder_experiment
        finder_experiment.PATCHES[args.patch]()
        PATCH, BOX_CACHE = args.patch, RUNS / "flat" / f"_boxes_{args.patch}"
    recs = []
    for spec in args.pairs:
        fid, rest = spec.split("=", 1)
        parts = rest.split(":")
        raw, twin = REPO / parts[0], REPO / parts[1]
        truth = BLUEPRINTS / f"{parts[2]}.bpt" if len(parts) > 2 and parts[2] else None
        r = run_pair(fid, raw, twin, truth, args.workers)
        recs.append(r)
        show(r)
    args.save.parent.mkdir(parents=True, exist_ok=True)
    args.save.write_text(json.dumps({"when": time.strftime("%Y-%m-%d %H:%M:%S"), "forms": recs}, indent=1))
    tot = collections.Counter()
    for r in recs:
        a = r["boxes_after"]
        for k in ("widgets", "hit", "miss", "in_region", "part", "unbacked"):
            tot[k] += a[k]
        tot["tokens"] += r["tokens"]
        tot["sec"] += r["seconds"]["total"]
        for k, v in (r.get("groups_vs_validated") or {}).items():
            tot["g_" + k] += v
    print(f"\nALL {tot['widgets']} twin fields: hit {_pct(tot['hit'], tot['widgets'])}, in_region {tot['in_region']}, "
          f"part {tot['part']}, miss {tot['miss']}; unbacked {tot['unbacked']}; groups {tot['g_exact']} of "
          f"{tot['g_truth_groups']} exact; ${tot['tokens'] / 1e6 * PRICE / max(tot['widgets'], 1) * 1000:.3f} per "
          f"1000 fields, {tot['sec'] / max(tot['widgets'], 1):.2f} s a field")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
