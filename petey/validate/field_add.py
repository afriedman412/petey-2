"""Field add (and remove): the Add / remove mode of the blueprint review page, for adding the fields a blueprint
missed and removing the ones it should not have. Removing is recorded from this mode (click a field) or from Review
(`removed` in the record); `--apply` drops those fields, and their boxes stay out of the suggestions afterwards.

Adding: draw a box over an area of the blank (or click a
suggestion) and the page proposes the field(s) under it, with everything the documents already say about them:

    geometry   the AcroForm widget under the area (path, type, on-state, max length), else the finder's box
               (`boxes.find_boxes`, cached), else the drawn box itself
    caption    the classifier's reading of the box (`classify_form`, cache only), else the printed words the area
               takes in, beside the box on its line, or just above it; an option's caption from
               `captions.caption_right_of`
    name       slug of the caption, else of the tooltip, else a placeholder; the AcroForm labeler
               (`auto_label.label_page_via_llm`, one call, the page's words) only when asked for
    type       from the name through the semantic-type registry (`enrich_field`), as the labelers type; the
               classifier's class is shown and recorded, not applied (two readings stay two, see flat_label)
    options    several option boxes in the area are one group (`category`), keyed by on-state when the widgets'
               on-states tell the options apart (`expand_options`' shape), else by caption; a radio kid brings its
               unclaimed siblings; one option box alone is a boolean `indicator`

Suggestions (outlined on the page, stepped through with n / p): widgets no field covers, and finder boxes no field
covers that the classifier did not call `none`. A suggestion can be dismissed as not a field; the dismissal is
recorded with the rest, a fixture for the "not a field" question the witnesses cannot answer.

    PYTHONPATH=. venv/bin/python -m petey.validate.field_add [--port 5007]     # then open http://127.0.0.1:5007/
    PYTHONPATH=. venv/bin/python -m petey.validate.field_add --summary
    PYTHONPATH=. venv/bin/python -m petey.validate.field_add --plan <id>       # what --apply would add
    PYTHONPATH=. venv/bin/python -m petey.validate.field_add --apply <id>      # write it into the blueprint

The page only records (`runs/field_add/<id>.json`: fields added, suggestions dismissed, the blueprint's sha), like
the hand review and the group review. `--apply` inserts the added fields in reading order (after the field that
precedes each on the page), each marked `x_petey_added` (where its geometry, caption and name came from) with
`label_source` as the flat labeler writes it, and `needs_review` on placeholder names. Blueprints offered are the
hand review's. Since 2026-10-13 the review page applies each save to its working copy of the blueprint at once
(`draft.py`), and `--apply` writes that copy while it is open.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Optional

import pymupdf
import yaml

from petey.label import auto_label
from petey.label.captions import caption_right_of
from petey.locate.acroform import enumerate_widgets
from petey.paths import RUNS
from petey.semantic_types import enrich_field, registered_names
from petey.synth.boxes import CACHE_DIR as BOX_CACHE, FINDER_VERSION, find_boxes, overlap
from petey.synth.classify import classify_form
from petey.validate import field_ids
from petey.validate.hand_review import _load, _sha, blueprint_paths, working_path
from petey.validate.retype import resolve_blank

OUT = RUNS / "field_add"
DPI = 144
LABEL_MODEL = auto_label.MODEL
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_]*$")     # spec 5.2 allows digits anywhere
OPTION_WIDGETS = ("checkbox", "radiobutton")
CLAIM = 0.5                     # overlap (of the smaller rect) at which a field covers a box
_DROP = {"the", "a", "an", "your", "enter", "here", "please", "print", "type", "and", "or", "if", "any", "see",
         "instructions", "optional", "applicable", "check", "box", "this", "below", "above", "following"}
_ITEM_NO = re.compile(r"^\s*(\(?\d{1,3}[a-z]?\)?[.:]?|\(?[a-z]\)[.:]?|[A-Z][.:])\s+")
_LEADERS = re.compile(r"[._…]{2,}.*$")


def record_path(bid: str) -> Path:
    return OUT / f"{bid}.json"


def load_record(bid: str) -> dict:
    p = record_path(bid)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", (s or "").lower()).strip("_")


def _area(r) -> float:
    return max(0.0, r[2] - r[0]) * max(0.0, r[3] - r[1])


def _center_in(r, sel, pad: float = 0.5) -> bool:
    cx, cy = (r[0] + r[2]) / 2, (r[1] + r[3]) / 2
    return sel[0] - pad <= cx <= sel[2] + pad and sel[1] - pad <= cy <= sel[3] + pad


def _union(rects) -> list[float]:
    return [min(r[0] for r in rects), min(r[1] for r in rects), max(r[2] for r in rects), max(r[3] for r in rects)]


def _order(page: int, rect) -> tuple:
    return int(page), round(rect[1] / 6), rect[0]


def clean_caption(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = " ".join(s.split())
    s = _LEADERS.sub("", s)
    for _ in range(2):
        s = _ITEM_NO.sub("", s)
    s = s.strip(" :;,.-")
    words = s.split()
    if len(words) > 10:
        s = " ".join(words[:10])
    return s or None


def name_from(text: Optional[str], kind: str) -> Optional[str]:
    """A field name from a caption or tooltip: its first content words, slugged; `_ind` on a lone option (the
    flat labeler's rule). None when nothing usable is left."""
    text = re.sub(r"\([^)]*\)?", " ", clean_caption(text) or "")          # "(see application status at ...)"
    text = re.sub(r"(\w)['\u2019]s\b", r"\1", text)                          # "Veteran's" -> "Veteran"
    toks = [t for t in _slug(text).split("_") if t and t not in _DROP]
    if not toks:
        return None
    name = "_".join(toks[:6])
    if not name[0].isalpha():
        name = "f_" + name
    return name + ("_ind" if kind == "option" and not name.endswith("_ind") else "")


# ---------------------------------------------------------------- what the documents say about a blueprint's blank

def _finder_cached(blank: Path) -> bool:
    h = hashlib.sha256(blank.read_bytes() + b"\x00boxes\x00" + FINDER_VERSION.encode()).hexdigest()
    return (BOX_CACHE / f"{h}.json").exists()


def path_stem(path: Optional[str]) -> Optional[str]:
    """A widget path with its last part's index and trailing part number or column letter removed: siblings
    (`Pt7Line4_Weight1[0]` / `Weight2[0]`, `APPRV_C[0]` / `APPRV_D[0]`) share it."""
    if not path:
        return None
    parent, _, last = path.rpartition(".")
    last = re.sub(r"\[\d+\]$", "", last)
    stem = re.sub(r"(\d+|_[A-Z])$", "", last)
    return f"{parent}.{stem}" if stem != last else None


def _norm_tip(t: Optional[str]) -> Optional[str]:
    t = " ".join((t or "").lower().split())
    return t if len(t) >= 12 else None


def field_rects(bp: dict) -> list[dict]:
    out = []
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        blocks = list((spec.get("widgets") or {}).values()) or ([spec["widget"]] if spec.get("widget") else [])
        for w in blocks:
            if w.get("rect") and w.get("page"):
                out.append({"name": name, "page": int(w["page"]), "rect": [float(c) for c in w["rect"]]})
    return out


class Context:
    """One blueprint's blank, read once per blueprint version: its widgets (with max length), the finder's boxes
    and the classifier's map when cached, and which of them a field already covers."""

    def __init__(self, bid: str, p: Path):
        self.bid, self.path = bid, p
        self.bp = _load(p)
        self.sha = _sha(p)
        self.blank = resolve_blank(self.bp)
        self.fields = field_rects(self.bp)
        self.names = set((self.bp.get("fields") or {}).keys())
        self.pages: list[dict] = []
        self.widgets: list[dict] = []
        self.boxes: Optional[list[dict]] = None
        self.cmap: Optional[dict] = None
        self._words: dict[int, list] = {}
        if not self.blank or not self.blank.exists():
            return
        doc = pymupdf.open(str(self.blank))
        try:
            self.pages = [{"page": i, "w_pt": pg.rect.width, "h_pt": pg.rect.height} for i, pg in enumerate(doc, 1)]
            maxlen: dict[tuple, int] = {}
            for i, pg in enumerate(doc, 1):
                for w in pg.widgets() or []:
                    if getattr(w, "text_maxlen", 0):
                        maxlen[(i, w.field_name, round(w.rect.x0), round(w.rect.y0))] = w.text_maxlen
        finally:
            doc.close()
        ws, _dropped = enumerate_widgets(self.blank)
        owner = {}                                       # a widget whose path a field already holds is that field
        for name, spec in (self.bp.get("fields") or {}).items():
            if isinstance(spec, dict):
                for wb in list((spec.get("widgets") or {}).values()) + [spec.get("widget") or {}]:
                    if wb.get("path"):
                        owner.setdefault(wb["path"], name)
        self.by_tip: dict[str, str] = {}             # tooltip -> the field holding a widget with it
        self.by_stem: dict[str, str] = {}            # path stem -> a field holding a sibling widget
        for w in ws:
            if w["path"] in owner:
                if _norm_tip(w.get("tooltip")):
                    self.by_tip.setdefault(_norm_tip(w["tooltip"]), owner[w["path"]])
                if path_stem(w["path"]):
                    self.by_stem.setdefault(path_stem(w["path"]), owner[w["path"]])
        first = auto_label.first_copy_ids(ws)            # the labeler names Copy A only; B, C ... repeat it
        placed = {f["name"] for f in self.fields}        # fields with a box of their own somewhere
        for w in ws:
            w["sid"] = f"w{w['id']}"
            w["maxlen"] = maxlen.get((w["page"], w["path"], round(w["rect"][0]), round(w["rect"][1])))
            # a box the blueprint covers where it is; by path only when the field holding the path has no box of its
            # own. A box that shares its PDF name with a field placed elsewhere is a separate box the PDF ties to it
            # (FAA 8710: the instructor's and the examiner's 'Rejected Student Pilot Application' boxes, 2026-10-13)
            w["claimed_by"] = self._claimed(w["page"], w["rect"]) or (
                f"{owner[w['path']]} (same path)" if w["path"] in owner and owner[w["path"]] not in placed else None)
            w["shares_path_with"] = owner.get(w["path"]) if not w["claimed_by"] else None
            w["copy"] = w["id"] not in first
        self.widgets = ws
        self.load_finder(run=False)

    def _claimed(self, page: int, rect) -> Optional[str]:
        best, score = None, 0.0
        for f in self.fields:
            if f["page"] == page:
                s = overlap(rect, f["rect"])
                if s > score:
                    best, score = f["name"], s
        return best if score >= CLAIM else None

    def load_finder(self, run: bool) -> None:
        """The finder's boxes (cached, or run now when `run`: local CPU) joined to the classifier's map (cache only)."""
        if not self.blank or not (run or _finder_cached(self.blank)):
            return
        boxes = find_boxes(self.blank)
        try:
            self.cmap = classify_form(self.blank, cache_only=True)
        except Exception:
            self.cmap = None
        cm = (self.cmap or {}).get("boxes") or {}
        out = []
        for b in boxes:
            c = cm.get(b["key"]) or {}
            # a box the finder's minor version added (finder_addons: radio circles) has no class map entry: an option
            out.append({**b, "sid": f"b{b['id']}", "class": c.get("class") or ("option" if b.get("addon") else None),
                        "label": c.get("label"),
                        "group": c.get("group"), "entity": c.get("entity"),
                        "claimed_by": self._claimed(b["page"], b["rect"])})
        self.boxes = out

    def words(self, page: int) -> list[tuple]:
        if page not in self._words:
            doc = pymupdf.open(str(self.blank))
            try:
                self._words[page] = [tuple(w[:8]) for w in doc[page - 1].get_text("words")]
            finally:
                doc.close()
        return self._words[page]

    def suggestions(self) -> list[dict]:
        out = []
        free_w = [w for w in self.widgets if not w["claimed_by"]]
        for w in free_w:
            out.append({"sid": w["sid"], "source": "widget", "page": w["page"], "rect": w["rect"], "copy": w["copy"],
                        "what": f"{w['widget_type']} widget {w['path'].split('.')[-1]}"
                                + (" (a repeated copy of the form)" if w["copy"] else "")
                                + (f" (shares its PDF name with field {w['shares_path_with']}: the PDF fills both "
                                   f"with one value)" if w.get("shares_path_with") else "")})
        # finder boxes: screened by the classifier when its map is cached; unscreened only on a flat blank, where
        # nothing else marks a field (on a form layer they are mostly printed cells the widgets already cover)
        screened = bool(self.cmap)
        for b in (self.boxes or []) if screened or not self.widgets else []:
            if b["claimed_by"] or (screened and b.get("class") in (None, "none")):
                continue
            if any(w["page"] == b["page"] and overlap(w["rect"], b["rect"]) >= CLAIM for w in free_w):
                continue
            out.append({"sid": b["sid"], "source": "finder", "page": b["page"], "rect": b["rect"],
                        "what": f"finder {b['kind']} box" + (f", classifier: {b['class']}" if b.get("class")
                                                             else ", not screened by the classifier")})
        out.sort(key=lambda s: _order(s["page"], s["rect"]))
        return out


# ---------------------------------------------------------------- proposals: an area -> field(s)

def _text_caption(words: list[tuple], r, sel) -> tuple[Optional[str], Optional[str]]:
    """Printed words that name a text box at `r`: words the drawn area takes in outside the box; the box's own
    words (a cell's printed label); words just left on its line; the line just above it."""
    def txt(ws):
        return clean_caption(" ".join(w[4] for w in ws))
    inbox = lambda w: _center_in(w[:4], r, pad=1)
    if sel is not None:
        took = [w for w in words if _center_in(w[:4], sel) and not inbox(w)]
        if took and txt(took):
            return txt(took), "page text (in the area)"
    own = [w for w in words if inbox(w)]
    if own and (r[3] - r[1]) > 14 and txt(own):
        return txt(own), "page text (in the box)"
    line = [w for w in words if w[2] <= r[0] + 2 and min(w[3], r[3] + 3) - max(w[1], r[1] - 3) >= 0.5 * (w[3] - w[1])]
    line.sort(key=lambda w: -w[2])
    left, edge = [], r[0]
    for w in line:
        if edge - w[2] > (40 if not left else 12):
            break
        left.insert(0, w)
        edge = w[0]
    if left and txt(left):
        return txt(left), "page text (left of the box)"
    above = [w for w in words if r[1] - 16 <= w[3] <= r[1] + 3 and min(w[2], r[2]) - max(w[0], r[0]) > 0.3 * (w[2] - w[0])]
    if above:
        y = max(w[3] for w in above)
        row = sorted((w for w in above if abs(w[3] - y) < 3), key=lambda w: w[0])
        if txt(row):
            return txt(row), "page text (above the box)"
    return None, None


def _box_info(ctx: Context, page: int, rect) -> Optional[dict]:
    best, score = None, 0.0
    for b in ctx.boxes or []:
        if b["page"] == page:
            s = overlap(rect, b["rect"])
            if s > score:
                best, score = b, s
    return best if score >= CLAIM else None


def _named(p: dict, candidates: list[tuple[Optional[str], str]], kind: str, taken: set[str],
           ctx: Optional[Context] = None) -> None:
    """Name options in order of preference, each with the typing it implies: a twin's name verbatim with the
    twin's type, semantic type and pattern; a name made from a caption or tooltip typed through the registry (a
    text box), `indicator` (a lone option) or `category` (a group). The first becomes the proposal's."""
    opts, seen = [], set()
    for text, source in candidates:
        n = text if source.startswith("twin") else name_from(text, kind)
        if n and n not in seen:
            seen.add(n)
            opts.append({"name": n, "source": source})
    if not opts:
        opts.append({"name": f"p{p['page']}_{kind}_{int(p['rect'][0])}_{int(p['rect'][1])}", "source": "placeholder"})
    for o in opts:
        if o["source"].startswith("twin") and ctx is not None:
            spec = (ctx.bp.get("fields") or {}).get(o["name"]) or {}
            o["types"] = {k: spec[k] for k in ("type", "semantic_type", "pattern") if spec.get(k)}
            o["twin"] = o["name"]
        elif kind == "text":
            o["types"] = enrich_field(o["name"], "text")
        elif kind == "option":
            o["types"] = {"type": "boolean", "semantic_type": "indicator"}
        else:
            o["types"] = {"type": p.get("type") or "category"}
        base, k = o["name"], 2
        while o["name"] in taken:
            o["name"], k = f"{base}_{k}", k + 1
    p["name"], p["name_source"], p["name_options"] = opts[0]["name"], opts[0]["source"], opts
    for k in ("type", "semantic_type", "pattern"):
        p.pop(k, None)
    p.update(opts[0]["types"])
    if opts[0].get("twin"):
        p["twin"] = opts[0]["twin"]


def switch_kind(p: dict, kind: str, taken: set[str] = frozenset()) -> dict:
    """A one-box proposal made a text box or a checkbox by hand (Andrew, 2026-10-20: "we need a way to designate a
    field a checkbox and not a textfield"; what is under the drawn box decides, and sometimes wrongly). Its name
    options are typed again for the new kind (`_named`: a checkbox is a boolean `indicator` named ..._ind; a text
    box is typed from its name); a name typed by hand stays. A text widget made a checkbox loses its form path, as
    eval/split_yes_no.py does: the page shows a checkbox, the form layer a text box, and extraction reads the page
    (memory: page over metadata); a checkbox made a text box gets its path back."""
    if p.get("kind") not in ("text", "option") or kind not in ("text", "option") or p["kind"] == kind:
        return p
    q = {**p, "kind": kind, "widget": dict(p["widget"]), "evidence": list(p.get("evidence") or [])}
    w = q["widget"]
    if kind == "option":
        if w.get("path") and w.get("widget_type") == "text":
            q["text_path"] = w["path"]
            w["path"] = None
            q["evidence"].append(f"made a checkbox by hand: the form's text widget {q['text_path']} is left out "
                                 "(the page shows a checkbox)")
        else:
            q["evidence"].append("made a checkbox by hand")
        w["widget_type"] = "checkbox"
    else:
        w["widget_type"] = "text"
        if q.get("text_path"):
            w["path"] = q.pop("text_path")
        w.pop("on_state", None)
        q["evidence"].append("made a text box by hand")
    def renamed(n: str) -> str:
        base = n[:-4] if n.endswith("_ind") else n
        base = re.sub(r"^(p\d+)_(text|option)_(\d+_\d+)$", rf"\1_{kind}_\3", base)    # a placeholder says its kind
        return base + "_ind" if kind == "option" else base

    def typed(n: str) -> dict:
        return {"type": "boolean", "semantic_type": "indicator"} if kind == "option" else enrich_field(n, "text")
    opts, seen, now = [], set(), {}
    for o in p.get("name_options") or [{"name": p["name"], "source": p.get("name_source") or "hand"}]:
        n = renamed(o["name"])
        base, k = n, 2
        while n in taken:
            n, k = f"{base}_{k}", k + 1
        now[o["name"]] = n
        if n not in seen:
            seen.add(n)
            opts.append({"name": n, "source": o["source"], "types": typed(n)})
    q["name_options"] = opts
    for k in ("type", "semantic_type", "pattern", "twin"):
        q.pop(k, None)
    # a name typed by hand stays as typed; else the current name, made for the new kind
    q["name"] = p["name"] if p.get("name_source") == "hand" else now.get(p["name"], renamed(p["name"]))
    q.update(typed(q["name"]))
    return q


def _twins(ctx: Context, cands: list[dict], evidence: list[str]) -> list[tuple[str, str]]:
    """Fields the blueprint already has for the same thing: a widget with the same publisher tooltip (a header
    repeated on a later page), or a sibling widget (the other part of a split number, the same row in another
    column). Their names are offered first, as-is (`_named` adds a suffix) and their types are copied."""
    out: list[tuple[str, str]] = []
    for c in cands:
        t = ctx.by_tip.get(_norm_tip(c.get("tooltip")) or "")
        if t and (t, "twin: same tooltip") not in out:
            out.append((t, "twin: same tooltip"))
            evidence.append(f"same tooltip as field {t}")
        st = ctx.by_stem.get(path_stem(c.get("path")) or "")
        if st and all(n != st for n, _ in out):
            out.append((st, "twin: sibling path"))
            evidence.append(f"sibling of field {st} (path {c['path'].split('.')[-1]} beside its widget's)")
    return out


def _text_proposal(ctx: Context, c: dict, src: str, sel, taken: set[str]) -> dict:
    page, rect = c["page"], c["rect"]
    box = c if src == "finder" else _box_info(ctx, page, rect)
    evidence = []
    if src == "widget":
        evidence.append(f"AcroForm {c['widget_type']} widget {c['path']}")
        if c.get("copy"):
            evidence.append("this widget repeats an earlier copy of the form (Copy B, C ...); the labeler names only the first")
        if c.get("maxlen"):
            evidence.append(f"max length {c['maxlen']}")
    elif src == "finder":
        evidence.append(f"finder {c.get('kind')} box (confidence {c.get('conf')})")
    else:
        evidence.append("no widget or finder box here: the drawn box is the field's box")
    cls_cap = (box or {}).get("label")
    if box and box.get("class"):
        evidence.append(f"classifier: {box['class']}" + (f" for {box['entity']}" if box.get("entity") else "")
                        + (f", caption {cls_cap!r}" if cls_cap else ""))
    cap, cap_src = _text_caption(ctx.words(page), rect, sel)
    if cap:
        evidence.append(f"{cap_src}: {cap!r}")
    tip = c.get("tooltip")
    desc = auto_label._description_from_tooltip(tip)
    if tip:
        evidence.append(f"tooltip: {tip!r}")
    twins = _twins(ctx, [c], evidence)
    p = {"kind": "text", "page": page, "rect": rect, "geometry": src,
         "widget": {"page": page, "rect": rect, "widget_type": "text" if src != "widget" else c["widget_type"],
                    "path": c.get("path")},
         "caption": clean_caption(cls_cap) or cap, "page_class": (box or {}).get("class"),
         "entity": (box or {}).get("entity"), "description": desc, "evidence": evidence}
    _named(p, twins + [(cls_cap, "classifier caption"), (cap, cap_src or "page text"), (tip, "tooltip")], "text", taken,
           ctx)
    return p


def _option_caption(ctx: Context, page: int, rect, others) -> Optional[str]:
    doc = pymupdf.open(str(ctx.blank))
    try:
        return caption_right_of(doc[page - 1], rect, words=ctx.words(page), options_rects=others)
    finally:
        doc.close()


def _options_proposal(ctx: Context, cands: list[tuple[dict, str]], sel, taken: set[str]) -> dict:
    page = cands[0][0]["page"]
    rects = [c["rect"] for c, _ in cands]
    opts, evidence = [], []
    for c, src in cands:
        box = c if src == "finder" else _box_info(ctx, c["page"], c["rect"])
        cap = clean_caption((box or {}).get("label")) or _option_caption(ctx, c["page"], c["rect"],
                                                                         [r for r in rects if r is not c["rect"]])
        wt = c.get("widget_type") if src == "widget" else ("radiobutton" if c.get("kind") == "radio" else "checkbox")
        opts.append({"page": c["page"], "rect": c["rect"], "widget_type": wt, "path": c.get("path"),
                     "on_state": c.get("on_state"), "caption": cap, "tooltip": c.get("tooltip"),
                     "group": (box or {}).get("group")})
    srcs = sorted({s for _, s in cands})
    evidence.append(f"{len(opts)} option box(es) from {' and '.join(srcs)}")
    paths = sorted({o["path"] for o in opts if o["path"]})
    if paths:
        evidence.append("paths: " + ", ".join(pp.split(".")[-1] for pp in paths[:6]) + (" ..." if len(paths) > 6 else ""))
    if len(opts) == 1:
        o = opts[0]
        tip = o.get("tooltip")
        p = {"kind": "option", "page": page, "rect": o["rect"], "geometry": srcs[0],
             "widget": {k: o[k] for k in ("page", "rect", "widget_type", "path")} | ({"on_state": o["on_state"]} if o.get("on_state") else {}),
             "caption": o["caption"], "description": auto_label._description_from_tooltip(tip) or o["caption"],
             "evidence": evidence + ([f"caption: {o['caption']!r}"] if o["caption"] else []) + ([f"tooltip: {tip!r}"] if tip else []),
             "type": "boolean", "semantic_type": "indicator"}
        _named(p, _twins(ctx, [o], p["evidence"]) + [(o["caption"], "option caption"), (tip, "tooltip")], "option",
               taken, ctx)
        return p
    states = [o.get("on_state") for o in opts]
    by_state = all(states) and len(set(states)) == len(states)      # distinct on-states name the options
    used = set()
    for i, o in enumerate(opts):
        k = (str(o["on_state"]) if by_state else _slug(o["caption"] or "")) or f"option_{i + 1}"
        if k[0].isdigit() and not by_state:
            k = "opt_" + k
        base, n = k, 2
        while k in used:
            k, n = f"{base}_{n}", n + 1
        used.add(k)
        o["key"] = k
    groups = {o["group"] for o in opts if o.get("group")}
    question = next(iter(groups)) if len(groups) == 1 else None
    if question:
        evidence.append(f"classifier: one question, {question!r}")
    if not question:                                  # the words beside the first option: left on its line, or above
        first = min(opts, key=lambda o: _order(o["page"], o["rect"]))
        capwords = {t.lower() for o in opts for t in (o["caption"] or "").split()}
        near = [w for w in ctx.words(page) if w[4].lower() not in capwords]
        q, q_src = _text_caption(near, first["rect"], None)
        if q:
            question = q
            evidence.append(f"question, {q_src}: {q!r}")
    if not question and sel is not None:              # else what the area takes in, when it is short
        capwords = {t.lower() for o in opts for t in (o["caption"] or "").split()}
        took = [w for w in ctx.words(page) if _center_in(w[:4], sel) and w[4].lower() not in capwords
                and not any(_center_in(w[:4], r, pad=1) for r in rects)]
        if 0 < len(took) <= 8:
            question = clean_caption(" ".join(w[4] for w in took))
            evidence.append(f"question, page text in the area: {question!r}")
    tip = next((o["tooltip"] for o in opts if o.get("tooltip")), None)
    p = {"kind": "group", "page": page, "rect": _union(rects), "geometry": "+".join(srcs), "type": "category",
         "options": [{k: o[k] for k in ("key", "caption", "page", "rect", "widget_type", "path", "on_state")} for o in opts],
         "caption": question, "description": auto_label._description_from_tooltip(tip), "evidence": evidence,
         "keyed_by": "on-state" if by_state else "caption"}
    twin_cands = [{"path": o["path"], "tooltip": o.get("tooltip")} for o in opts]
    _named(p, _twins(ctx, twin_cands, evidence) + [(question, "question text"), (tip, "tooltip")], "group", taken, ctx)
    p["type"] = "category" if p.get("type") not in ("category", "multi_category") else p["type"]
    return p


def propose(ctx: Context, page: int, rect: Optional[list[float]] = None, sid: Optional[str] = None,
            taken_extra: set[str] = frozenset()) -> dict:
    """Proposed field(s) for a drawn area (`rect`) or a suggestion (`sid`), with notes on what the area holds
    that a field already covers."""
    taken = ctx.names | set(taken_extra)
    notes: list[str] = []
    sel = None
    if sid:
        c = next((w for w in ctx.widgets if w["sid"] == sid), None) or next((b for b in ctx.boxes or [] if b["sid"] == sid), None)
        if c is None:
            return {"proposals": [], "notes": [f"no suggestion {sid}"]}
        cands = [(c, "widget" if sid.startswith("w") else "finder")]
        page = c["page"]
    else:
        sel = [float(v) for v in rect]
        point = (sel[2] - sel[0]) < 3 and (sel[3] - sel[1]) < 3
        def hit(r):
            return (sel[0] >= r[0] - 1 and sel[2] <= r[2] + 1 and sel[1] >= r[1] - 1 and sel[3] <= r[3] + 1) if point \
                else (_center_in(r, sel) or overlap(r, sel) >= 0.6 and _area(r) <= _area(sel) * 1.5)
        ws = [w for w in ctx.widgets if w["page"] == page and hit(w["rect"])]
        bs = [b for b in ctx.boxes or [] if b["page"] == page and hit(b["rect"])]
        if point:                                          # a click: the smallest thing under it
            ws = sorted(ws, key=lambda w: _area(w["rect"]))[:1]
            bs = sorted(bs, key=lambda b: _area(b["rect"]))[:1] if not ws else []
        for w in ws:
            if w["claimed_by"]:
                notes.append(f"{w['widget_type']} widget {w['path'].split('.')[-1]} is already field {w['claimed_by']}")
        free_w = [w for w in ws if not w["claimed_by"]]
        cands = [(w, "widget") for w in free_w]
        for b in bs:
            if b["claimed_by"]:
                if not any(overlap(b["rect"], w["rect"]) >= CLAIM for w in ws):
                    notes.append(f"finder box at {[round(v) for v in b['rect']]} is already field {b['claimed_by']}")
                continue
            if any(overlap(b["rect"], w["rect"]) >= CLAIM for w in ws):
                continue                                   # the widget speaks for it
            if ctx.cmap and b.get("class") == "none" and not point:
                notes.append(f"finder box at {[round(v) for v in b['rect']]}: the classifier says not a field (skipped; click it to use it)")
                continue
            cands.append((b, "finder"))
        if not cands:
            if ws or bs:
                return {"proposals": [], "notes": notes}
            w_, h_ = sel[2] - sel[0], sel[3] - sel[1]
            if w_ < 3 or h_ < 3:
                return {"proposals": [], "notes": ["nothing here; drag a box over the area to make a field of it"]}
            small_square = w_ <= 16 and h_ <= 16 and abs(w_ - h_) <= 4
            c = {"page": page, "rect": [round(v, 2) for v in sel], "kind": "checkbox" if small_square else "text"}
            cands = [(c, "selection")]
            if ctx.widgets:
                notes.append("this blank has a form layer but no widget here: a filler cannot type into this box")
    # a radio kid brings its unclaimed siblings (one AcroForm field, one group)
    for c, src in list(cands):
        if src == "widget" and c["widget_type"] == "radiobutton":
            for w in ctx.widgets:
                if w["path"] == c["path"] and not w["claimed_by"] and all(w is not x for x, _ in cands):
                    cands.append((w, "widget"))
                    notes.append(f"added radio sibling {w['on_state']!r} of {c['path'].split('.')[-1]}")
    is_opt = lambda c, s: (c.get("widget_type") in OPTION_WIDGETS) if s == "widget" else (
        c.get("kind") in ("checkbox", "radio") or c.get("class") == "option")
    opts = [(c, s) for c, s in cands if is_opt(c, s)]
    texts = [(c, s) for c, s in cands if not is_opt(c, s)]
    texts.sort(key=lambda t: _order(t[0]["page"], t[0]["rect"]))
    opts.sort(key=lambda t: _order(t[0]["page"], t[0]["rect"]))
    out = []
    for c, s in texts:
        p = _text_proposal(ctx, c, s, sel, taken)
        taken.add(p["name"])
        out.append(p)
    if opts:
        p = _options_proposal(ctx, opts, sel, taken)
        taken.add(p["name"])
        out.append(p)
    for p in out:
        p["sids"] = [c["sid"] for c, _ in cands if c.get("sid") and _center_in(c["rect"], p["rect"], pad=1)]
    return {"proposals": out, "notes": notes}


def labeler_name(ctx: Context, p: dict, model: str = LABEL_MODEL, think: bool = True) -> Optional[str]:
    """One call to the AcroForm labeler for this proposal, with the page's printed words. `think=False`: Groups'
    button, without the model's hidden thinking (a few seconds instead of eight)."""
    entry = {"id": 1, "page": p["page"], "rect": p["rect"],
             "widget_type": {"text": "text", "option": "checkbox", "group": "radiobutton"}[p["kind"]]}
    if p["kind"] == "group":
        entry["options"] = [o.get("caption") or o["key"] for o in p["options"]]
    w = next((w for w in ctx.widgets if w.get("path") and w["path"] == (p.get("widget") or {}).get("path")), None)
    if w and w.get("tooltip"):
        entry["tooltip"] = w["tooltip"]
    doc = pymupdf.open(str(ctx.blank))
    try:
        words = auto_label._words_from_page(doc[p["page"] - 1])
    finally:
        doc.close()
    auto_label.CALL_TAG = f"field_add/{ctx.path.stem}"
    got = auto_label.label_page_via_llm([entry], words, model=model, think=think)
    n = _slug((got.get(1) or "").replace(".", "_"))
    return n or None


# ---------------------------------------------------------------- the plan: record -> blueprint

def spec_of(p: dict, now: str) -> dict:
    """The blueprint field for one added proposal."""
    spec: dict = {"type": p.get("type") or "string"}
    if p.get("semantic_type"):
        spec["semantic_type"] = p["semantic_type"]
    if p.get("pattern") and spec["type"] == "string":
        spec["pattern"] = p["pattern"]
    if p["kind"] == "group":
        widgets = {}
        for o in p["options"]:
            wb = {"page": int(o["page"]), "rect": [float(c) for c in o["rect"]], "widget_type": o["widget_type"],
                  "path": o.get("path")}
            if o.get("on_state"):
                wb["on_state"] = o["on_state"]
            if o.get("caption"):
                wb["caption"] = o["caption"]
            widgets[o["key"]] = wb
        spec["values"] = list(widgets)
        spec["widgets"] = widgets
    else:
        w = p["widget"]
        spec["widget"] = {"page": int(w["page"]), "rect": [float(c) for c in w["rect"]],
                          "widget_type": w["widget_type"], "path": w.get("path")}
        if w.get("on_state"):
            spec["widget"]["on_state"] = w["on_state"]
    if p.get("description"):
        spec["description"] = p["description"]
    src = p.get("name_source") or "hand"
    spec["label_source"] = ("llm" if src == "labeler" else src if src in ("placeholder", "hand", "tooltip")
                            else "twin" if src.startswith("twin") else "classifier_caption"
                            if src == "classifier caption" else "page_caption")
    if src == "placeholder":
        spec["needs_review"] = True
    spec["x_petey_added"] = {k: v for k, v in {
        "source": "field_add", "when": p.get("when") or now, "geometry": p.get("geometry"),
        "name_from": src, "caption": p.get("caption"), "page_class": p.get("page_class"),
        "entity": p.get("entity"), "finder": FINDER_VERSION if "finder" in (p.get("geometry") or "") else None,
    }.items() if v}
    return spec


def _first_rect(spec: dict) -> Optional[tuple]:
    blocks = list((spec.get("widgets") or {}).values()) or ([spec["widget"]] if spec.get("widget") else [])
    keys = [_order(w["page"], w["rect"]) for w in blocks if w.get("rect") and w.get("page")]
    return min(keys) if keys else None


def plan(bp: dict, added: list[dict], removed: list[dict] = ()) -> dict:
    """`{changes, errors, skipped, fields}`: the blueprint's fields less the removed ones, with the added ones
    inserted, each after the field that precedes it in reading order. An added field whose box a field now covers is
    skipped (added since, by another route); a removal of a field that is no longer there is skipped too. An added
    field may take the name of a removed one."""
    errors, changes, skipped = [], [], []
    fields = dict(bp.get("fields") or {})
    for r in removed:
        if r.get("name") in fields:
            spec = fields.pop(r["name"])
            t = spec.get("type") if isinstance(spec, dict) else None
            changes.append(f"remove {r['name']}" + (f" (p{r['page']}, {t})" if r.get("page") else ""))
        else:
            skipped.append(f"{r.get('name')}: already not in the blueprint")
    rects = field_rects({"fields": fields})
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    names = [p["name"] for p in added]
    for n in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"two added fields are both named {n!r}")
    new: list[tuple[str, dict]] = []
    for p in added:
        if not NAME_RE.match(p.get("name") or ""):
            errors.append(f"{p.get('name')!r} is not a field name (lower case, digits, underscores)")
            continue
        if p["name"] in fields:
            errors.append(f"{p['name']!r} is already a field in the blueprint")
            continue
        box = p["rect"] if p["kind"] != "group" else p["options"][0]["rect"]
        hit = next((f["name"] for f in rects if f["page"] == p["page"] and overlap(box, f["rect"]) >= CLAIM), None)
        if hit:
            skipped.append(f"{p['name']}: its box is now field {hit}")
            continue
        spec = spec_of(p, now)
        new.append((p["name"], spec))
        what = (f"group of {len(p['options'])} ({', '.join(o['key'] for o in p['options'])})" if p["kind"] == "group"
                else spec["type"] + (f"/{spec['semantic_type']}" if spec.get("semantic_type") else ""))
        changes.append(f"add {p['name']} on p{p['page']}: {what}; {p.get('geometry')} geometry, name from "
                       f"{p.get('name_source')}")
    if errors:
        return {"changes": changes, "errors": errors, "skipped": skipped, "fields": None}
    order = [(n, _first_rect(s)) for n, s in fields.items() if isinstance(s, dict)]
    after: dict[Optional[str], list] = {}
    for n, s in new:
        k = _first_rect(s)
        prev = None
        for en, ek in order:
            if ek is not None and ek <= k and (prev is None or ek >= prev[1]):
                prev = (en, ek)
        after.setdefault(prev[0] if prev else None, []).append((k, n, s))
    out: dict = {}
    for k, n, s in sorted(after.get(None, []), key=lambda t: t[0]):
        out[n] = s
    for name, spec in fields.items():
        out[name] = spec
        for k, n, s in sorted(after.get(name, []), key=lambda t: t[0]):
            out[n] = s
    return {"changes": changes, "errors": [], "skipped": skipped, "fields": out}


def apply(bid: str) -> dict:
    """Write the record's additions and removals into the blueprint (its working copy while one is open, `draft.py`)."""
    p = working_path(bid)
    bp = _load(p)
    rec = load_record(bid)
    added, removed = rec.get("added") or [], rec.get("removed") or []
    if not added and not removed:
        print(f"{bid}: nothing recorded to add or remove")
        return {}
    pl = plan(bp, added, removed)
    if pl["errors"]:
        raise SystemExit(f"{bid}: not applied:\n  " + "\n  ".join(pl["errors"]))
    for s in pl["skipped"]:
        print(f"  skipped {s}")
    if pl["changes"]:
        bp["fields"] = pl["fields"]
        field_ids.assign(bp)                    # a new field gets the next free id on its page
        p.write_text(yaml.safe_dump(bp, sort_keys=False, allow_unicode=True), encoding="utf-8")
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    rec.setdefault("applied", []).append({"when": now, "sha_before": rec.get("blueprint_sha"), "sha_after": _sha(p),
                                          "changes": pl["changes"], "skipped": pl["skipped"]})
    rec["removed_applied"] = (rec.get("removed_applied") or []) + removed    # their boxes stay out of the suggestions
    rec["added"], rec["removed"], rec["blueprint_sha"], rec["updated"] = [], [], _sha(p), now
    record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{bid}: wrote {p}")
    for c in pl["changes"]:
        print(f"  {c}")
    return pl


# ---------------------------------------------------------------- server

class State:
    def __init__(self) -> None:
        self.paths = blueprint_paths()
        self.png: dict[tuple[str, int], bytes] = {}
        self._ctx: dict[str, Context] = {}

    def ctx(self, bid: str) -> Context:
        p = working_path(bid, self.paths)
        c = self._ctx.get(bid)
        if c is None or c.sha != _sha(p):
            c = self._ctx[bid] = Context(bid, p)
        return c

    def listing(self) -> list[dict]:
        out = []
        for bid, p in self.paths.items():
            rec = load_record(bid)
            out.append({"id": bid, "source": bid.split("__")[0], "form": p.stem,
                        "added": len(rec.get("added") or []), "dismissed": len(rec.get("dismissed") or []),
                        "removed": len(rec.get("removed") or []),
                        "applied": sum(len(a.get("changes") or []) for a in rec.get("applied") or [])})
        return out

    def detail(self, bid: str) -> dict:
        c = self.ctx(bid)
        rec = load_record(bid)
        gone = [r for r in (rec.get("removed") or []) + (rec.get("removed_applied") or []) if r.get("rect")]
        sugg = [x for x in c.suggestions()                  # a removed field's box is not a missing field
                if not any(r["page"] == x["page"] and overlap(r["rect"], x["rect"]) >= CLAIM for r in gone)]
        return {"id": bid, "path": str(self.paths[bid]), "blank": str(c.blank) if c.blank else None, "sha": c.sha,
                "pages": c.pages, "fields": c.fields, "suggestions": sugg,
                "field_specs": {k: {x: v.get(x) for x in ("type", "semantic_type", "description", "x_petey_id") if v.get(x)}
                                for k, v in (c.bp.get("fields") or {}).items() if isinstance(v, dict)},
                "finder": "cached" if c.boxes is not None else "not run",
                "classifier": "cached" if c.cmap else "not cached", "has_widgets": bool(c.widgets),
                "added": rec.get("added") or [], "dismissed": rec.get("dismissed") or [],
                "removed": rec.get("removed") or [],
                "stale": bool(rec) and rec.get("blueprint_sha") != c.sha, "applied": rec.get("applied") or [],
                "semantic_types": registered_names(), "label_model": LABEL_MODEL,
                "plan": {k: v for k, v in plan(c.bp, rec.get("added") or [], rec.get("removed") or []).items()
                         if k != "fields"}}

    def page_png(self, bid: str, page: int) -> Optional[bytes]:
        key = (bid, page)
        if key not in self.png:
            blank = self.ctx(bid).blank
            if not blank or not blank.exists():
                return None
            doc = pymupdf.open(str(blank))
            try:
                if not 1 <= page <= len(doc):
                    return None
                self.png[key] = doc[page - 1].get_pixmap(dpi=DPI).tobytes("png")
            finally:
                doc.close()
        return self.png[key]

    def save(self, bid: str, body: dict) -> dict:
        c = self.ctx(bid)
        rec = load_record(bid)
        rec.update({"blueprint": str(self.paths[bid]), "form": c.path.stem, "blueprint_sha": c.sha,
                    "updated": time.strftime("%Y-%m-%d %H:%M:%S")})
        for k in ("added", "dismissed", "removed"):          # only what the caller sent: Review sends removals only
            if k in body:
                rec[k] = body[k] or []
        OUT.mkdir(parents=True, exist_ok=True)
        record_path(bid).write_text(json.dumps(rec, indent=1, ensure_ascii=False), encoding="utf-8")
        pl = plan(c.bp, rec.get("added") or [], rec.get("removed") or [])
        return {"saved": rec["updated"], "changes": pl["changes"], "errors": pl["errors"], "skipped": pl["skipped"]}


def summary() -> None:
    paths = blueprint_paths()
    print(f"{'blueprint':44} {'added':>5} {'dismissed':>9} {'applied':>7} {'stale':>5}  updated")
    n = 0
    for rp in sorted(OUT.glob("*.json")):
        rec = json.loads(rp.read_text(encoding="utf-8"))
        p = working_path(rp.stem, paths)
        if p is None:
            continue
        stale = rec.get("blueprint_sha") != _sha(p)
        print(f"{rp.stem[:44]:44} {len(rec.get('added') or []):5} {len(rec.get('dismissed') or []):9} "
              f"{sum(len(a.get('changes') or []) for a in rec.get('applied') or []):7} {'yes' if stale else '':>5}  "
              f"{rec.get('updated')}")
        n += 1
    if not n:
        print(f"no records yet under {OUT}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--port", type=int, default=5007)
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--plan", metavar="ID", help="print what --apply would add to this blueprint")
    ap.add_argument("--apply", metavar="ID", help="write the recorded fields into this blueprint")
    ap.add_argument("--no-open", action="store_true")
    args = ap.parse_args()
    if args.summary:
        summary()
        return 0
    if args.plan or args.apply:
        bid = args.plan or args.apply
        if bid not in blueprint_paths():
            raise SystemExit(f"no blueprint {bid!r} (ids look like lib__fw9, je__<form>, rl__<form>, fl__<form>)")
        if args.apply:
            apply(bid)
            return 0
        rec = load_record(bid)
        pl = plan(_load(working_path(bid)), rec.get("added") or [], rec.get("removed") or [])
        for c in pl["changes"] or ["nothing to add"]:
            print(f"  {c}")
        for s in pl["skipped"]:
            print(f"  skip {s}")
        for e in pl["errors"]:
            print(f"  ERROR {e}")
        return 0
    from petey.validate.blueprint_review import serve
    return serve(args.port, "add", not args.no_open)


if __name__ == "__main__":
    raise SystemExit(main())
