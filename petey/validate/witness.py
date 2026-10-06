"""How sure are we of each field? A count of independent witnesses, not a score.

Every check the loop runs says something about some fields and nothing about the rest. This puts them side by side
per field, each reading `for`, `against` or silent, and sorts the field into a tier so a person reviews the
contested ones first and the settled ones last (Andrew, 2026-10-05: spend as little attention on hand review as
possible). Confidence comes from independent agreement, not from any single score (`worklist.py`, petey-master).

Witnesses, each reading a different source:

    publisher   the PDF's own words for the widget: the tooltip (TU) and, on an XFA hybrid, the template's caption
                and tooltip. They explain the name -> for; share nothing with it, or belong to another field ->
                against.
    page        the printed text at the widget on the blank: the lines lined up with it and near it, the column
                header above a table cell, the row label to its left (`field_chain.candidate_captions`,
                `column_header`, `row_header`). The text layer, not a model. Against only when the nearest
                caption belongs to another field: a line number or a neighbour's text beside a box is common.
    classifier  the vision classifier's reading of the box (`class_map`, cached per blank): class `none` (the page
                says nothing goes here), a class whose family contradicts the field's type, or a caption that
                belongs to another field -> against; the same family or a caption that explains the name -> for.
                Silent when its caption for the box is misattributed (`field_chain` verified False): one
                misreading must not count twice.

"Belongs to another field" is contrastive: another name on the page is explained better by the text than this
one, and better than by that field's own text. Words count by how rare they are among the form's names, and a
score is the share of the name the text explains (`Names`). That is the signature of a swap or a widget placed one
row off (5500-SF's day/month, ACORD 25's phone names on the state and ZIP boxes); a neighbour a tooltip merely
mentions ('mailing address' in a ZIP tooltip) does not qualify.
    judge       the by-name reader over the run's cases: found the case's value -> for, a different value or
                nothing -> against. Counted only on filled values (agreement by absence is not evidence) and only
                where the chain holds at `value`.
    structure   the inventory check (`option_group_mismatch`, `merged_box`, `split_box`, `tie`), the classifier's
                option groups against the blueprint's, and separate checkboxes lined up as one question
                (`lined_up_checkboxes`) -> against. Never `for`: a box the finder matched says nothing about the
                name.
    adjudicator `x_petey_adjudication`: `current` or `proposed` upheld the name the field holds -> for; `unclear` ->
                against.
    page_check  the vision first pass over the whole rendered page (`page_check.py`, stamped on the blueprint as
                `x_petey_page_check`): accepted -> for; flagged -> against, with its problem, reading and reason.
                Only for fields whose definition is unchanged since the check; reads the stored record, no calls.

Tiers: `contested` (any witness against), `settled` (two or more for, none against), `single` (one for),
`unknown` (none spoke). The run's results are joined to the blueprint by widget path, so a field renamed since
the run gets no judge or classifier witness for its new name.

The tiers are calibrated against hand review (`--calibrate`): the share of fields a person flagged in each tier.
First reading (2026-10-05, six library blueprints, 442 verdicts, 30 flags): settled 278 with 5 flags, single 35
with 0, contested 129 with 25. The settled misses: a widget the publisher put on a header ('not a field', 1014r),
a radio group that holds two questions (5500-SF `return_type`, no classifier box under it), and three the notes
leave open. The rules were fitted on these same verdicts, so the next blueprints reviewed are the real test.

    PYTHONPATH=. venv/bin/python -m petey.validate.witness blueprints/2022_rev_form_1014r.bpt [--run runs/...] [--show]
    PYTHONPATH=. venv/bin/python -m petey.validate.witness --calibrate     # every blueprint with hand-review verdicts
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
from pathlib import Path
from typing import Optional

import pymupdf
import yaml

from petey.label import xfa as xfa_mod
from petey.paths import RUNS
from petey.synth.boxes import match_rect
from petey.synth.classify import classify_form
from petey.validate.class_check import _CONTROL_CLASSES, _family, blueprint_class
from petey.validate.field_chain import _agrees, _page_lines, candidate_captions, column_header, field_chain, \
    row_header
from petey.validate.name_caption import tokens
from petey.validate.retype import resolve_blank

TIERS = ("contested", "unknown", "single", "settled")     # review order
STRUCTURE_AGAINST = {"option_group_mismatch", "merged_box", "split_box", "tie"}
_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)


def _load(p: Path) -> dict:
    return yaml.load(Path(p).read_text(encoding="utf-8"), Loader=_LOADER) or {}


def _widgets(spec: dict) -> list[dict]:
    if spec.get("widgets"):
        return [w for w in spec["widgets"].values() if isinstance(w, dict)]
    w = spec.get("widget") or {}
    return [w] if w else []


def _key(spec: dict) -> str:
    """A field's identity across renames: its widget path (an option group: its option paths and on-states)."""
    if spec.get("widgets"):
        return "group:" + "|".join(sorted(f"{w.get('path')}#{k}" for k, w in spec["widgets"].items()))
    w = spec.get("widget") or {}
    return f"{w.get('page')}:{w.get('path')}"


# ------------------------------------------------------------------- publisher and page (blueprint + blank only)

def publisher_words(blank: Path) -> dict[str, list[str]]:
    """`{path: [tooltip, xfa caption, xfa tooltip]}`: what the publisher says each widget is."""
    out: dict[str, list[str]] = collections.defaultdict(list)
    doc = pymupdf.open(str(blank))
    try:
        for page in doc:
            for w in page.widgets() or []:
                t = (w.field_label or "").strip()
                if t and t not in out[w.field_name]:
                    out[w.field_name].append(t)
    finally:
        doc.close()
    try:
        tpl = xfa_mod.parse(blank)
    except Exception:
        tpl = None
    if tpl is not None:
        for path in list(out):
            x = tpl.lookup(path)
            for t in ((x.caption, x.tooltip) if x is not None else ()):
                t = (t or "").strip()
                if t and t not in out[path]:
                    out[path].append(t)
    return out


def _toks(s: str) -> set[str]:
    """`name_caption.tokens`, every token cut to the same five-letter stem: its expansions are whole words
    ('zip' -> 'postal') while caption words are stems ('posta'), so 'zip' never met 'postal code'."""
    return {_MORE_ABBR.get(t, t)[:5] for t in tokens(s)}


_MORE_ABBR = {"nbr": "number", "zip": "postal"}     # slugs the labeler writes that `name_caption._ABBR` lacks


class Names:
    """The form's field names as token sets, for contrastive matching: a name is evidence for a text only when it
    matches that text better than the other names on its page do, and a word counts by how rare it is among the
    form's names ('plan' on Form 5500 says nothing; 'month' against 'day' says everything)."""

    def __init__(self, fields: dict) -> None:
        self.toks = {n: _toks(n) for n in fields}
        self.page = {n: (_widgets(s)[0].get("page") if _widgets(s) else None) for n, s in fields.items()}
        df = collections.Counter(t for ts in self.toks.values() for t in ts)
        n = max(len(self.toks), 1)
        self.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
        self.own: dict[str, float] = {}     # how well each field's own text (of this witness) explains its name

    def set_own(self, texts_by_field: dict[str, list[str]]) -> None:
        self.own = {n: max((self.score(n, _toks(t)) for t in ts), default=0.0) for n, ts in texts_by_field.items()}

    def score(self, name: str, tt: set[str]) -> float:
        """How much of the name the text explains: matched weight over the name's weight. Raw overlap favours
        long names against long tooltips (ACORD 25: 'producer's contact person's phone number ... area code'
        out-matched `contact_phone_nbr` with `producer_phone_area_cd`)."""
        mine = self.toks.get(name, set())
        total = sum(self.idf.get(t, 0.0) for t in mine)
        return sum(self.idf.get(t, 0.0) for t in mine & tt) / total if total > 0 else 0.0

    def judge(self, name: str, texts: list[str]) -> tuple[Optional[bool], str]:
        """True: the text explains the name; False: the text has words and the name shares none of them, or the
        text belongs to another field on the page more than that field's own text does (a swap, a widget placed
        one row off: 5500-SF's day box carries 'Enter month of waiver letter'); None: nothing to compare. A
        neighbour the text merely mentions ('mailing address' in a ZIP tooltip) is not enough: its own text
        explains it at least as well. The detail names the field the text belongs to."""
        tt = set().union(*(_toks(t) for t in texts)) if texts else set()
        if not tt:
            return None, ""
        mine = self.score(name, tt)
        if mine <= 0:
            return False, ""
        page = self.page.get(name)
        best, who = mine, None
        for other in self.toks:
            if other != name and self.page.get(other) == page:
                s = self.score(other, tt)
                if s > best + 1e-9 and s > self.own.get(other, 0.0) + 1e-9:
                    best, who = s, other
        return (False, f"belongs to: {who}") if who else (True, "")


def publisher_texts(spec: dict, words: dict[str, list[str]]) -> list[str]:
    w = _widgets(spec)
    return words.get((w[0] if w else {}).get("path") or "", [])


def page_texts(spec: dict, lines: dict) -> list[str]:
    """The printed lines that could caption a text field's widget, nearest first, then its column and row
    headers. Option groups: none (their captions are checked per option)."""
    w = spec.get("widget") or {}
    pl = lines.get(w.get("page"), [])
    if spec.get("widgets") or not w.get("rect") or not pl:
        return []
    near = candidate_captions(w["rect"], pl)
    heads = [h for h in (column_header(w["rect"], pl), row_header(w["rect"], pl)) if h]
    return near[:3] + heads


def page_witness(name: str, spec: dict, lines: dict, texts: list[str], names: Names) -> tuple[Optional[bool], str]:
    """Text fields: the name against the printed text at the widget. Option groups: each option's caption against
    the text at its own box (the group's name is a question the page prints once, elsewhere)."""
    if spec.get("widgets"):
        hits = misses = 0
        for w in _widgets(spec):
            cap = w.get("caption")
            pl = lines.get(w.get("page"), [])
            if not cap or not w.get("rect") or not pl:
                continue
            near = candidate_captions(w["rect"], pl)
            if not near:
                continue
            if _agrees(cap, near):
                hits += 1
            else:
                misses += 1
        if not hits and not misses:
            return None, ""
        return (misses == 0), f"option captions at their boxes: {hits} agree, {misses} do not"
    return _per_line(name, texts, names, owned_only=True) if texts else (None, "")


def _per_line(name: str, texts: list[str], names: Names, owned_only: bool = False) -> tuple[Optional[bool], str]:
    """One text at a time, not pooled: a pool of nearby lines holds the neighbours' captions too, and a neighbour
    then out-matches the field on its own caption. For when the name is the best match for any line. Against when
    the name matches no line and the first line with words is another field's (a better match); with
    `owned_only` False (the publisher's words, which are about this widget and nothing else) also when the name
    simply shares nothing with them. The page's nearby lines are often a line number or a neighbour's text, so
    sharing nothing with them says nothing (hand review of the 5500s: 119 accepted fields contested that way)."""
    shown = " | ".join(texts)[:140]
    verdicts = [names.judge(name, [t]) for t in texts]
    if any(v is True for v, _ in verdicts):
        return True, shown
    first = next(((v, why) for v, why in verdicts if v is not None), None)
    if first is None or (owned_only and not first[1]):
        return None, shown
    return False, " ; ".join(x for x in (shown, first[1]) if x)


# ------------------------------------------------------------------- classifier witnesses (class map)

def _box(spec: dict, by_page: dict[int, list[dict]]) -> Optional[dict]:
    w = _widgets(spec)
    w0 = w[0] if w else {}
    rect = w0.get("rect") or w0.get("box")
    return match_rect(rect, by_page.get(w0.get("page"), [])) if rect else None


def _verified(b: dict, spec: dict, lines: dict) -> Optional[bool]:
    """`field_chain`'s test without a case: is the classifier's caption printed at the widget?"""
    w = (_widgets(spec) or [{}])[0]
    pl = lines.get(w.get("page"), [])
    if not b.get("label") or not w.get("rect") or not pl:
        return None
    near = candidate_captions(w["rect"], pl)
    heads = [h for h in (column_header(w["rect"], pl), row_header(w["rect"], pl)) if h]
    if not near and not heads:
        return None
    return _agrees(b["label"], near) or _agrees(b["label"], heads)


def class_witness(name: str, spec: dict, by_page: dict[int, list[dict]], verified,
                  names: Names) -> tuple[Optional[bool], str]:
    """The classifier's class for the box against the field's type, and its caption against the name. Either one
    against -> against; for when one is for and neither against."""
    if verified is False:
        return None, "classifier caption is another box's"
    b = _box(spec, by_page)
    if b is None:
        return None, "no classifier box"
    page_cls = b.get("class")
    label = b.get("label") or ""
    if page_cls == "none":
        return False, f"page says nothing goes here ({label})".strip()
    cap, cap_why = names.judge(name, [label]) if label and not spec.get("widgets") else (None, "")
    bp_cls, _ = blueprint_class(name, spec)
    if page_cls == "other" or not label:
        cls = None
    elif page_cls in _CONTROL_CLASSES and (bp_cls in _CONTROL_CLASSES or spec.get("type") == "boolean"):
        cls = True
    elif bp_cls is None:
        cls = None
    else:
        cls = _family(page_cls) == _family(bp_cls)
    detail = f"{page_cls} vs {bp_cls or 'untyped'} ({label})" + (f" ; {cap_why}" if cap_why else "")
    if cls is False or cap is False:
        return False, detail
    return (True if (cls or cap) else None), detail


def grouping_witnesses(fields: dict, by_page: dict[int, list[dict]]) -> dict[str, tuple[bool, str]]:
    """Option structure, page against blueprint. The classifier groups option boxes that answer one question;
    a classifier group spread over several blueprint fields (5500 line 10a: five `_ind` checkboxes) or a blueprint
    option group spread over several classifier groups (5500-SF `return_type`: two questions in one field) is
    against. Only `against`: agreeing on structure says nothing about the names."""
    owner: dict[tuple, str] = {}          # (page, classifier group) -> fields whose option boxes sit in it
    members: dict[tuple, set] = collections.defaultdict(set)
    field_groups: dict[str, set] = collections.defaultdict(set)
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        for w in _widgets(spec):
            rect = w.get("rect") or w.get("box")
            b = match_rect(rect, by_page.get(w.get("page"), [])) if rect else None
            if b is None or not b.get("group") or b.get("class") not in _CONTROL_CLASSES:
                continue
            g = (b["page"], b["group"])
            members[g].add(name)
            field_groups[name].add(g)
    out: dict[str, tuple[bool, str]] = {}
    for g, names in members.items():
        if len(names) > 1:
            for n in names:
                others = sorted(names - {n})
                out[n] = (False, f"page reads {len(names)} fields as one question: {', '.join(others[:4])}")
    for n, gs in field_groups.items():
        if len(gs) > 1 and fields[n].get("widgets"):
            out.setdefault(n, (False, f"page reads this field's options as {len(gs)} questions"))
    return out


def class_map_boxes(blank: Optional[Path], run_dir: Optional[Path]) -> dict[int, list[dict]]:
    """The classifier's boxes by page: the run's class map, else the cached one for the blank (never a new call)."""
    boxes = None
    cp = run_dir / "case_001_intact" / "class_map.json" if run_dir else None
    if cp and cp.exists():
        boxes = json.loads(cp.read_text()).get("boxes")
    elif blank and blank.exists():
        cm = classify_form(blank, cache_only=True)
        boxes = (cm or {}).get("boxes")
    by_page: dict[int, list[dict]] = collections.defaultdict(list)
    for b in (boxes or {}).values():
        by_page[b["page"]].append(b)
    return by_page


ROW_TOL, ROW_GAP = 3.0, 220.0       # same row: centres within 3 pt, next box within 220 pt
COL_TOL, COL_GAP = 3.0, 30.0        # same column: left edges within 3 pt, next box within 30 pt


def lined_up_checkboxes(fields: dict) -> dict[str, tuple[bool, str]]:
    """Separate single-checkbox fields lined up in one row or column of the page: one question answered by
    several boxes, written as several booleans (Andrew's hand review of the 5500s, 2026-10-02: line 10a, the
    Form 5558 / automatic / special extension row, the four ADP-test boxes "should be one category widget").
    From the blueprint alone, no classifier: the finder misses half the 5500 boxes."""
    boxes = []
    for name, spec in fields.items():
        w = spec.get("widget") or {}
        if spec.get("widgets") or w.get("widget_type") not in ("checkbox", "radiobutton") or not w.get("rect"):
            continue
        boxes.append((name, w.get("page"), w["rect"]))

    order = {n: i for i, n in enumerate(fields)}

    def stem(n: str) -> str:
        """The name's question prefix: '10a' for 10a1_schedule_r_ind, 'gl' for gl_occur_ind."""
        return re.sub(r"\d+$", "", n.split("_")[0])
    parent = {n: n for n, _, _ in boxes}

    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n
    for i, (a, pa, ra) in enumerate(boxes):
        for b, pb, rb in boxes[i + 1:]:
            if pa != pb:
                continue
            same_row = (abs((ra[1] + ra[3]) - (rb[1] + rb[3])) / 2 <= ROW_TOL
                        and max(ra[0], rb[0]) - min(ra[2], rb[2]) <= ROW_GAP)
            # a column links only within one question: ACORD 25's coverage grid stacks gl_, auto_ and umbrella_
            # checkboxes in one column, 20 boxes that answer five questions. One question = one name prefix
            # (10a1_, 10a2_), or neighbours in the blueprint's order (5500-SF's four ADP-test boxes)
            same_col = (abs(ra[0] - rb[0]) <= COL_TOL
                        and (stem(a) == stem(b) or abs(order[a] - order[b]) == 1)
                        and max(ra[1], rb[1]) - min(ra[3], rb[3]) <= COL_GAP)
            if same_row or same_col:
                parent[root(a)] = root(b)
    runs = collections.defaultdict(list)
    for n, _, _ in boxes:
        runs[root(n)].append(n)
    out = {}
    for members in runs.values():
        if len(members) > 1:
            for n in members:
                others = [m for m in members if m != n]
                out[n] = (False, f"{len(members)} separate checkboxes lined up: {', '.join(others[:4])}")
    return out


def run_for(bpt_path: Path, bp: dict) -> Optional[Path]:
    """The run that last validated this blueprint: the side copy's loop record, else the form's latest run."""
    stem = bpt_path.stem
    for loop in (RUNS / "judge_eval" / f"{stem}_loop2.json", RUNS / "judge_eval" / f"{stem}_loop.json"):
        if loop.exists():
            try:
                its = [it for it in json.loads(loop.read_text()).get("iterations", []) if it.get("run")]
            except Exception:
                its = []
            for it in reversed(its):
                d = RUNS / it["run"]
                if (d / "case_001_intact").exists():
                    return d
    run = (bp.get("x_petey_build") or {}).get("run")
    if run and (RUNS / run / "case_001_intact").exists():
        return RUNS / run
    dirs = sorted(d for d in RUNS.glob(f"{stem}_2*") if (d / "case_001_intact" / "class_map.json").exists())
    return dirs[-1] if dirs else None


def _judge_rows(case_dir: Path) -> dict[str, dict]:
    for p in sorted(case_dir.glob("score_judge*.json")):
        try:
            return {r["field"]: r for r in json.loads(p.read_text()).get("per_field", [])}
        except Exception:
            continue
    return {}


def run_witnesses(run_dir: Path, blank: Optional[Path]) -> dict[str, dict]:
    """`{field key: {judge, classifier, structure, verified, run_name}}` from one run, keyed by widget path."""
    rbp = _load(run_dir / "blueprint.bpt") if (run_dir / "blueprint.bpt").exists() else {}
    fields = rbp.get("fields") or {}
    out: dict[str, dict] = {}
    cases = sorted(d for d in run_dir.glob("case_*_intact") if d.is_dir())
    judge: dict[str, list[int]] = collections.defaultdict(list)
    chains = {}
    structure: dict[str, set] = collections.defaultdict(set)
    for case in cases:
        chain = field_chain(rbp, case, blank)
        chains.setdefault("first", chain)
        rows = _judge_rows(case)
        for name in fields:
            r = rows.get(name)
            if not r or chain.get(name, {}).get("stage") != "value":
                continue
            gt = r.get("gt_value")
            if gt in (None, "", [], False):
                continue
            if r.get("verdict") == "agree":
                judge[name].append(1)
            elif r.get("verdict") in ("differ", "extract_miss"):
                judge[name].append(-1)
        inv = case / "inventory_check.json"
        if inv.exists():
            for row in json.loads(inv.read_text()).get("rows", []):
                if row.get("class") in STRUCTURE_AGAINST and row.get("field"):
                    structure[row["field"]].add(row["class"])
    chain = chains.get("first", {})
    for name, spec in fields.items():
        if not isinstance(spec, dict):
            continue
        rec: dict = {"run_name": name, "stage": chain.get(name, {}).get("stage")}
        votes = judge.get(name, [])
        if votes:
            good, bad = votes.count(1), votes.count(-1)
            rec["judge"] = (bad == 0, f"{good}/{len(votes)} filled cases read back by name")
        if structure.get(name):
            rec["structure"] = (False, ", ".join(sorted(structure[name])))
        out[_key(spec)] = rec
    return out


# ------------------------------------------------------------------- per field

def page_check_witness(v: dict) -> tuple[Optional[bool], str]:
    if v.get("verdict") == "accept":
        return True, "page check: fits the page"
    prop = " ".join(x for x in (v.get("proposed_name"), v.get("proposed_type")) if x)
    return False, (f"page check {v.get('problem')}: {v.get('reason') or ''}"
                   + (f" (would be: {prop})" if prop else ""))


def tier(ws: dict[str, tuple]) -> str:
    votes = [v for v, _ in ws.values() if v is not None]
    if any(v is False for v in votes):
        return "contested"
    n = sum(1 for v in votes if v)
    return "settled" if n >= 2 else ("single" if n == 1 else "unknown")


def witnesses(bpt_path: Path, run_dir: Optional[Path] = None, *, use_run: bool = True,
              judge: bool = True) -> dict:
    """`{"run": run name or None, "fields": {name: {"tier", "witnesses": {witness: [verdict, detail]}}}}`.
    `judge` False skips the run's judge and inventory witnesses (the run's class map is still read)."""
    bpt_path = Path(bpt_path)
    bp = _load(bpt_path)
    blank = resolve_blank(bp)
    words = publisher_words(blank) if blank and blank.exists() else {}
    lines = _page_lines(str(blank)) if blank and blank.exists() else {}
    if use_run and run_dir is None:
        run_dir = run_for(bpt_path, bp)
    by_key = run_witnesses(run_dir, blank) if use_run and judge and run_dir else {}
    fields = {n: s for n, s in (bp.get("fields") or {}).items() if isinstance(s, dict)}
    by_page = class_map_boxes(blank, run_dir)
    from petey.validate.page_check import verdicts as page_check_verdicts
    checked = page_check_verdicts(bp)
    grouping = {**lined_up_checkboxes(fields), **(grouping_witnesses(fields, by_page) if by_page else {})}
    # each witness's own text per field, so 'belongs to another field' compares like with like
    pub = {n: publisher_texts(s, words) for n, s in fields.items()}
    printed = {n: page_texts(s, lines) for n, s in fields.items()}
    boxes = {n: _box(s, by_page) if by_page else None for n, s in fields.items()}
    by_witness = {}
    for k, texts in (("publisher", pub), ("page", printed),
                     ("classifier", {n: [b["label"]] if b and b.get("label") else [] for n, b in boxes.items()})):
        by_witness[k] = Names(fields)
        by_witness[k].set_own(texts)
    out = {}
    for name, spec in fields.items():
        ws: dict[str, tuple] = {"publisher": _per_line(name, pub[name], by_witness["publisher"]),
                                "page": page_witness(name, spec, lines, printed[name], by_witness["page"])}
        if by_page:
            b = boxes[name]
            ws["classifier"] = class_witness(name, spec, by_page, _verified(b, spec, lines) if b else None,
                                             by_witness["classifier"])
        r = by_key.get(_key(spec), {})
        same_name = r.get("run_name") == name
        if "judge" in r and same_name:
            ws["judge"] = r["judge"]
        if "structure" in r:
            ws["structure"] = r["structure"]
        elif name in grouping:
            ws["structure"] = grouping[name]
        adj = spec.get("x_petey_adjudication") or {}
        if adj.get("verdict") in ("current", "proposed"):
            ws["adjudicator"] = (True, adj.get("reason") or "")
        elif adj.get("verdict") == "unclear":
            ws["adjudicator"] = (False, adj.get("reason") or "")
        pc = checked.get(name)
        if pc:
            ws["page_check"] = page_check_witness(pc)
        ws = {k: v for k, v in ws.items() if v[0] is not None or v[1]}
        out[name] = {"tier": tier(ws), "stage": r.get("stage") if same_name else None,
                     "witnesses": {k: [v[0], v[1]] for k, v in ws.items()}}
    return {"blueprint": str(bpt_path), "run": run_dir.name if run_dir else None, "fields": out}


# ------------------------------------------------------------------- the loop's view

_FLAG_SOURCE = {"publisher": "the publisher's tooltip / XFA caption for this widget",
                "page": "the caption printed at this widget",
                "classifier": "the page classifier's caption for this box"}


PAGE_CHECK_TO_REVIEWER = ("wrong_name", "wrong_type")     # what the reviewer can answer; not_a_field, should_group,
                                                          # options stay with the hand-review page


def against_flags(run_dir: Path) -> dict[str, list[dict]]:
    """Reviewer flags from the witnesses, for the loop (`review.flags_from_run`): a text that belongs to another
    field (a swap, a widget placed one row off), the one text-witness signal a rename can answer, and the page
    check's wrong_name / wrong_type flags (2026-10-06). Witnesses
    that merely share nothing with the name, the classifier's 'nothing goes here' and checkbox runs stay with
    the hand-review page: the reviewer cannot delete or merge fields. Read from the blank and the run's class
    map, not from the case, so a box- or class-stage field is flagged too; a rename on a flagged field always
    goes to the adjudicator (`contested_fields`), since the loop's before/after is blind to these signals."""
    bp_path = run_dir / "blueprint.bpt"
    if not bp_path.exists():
        return {}
    res = witnesses(bp_path, run_dir, judge=False)
    flags: dict[str, list[dict]] = {}
    from petey.validate.page_check import verdicts as page_check_verdicts
    checked = page_check_verdicts(_load(bp_path))
    for name, f in res["fields"].items():
        pc = checked.get(name)
        if pc and pc.get("verdict") == "flag" and pc.get("problem") in PAGE_CHECK_TO_REVIEWER:
            prop = {k: pc[k] for k in ("proposed_name", "proposed_type") if pc.get(k)}
            flags.setdefault(name, []).append({
                "detector": "page_check",
                "detail": f"a vision check of the whole page ({pc['problem']}): {pc.get('reason') or ''}",
                "text": pc.get("box_holds") or "", **({"page_check_proposes": prop} if prop else {})})
        for k, (v, detail) in f["witnesses"].items():
            if v is not False or k not in _FLAG_SOURCE or "belongs to: " not in (detail or ""):
                continue
            text, other = re.match(r"(.*?)(?: ; )?belongs to: (\S+)$", detail).groups()
            flags.setdefault(name, []).append({
                "detector": "witness",
                "detail": f"{_FLAG_SOURCE[k]} describes the field `{other}` better than this name, and better "
                          f"than `{other}`'s own text does",
                "text": text})
    return flags


def contested_fields(flags: dict[str, list[dict]]) -> dict[str, str]:
    """`{field: why}` for `adjudicate.adjudicate_decisions`: witness-flagged fields whose renames need the page."""
    out = {}
    for f, fl in flags.items():
        if any(x.get("detector") == "witness" for x in fl):
            out[f] = "a witness says this widget's text belongs to another field"
        elif any(x.get("detector") == "page_check" for x in fl):
            out[f] = "the page check says the name or type does not fit the box"
    return out


# ------------------------------------------------------------------- calibration against hand review

def calibrate(use_run: bool = True) -> dict:
    """Per tier: fields a person accepted / flagged, over every blueprint with hand-review verdicts."""
    table = collections.defaultdict(collections.Counter)
    flags = []
    for vp in sorted((RUNS / "hand_review").glob("*.json")):
        v = json.loads(vp.read_text())
        bpt = Path(v["blueprint"])
        if not bpt.exists():
            continue
        res = witnesses(bpt, use_run=use_run)
        for name, rec in (v.get("verdicts") or {}).items():
            f = res["fields"].get(name)
            if f is None:
                continue
            table[f["tier"]][rec["verdict"]] += 1
            if rec["verdict"] == "flag":
                flags.append({"form": bpt.stem, "field": name, "tier": f["tier"], "note": rec.get("note"),
                              "witnesses": f["witnesses"]})
    return {"tiers": {t: dict(table[t]) for t in TIERS if t in table}, "flags": flags}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bpt", nargs="?")
    ap.add_argument("--run", help="run dir (default: the blueprint's last loop run, else the form's latest run)")
    ap.add_argument("--no-run", action="store_true", help="publisher and page witnesses only")
    ap.add_argument("--show", action="store_true", help="every field with its witnesses")
    ap.add_argument("--calibrate", action="store_true")
    args = ap.parse_args()
    if args.calibrate:
        c = calibrate(use_run=not args.no_run)
        print(f"{'tier':10} {'accept':>7} {'flag':>5}")
        for t, n in c["tiers"].items():
            print(f"{t:10} {n.get('accept', 0):>7} {n.get('flag', 0):>5}")
        for f in c["flags"]:
            print(f"\n  {f['form']}  {f['field']}  [{f['tier']}]  note: {f['note']}")
            for k, (v, d) in f["witnesses"].items():
                print(f"      {k:11} {str(v):5}  {d[:110]}")
        return 0
    if not args.bpt:
        ap.error("a blueprint path, or --calibrate")
    res = witnesses(Path(args.bpt), Path(args.run) if args.run else None, use_run=not args.no_run)
    counts = collections.Counter(f["tier"] for f in res["fields"].values())
    print(f"{res['blueprint']}  run: {res['run']}")
    print("  " + "  ".join(f"{t} {counts.get(t, 0)}" for t in TIERS))
    if args.show:
        for t in TIERS:
            for name, f in res["fields"].items():
                if f["tier"] != t:
                    continue
                print(f"\n  [{t}] {name}")
                for k, (v, d) in f["witnesses"].items():
                    print(f"      {k:11} {str(v):5}  {d[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
