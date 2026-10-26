"""The mechanical pass on generated blueprints: the fixes and checks of the 2026-10-13/14 review round that need no
model, in one place (they were scratch scripts then). Run it on a form before any model check (Jev, the VLM page
check), so those see a blueprint the rules have already cleaned.

Fixes, written into the review page's working copy (`draft`), so Andrew checks and saves them as usual; each field
records `x_petey_hand_edit` {by: claude, kind: type, why}:

    reserved      a box whose line reads "Reserved for future use" (or "further use") is not a field: the shaded box
                  of a line not in use, mostly on IRS forms (Andrew, 2026-10-16, after removing Schedule 8812's line
                  15). Read from the caption on the box's line (from the box before it on the line to the box), the
                  text inside the box, its tooltip, description and name; the shaded boxes after it on the line go
                  too (a white one is still a field: a grid may block out only some cells); recorded as a removal in
                  Add / remove (from: mechanical pass) and applied, so the review page shows it and it can be undone
                  there, and listed in a form note (`note_removed`). Option groups are left alone. Runs first, so no
                  other fix works on a box that is going
    group_type    a field holding several option boxes but typed boolean (or anything but category /
                  multi_category) becomes category (2026-10-15: SSA-827, VA 21-0966)
    person_name   the leftover `person_name` semantic type is cleared (it is no longer assigned; it changed nothing)
    pattern       a string field whose semantic type has a registry pattern gets it (`semantic_types.pattern_for`)
    yes_no        loose Yes / No checkbox pairs become one group each (`yes_no_groups`)
    dropdowns     dropdown entries as options {key: {caption, stored}}, the empty / prompt entry dropped
                  (`dropdowns.options_into_working`; 2026-10-15: the passes after generation had not done it)
    row_groups    loose checkboxes on one row with no ruling line or item number between them become one group
                  (`cell_groups.proposals`; tables of separate items are left alone), one-of (`category`)

Checks, reported only:

    grid_naming   cells of a table whose name breaks the table's pattern: another number than their row's (or
                  column's), or another wording than their column's (`grid_naming.py`)
    unclaimed     AcroForm widgets no field covers (missing boxes; I-130 had two)
    keys_inverted a Yes / No option whose key says yes and whose export value says no, or the reverse
    code_caption  option captions that are export codes ('BLK', 'N') rather than the printed words
    far_pages     an option group whose boxes are on pages more than one apart
    bad_semtype   a semantic type the registry does not know
    name_errors   fields the review page marks as errors (the name checks: belongs to / does not describe, item
                  number only, suffix against type); `name_hints` the suggestions

    PYTHONPATH=. venv/bin/python eval/mechanical_pass.py lib__fw9 lib__ds11 [--dry]
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import time
from pathlib import Path
from typing import Optional

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cell_groups as cg  # noqa: E402
from petey.validate import grid_naming  # noqa: E402
import yes_no_groups as yn  # noqa: E402

from petey.semantic_types import pattern_for, registered_names  # noqa: E402
from petey.validate import draft, field_add, group_review as g, hand_review as h, witness  # noqa: E402
from petey.validate import dropdowns as dd  # noqa: E402
from petey.validate.retype import resolve_blank  # noqa: E402

CODEISH = re.compile(r"^(Y|N|YES|NO|[A-Z]{2,4}|\d+[a-zA-Z]?|[a-z]\d*|#20.*|\s*)$")
RESERVED = re.compile(r"reserved\W+for\W+(future|further)\W+use", re.I)
LINE_NO = re.compile(r"^\(?\d+[a-z]{0,2}\)?\.?$")
FIXES = ("reserved", "group_type", "person_name", "pattern", "yes_no", "row_groups", "dropdowns")
CHECKS = ("grid_naming", "unclaimed", "keys_inverted", "code_caption", "far_pages", "bad_semtype", "name_errors", "name_hints")


def type_edits(fields: dict) -> tuple[dict, dict]:
    """({field: edit}, {field: {kind, why}}) for the group type, person_name and pattern fixes."""
    edits, extra = {}, {}
    for n, s in fields.items():
        if not isinstance(s, dict):
            continue
        if len(s.get("widgets") or {}) > 1 and s.get("type") not in ("category", "multi_category"):
            edits[n] = {"type": "category"}
            extra[n] = {"kind": "type", "why": f"a group of {len(s['widgets'])} options is one of (category), not "
                                               f"{s.get('type')}"}
            continue
        st = s.get("semantic_type")
        if st == "person_name":
            edits[n] = {"semantic_type": "none"}
            extra[n] = {"kind": "type", "why": "person_name is no longer assigned (it changed nothing)"}
        elif s.get("type", "string") == "string" and not s.get("pattern") and pattern_for(st):
            edits[n] = {"pattern": pattern_for(st)}
            extra[n] = {"kind": "type", "why": f"the pattern of its semantic type ({st})"}
    return edits, extra


def _line_caption(page, rect: list, others: list) -> str:
    """The words on a box's line to its left, back to the nearest other box on that line (IRS: "15 Reserved for future
    use ..... 15" then the shaded box)."""
    x0, y0, x1, y1 = rect
    left = max([r[2] for r in others if r[2] <= x0 + 1 and min(r[3], y1) - max(r[1], y0) > 0.5 * (y1 - y0)],
               default=0)
    return " ".join(w[4] for w in sorted(page.get_text("words"), key=lambda w: w[0])
                    if y0 <= (w[1] + w[3]) / 2 <= y1 and w[0] >= left - 1 and w[2] <= x0 + 1)


def _fills(page) -> list:
    """The page's filled shapes smaller than most of the page: (rect, fill colour)."""
    return [(d["rect"], d["fill"]) for d in page.get_drawings()
            if d.get("fill") and d["rect"].width < 0.6 * page.rect.width]


def _shaded(rect: list, fills: list) -> bool:
    """The box sits on a grey (or any non-white) fill printed on the page: a blocked-out cell. The box's own white
    background, drawn by a viewer, is not part of the page."""
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return any(r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 and max(col) < 0.95 for r, col in fills)


def reserved(bp: dict, blank: Optional[Path]) -> list[dict]:
    """Add / remove entries for the fields that are a box reserved for future use (see `reserved` above)."""
    import pymupdf
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    doc = pymupdf.open(blank) if blank else None
    hot = {i + 1 for i, pg in enumerate(doc) if RESERVED.search(pg.get_text())} if doc else set()
    rects = collections.defaultdict(list)
    for s in fields.values():
        for w in [s.get("widget")] + list((s.get("widgets") or {}).values()):
            if w and w.get("rect"):
                rects[w.get("page")].append(w["rect"])
    out, now = [], time.strftime("%Y-%m-%d %H:%M:%S")
    for n, s in fields.items():
        w = s.get("widget") or {}
        if s.get("widgets") or not w:
            continue
        said = [("name", n.replace("_", " ")), ("description", s.get("description")), ("tooltip", w.get("tooltip"))]
        if w.get("page") in hot and w.get("rect"):
            pg = doc[w["page"] - 1]
            said += [("text in the box", pg.get_textbox(pymupdf.Rect(w["rect"]))),
                     ("its line", _line_caption(pg, w["rect"], [r for r in rects[w["page"]] if r != w["rect"]]))]
        hit = next((k for k, t in said if RESERVED.search(str(t or ""))), None)
        if hit:
            out.append({"name": n, "page": w.get("page"), "rect": w.get("rect"), "when": now, "from": "mechanical pass",
                        "why": f"reserved for future use ({hit}): not a field"})
    # the rest of a reserved line (941-X line 24: four columns of dollars and cents, all shaded): the next box to the
    # right on the line, when it is shaded on the page (a blocked-out cell; Andrew, 2026-10-16: "sometimes it's a grid
    # where only one box is reserved", so a white box on the line is still a field and ends it) and nothing but
    # symbols and line numbers sit between them ("-", "=", "24"; words, such as a second table's caption, end it)
    singles = [(n, s["widget"]) for n, s in fields.items() if not s.get("widgets") and (s.get("widget") or {}).get("rect")]
    done = {e["name"] for e in out}
    for e in list(out):
        if not doc or not e.get("rect"):
            continue
        words = doc[e["page"] - 1].get_text("words")
        fills = _fills(doc[e["page"] - 1])
        cur = e["rect"]
        while True:
            y0, y1 = cur[1], cur[3]
            nxt = min([(w["rect"][0], n, w) for n, w in singles if w.get("page") == e["page"] and w["rect"][0] > cur[0] and w["rect"][0] >= cur[2] - 1
                       and min(w["rect"][3], y1) - max(w["rect"][1], y0) > 0.5 * (y1 - y0)], default=None)
            if not nxt:
                break
            _, n, w = nxt
            between = [t[4] for t in words if y0 <= (t[1] + t[3]) / 2 <= y1 and t[0] >= cur[2] - 1 and t[2] <= w["rect"][0] + 1]
            if any(sum(c.isalpha() for c in t) > 1 and not LINE_NO.match(t) for t in between) or not _shaded(w["rect"], fills):
                break
            if n not in done:
                done.add(n)
                out.append({"name": n, "page": w.get("page"), "rect": w["rect"], "when": now, "from": "mechanical pass",
                            "why": f"on the line of {e['name']}, reserved for future use: not a field"})
            cur = w["rect"]
    return out


def remove(bid: str, entries: list[dict]) -> list[str]:
    """Record the removals in the form's Add / remove record and apply them to the working copy, as the review page's
    remove does (`App.save_add`)."""
    rec = field_add.load_record(bid)
    have = {r.get("name") for r in (rec.get("removed") or [])}
    new = [e for e in entries if e["name"] not in have]
    if not new:
        return []
    p = draft.ensure(bid, h.blueprint_paths()[bid])
    rec.update({"blueprint": str(h.blueprint_paths()[bid]), "form": p.stem, "blueprint_sha": h._sha(p),
                "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "removed": (rec.get("removed") or []) + new})
    field_add.record_path(bid).parent.mkdir(parents=True, exist_ok=True)
    field_add.record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    bp = h._load(p)
    code = {n: f"{p.stem}_{s.get('x_petey_id')}" for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    before = h._sha(p)
    pl = field_add.apply(bid) or {}
    draft.follow(bid, before, h._sha(p))
    draft.log(bid, "add", pl.get("changes") or [])
    note_removed(bid, new, code)
    return pl.get("changes") or []


def note_removed(bid: str, entries: list[dict], code: dict[str, str]) -> None:
    """A form note listing the reserved boxes removed (Andrew, 2026-10-16: "add a note but go ahead and remove the
    field"), by page, field code and name, the shaded boxes after one on its line listed with it; added to any note
    the form has."""
    lines: dict[str, list[str]] = {}
    for e in entries:
        if not e["why"].startswith("on the line of "):
            lines[e["name"]] = []
    for e in entries:
        if e["why"].startswith("on the line of "):
            lines.setdefault(e["why"][len("on the line of "):].split(",")[0], []).append(code.get(e["name"], e["name"]))
    page = {e["name"]: e.get("page") for e in entries}
    body = "\n".join(f"- p{page.get(n)} {code.get(n, n)} {n}" + (f" + {len(after)} shaded box(es) after it on the line: "
                                                                 f"{', '.join(after)}" if after else "")
                     for n, after in lines.items())
    head = (f"Reserved for future use (clearing step, {time.strftime('%Y-%m-%d')}): removed these boxes, their lines "
            f"read \"Reserved for future use\". Undo in Add / remove if one is a field.")
    old = (h.form_notes().get(bid) or {}).get("text") or ""
    h.set_form_note(bid, (old + "\n\n" if old else "") + head + "\n" + body)


def checks(bid: str, p: Path, bp: dict, blank: Path) -> tuple[collections.Counter, list[str]]:
    """The report-only checks: counts, and one line per finding."""
    c, lines = collections.Counter(), []
    for ln in grid_naming.check(bp):             # a grid named on one pattern (Andrew, 2026-10-15)
        c["grid_naming"] += 1
        lines.append(f"grid_naming   {ln}")
    valid = set(registered_names())
    try:
        ctx = field_add.Context(bid, p)
        for w in ctx.widgets:
            if not w["claimed_by"] and not w["copy"]:
                c["unclaimed"] += 1
                lines.append(f"unclaimed     p{w.get('page')} {w.get('path') or w.get('rect')}")
    except Exception as e:                              # a blank the finder cannot read: say so, go on
        lines.append(f"unclaimed     not checked ({type(e).__name__}: {e})")
    items, units = g.option_items(bp)
    for u in units:
        its = [items[i] for i in u["items"]]
        pages = sorted({it["page"] for it in its})
        if len(pages) > 1 and pages[-1] - pages[0] > 1:
            c["far_pages"] += 1
            lines.append(f"far_pages     {u['name']} pages {pages}")
        for it in its:
            k, on = (it["key"] or it["field"]).lower(), str(it.get("on_state") or "").lower().replace("#20", "")
            if on in ("y", "yes", "n", "no") and (("_yes" in k and on.startswith("n")) or
                                                  ("_no_" in k + "_" and on.startswith("y"))):
                c["keys_inverted"] += 1
                lines.append(f"keys_inverted {u['name']} :: {it['key'] or it['field']} on={it.get('on_state')}")
            cap = it.get("caption")
            if len(its) > 1 and cap is not None and CODEISH.match(str(cap)) and str(cap).strip().lower() not in ("yes", "no"):
                c["code_caption"] += 1
                lines.append(f"code_caption  {u['name']} :: {it['key'] or it['field']} caption={cap!r}")
    for n, s in (bp.get("fields") or {}).items():
        st = (s or {}).get("semantic_type") if isinstance(s, dict) else None
        if st and st not in valid and st != "none":
            c["bad_semtype"] += 1
            lines.append(f"bad_semtype   {n} {st}")
    res = witness.witnesses(p)
    code = {n: f"{p.stem}_{s.get('x_petey_id')}" for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    for n, f in (res.get("fields") or {}).items():
        why = f.get("why") or []
        errs = [w for w in why if w.get("kind") == "error"]
        if errs:
            c["name_errors"] += 1
            lines.append(f"name_error    {code.get(n, n)} {n}: {errs[0]['text'][:140]}")
        elif why:
            c["name_hints"] += 1
    return c, lines


def run(bid: str, dry: bool) -> dict:
    real = h.blueprint_paths()[bid]
    p = h.working_path(bid)
    bp = h._load(p)
    blank = resolve_blank(bp)
    gone = reserved(bp, blank)
    if not dry and gone:
        remove(bid, gone)
        p = h.working_path(bid)
        bp = h._load(p)
    edits, extra = type_edits(bp.get("fields") or {})
    pairs = yn.pairs(bp, blank) if blank else []
    rows = cg.proposals(bp, blank, {i for _, y, n in pairs for i in (y, n)}) if blank else []
    fixed = collections.Counter({"reserved": len(gone), "group_type": sum("type" in e for e in edits.values()),
                                 "person_name": sum("semantic_type" in e for e in edits.values()),
                                 "pattern": sum("pattern" in e for e in edits.values()), "yes_no": len(pairs),
                                 "row_groups": len(rows),
                                 "dropdowns": sum(1 for sp in (bp.get("fields") or {}).values() if isinstance(sp, dict)
                                                  and not sp.get("widgets") and sp.get("values") and not sp.get("options")
                                                  and (sp.get("widget") or {}).get("widget_type") in dd.KINDS)})
    if not dry and edits:
        p = draft.ensure(bid, real)
        bp = h._load(p)
        clean = {n: e for n, e in ((n, h.clean_edit(n, bp["fields"][n], e)) for n, e in edits.items()) if e}
        before = h._sha(p)
        bp["fields"] = h.edit_fields(bp["fields"], clean, {n: n for n in clean}, time.strftime("%Y-%m-%d %H:%M:%S"),
                                     "eval/mechanical_pass.py", by="claude", extra=extra)
        p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True, default_flow_style=False), encoding="utf-8")
        draft.follow(bid, before, h._sha(p))
        draft.log(bid, "claude", [f"{n}: {extra[n]['why']}" for n in clean])
    if not dry and (pairs or rows):
        yn.run(bid, False, rows)
    if not dry and fixed["dropdowns"]:
        dd.options_into_working(bid)
    p = h.working_path(bid)
    c, lines = checks(bid, p, h._load(p), blank) if blank else (collections.Counter(), ["no blank"])
    lines = [f"reserved      {e['name']}: {e['why']}" for e in gone] + lines
    return {"bid": bid, "fixed": dict(fixed), "checks": dict(c), "lines": lines}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("ids", nargs="+", help="review-page ids (lib__fw9)")
    ap.add_argument("--dry", action="store_true", help="count the fixes, write nothing")
    ap.add_argument("--save", help="write the report (json) here")
    args = ap.parse_args()
    out = []
    print(f"{'form':30} " + " ".join(f"{k:>11}" for k in FIXES + CHECKS))
    for bid in args.ids:
        r = run(bid, args.dry)
        out.append(r)
        print(f"{bid:30} " + " ".join(f"{r['fixed'].get(k, r['checks'].get(k, 0)):>11}" for k in FIXES + CHECKS),
              flush=True)
    tot = collections.Counter()
    for r in out:
        tot.update(r["fixed"])
        tot.update(r["checks"])
    print(f"{'total':30} " + " ".join(f"{tot.get(k, 0):>11}" for k in FIXES + CHECKS))
    if args.save:
        Path(args.save).parent.mkdir(parents=True, exist_ok=True)
        Path(args.save).write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
