"""XFA template parser: what the publisher DECLARED about each field.

STRATEGY_v1 §3.5, rule zero: a form layer is derived, never re-authored.
On an XFA hybrid the publisher already wrote the field-level validation
that `semantic_types` otherwise infers from a slug — `picture` (shape),
`nullTest` (required), `items` (allowed values), `validate/message`
(what a violation means). This module reads the template packet and
`apply_declared` overlays those onto a bpt field spec. Declared beats
inferred.

Path join. AcroForm widget names on a Designer hybrid are the template's
SOM path in a fixed spelling:
  - named nodes index among same-named siblings: `Page1[0]`, `Amount[3]`
  - unnamed nodes are `#<class>[n]`, n counting ALL siblings of that
    class, named or not: `#subform[10]`, `#area[0]`, `#field[1]`
  - `.` inside a name is written `\\.`
  - an exclGroup is ONE AcroForm field (its member fields are the states)
  - master-page fields carry a per-page instance index (`Page1[10]`)
  - repeating-subform / table-row instances (`Row5[10]`) are not in the
    template; the template describes one occurrence.
`lookup` tries exact, then master-page index normalized, then an
index-stripped shape path. Measured across the 99 XFA PDFs in the corpus:
exact join covers ~95% of widget paths.

Picture clauses translate to regexes for TEXT fields only. Fields the
template declares as dates or numbers become `type: date` / `number`,
where the spec forbids `pattern` (§5.6); their pictures are kept verbatim
under `x_petey_xfa` so nothing declared is lost.

Parsing: lxml with `recover=True` and `{*}` wildcards — the packets
carry unbound prefixes that ElementTree rejects.
"""
from __future__ import annotations

import argparse
import collections
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Optional, Union

import pymupdf
from lxml import etree

CONTAINERS = ("subform", "field", "exclGroup", "area", "subformSet",
              "pageSet", "pageArea")
_PARSER = etree.XMLParser(recover=True, huge_tree=True)
_CLAUSE_RE = re.compile(r"^\s*(\w+)\s*(?:\(([^)]*)\))?\{(.*)\}\s*$", re.S)
_PAGE_INSTANCE_RE = re.compile(r"(#pageSet\[\d+\]\.[^.\[]+)\[\d+\]")
_INDEX_RE = re.compile(r"\[\d+\]")
_TAG_RE = re.compile(r"<[^>]+>")


def _ln(e) -> Optional[str]:
    return etree.QName(e).localname if isinstance(e.tag, str) else None


def _escape(name: str) -> str:
    return name.replace(".", "\\.")


def _clean(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    s = " ".join(_TAG_RE.sub(" ", s).replace("&#160;", " ").split())
    return s or None


def _text_of(e) -> Optional[str]:
    """All text under an element, html tags stripped."""
    if e is None:
        return None
    return _clean(etree.tostring(e, method="text", encoding="unicode"))


@dataclass
class XfaField:
    path: str
    name: str
    kind: str                       # text|date|num|check|excl|choice|signature|image|button|other
    ui: Optional[str] = None
    value_type: Optional[str] = None
    caption: Optional[str] = None
    tooltip: Optional[str] = None
    pictures: dict = field(default_factory=dict)   # format|ui|validate|bind -> [clause, ...]
    null_test: Optional[str] = None
    format_test: Optional[str] = None
    script_test: Optional[str] = None
    messages: dict = field(default_factory=dict)   # nullTest|formatTest|scriptTest -> text
    items: list = field(default_factory=list)      # export values
    item_labels: list = field(default_factory=list)  # choiceList display values
    members: list = field(default_factory=list)    # exclGroup: [{value, caption, name}]
    scripts: list = field(default_factory=list)    # [{where, activity, text}] for rule mining
    join: str = "exact"

    @property
    def required(self) -> bool:
        return self.null_test == "error"


# ---------------------------------------------------------------- pictures

def split_clauses(picture: str) -> list[tuple[str, str]]:
    """`text{999-99-9999}|text{999999999}` -> [(category, body), ...].

    A bare picture (no category) comes back as ("", body).
    """
    out = []
    depth = 0
    buf = ""
    for ch in picture:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == "|" and depth == 0:
            out.append(buf)
            buf = ""
        else:
            buf += ch
    out.append(buf)
    res = []
    for clause in out:
        m = _CLAUSE_RE.match(clause)
        if m:
            res.append((m.group(1), m.group(3)))
        elif clause.strip():
            res.append(("", clause.strip()))
    return res


def _runs(body: str) -> Iterator[tuple[str, str]]:
    """Yield (kind, text): ("lit", literal) or ("sym", run of one symbol)."""
    i = 0
    n = len(body)
    while i < n:
        ch = body[i]
        if ch == "'":
            j = body.find("'", i + 1)
            if j < 0:
                j = n
            yield ("lit", body[i + 1:j])
            i = j + 1
        elif ch == "\\" and i + 1 < n:
            yield ("lit", body[i + 1])
            i += 2
        elif ch.isalnum() or ch in "$,.":
            j = i
            while j < n and body[j] == ch:
                j += 1
            yield ("sym", body[i:j])
            i = j
        else:
            yield ("lit", ch)
            i += 1


_TEXT_SYM = {"9": r"\d", "A": r"[A-Za-z]", "O": r"[A-Za-z0-9]", "X": r"."}


def _text_re(body: str) -> str:
    parts = []
    for kind, run in _runs(body):
        if kind == "lit":
            parts.append(re.escape(run))
            continue
        sym = run[0]
        if sym in _TEXT_SYM:
            parts.append(_TEXT_SYM[sym] + (f"{{{len(run)}}}" if len(run) > 1 else ""))
        else:
            parts.append(re.escape(run))
    return "".join(parts)


def _date_re(body: str) -> str:
    parts = []
    for kind, run in _runs(body):
        if kind == "lit":
            parts.append(re.escape(run))
            continue
        sym, k = run[0], len(run)
        if sym == "Y":
            parts.append(r"\d{4}" if k >= 4 else r"\d{2}")
        elif sym in "MD":
            if k >= 3:
                parts.append(r"[A-Za-z]{3,}")
            elif k == 2:
                parts.append(r"\d{2}")
            else:
                parts.append(r"\d{1,2}")
        elif sym == "E":
            parts.append(r"[A-Za-z]+" if k >= 3 else r"\d")
        elif sym == "J":
            parts.append(r"\d{1,3}")
        elif sym == "G":
            parts.append(r"[A-Za-z]+")
        else:
            parts.append(re.escape(run))
    return "".join(parts)


def _time_re(body: str) -> str:
    parts = []
    for kind, run in _runs(body):
        if kind == "lit":
            parts.append(re.escape(run))
            continue
        sym, k = run[0], len(run)
        if sym in "HhKkMS":
            parts.append(r"\d{2}" if k >= 2 else r"\d{1,2}")
        elif sym == "F":
            parts.append(r"\d{1,%d}" % k)
        elif sym == "A":
            parts.append(r"[AaPp][Mm]")
        elif sym in "Zz":
            parts.append(r"[-+]?[\dZ:]*")
        else:
            parts.append(re.escape(run))
    return "".join(parts)


def _num_re(body: str) -> str:
    """Permissive regex for a num picture: grouping separators optional,
    sign and currency optional. Good enough to gate a displayed amount;
    number fields do not carry `pattern` in the bpt anyway."""
    int_syms = frac_syms = 0
    seen_radix = grouped = currency = percent = parens = False
    prefix_lits: list[str] = []
    suffix_lits: list[str] = []
    for kind, run in _runs(body):
        if kind == "lit":
            (suffix_lits if (int_syms or frac_syms) else prefix_lits).append(run)
            continue
        sym, k = run[0], len(run)
        if sym in "9zZ8":
            if seen_radix:
                frac_syms += k
            else:
                int_syms += k
        elif sym == "." or sym.lower() == "v":
            seen_radix = True
        elif sym == ",":
            grouped = True
        elif sym == "$":
            currency = True
        elif sym == "%":
            percent = True
        elif sym in "()":
            parens = True
        elif sym in "Ee":
            pass
    out = "".join(re.escape(x) for x in prefix_lits if x not in "()")
    if parens:
        out += r"\(?"
    out += r"[-+]?"  # a sign is displayed whether or not the picture reserves one
    if currency:
        out += r"\$?\s?"
    if grouped:
        out += r"\d{1,3}(?:,?\d{3})*"
    else:
        out += r"\d{1,%d}" % max(int_syms, 1)
    if seen_radix:
        out += r"(?:\.\d{0,%d})?" % max(frac_syms, 1) if frac_syms else r"\.?"
    if percent:
        out += r"\s?%"
    if parens:
        out += r"\)?"
    out += "".join(re.escape(x) for x in suffix_lits if x not in "()")
    return out


def clause_to_regex(category: str, body: str) -> Optional[str]:
    """One picture clause -> anchored regex, or None for zero/null clauses."""
    cat = category.lower()
    if cat in ("zero", "null"):
        return None
    if cat == "date":
        core = _date_re(body)
    elif cat == "time":
        core = _time_re(body)
    elif cat == "num":
        core = _num_re(body)
    elif cat == "datetime":
        core = r".+"
    else:
        core = _text_re(body)
    return f"^{core}$"


def picture_to_regex(picture: str, default_category: str = "text") -> Optional[str]:
    """Whole picture (alternatives joined with `|`) -> one anchored regex."""
    alts = []
    for cat, body in split_clauses(picture):
        r = clause_to_regex(cat or default_category, body)
        if r and r not in alts:
            alts.append(r)
    if not alts:
        return None
    if len(alts) == 1:
        return alts[0]
    return "^(?:" + "|".join(a[1:-1] for a in alts) + ")$"


def clause_categories(picture: str) -> set[str]:
    return {cat.lower() for cat, _ in split_clauses(picture) if cat}


# ---------------------------------------------------------------- template

def template_root(doc: pymupdf.Document):
    """The XFA template packet as an lxml root, or None."""
    try:
        cat = doc.pdf_catalog()
        t, af = doc.xref_get_key(cat, "AcroForm")
        if t == "xref":
            tx, arr = doc.xref_get_key(int(af.split()[0]), "XFA")
        else:
            tx, arr = doc.xref_get_key(cat, "AcroForm/XFA")
        if tx != "array":
            return None
        parts = dict(re.findall(r"\((\w+)\)\s*(\d+)\s+0\s+R", arr))
        if "template" not in parts:
            return None
        raw = doc.xref_stream(int(parts["template"]))
    except Exception:
        return None
    if not raw:
        return None
    return etree.fromstring(raw, _PARSER)


def _kind(node, ui_name: Optional[str], value_type: Optional[str],
          pictures: dict) -> str:
    if _ln(node) == "exclGroup":
        return "excl"
    if ui_name == "checkButton":
        return "check"
    if ui_name == "choiceList":
        return "choice"
    if ui_name == "dateTimeEdit":
        return "date"
    if ui_name == "numericEdit":
        return "num"
    if ui_name in ("signature", "imageEdit", "button", "barcode"):
        return {"signature": "signature", "imageEdit": "image",
                "button": "button", "barcode": "other"}[ui_name]
    if value_type == "date":
        return "date"
    if value_type in ("integer", "decimal", "float"):
        return "num"
    cats = set()
    for where in ("format", "validate", "ui"):
        for p in pictures.get(where, []):
            cats |= clause_categories(p)
    cats -= {"zero", "null"}
    if cats == {"date"}:
        return "date"
    if cats == {"num"}:
        return "num"
    return "text"


def _pictures(node) -> dict:
    out: dict[str, list[str]] = {}
    for where in ("ui", "format", "validate", "bind"):
        holder = node.find(f"{{*}}{where}")
        if holder is None:
            continue
        for p in holder.iter("{*}picture"):
            if p.text and p.text.strip():
                out.setdefault(where, []).append(p.text.strip())
    return out


def _items(node) -> tuple[list[str], list[str]]:
    """(export values, display labels). choiceList carries two lists; the
    `save="1"` one is what the widget stores."""
    lists = [e for e in node if _ln(e) == "items"]
    if not lists:
        return [], []
    def vals(lst):
        return [(c.text or "").strip() for c in lst if _ln(c)]
    saved = [l for l in lists if l.get("save") == "1"]
    if saved and len(lists) > 1:
        display = [l for l in lists if l is not saved[0]]
        return vals(saved[0]), vals(display[0])
    return vals(lists[0]), []


def _scripts(node, where: str) -> list[dict]:
    out = []
    for ev in node.findall("{*}event"):
        for sc in ev.findall("{*}script"):
            if sc.text and sc.text.strip():
                out.append({"where": where, "activity": ev.get("activity"),
                            "text": sc.text.strip()})
    for holder in ("validate", "calculate"):
        h = node.find(f"{{*}}{holder}")
        if h is None:
            continue
        for sc in h.findall("{*}script"):
            if sc.text and sc.text.strip():
                out.append({"where": where, "activity": holder,
                            "text": sc.text.strip()})
    return out


def _field_record(node, path: str) -> XfaField:
    name = node.get("name") or f"#{_ln(node)}"
    ui = node.find("{*}ui")
    ui_name = None
    if ui is not None:
        for c in ui:
            if _ln(c) and _ln(c) != "picture":
                ui_name = _ln(c)
                break
    value = node.find("{*}value")
    value_type = None
    if value is not None:
        for c in value:
            if _ln(c):
                value_type = _ln(c)
                break
    pictures = _pictures(node)
    f = XfaField(
        path=path, name=name,
        kind=_kind(node, ui_name, value_type, pictures),
        ui=ui_name, value_type=value_type, pictures=pictures,
        caption=_text_of(node.find("{*}caption/{*}value")),
        tooltip=_text_of(node.find("{*}assist/{*}toolTip")),
        scripts=_scripts(node, "field"),
    )
    v = node.find("{*}validate")
    if v is not None:
        f.null_test = v.get("nullTest")
        f.format_test = v.get("formatTest")
        f.script_test = v.get("scriptTest")
        msg = v.find("{*}message")
        if msg is not None:
            for t in msg.findall("{*}text"):
                txt = _clean(t.text)
                if txt:
                    f.messages[t.get("name") or "message"] = txt
    if f.kind == "excl":
        for m in node.findall("{*}field"):
            vals, _ = _items(m)
            f.members.append({
                "value": vals[0] if vals else None,
                "caption": _text_of(m.find("{*}caption/{*}value")),
                "name": m.get("name"),
                "tooltip": _text_of(m.find("{*}assist/{*}toolTip")),
            })
            f.scripts.extend(_scripts(m, "member"))
        f.items = [m["value"] for m in f.members if m["value"] is not None]
    else:
        f.items, f.item_labels = _items(node)
    return f


class XfaTemplate:
    def __init__(self, root, source: str = ""):
        self.root = root
        self.source = source
        self.fields: dict[str, XfaField] = {}
        self.form_name: Optional[str] = None
        self._shape: dict[str, list[str]] = {}
        self._walk(root, "")
        for p in self.fields:
            self._shape.setdefault(_INDEX_RE.sub("", p), []).append(p)

    def _walk(self, node, prefix: str) -> None:
        named: collections.Counter = collections.Counter()
        byclass: collections.Counter = collections.Counter()
        for ch in node:
            l = _ln(ch)
            if l not in CONTAINERS:
                continue
            name = ch.get("name")
            if name:
                seg = f"{_escape(name)}[{named[name]}]"
                named[name] += 1
            else:
                seg = f"#{l}[{byclass[l]}]"
            byclass[l] += 1
            path = f"{prefix}.{seg}" if prefix else seg
            if self.form_name is None and l == "subform" and name:
                self.form_name = name
            if l in ("field", "exclGroup"):
                self.fields[path] = _field_record(ch, path)
            if l != "field":
                self._walk(ch, path)

    def lookup(self, widget_path: Optional[str]) -> Optional[XfaField]:
        """Template record for an AcroForm widget path, or None."""
        if not widget_path:
            return None
        f = self.fields.get(widget_path)
        if f is not None:
            return f
        alt = _PAGE_INSTANCE_RE.sub(r"\1[0]", widget_path)
        f = self.fields.get(alt)
        if f is not None:
            return _joined(f, "page_instance")
        cands = self._shape.get(_INDEX_RE.sub("", widget_path))
        if cands:
            return _joined(self.fields[cands[0]], "shape")
        return None

    def census(self) -> dict:
        c: collections.Counter = collections.Counter()
        for f in self.fields.values():
            c["fields"] += 1
            c[f"kind:{f.kind}"] += 1
            if f.pictures:
                c["with_picture"] += 1
            if f.required:
                c["required"] += 1
            if f.items and f.kind in ("choice", "excl"):
                c["with_values"] += 1
            if f.messages:
                c["with_message"] += 1
            if f.scripts:
                c["with_script"] += 1
        return dict(c)


def _joined(f: XfaField, how: str) -> XfaField:
    g = XfaField(**{k: v for k, v in f.__dict__.items()})
    g.join = how
    return g


def parse(pdf: Union[str, Path, pymupdf.Document]) -> Optional[XfaTemplate]:
    """Parse the XFA template of a PDF. None when there is no template."""
    close = False
    doc = pdf
    if not isinstance(pdf, pymupdf.Document):
        doc = pymupdf.open(str(pdf))
        close = True
    try:
        root = template_root(doc)
        if root is None:
            return None
        return XfaTemplate(root, source=str(getattr(doc, "name", "")))
    finally:
        if close:
            doc.close()


# ---------------------------------------------------------------- rules

_CLEAR_RE = re.compile(
    r"([\w\.\[\]#\\]+)\.rawValue\s*=\s*(?:0|null|\"\"|''|\"Off\")\s*;?")


def _resolve_ref(ref: str, origin: XfaField, t: "XfaTemplate",
                 by_leaf: dict) -> Optional[str]:
    """A script reference (`married`, `Page1.married`, `this.parent.x`)
    -> template path. Siblings of the scripted field first, then a
    unique leaf name anywhere; ambiguous names are skipped."""
    leaf = ref.split(".")[-1].split("[")[0].lower()
    if leaf in ("this", "parent", "xfa", "form"):
        return None
    cands = by_leaf.get(leaf) or []
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    parent = origin.path.rsplit(".", 1)[0]
    sib = [p for p in cands if p.rsplit(".", 1)[0] == parent]
    return sib[0] if len(sib) == 1 else None


def mutex_groups(t: "XfaTemplate") -> list[list[str]]:
    """Reciprocal clear-others groups mined from field scripts.

    A clears B (`B.rawValue = 0`) is not enough — publishers copy scripts
    between forms (526EZ carries 19 that name fields it does not have).
    A and B form a group only when each clears the other; the group is
    the pair plus every field both clear. Returns lists of template
    paths, size >= 2, one per distinct group.
    """
    by_leaf: dict[str, list[str]] = {}
    for p, f in t.fields.items():
        by_leaf.setdefault(f.name.lower(), []).append(p)
    clears: dict[str, set[str]] = {}
    for p, f in t.fields.items():
        for s in f.scripts:
            for m in _CLEAR_RE.finditer(s["text"]):
                target = _resolve_ref(m.group(1), f, t, by_leaf)
                if target and target != p:
                    clears.setdefault(p, set()).add(target)
    groups: set[frozenset] = set()
    for a, ts in clears.items():
        for b in ts:
            if a in clears.get(b, ()):
                groups.add(frozenset({a, b} | (ts & clears[b])))
    # Members must share a kind. A checkbox that clears a block of text
    # fields, which in turn clear it ("same as physical address"), is
    # reciprocal but is a toggle, not a mutex: on a normal fill most of
    # its members hold a value at once.
    out = []
    for g in groups:
        if len(g) < 2:
            continue
        kinds = {t.fields[p].kind for p in g}
        if len(kinds) == 1:
            out.append(sorted(g))
    return sorted(out)


# ---------------------------------------------------------------- overlay

def choices_description(choices: dict) -> str:
    """`{"0": "FEMALE", "1": "MALE"}` -> 'One of: 0 = FEMALE; 1 = MALE'."""
    return "One of: " + "; ".join(f"{k} = {v}" for k, v in choices.items() if v)


def declared_pattern(f: XfaField) -> tuple[Optional[str], Optional[str]]:
    """(regex, source picture) for a TEXT field. Display form (`format`)
    first, then the validate picture, then the accepted-input alternatives
    in `ui` — the displayed value is one of those when nothing reformats it."""
    for where in ("format", "validate", "ui"):
        for pic in f.pictures.get(where, []):
            r = picture_to_regex(pic, "text")
            if r:
                return r, pic
    return None, None


def apply_declared(spec: dict, f: XfaField) -> list[str]:
    """Overlay the publisher's declarations onto a bpt field spec.

    Returns the keys that changed. Rules, in order:
      date kind   -> type date, pattern dropped (spec §5.6 forbids it)
      num kind    -> type number, pattern dropped
      text kind with a picture -> type string, pattern from the picture
      choice      -> type category, values = export items
      excl        -> values recorded; the emitter's AcroForm on-states stay
      nullTest="error" -> required
      validate message -> description when the field has none
    `semantic_type` is left alone: it is advisory (§5.8) and `pattern`
    governs where they disagree.
    """
    changed: list[str] = []
    x: dict = {"kind": f.kind}
    if f.join != "exact":
        x["join"] = f.join

    def set_(k, v):
        if spec.get(k) != v:
            spec[k] = v
            changed.append(k)

    if f.kind == "date":
        set_("type", "date")
        if spec.pop("pattern", None) is not None:
            changed.append("pattern")
    elif f.kind == "num":
        set_("type", "number")
        if spec.pop("pattern", None) is not None:
            changed.append("pattern")
    elif f.kind == "text":
        regex, pic = declared_pattern(f)
        if regex:
            set_("type", "string")
            set_("pattern", regex)
            x["picture"] = pic
    elif f.kind == "choice" and f.items:
        set_("type", "category")
        set_("values", list(f.items))
        spec.pop("pattern", None)
        if f.item_labels:
            x["labels"] = dict(zip(f.items, f.item_labels))
    elif f.kind == "excl":
        # On a Designer hybrid the AcroForm appearance states are the
        # members' ordinals (0..n-1) in template order, while the XFA
        # item values are what the data packet stores. The extractor
        # reads the appearance state, so `values` keeps the on-states;
        # the declared captions are paired by position when the states
        # are ordinals, else by declared value.
        states = spec.get("values") or []
        # A shape-fallback join (index-stripped path) lands on a same-named
        # SIBLING group: on 526EZ page 13 the branch-of-service group
        # (8 states) and the checking/savings group both resolved to the
        # first RadioButtonList, a yes/no, and wore its captions. Declared
        # captions are applied only from an exact or page-instance join,
        # and only when the state count matches the member count.
        trusted = getattr(f, "join", None) != "shape" and not (states and len(states) != len(f.members))
        # caption > declared value when it is a word (YES / NO) > member
        # name. 10-10EZ's section 2 members have no caption, values YES /
        # NO and names YES4 / NO4; the name is the template's, not the page's.
        def _cap(m):
            v = m.get("value")
            if m.get("caption"):
                return m["caption"]
            if v and not str(v).isdigit():
                return str(v)
            return m.get("name")
        caps = [_cap(m) for m in f.members] if trusted else []
        if not trusted:
            x["choices"] = {}
        elif states and len(states) == len(caps) and \
                list(states) == [str(i) for i in range(len(caps))]:
            x["choices"] = dict(zip(states, caps))
        else:
            x["choices"] = {m["value"]: _cap(m)
                            for m in f.members if m["value"] is not None}
            if not states and f.items:
                set_("type", "category")
                set_("values", list(f.items))
        # The values are appearance states ("0", "1"); a reader that goes
        # by meaning needs the captions to pick one. Publisher text, so it
        # belongs in the description when nothing better is there.
        if x["choices"] and not spec.get("description"):
            set_("description", choices_description(x["choices"]))
            spec["x_petey_description_source"] = "xfa_choices"

    for where in ("format", "validate", "ui"):
        if f.pictures.get(where):
            x.setdefault("pictures", {})[where] = f.pictures[where]
    if f.required:
        set_("required", True)
    elif f.null_test:
        x["null_test"] = f.null_test
    msg = f.messages.get("formatTest") or f.messages.get("nullTest") \
        or f.messages.get("scriptTest") or next(iter(f.messages.values()), None)
    if msg:
        x["message"] = msg
        if not spec.get("description"):
            set_("description", msg)
            spec["x_petey_description_source"] = "xfa_message"

    if any(k in changed for k in ("pattern", "required", "values", "type")):
        spec["x_petey_validation_source"] = "xfa"
    if len(x) > 1:  # something declared, not just the kind
        spec["x_petey_xfa"] = x
    return changed


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="Census of what an XFA template declares.")
    ap.add_argument("pdf", type=Path, nargs="+")
    ap.add_argument("--json", action="store_true", help="dump parsed fields as JSON")
    ap.add_argument("--join", action="store_true", help="report widget-path join coverage")
    args = ap.parse_args()
    for pdf in args.pdf:
        t = parse(pdf)
        if t is None:
            print(f"{pdf}: no XFA template")
            continue
        print(f"{pdf}: root={t.form_name} {t.census()}")
        if args.join:
            doc = pymupdf.open(str(pdf))
            paths = [w.field_name for pg in doc for w in pg.widgets()]
            doc.close()
            how = collections.Counter()
            for p in set(paths):
                f = t.lookup(p)
                how[f.join if f else "miss"] += 1
            print(f"  join over {len(set(paths))} widget paths: {dict(how)}")
        if args.json:
            print(json.dumps([f.__dict__ for f in t.fields.values()], indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
