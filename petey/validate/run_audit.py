"""Run audit: one form's history and numbers in one place, for the review page's Audit mode (Andrew, 2026-10-14: "build
a 'run audit' into the review interface, so you can see the run history and all the data for each form").

A form is its blank; it can have several blueprints (versions): the library copy (`lib__<stem>`, most imported from
petey-master on 2026-09-28) and a fresh run of the current pipeline (`je__<stem>`, `petey.validate.form_run`). For
each version: pages and fields, the page check's flags, Jev's doubts, the name checks' errors, the mechanical pass,
hand review and the corrections recorded on fields. Counts are given per page as well, since forms differ too much
in size for per-form numbers to compare (Andrew, 2026-10-14).

The history is read from what each step already leaves behind, nothing new is recorded:

    import        runs/_gen_cache/imported.json (the petey-master run and labeler model), git's first commit of the file
    form run      runs/judge_eval/form_runs/<stem>[__<when>].json: rounds, models, status, code commit; cost from the
                  rounds' page checks and reviews plus the label / classify / adjudicate calls in runs/_calls
    validate      runs/<stem>_<YYYYMMDD_HHMMSS>/summary.json (fill, extract, compare)
    page check    runs/page_check/*.json records (model, cost, flags)
    Jev           runs/jev/*.json batch outputs (eval/jev_forms.py)
    mechanical    runs/mech_batch_*.json (eval/mechanical_pass.py)
    hand review   runs/hand_review/<id>.json, the working copy's log (runs/drafts), Claude's pass (runs/claude_pass)
    git           commits that touched the library file
"""
from __future__ import annotations

import collections
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Optional

from petey.paths import BLUEPRINTS, REPO, RUNS

NAME_PROBLEMS = ("wrong_name", "not_a_field", "continues", "other")
_memo: dict = {}


def _cached(key, path: Path, fn):
    """fn(path) memoized on the file's mtime."""
    try:
        m = path.stat().st_mtime
    except OSError:
        return None
    hit = _memo.get((key, str(path)))
    if hit and hit[0] == m:
        return hit[1]
    try:
        val = fn(path)
    except Exception:            # an unreadable or odd file is left out of the audit, not fatal
        val = None
    _memo[(key, str(path))] = (m, val)
    return val


def _json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def stem_of(bid: str) -> str:
    return bid.split("__", 1)[1] if "__" in bid else bid


def _prices() -> dict:
    from petey.validate.page_check import PRICES
    return PRICES


def _cost(model: Optional[str], usage: Optional[dict]) -> float:
    if not usage:
        return 0.0
    pi, po = _prices().get(model or "", (0.0, 0.0))
    return ((usage.get("input_tokens") or 0) * pi + (usage.get("output_tokens") or 0) * po) / 1e6


# ----------------------------------------------------------------------------------------------- one version

def _widget_page(spec: dict) -> Optional[int]:
    w = spec.get("widget") or next(iter((spec.get("widgets") or {}).values()), {})
    return (w or {}).get("page")


def text_layer(blank: Optional[Path], pages: list[int]) -> dict:
    """{page: words printed} on the pages that hold fields: a page with almost none has no text layer, and the
    labeler refuses it (2026-10-14: CMS-1500, RRC H-9)."""
    if not blank or not blank.exists():
        return {}

    def read(p: Path) -> dict:
        import pymupdf
        doc = pymupdf.open(str(p))
        try:
            return {i + 1: len(pg.get_text("words")) for i, pg in enumerate(doc)}
        finally:
            doc.close()
    words = _cached("words", blank, read) or {}
    return {pg: words.get(pg, 0) for pg in pages}


def _jev_index() -> dict:
    """{id: [(when, path, [(field, name_fits, check_error)])]} from the batch outputs of eval/jev_forms.py."""
    out = collections.defaultdict(list)
    for p in sorted((RUNS / "jev").glob("*.json")):
        rows = _cached("jev", p, _json)
        if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict) or "bid" not in rows[0]:
            continue
        by = collections.defaultdict(list)
        for r in rows:
            by[r["bid"]].append((r["field"], r.get("name_fits"), r.get("check_error")))
        for b, xs in by.items():
            out[b].append((p.stat().st_mtime, p, xs))
    return out


def _mech_index() -> dict:
    out = collections.defaultdict(list)
    for p in sorted(RUNS.glob("mech_batch_*.json")):
        if p.stem.endswith("_dry"):                  # a dry run changed nothing
            continue
        rows = _cached("mech", p, _json)
        for r in rows or []:
            out[r["bid"]].append((p.stat().st_mtime, p, r))
    return out


def version(bid: str, p: Path, entry: Optional[dict] = None, heavy: bool = False) -> dict:
    """One blueprint's numbers. `heavy` adds the name checks (witness) and the boxes no field covers."""
    from petey.validate import hand_review as h
    from petey.validate.retype import resolve_blank
    bp = h._load(p)
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    per_page = collections.Counter(_widget_page(s) for s in fields.values())
    pages = sorted(x for x in per_page if x)
    blank = resolve_blank(bp)
    words = text_layer(blank, pages)
    out = {"id": bid, "path": str(p.relative_to(REPO)) if p.is_relative_to(REPO) else str(p),
           "kind": "library" if bid.startswith("lib__") else "fresh run" if bid.startswith("je__") else bid.split("__")[0],
           "fields": len(fields), "pages": len(pages), "fields_per_page": {pg: per_page[pg] for pg in pages},
           "no_text_pages": [pg for pg, n in words.items() if n < 20],
           "build": bp.get("x_petey_build") or None, "stable": (bp.get("x_petey_build") or {}).get("stable")}
    # page check
    pc = bp.get("x_petey_page_check")
    if pc:
        from petey.validate.page_check import verdicts
        v = verdicts(bp)
        fl = {n: x for n, x in v.items() if x.get("verdict") == "flag"}
        probs = collections.Counter(x.get("problem") for x in fl.values())
        out["page_check"] = {"when": pc.get("when"), "model": pc.get("model"), "judged": len(v),
                             "flags": len(fl), "name_flags": sum(probs[k] for k in NAME_PROBLEMS),
                             "problems": dict(probs.most_common())}
    # Jev, the latest batch that scored this version
    jv = _jev_index().get(bid)
    if jv:
        when, jp, xs = max(jv, key=lambda x: x[0])
        sc = [f for _, f, _ in xs if f is not None]
        out["jev"] = {"when": time.strftime("%Y-%m-%d %H:%M", time.localtime(when)), "file": jp.name, "scored": len(sc),
                      "below_05": sum(1 for f in sc if f < 0.5), "below_03": sum(1 for f in sc if f < 0.3)}
        if not heavy:
            out["name_errors"] = sum(1 for _, _, e in xs if e)
            out["name_errors_from"] = jp.name
    mc = _mech_index().get(bid)
    if mc:
        when, mp, r = max(mc, key=lambda x: x[0])
        out["mechanical"] = {"when": time.strftime("%Y-%m-%d %H:%M", time.localtime(when)), "file": mp.name,
                             "fixed": r.get("fixed"), "checks": r.get("checks")}
    # hand review and corrections
    v = h.load_verdicts(bid)
    vs = v.get("verdicts") or {}
    out["review"] = {"verdicts": len(vs), "flags": sum(1 for x in vs.values() if x.get("verdict") == "flag"),
                     "looked_at": sum(1 for x in vs.values() if not (x.get("note") or "").startswith(("bulk", "auto"))),
                     "checked": (entry or {}).get("checked")}
    edits = collections.Counter()
    for s in fields.values():
        he = s.get("x_petey_hand_edit")
        if he:
            edits[f"{he.get('by') or 'andrew'}:{he.get('kind') or 'edit'}"] += 1
    out["corrections"] = dict(edits.most_common())
    if heavy:
        from petey.validate import field_add, witness
        res = witness.witnesses(p)
        out["name_errors"] = sum(1 for f in (res.get("fields") or {}).values()
                                 if any(w.get("kind") == "error" for w in f.get("why") or []))
        try:
            ctx = field_add.Context(bid, p)
            out["unclaimed"] = sum(1 for w in ctx.widgets if not w["claimed_by"] and not w["copy"])
        except Exception as e:
            out["unclaimed_error"] = f"{type(e).__name__}: {e}"
    n = max(1, len(pages))
    out["per_page"] = {k: round(val / n, 2) for k, val in (
        ("fields", len(fields)), ("page_check_flags", (out.get("page_check") or {}).get("flags")),
        ("page_check_name_flags", (out.get("page_check") or {}).get("name_flags")),
        ("jev_below_03", (out.get("jev") or {}).get("below_03")), ("name_errors", out.get("name_errors")),
        ("unclaimed", out.get("unclaimed"))) if val is not None}
    return out


# ----------------------------------------------------------------------------------------------- history

def _calls_cost(stem: str, start: str, end: str) -> tuple[float, collections.Counter]:
    """Model calls logged for this form between two times (label, classify, adjudicate, ...): cost and count by
    tag/model. Page-check calls are logged without the form, so they come from the run record instead."""
    cost, n = 0.0, collections.Counter()
    for d in RUNS.glob(f"_calls/*/{stem}/*"):
        for f in d.glob("*.json"):
            rec = _cached("call", f, lambda p: {k: v for k, v in _json(p).items() if k in ("when", "usage")})
            if not rec or not (start <= (rec.get("when") or "") <= end):
                continue
            model = d.name
            cost += _cost(model, rec.get("usage"))
            n[f"{d.parent.parent.name}/{model}"] += 1
    return cost, n


def _form_run_event(p: Path, stem: str) -> Optional[dict]:
    d = _cached("form_run", p, _json)
    if not d:
        return None
    res, cfg, code = d.get("result") or {}, d.get("config") or {}, d.get("code") or {}
    pc_cost = rv_cost = 0.0
    pages = set()
    for r in d.get("rounds") or []:
        run = r.get("page_check_run") or {}
        pc_cost += run.get("cost_usd") or 0.0
        if r.get("stage") == "label":
            pages |= set(run.get("pages") or [])
        lp = r.get("loop") or {}
        rv_cost += (lp.get("review") or {}).get("cost_usd") or (lp.get("review_run") or {}).get("cost_usd") or 0.0
    start, end = d.get("started") or "", res.get("finished") or (d.get("rounds") or [{}])[-1].get("when") or ""
    calls, ncalls = _calls_cost(stem, start, end or "9999")
    total = pc_cost + rv_cost + calls
    secs = None
    try:
        secs = time.mktime(time.strptime(end, "%Y-%m-%d %H:%M:%S")) - time.mktime(time.strptime(start, "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        pass
    n = max(1, len(pages))
    return {"when": start, "end": end, "kind": "form run", "file": str(p.relative_to(REPO)),
            "title": f"fresh run: {res.get('status') or 'unfinished'}" + ("" if res.get("stable", True) else " (not stable)"),
            "detail": {"stop": res.get("stop"), "review rounds": res.get("review_rounds"), "rounds": len(d.get("rounds") or []),
                       "labeler": cfg.get("labeler"), "page check": f"{(cfg.get('page_check') or {}).get('round0_model')} then "
                                                                      f"{(cfg.get('page_check') or {}).get('loop_model')}",
                       "reviewer": (cfg.get("reviewer") or {}).get("model"), "code": f"{code.get('branch')} {str(code.get('commit'))[:8]}"
                                                                                   + (" (uncommitted changes)" if code.get("dirty") else ""),
                       "calls": dict(ncalls), "blueprint": res.get("bpt")},
            "cost": round(total, 4), "pages": len(pages), "cost_per_page": round(total / n, 4) if pages else None,
            "minutes": round(secs / 60, 1) if secs is not None else None,
            "minutes_per_page": round(secs / 60 / n, 2) if secs is not None and pages else None}


def _pc_record(p: Path) -> dict:
    d = _json(p)
    if not isinstance(d, dict):
        return {}
    return {**{k: v for k, v in d.items() if k != "fields"},
            "flags": sum(1 for x in (d.get("fields") or {}).values() if isinstance(x, dict) and x.get("verdict") == "flag")}


def history(stem: str, ids: list[str]) -> list[dict]:
    ev = []
    imp = _cached("imported", RUNS / "_gen_cache" / "imported.json", _json) or {}
    for x in imp.values():
        if x.get("form") == stem:
            m = re.search(r"_(\d{8})_(\d{6})$", x.get("source_run") or "")
            when = f"{m[1][:4]}-{m[1][4:6]}-{m[1][6:]} {m[2][:2]}:{m[2][2:4]}:{m[2][4:]}" if m else ""
            ev.append({"when": when, "kind": "generated (petey-master)",
                       "title": f"generated in petey-master, labeler {x.get('cached_under_model')}",
                       "detail": {"run": x.get("source_run"), "values": x.get("n_values")}})
    lib = BLUEPRINTS / f"{stem}.bpt"
    if lib.exists():
        log = subprocess.run(["git", "log", "--follow", "--format=%ad\t%h\t%s", "--date=format:%Y-%m-%d %H:%M:%S", "--",
                              str(lib)], cwd=REPO, capture_output=True, text=True).stdout
        for line in log.splitlines():
            when, h, subj = (line.split("\t", 2) + ["", ""])[:3]
            ev.append({"when": when, "kind": "library commit", "title": subj[:140], "detail": {"commit": h}})
    fr = RUNS / "judge_eval" / "form_runs"
    for p in [fr / f"{stem}.json", *sorted(fr.glob(f"{stem}__*.json"))]:
        if p.exists() and (e := _form_run_event(p, stem)):
            ev.append(e)
    pat = re.compile(rf"^{re.escape(stem)}_(\d{{8}})_(\d{{6}})$")
    for d in RUNS.glob(f"{stem}_*"):
        m = pat.match(d.name)
        if not m or not (d / "summary.json").exists():
            continue
        s = _cached("summary", d / "summary.json", _json) or {}
        meth = next(iter((s.get("intact") or {}).items()), (None, {}))
        ev.append({"when": f"{m[1][:4]}-{m[1][4:6]}-{m[1][6:]} {m[2][:2]}:{m[2][2:4]}:{m[2][4:]}", "kind": "validate",
                   "title": f"fill / extract / compare: {meth[1].get('agree', '?')} agree, {meth[1].get('differ', '?')} differ, "
                            f"{meth[1].get('extract_miss', '?')} not read back", "detail": {"run": d.name, "method": meth[0]}})
    for p in (RUNS / "page_check").glob("*.json"):
        r = _cached("pc_record", p, _pc_record)
        if not isinstance(r, dict) or r.get("form") is None:
            continue
        bp = Path(r.get("blueprint") or "")
        if bp.stem != stem and not p.name.startswith(tuple(f"{i}__" for i in ids)):
            continue
        which = ("library" if bp.parent == BLUEPRINTS else "fresh run" if "judge_eval" in str(bp)
                 else "before-review copy" if "belongs_to" in str(bp) else str(bp.parent.name))
        ev.append({"when": r.get("when") or "", "kind": "page check",
                   "title": f"page check on the {which}: {r.get('flags')} flags, {r.get('model')}",
                   "cost": r.get("cost_usd"), "pages": len(r.get("pages") or []),
                   "cost_per_page": round((r.get("cost_usd") or 0) / max(1, len(r.get("pages") or [])), 4),
                   "detail": {"record": p.name}})
    for b in ids:
        for when, jp, xs in _jev_index().get(b, []):
            sc = [f for _, f, _ in xs if f is not None]
            ev.append({"when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)), "kind": "Jev",
                       "title": f"Jev on {b}: {sum(1 for f in sc if f < 0.3)} below 0.3, {sum(1 for f in sc if f < 0.5)} "
                                f"below 0.5 of {len(sc)}", "detail": {"file": jp.name}})
        for when, mp, r in _mech_index().get(b, []):
            ev.append({"when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(when)), "kind": "mechanical pass",
                       "title": f"mechanical pass on {b}: fixed {r.get('fixed')}", "detail": {"checks": r.get("checks"), "file": mp.name}})
        hr = RUNS / "hand_review" / f"{b}.json"
        if hr.exists():
            v = _cached("hr", hr, _json) or {}
            ws = sorted(x.get("when") or "" for x in (v.get("verdicts") or {}).values() if x.get("when"))
            if ws:
                ev.append({"when": ws[0], "kind": "hand review",
                           "title": f"hand review of {b}: {len(ws)} verdicts, {ws[0][:10]} to {ws[-1][:10]}",
                           "detail": {"validated": ((v.get("checked") or {}).get("when"))}})
        for sub, what in (("proposals", "Claude's pass"), ("suggestions", "Claude's suggestions")):
            cp = RUNS / "claude_pass" / sub / f"{b}.json"
            if cp.exists():
                ev.append({"when": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(cp.stat().st_mtime)), "kind": "Claude",
                           "title": f"{what} for {b}", "detail": {"file": str(cp.relative_to(REPO))}})
        dm = RUNS / "drafts" / b / "draft.json"
        if dm.exists():
            m = _cached("draft", dm, _json) or {}
            ev.append({"when": m.get("made") or "", "kind": "working copy",
                       "title": f"working copy of {b} open: {len(m.get('log') or [])} changes not saved",
                       "detail": {"changes": [f"{x['mode']}: {x['change']}" for x in (m.get("log") or [])[-30:]]}})
    # the validate runs a fresh run makes each round belong to it, not to the form's history
    spans = [(e["when"], e["end"]) for e in ev if e["kind"] == "form run" and e.get("end")]
    ev = [e for e in ev if e["kind"] != "validate" or not any(a <= e["when"] <= b for a, b in spans)]
    return sorted(ev, key=lambda e: e.get("when") or "", reverse=True)


def audit(bid: str, paths: dict, entries: dict) -> dict:
    """Everything for one form: each version's numbers (the one asked for in full) and the history."""
    stem = stem_of(bid)
    ids = [b for b in paths if stem_of(b) == stem and b.split("__")[0] in ("lib", "je")] or [bid]
    from petey.validate.hand_review import working_path
    vers = [version(b, working_path(b, paths), entries.get(b), heavy=(b == bid)) for b in sorted(ids)]
    return {"id": bid, "form": stem, "versions": vers, "history": history(stem, ids)}


def batch(bids: list[str], paths: dict, entries: dict) -> list[dict]:
    """The batch table: every version of each listed form, light numbers only."""
    from petey.validate.hand_review import working_path
    seen, rows = set(), []
    for bid in bids:
        stem = stem_of(bid)
        if stem in seen:
            continue
        seen.add(stem)
        ids = sorted(b for b in paths if stem_of(b) == stem and b.split("__")[0] in ("lib", "je"))
        for b in ids:
            try:
                rows.append(dict(version(b, working_path(b, paths), entries.get(b)), form=stem))
            except Exception as e:
                rows.append({"id": b, "form": stem, "error": f"{type(e).__name__}: {e}"})
    return rows
