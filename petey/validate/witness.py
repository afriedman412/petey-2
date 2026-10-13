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

"Belongs to another field" is contrastive: another name is explained better by the text than this one, and
better than by that field's own text. Words count by how rare they are among the form's names, and a fit is the
harmonic mean of the share of the name the text explains and the share of the text the name explains (`Names`).
That is the signature of a swap or a widget placed one row off (5500-SF's day/month, ACORD 25's phone names on the
state and ZIP boxes), so since 2026-10-09 the other field must be near (within an inch), in the same section (same
XFA subform, no heavier-than-usual rule between the two), better by a margin, and the text must be one only this
field carries; a neighbour a tooltip merely mentions ('mailing address' in a ZIP tooltip) does not qualify.
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
import functools
import json
import math
import os
import re
import string
from pathlib import Path
from typing import Optional

import pymupdf
import snowballstemmer
import yaml

from petey.label import text_match
from petey.label import xfa as xfa_mod
from petey.paths import RUNS
from petey.synth.boxes import match_rect, widget_key
from petey.synth.classify import classify_form
from petey.validate.class_check import _CONTROL_CLASSES, _family, blueprint_class
from petey.validate.field_chain import _agrees, _page_lines, candidate_captions, column_header, field_chain, \
    row_header
from petey.validate.name_caption import _ABBR, _STOP, tokens
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
    """A field's identity across renames: its widget path (an option group: its option paths and on-states); on a
    flat blueprint, where no widget has a path, its page and rect (`boxes.widget_key`)."""
    if spec.get("widgets"):
        return "group:" + "|".join(sorted(f"{widget_key(w)}#{k}" for k, w in spec["widgets"].items()))
    w = spec.get("widget") or {}
    return f"{w.get('page')}:{widget_key(w)}"


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
    """Words for matching a name against a text: abbreviations written out (`name_caption._ABBR`, `_EXPAND`),
    filler dropped, the rest Snowball-stemmed ('addresses' ~ 'address'). Until 2026-10-09 every word was cut to
    five letters, which joined employer / employee, international / interest / internal, state / statement."""
    out: set[str] = set()
    for t in re.findall(r"[a-z]+", (s or "").lower()):
        for w in _EXPAND_WORDS.get(t, ()):
            out.add(_stem(w))
        t = _MORE_ABBR.get(t, _ABBR.get(t, t))
        if t and t not in _STOP and len(t) > 1:
            out.add(_stem(t))
    return out


_MORE_ABBR = {"nbr": "number"}     # slugs the labeler writes that `name_caption._ABBR` lacks
# a name token that stands for several caption words, in whole words (name_caption._EXPAND has five-letter stems)
_EXPAND_WORDS = {"ssn": ("social", "security"), "ein": ("employer", "identification"),
                 "fein": ("employer", "identification"), "dob": ("birth",), "zip": ("postal",),
                 "tel": ("phone", "telephone"), "ptin": ("preparer",)}


@functools.lru_cache(maxsize=None)
def _stem(w: str) -> str:
    """Snowball by default. PETEY_STEM=plural strips plurals only ('addresses' ~ 'address', 'insured' stays apart
    from 'insurer', which Snowball joins); PETEY_STEM=none keeps words as they are (a test, 2026-10-12)."""
    mode = os.environ.get("PETEY_STEM", "snowball")
    if mode == "none":
        return w
    if mode == "plural":
        if len(w) > 4 and w.endswith("ies"):
            return w[:-3] + "y"
        if len(w) > 4 and w.endswith(("ses", "xes", "zes", "ches", "shes")):
            return w[:-2]
        if len(w) > 3 and w.endswith("s") and not w.endswith(("ss", "us", "is")):
            return w[:-1]
        return w
    return _STEMMER.stemWord(w)


_STEMMER = snowballstemmer.stemmer("english")


def _same_text(t: str) -> str:
    """The text's exact words, for 'several fields carry the same text': case and punctuation aside, word for word
    (no stemming: within one form a repeated tooltip is repeated exactly)."""
    return " ".join(re.findall(r"[a-z0-9]+", (t or "").lower()))


class Names:
    """The form's field names as token sets, for contrastive matching: a name is evidence for a text only when it
    matches that text better than the other names on its page do, and a word counts by how rare it is among the
    form's names ('plan' on Form 5500 says nothing; 'month' against 'day' says everything)."""

    def __init__(self, fields: dict, boundaries: Optional[dict[int, list[float]]] = None,
                 model: Optional[bool] = None) -> None:
        self.model = use_model() if model is None else model    # `text_match` scores the texts (2026-10-09)
        self.toks = {n: _toks(n) for n in fields}
        self.page = {n: (_widgets(s)[0].get("page") if _widgets(s) else None) for n, s in fields.items()}
        self.rect = {n: _field_rect(s) for n, s in fields.items()}
        self.parent = {n: _xfa_parent((_widgets(s)[0].get("path") if _widgets(s) else None) or "")
                       for n, s in fields.items()}
        self.boundaries = boundaries or {}  # page -> y of the section rules on it (`section_rules`)
        df = collections.Counter(t for ts in self.toks.values() for t in ts)
        n = max(len(self.toks), 1)
        self.idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
        self._unseen = math.log((n + 1) / 0.5)     # a text word no name uses: as rare as a word can be
        self.own: dict[str, float] = {}     # how well each field's own text (of this witness) explains its name
        self.own_fit: dict[str, float] = {}
        self.shared: set[str] = set()     # texts several fields carry word for word: they cannot tell those apart

    def set_own(self, texts_by_field: dict[str, list[str]]) -> None:
        self.own_texts = texts_by_field
        self._own_model: dict[str, float] = {}
        self.own = {n: max((self.score(n, _toks(t)) for t in ts), default=0.0) for n, ts in texts_by_field.items()}
        self.own_fit = {n: max((self.fit(n, _toks(t)) for t in ts), default=0.0) for n, ts in texts_by_field.items()}
        carriers = collections.Counter(_same_text(t) for ts in texts_by_field.values() for t in set(ts))
        self.shared = {t for t, c in carriers.items() if c > 1 and t}

    def score(self, name: str, tt: set[str]) -> float:
        """How much of the name the text explains: matched weight over the name's weight. Raw overlap favours
        long names against long tooltips (ACORD 25: 'producer's contact person's phone number ... area code'
        out-matched `contact_phone_nbr` with `producer_phone_area_cd`)."""
        mine = self.toks.get(name, set())
        total = sum(self.idf.get(t, 0.0) for t in mine)
        return sum(self.idf.get(t, 0.0) for t in mine & tt) / total if total > 0 else 0.0

    def fit(self, name: str, tt: set[str]) -> float:
        """The name's share of the text and the text's share of the name, together (their harmonic mean): with the
        name's share alone a short name beats a specific one ('Retirement account name': `retirement_account_amt`
        0.86 over `retirement_account_institution_name` 0.76, 'institution' being rare and unmatched)."""
        p = self.score(name, tt)
        total = sum(self.idf.get(t, self._unseen) for t in tt)
        r = sum(self.idf.get(t, 0.0) for t in self.toks.get(name, set()) & tt) / total if total > 0 else 0.0
        return 2 * p * r / (p + r) if p + r > 0 else 0.0

    def rivals(self, name: str) -> list[str]:
        """The fields a swap or a one-row slip could involve: same page, within `_REACH` of the field, and not
        across a section boundary (a different XFA subform, or a section rule between the two)."""
        page, r = self.page.get(name), self.rect.get(name)
        out = []
        for other in self.toks:
            if other == name or self.page.get(other) != page:
                continue
            o = self.rect.get(other)
            if r is None or o is None or _gap(r, o) > _REACH:
                continue
            if self.parent.get(name) and self.parent.get(other) and self.parent[name] != self.parent[other]:
                continue
            if any(min(r[1], o[1]) < y < max(r[3], o[3]) and not (r[1] < y < r[3] or o[1] < y < o[3])
                   for y in self.boundaries.get(page, [])):
                continue
            out.append(other)
        return out

    def judge(self, name: str, texts: list[str]) -> tuple[Optional[bool], str]:
        """True: the text explains the name; False: the text has words and the name shares none of them, or the
        text belongs to a nearby field more than to this one and more than that field's own text does (a swap, a
        widget placed one row off: 5500-SF's day box carries 'Enter month of waiver letter'); None: nothing to
        compare. A neighbour the text merely mentions ('mailing address' in a ZIP tooltip) is not enough: its own
        text explains it at least as well. Belonging takes a clear margin (`_MARGIN`: ACORD 140 `1_25` lost 0.489
        to 0.488 on 'coverages' and 'other'), a rival near the box (`rivals`), and a text only this field carries.
        The detail names the field the text belongs to."""
        tt = set().union(*(_toks(t) for t in texts)) if texts else set()
        if not tt:
            return None, ""
        rules = self._judge_rules(name, texts, tt)
        if not self.model:
            return rules
        model = self._judge_model(name, texts, tt)
        # both read the text; the model reads meaning (STREET ~ address line), the rules shared words. Either one's
        # 'belongs to' counts, then the model's 'does not describe'; either one's match is a match (2026-10-09)
        for v in (model, rules):
            if v[0] is False and v[1].startswith("belongs to"):
                return v
        if model[0] is False:
            return model
        if True in (model[0], rules[0]):
            return True, ""
        return rules if rules[0] is not None else model

    def _judge_rules(self, name: str, texts: list[str], tt: set[str]) -> tuple[Optional[bool], str]:
        if self.score(name, tt) <= 0:
            return False, ""
        if _same_text(" ".join(texts)) in self.shared:
            return True, ""
        mine = self.fit(name, tt)
        best, who = mine + _MARGIN, None
        for other in self.rivals(name):
            s = self.fit(other, tt)
            if s > best and s > self.own_fit.get(other, 0.0) + _MARGIN:
                best, who = s, other
        return (False, f"belongs to: {who}") if who else (True, "")

    def _own_score(self, field: str) -> float:
        """How well the field's own texts (of this witness) describe it, by the model; cached."""
        if field not in self._own_model:
            ts = [t for t in (self.own_texts.get(field) or []) if t]
            got = text_match.score_pairs([(t, text_match.name_words(field, text=t)) for t in ts]) if ts else []
            self._own_model[field] = max(got or [0.0])
        return self._own_model[field]

    def _judge_model(self, name: str, texts: list[str], tt: set[str]) -> tuple[Optional[bool], str]:
        """`judge` with `text_match` as the scorer: the same verdicts, read off P(text describes field). The text
        does not describe the name (below `_LOW`) -> False 'does not describe'; a rival it describes better by
        `_MARGIN_M`, and better than the rival's own text does -> False 'belongs to'. Rivals and the shared-text
        rule as in the rules."""
        text = " | ".join(texts)
        shared = _same_text(text) in self.shared   # a text several fields carry names none of them: no verdict
        rivals = [] if shared else self.rivals(name)
        got = text_match.score_pairs([(text, text_match.name_words(n, text=text)) for n in [name] + rivals])
        mine, theirs = got[0], dict(zip(rivals, got[1:]))
        best, who = mine + _MARGIN_M, None
        for other, s in theirs.items():
            if s > best and s > self._own_score(other) + 0.05:
                best, who = s, other
        if who:
            return False, f"belongs to: {who}"
        if mine < _LOW:
            return (None, "") if shared else (False, f"does not describe ({mine:.2f})")
        return True, ""


def prefetch_scores(fields: dict, by_witness: dict[str, "Names"]) -> int:
    """Score every (text, name) pair the witnesses will ask about in one pass, so `_judge_model` reads them from
    `text_match`'s cache instead of asking field by field (ACORD 125: 2,359 calls for 4,907 pairs). The same pairs
    `_judge_model` builds: each text of a field against its own name and its rivals' (none for a shared text). Page
    and classifier texts are only judged for text fields. Measured 2026-10-10: barely faster, since the cost is per
    pair (dense forms with long tooltips hit the 96-token cap: I-130 4,610 pairs, ~12 s); the speed lever is the
    int8 model (`text_match`, PETEY_TEXT_MATCH_INT8). Returns the number of pairs."""
    pairs = []
    for k, nm in by_witness.items():
        for name, spec in fields.items():
            if k != "publisher" and spec.get("widgets"):
                continue
            for t in nm.own_texts.get(name) or []:
                if not t or not _toks(t):
                    continue
                rivals = [] if _same_text(t) in nm.shared else nm.rivals(name)
                pairs += [(t, text_match.name_words(n, text=t)) for n in [name] + rivals]
    pairs = list(dict.fromkeys(pairs))
    text_match.score_pairs(pairs)
    return len(pairs)


_LOW = 0.01        # model: below this the text does not describe the name (0.2 flagged 286 looked-at accepts)
_MARGIN_M = 0.3    # model: how much better another field must be described


def use_model() -> bool:
    """Score texts with `text_match` as well as the rules when its model file is there (models/text_match), unless
    PETEY_TEXT_MATCH=0."""
    import os
    return os.environ.get("PETEY_TEXT_MATCH", "1") != "0" and text_match.available()


def printed_agrees(texts: list[str], printed: list[str]) -> bool:
    """Andrew's check (2026-10-09): the publisher's text is about this box when it shares two thirds of its words
    (of the shorter) with a line printed at the box. A flag built on a text the page does not echo is a hint: the
    tooltip may be a copy-paste from another box. On the 21 hand-flagged name errors: false alarms on looked-at
    fields 57 -> 22, real errors caught 16 -> 15."""
    return any(_agreement(t, line) >= _AGREE for t in texts for line in printed)


def _agreement(a: str, b: str) -> float:
    """The share of the shorter text's words the other one has: the same word (`_toks`: abbreviations written out,
    stemmed), or one an abbreviation of the other (`text_match.abbreviates`: the printed header 'ADDL INSD' ~ the
    tooltip's 'additional insured'; 2026-10-12, before which ACORD 25's ADDL INSD flags were all demoted). Each
    word of the longer text answers for one word only."""
    wa, wb = (list(dict.fromkeys(w for w in re.findall(r"[a-z]+", (x or "").lower()) if _toks(w)))
              for x in (a, b))
    if len(wa) > len(wb):
        wa, wb = wb, wa
    if not wa:
        return 0.0
    left, hit = list(wb), 0
    for w in wa:
        for i, v in enumerate(left):
            if _toks(w) & _toks(v) or text_match.abbreviates(w, v) or text_match.abbreviates(v, w):
                hit += 1
                del left[i]
                break
    return hit / len(wa)


_AGREE = 2 / 3


_REACH = 72.0      # pt between two boxes a swap or a one-row slip can span (one inch)
_MARGIN = 0.10     # how much better another field's fit must be


def _field_rect(spec: dict) -> Optional[tuple]:
    """The field's box on its first page; an option group: the span of its options there."""
    ws = [w for w in _widgets(spec) if w.get("rect")]
    if not ws:
        return None
    page = ws[0].get("page")
    rs = [w["rect"] for w in ws if w.get("page") == page]
    return (min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs))


def _gap(a, b) -> float:
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def _xfa_parent(path: str) -> str:
    """The XFA subform a widget sits in (`form1[0].#subform[7].Pt8Line1B1f_TiterOne[0]` -> `form1[0].#subform[7]`);
    '' for a plain AcroForm name."""
    return path.rsplit(".", 1)[0] if "[" in path and "." in path else ""


def section_rules(blank: Path) -> dict[int, list[float]]:
    """`{page: [y]}`: the lines a form draws between sections: horizontal, across a good part of the page, and
    heavier than the page's usual line (ACORD 140: 0.96 / 0.72 section, 0.48 row, 0.24 cell; docs/TODO.md,
    "Ruled-line weight"). A page drawn in one weight has none, and only distance limits its rivals. A filled
    bar (a section header's black band) counts as heavy."""
    out: dict[int, list[float]] = {}
    doc = pymupdf.open(str(blank))
    try:
        for page in doc:
            width = page.rect.width
            lines = []                       # (y, length, weight)
            for d in page.get_drawings():
                for it in d.get("items", []):
                    if it[0] == "l":
                        p, q = it[1], it[2]
                        if abs(p.y - q.y) < 1:
                            lines.append((p.y, abs(q.x - p.x), d.get("width") or 0.0))
                    elif it[0] == "re":
                        r = it[1]
                        if r.height < 4 and r.width > 2 * r.height:
                            lines.append(((r.y0 + r.y1) / 2, r.width, max(r.height, d.get("width") or 0.0)))
            if not lines:
                continue
            weights = collections.Counter(round(w, 2) for _, ln, w in lines if w > 0)
            usual = weights.most_common(1)[0][0] if weights else 0.0
            ys = {round(y, 1) for y, ln, w in lines
                  if ln >= _RULE_SHARE * width and usual > 0 and w >= _HEAVIER * usual}
            if ys:
                out[page.number + 1] = sorted(ys)
    finally:
        doc.close()
    return out


_RULE_SHARE = 0.4      # of the page's width
_HEAVIER = 1.5         # times the page's most common line weight


def publisher_texts(spec: dict, words: dict[str, list[str]]) -> list[str]:
    """The publisher's words for the widget; with the model and no tooltip, its readable path ('City': 1014r puts
    the box's meaning only there). Only then: any text that fits the name counts for it, so a path next to a
    tooltip would outvote the tooltip (I-130 'Pt3Line5 Eye Color' kept `eye_color_green_ind` on the Hazel box)."""
    w = _widgets(spec)
    path = (w[0] if w else {}).get("path") or ""
    out = list(words.get(path, []))
    if not out and use_model():
        pw = text_match.path_words(path)
        if pw:
            out.append(pw)
    return out


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
    if first is None or (owned_only and not first[1].startswith("belongs to")):
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

PAGE_CHECK_SUGGESTIONS = ("options", "should_group", "not_a_field", "continues")   # 2026-10-07: rules and captions, not errors


def page_check_witness(v: dict) -> tuple[Optional[bool], str]:
    """Accept -> for. A wrong name / type / other -> against. Option captions, grouping and "not a field" are
    suggestions (Andrew, 2026-10-07: most flagged fields were right; these depend on his rules or are cosmetic):
    shown, but silent in the tier."""
    if v.get("verdict") == "accept":
        return True, "page check: fits the page"
    prop = " ".join(x for x in (v.get("proposed_name"), v.get("proposed_type")) if x)
    text = f"page check {v.get('problem')}: {v.get('reason') or ''}" + (f" (would be: {prop})" if prop else "")
    if v.get("problem") in PAGE_CHECK_SUGGESTIONS:
        return None, "suggestion; " + text
    return False, text


_WITNESS_TEXT = {"publisher": "The publisher's tooltip", "page": "The caption printed at the box",
                 "classifier": "The page classifier's caption"}


def _first_sentence(t: str, n: int = 150) -> str:
    t = re.split(r"(?<=[.;])\s", (t or "").strip(), maxsplit=1)[0]
    return t if len(t) <= n else t[:n - 1] + "…"


# the captions a page-check reason states for its option boxes, read straight out of the sentence (Andrew, 2026-10-07:
# "it has the answers right there"): `27.a is "Flr."`, `179.c ... is printed as "RECONSTRUCTION"`, `39.d sits beside the
# printed caption "ISSUE POLICY"`. Only forms that state the right caption; a sentence quoting the wrong one first
# ("has the caption 'X' instead of 'Y'") is read by its "printed label" half or not at all
_Q = r"[\"“”]([^\"“”]{1,80})[\"“”]|['‘’]([^'‘’]{1,80})['‘’](?![A-Za-z])"
_CAP_STATED = [re.compile(r"\b\d+\.([a-z]{1,2})\b(?:'s)?\s+(?:caption\s+)?(?:is printed as|should be|should read|is)\s*(?:" + _Q + ")", re.I),
               re.compile(r"\b\d+\.([a-z]{1,2})\b[^.;]{0,60}?\bprinted (?:caption|label|text)(?: [a-z ]{0,25}?)?\s*(?:is\s*)?(?:" + _Q + ")", re.I)]


def stated_captions(spec: dict, reason: str) -> dict[str, dict]:
    """{option key: {"caption": ...}} for the boxes the reason names a caption for; letters follow the page check's
    order of the field's boxes (`page_check.boxes`)."""
    keys = [k for k, w in (spec.get("widgets") or {}).items() if w.get("rect") and w.get("page")]
    letters = {(string.ascii_lowercase[j] if j < 26 else string.ascii_lowercase[j // 26 - 1] + string.ascii_lowercase[j % 26]): k
               for j, k in enumerate(keys)}
    out = {}
    for rx in _CAP_STATED:
        for m in rx.finditer(reason or ""):
            k, cap = letters.get(m.group(1).lower()), (m.group(2) or m.group(3) or "").strip()
            if k and cap and k not in out:
                out[k] = {"caption": cap}
    return out


_PAGE_CTX: dict[str, tuple] = {}


def caption_suggestion(name: str, spec: dict, blank: Optional[Path], words: dict) -> Optional[dict]:
    """The caption chooser's proposals for an option group, as a review-page suggestion with a fix the 'use' button
    applies (`caption_choice.choose`: printed text around each box, judged by `text_match`; XFA and hand captions
    are never touched). None for a text field, without the model, or when it proposes nothing."""
    from petey.label import caption_choice
    if not spec.get("widgets") or not blank or not blank.exists() or not use_model():
        return None
    key = str(blank)
    if key not in _PAGE_CTX:
        _PAGE_CTX.clear()                          # one blank at a time
        _PAGE_CTX[key] = caption_choice.page_context(blank)
    page_words, page_lines = _PAGE_CTX[key]
    res = caption_choice.choose(name, spec, page_words, page_lines, words)
    props = {k: r for k, r in res.items() if r["propose"]}
    if not props:
        return None
    text = ", ".join(f"{(r['current'] or '(none)')[:30]!s} -> {r['best']}" for r in props.values())
    return {"kind": "suggestion", "text": f"Captions from the page: {text}",
            "fix": {"options": {k: {"caption": r["best"]} for k, r in props.items()}}}


def explain(name: str, spec: dict, ws: dict[str, tuple], pc: Optional[dict]) -> list[dict]:
    """One plain sentence per reason the field is questioned, for the review page (Andrew, 2026-10-07: the
    individual checks' output is opaque). [{"kind": "error" | "suggestion", "text"}], errors first."""
    out = []
    if pc and pc.get("verdict") == "flag":
        p, holds = pc.get("problem"), (pc.get("box_holds") or "").strip()
        pn, pt = pc.get("proposed_name"), pc.get("proposed_type")
        typ = "/".join(x for x in (spec.get("type"), spec.get("semantic_type")) if x)
        clean_name = pn if pn and re.fullmatch(r"[a-z0-9][a-z0-9_]*", pn) and pn != name else None
        clean_type = next((t for t in ("string", "number", "integer", "date", "boolean", "category")
                           if pt and re.match(rf"\s*{t}\b", pt)), None)
        if p == "wrong_name":
            t = (f"Name: the box holds {holds!r}, not what `{name}` says." if holds else
                 f"Name: {_first_sentence(pc.get('reason'))}")
            if pn and pn != name:
                t += f" Suggested: `{pn}`."
            out.append({"kind": "error", "text": t, **({"fix": {"name": clean_name}} if clean_name else {})})
        elif p == "wrong_type":
            # the page check's reason says why; "the box holds ..." often only restates the caption (Andrew,
            # 2026-10-07, DV-100 6_32: "the number or amount for row (4)")
            t = (f"Type: {_first_sentence(pc.get('reason'))} (it is {typ})" if pc.get("reason") else
                 f"Type: the box holds {holds!r}, which does not fit {typ}.")
            if pt:
                t += f" Suggested: {pt}."
            out.append({"kind": "error", "text": t,
                        **({"fix": {"type": clean_type}} if clean_type and clean_type != spec.get("type") else {})})
        elif p == "options":
            caps = stated_captions(spec, pc.get("reason") or "")
            out.append({"kind": "suggestion", "text": f"Option captions: {_first_sentence(pc.get('reason'))}",
                        **({"fix": {"options": caps}} if caps else {})})
        elif p == "should_group":
            out.append({"kind": "suggestion", "text": f"Could be one group: {_first_sentence(pc.get('reason'))}"})
        elif p == "not_a_field":
            out.append({"kind": "suggestion", "text": f"Maybe not a field: {_first_sentence(pc.get('reason'))}"})
        elif p == "continues":               # merged in Groups (text combining); Andrew, 2026-10-07
            into = f" `{pn}`" if pn else " another field"
            out.append({"kind": "suggestion", "text": f"Continues{into}; combine the two: "
                                                      f"{_first_sentence(pc.get('reason'))}"})
        else:
            out.append({"kind": "error", "text": f"Check: {_first_sentence(pc.get('reason'))}"})
    for k, (v, detail) in ws.items():
        if v is not False or k in ("page_check", "naming") or grade(k, v, detail) == "hint":
            continue
        m = re.match(r"(.*?)(?: ; )?belongs to: (\S+)$", detail or "")
        if k in _WITNESS_TEXT and m:
            said = m.group(1)
            cap = re.search(r"\(([^()]*)\)\s*$", said)          # the classifier's "class vs class (caption)"
            said = cap.group(1) if k == "classifier" and cap else said
            said = re.sub(r"\s+", " ", said.split(" | ")[0]).strip(" ;")
            said = said if len(said) <= 70 else said[:69] + "…"     # the text's start, not its first "sentence"
            out.append({"kind": "error", "text": f"{_WITNESS_TEXT[k]} ({said!r}) fits "
                                                 f"`{m.group(2)}` better than this field."})
        elif k == "classifier" and "nothing goes here" in (detail or ""):
            out.append({"kind": "error", "text": "The page classifier read this box as one where nothing is written."})
        elif k == "judge":
            out.append({"kind": "error", "text": "The reader, looking for this field by its name, found a different "
                                                 "value or none."})
        elif k == "adjudicator":
            out.append({"kind": "error", "text": "The adjudicator could not confirm the name from the page."})
        elif k == "structure":
            n = re.match(r"(\d+) separate checkboxes lined up", detail or "")
            out.append({"kind": "suggestion", "text": (f"Could be one group: {n.group(1)} separate checkboxes in a row."
                                                       if n else f"Structure: {_first_sentence(detail, 120)}")})
        else:
            out.append({"kind": "error", "text": f"{_WITNESS_TEXT.get(k, k)} disagrees: {_first_sentence(detail, 120)}"})
    return sorted(out, key=lambda x: x["kind"] != "error")


def grade(k: str, v: Optional[bool], detail: str) -> Optional[str]:
    """How much an `against` counts in the review page (2026-10-07), from hand review: over 1,508 reviewed fields
    (5% flagged by the person), the share of fields each witness marked against that the person flagged:
    page check 60% (38/70 on the fixture), classifier other 25%, publisher belongs-to 24% (re-measured the same
    evening on the current records: 8 of 102, none of the 8 for the tooltip's reason; Andrew: "usually wrong"; now a
    hint), lined-up checkboxes 20%
    (grouping), judge 8%, publisher other 7%, structure group 5%, classifier belongs-to 4%, page belongs-to 3%,
    page other / one-word texts 0%. 'error' makes the field contested; 'suggestion' is shown but does not;
    'hint' (no better than the 5% base rate) stays in the raw witness list only. The loop's reviewer flags
    (`against_flags`) are unchanged.

    Publisher belongs-to is an error again since 2026-10-09: honed (`Names.judge`: a near rival in the same
    section, a margin, a text only this field carries, fit both ways), it fires on 8 looked-at accepted fields
    instead of 93, keeps the 5500-SF day / month swap, and among the bulk-accepted fields it found slides the
    page confirms (ACORD 125 attachments, I-130 eye colour / race / province, f5500sf day / month;
    `eval/belongs_to_fixture.py`)."""
    if v is not False:
        return None
    d = detail or ""
    if k in ("page_check", "naming"):
        return "suggestion" if d.startswith("suggestion") else "error"
    belongs = "belongs to:" in d
    if k == "publisher":       # belongs to / does not describe, echoed by the page: error; otherwise a hint
        if d.startswith("unconfirmed"):
            return "hint"
        return "error" if belongs or "does not describe" in d else "hint"
    if k == "classifier":
        return "hint" if belongs else "error"
    if k == "structure":
        return "suggestion" if "lined up" in d else "hint"
    if k == "adjudicator":
        return "error"
    return "hint"                              # page, judge


def tier(ws: dict[str, tuple]) -> str:
    """Review-page tier: `contested` only on an error-grade against (`grade`); suggestions and hints do not
    contest a field. The loop's adjudicator routing reads witnesses directly, not this tier."""
    graded = [grade(k, v, d) for k, (v, d) in ws.items()]
    votes = [v for v, _ in ws.values() if v is not None]
    if "error" in graded:
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
    from petey.validate import name_type
    maxlens = name_type.text_maxlens(blank)
    from petey.validate.page_check import verdicts as page_check_verdicts
    checked = page_check_verdicts(bp)
    grouping = {**lined_up_checkboxes(fields), **(grouping_witnesses(fields, by_page) if by_page else {})}
    # each witness's own text per field, so 'belongs to another field' compares like with like
    pub = {n: publisher_texts(s, words) for n, s in fields.items()}
    printed = {n: page_texts(s, lines) for n, s in fields.items()}
    boxes = {n: _box(s, by_page) if by_page else None for n, s in fields.items()}
    by_witness = {}
    section_ys = section_rules(blank) if blank and blank.exists() else {}
    for k, texts in (("publisher", pub), ("page", printed),
                     ("classifier", {n: [b["label"]] if b and b.get("label") else [] for n, b in boxes.items()})):
        by_witness[k] = Names(fields, section_ys)
        by_witness[k].set_own(texts)
    if use_model():
        prefetch_scores(fields, by_witness)
    out = {}
    for name, spec in fields.items():
        pv = _per_line(name, pub[name], by_witness["publisher"])
        if pv[0] is False and ("belongs to:" in pv[1] or "does not describe" in pv[1]) \
                and not printed_agrees(pub[name], printed[name]):
            pv = (False, "unconfirmed; " + pv[1])      # the page does not echo the tooltip: a hint (`grade`)
        ws: dict[str, tuple] = {"publisher": pv,
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
        rules = name_type.check(name, spec, maxlens.get((spec.get("widget") or {}).get("path") or ""))
        if rules:                                  # name / type rules (2026-10-07): Y/N text boxes, suffix vs type
            ws["naming"] = (False, ("suggestion; " if rules[0]["grade"] == "suggestion" else "") + rules[0]["text"])
        ws = {k: v for k, v in ws.items() if v[0] is not None or v[1]}
        out[name] = {"tier": tier(ws), "stage": r.get("stage") if same_name else None,
                     "witnesses": {k: [v[0], v[1]] for k, v in ws.items()}}
        cap = caption_suggestion(name, spec, blank, words)
        out[name]["why"] = sorted(explain(name, spec, ws, pc)
                                  + [{"kind": r["grade"], "text": r["text"], "fix": r.get("fix")} for r in rules]
                                  + ([cap] if cap else []),
                                  key=lambda x: x["kind"] != "error")
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
            if v is not False or k not in _FLAG_SOURCE or "belongs to: " not in (detail or "") \
                    or (detail or "").startswith("unconfirmed"):
                continue
            m = re.match(r"(.*?)(?: ; )?belongs to: (\S+)$", detail)
            if m is None:                    # a detail in another shape (2026-10-06: crashed two forms on the runner)
                continue
            text, other = m.groups()
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
            wrong = rec["verdict"] == "flag" or bool(rec.get("edit"))   # a correction = the field was wrong
            table[f["tier"]]["flag" if wrong else "accept"] += 1
            if wrong:
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
