"""Derive a field slug from the publisher's own AcroForm name, deterministically.

The AcroForm name is embedded in the document by whoever built the form, so
where it is prose it is the most authoritative naming evidence available --
better than a tooltip (written for a human, often an instruction) and better
than printed text nearby (an inference from proximity). It was previously
passed to the labeler as `"path"`, an opaque id, and the model was free to
invent something else; the only check was a fuzzy oracle comparing the two
afterwards, which cannot tell `Print Name_2` from `print_name_2_nm`.

Deriving the slug instead of checking it removes the oracle from the loop:
agreement is true by construction for every field this module names.

Not every AcroForm name can be canon, so the first job is classification:

    prose             DescriptionOfMerchandise5, netIncomeAmt, TP_EMAIL
    positional+prose  Pt8Line44_YesNo, Policy_GeneralLiability_EffectiveDate
    positional        CRP14L5, 697172aaa, Line40Amount3
    caption           "Enclose Schedule Y", "Add lines 43 through 47"
    generic           "Yes", "Group39", "Reason Button"
    opaque            Text16, f1_07, topmostSubform[0].Page1[0].f1_01[0]

Only `prose` and `positional+prose` are nameable here. The rest fall through
to the tooltip, the Sensible vocabulary, the text labeler and finally the VLM
-- in that order, VLM last.

Usage:
    python publisher_name.py                 # coverage over the library
    python publisher_name.py --sample prose  # inspect one bucket
"""
from __future__ import annotations

import argparse
import collections
import random
import re
from pathlib import Path

import yaml

from petey.validate.correct import (_ABBREV, _STOP, _SUFFIX_WORDS, _tokens,
                     is_readable, leaf)

# Split letter/digit boundaries, so `Name22` and `value7` read as a
# generic word plus an ordinal rather than as one coined word. This is
# deliberately NOT done in `correct._tokens`: there, digits are what
# distinguish sibling widgets, and relaxing them costs more precision
# than it buys reach (see oracle_null.py).

from petey.paths import BLUEPRINTS
_ORDINAL_BOUNDARY = re.compile(
    r"(?<=[A-Za-z])(?=[0-9])|(?<=[0-9])(?=[A-Za-z])")


def _name_tokens(s: str) -> set[str]:
    return _tokens(_ORDINAL_BOUNDARY.sub(" ", s))

HERE = Path(__file__).resolve().parent

# A structural reference to a place on the form: box, line, part, page. These
# name WHERE the widget is, which the blueprint already records in `widget`.
POSITIONAL = re.compile(
    r"(?:^|[^a-z])(?:pt|part|line|box|item|page|p|q|row|col|sec|section|"
    r"chk|cb|group|grp|btn|button)\s*[_-]?\d", re.I)

# Prose that instructs a human rather than naming a field. A field name does
# not contain a verb in the imperative.
INSTRUCTION = re.compile(
    r"\b(?:enclose|enter|add|see|attach|check|subtract|multiply|combine|"
    r"through|instructions?|list|complete|sign|print|include|write)\b", re.I)

# Words that carry no field identity on their own. `Yes` names a widget in a
# mutex group; the group is what has meaning.
GENERIC = {
    "yes", "no", "yesno", "onoff", "off", "on", "value", "text", "field",
    "data", "other", "misc", "blank", "none", "temp", "item", "entry",
    "button", "reason", "group", "box", "check", "fill", "input",
}

# Names that are machine-generated and carry nothing, beyond what
# `is_readable` already rejects.
GENERATED = re.compile(
    r"^(?:text|txt|field|fld|form|check|cb|chk|radio|rb|button|btn|sig|"
    r"untitled|undefined|copy|dup)[\s_-]*\d*$", re.I)


def classify(name: str) -> str:
    """Which kind of name is this? Only prose kinds can be canon."""
    lf = leaf(name)
    if not lf or not is_readable(lf) or GENERATED.match(lf.strip()):
        return "opaque"
    words = [w for w in re.split(r"[^A-Za-z]+", lf) if len(w) > 1]
    # A long phrase is a caption, not a name; so is anything imperative.
    if INSTRUCTION.search(lf) or len(words) > 5:
        return "caption"
    toks = {t for t in _name_tokens(lf) - _STOP if not t.isdigit()}
    if not toks or toks <= GENERIC:
        return "generic"
    if POSITIONAL.search(lf):
        # Positional AND carrying prose is still usable: strip the box
        # reference and see whether anything meaningful survives.
        rest = {t for t in _name_tokens(POSITIONAL.sub(" ", lf)) - _STOP
                if t not in GENERIC and not t.isdigit()}
        return "positional+prose" if rest else "positional"
    return "prose"


NAMEABLE = ("prose", "positional+prose")


# Path components that describe the PDF's internal structure rather than the
# field. XFA forms bury every name under these.
# Kept deliberately narrow. An earlier version also held `entry`, `item`,
# `value` and `section`, which deleted real fields: `entryno` on CBP 7501 is
# THE entry number, and it reduced to `number`.
_STRUCTURAL = {
    "topmostsubform", "subform", "form", "form1", "page", "pg", "sheet",
    "body", "root", "main", "container", "layer", "copy", "tbl", "table",
    "hdr", "header", "grp",
}

# The convention: a slug ends in a short type marker. `_SUFFIX_WORDS` maps
# the marker to the word; this is the direction we need, word -> marker.
_SUFFIX_FOR = {
    "name": "nm", "date": "dt", "amount": "amt", "code": "cd",
    "number": "nbr", "indicator": "ind", "quantity": "qty",
    "percent": "pct", "count": "cnt", "text": "txt", "year": "yr",
    "month": "mo", "day": "dy", "description": "txt", "telephone": "nbr",
    "zipcode": "cd", "birthdate": "dt", "signature": "dt",
}

# Type markers the labeler writes that carry no word of their own.
_BARE_MARKERS = set(_SUFFIX_FOR.values()) | {"no", "num", "addr", "id"}


# Connectives, which a slug drops. Narrower than `correct._STOP` on purpose:
# that set also holds `name` / `date` / `number`, which we need, because they
# are what tells us which type marker to write.
_CONNECTIVE = {
    "the", "of", "a", "an", "and", "or", "for", "to", "in", "on", "at", "by",
    "is", "are", "was", "with", "from", "this", "that", "please", "if",
}

# Abbreviations publishers glue into compounds, beyond `correct._ABBREV`.
_MORE_ABBREV = {
    "rpt": "report", "spons": "sponsor", "spon": "sponsor", "admin":
    "administrator", "tp": "taxpayer", "sig": "signature", "eff": "effective",
    "exp": "expiration", "prem": "premium", "cov": "coverage", "pol":
    "policy", "clm": "claim", "veh": "vehicle", "drv": "driver", "bus":
    "business", "res": "residence", "occ": "occupation", "yr": "year",
    "bal": "balance", "eoy": "end_of_year", "boy": "begin_of_year", "int":
    "interest", "govt": "government", "sec": "securities", "cont": "contribution",
    "contrib": "contribution", "trans": "transfer", "num": "number", "dep": "depreciation", "wlfr": "welfare", "pen":
    "pension", "cba": "collective_bargaining_agreement",
}


def _depluralize(w: str) -> str:
    if len(w) <= 3 or w.endswith("ss"):
        return w
    if w.endswith("ies"):
        return w[:-3] + "y"
    if w.endswith(("ses", "xes", "ches", "shes")):
        return w[:-2]
    return w[:-1] if w.endswith("s") else w


def _vocab() -> set[str]:
    """Words the library actually uses, for segmenting glued compounds.

    Data-driven rather than hand-listed: a compound like `impcarrier` splits
    on words that already appear in our own field names, so the segmenter
    grows with the library instead of needing maintenance.
    """
    counts: collections.Counter = collections.Counter()
    for bpf in (BLUEPRINTS).glob("*.bpt"):
        try:
            bp = yaml.safe_load(bpf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(bp, dict):
            continue
        for n in (bp.get("fields") or {}):
            for w in str(n).split("_"):
                if len(w) >= 3 and w.isalpha():
                    counts[w] += 1
    # Threshold 2, not 3: a word used on one form twice (`export` on
    # CBP 7501) still has to be segmentable. Junk risk stays low
    # because `_segment` requires the WHOLE word to cover.
    return {w for w, c in counts.items() if c >= 2}


_VOCAB: set[str] | None = None


def _segment(word: str) -> list[str]:
    """Split a glued compound on known words, longest match first.

    `impcarrier` -> [importing, carrier] once `imp` expands. Returns the
    word unchanged unless the WHOLE string segments, so a partial match
    cannot manufacture a name out of noise.
    """
    global _VOCAB
    if len(word) < 6 or word in (_VOCAB if _VOCAB is not None else ()):
        return [word]
    if _VOCAB is None:
        _VOCAB = _vocab()
    if word in _VOCAB:
        return [word]
    known = (_VOCAB | set(_ABBREV) | set(_MORE_ABBREV)
             | _BARE_MARKERS | set(_SUFFIX_WORDS))
    n = len(word)
    # Shortest segmentation that covers the whole word; ties prefer longer
    # leading pieces, which is what `imp|carrier` needs over `imp|car|rier`.
    best: list[list[str] | None] = [None] * (n + 1)
    best[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - 14), i):
            if best[j] is None:
                continue
            piece = word[j:i]
            short_ok = len(piece) == 2 and piece in _BARE_MARKERS and i == n
            if (len(piece) >= 3 or short_ok) and piece in known:
                cand = best[j] + [piece]
                if best[i] is None or len(cand) < len(best[i]):
                    best[i] = cand
    return best[n] if best[n] and len(best[n]) > 1 else [word]


def _words(name: str) -> list[str]:
    """Ordered words from a publisher name, abbreviations expanded."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    spaced = _ORDINAL_BOUNDARY.sub(" ", spaced)
    out: list[str] = []
    for raw in re.split(r"[^A-Za-z0-9]+", spaced.lower()):
        if not raw:
            continue
        for piece in _segment(raw):
            w = _MORE_ABBREV.get(piece, _ABBREV.get(piece, piece))
            w = _SUFFIX_WORDS.get(w, w)
            w = _depluralize(w)
            # An expansion can itself be multi-word (`eoy` -> end_of_year),
            # so connectives are dropped AFTER splitting, not before.
            out.extend(x for x in w.split("_") if x and x not in _CONNECTIVE)
    return out


def derive_slug(path: str, declared_type: str | None = None) -> str | None:
    """The publisher's own name for this widget, in our convention.

    Returns None when the name is not one this module can be canon for --
    see `classify`. Callers fall through to the tooltip, the Sensible
    vocabulary, the text labeler and the VLM, in that order.

    The point is that agreement with the publisher becomes true by
    construction, so no fuzzy referee sits between the two names.
    """
    kind = classify(path)
    if kind not in NAMEABLE:
        return None
    lf = leaf(path)
    if kind == "positional+prose":
        # Drop the box/line/part reference: it names WHERE the widget sits,
        # which `widget` already records. Leaving it in produced slugs like
        # `p_line_outcome_dt_3` from `P12_Line29_Outcome3` -- the prose
        # survived but arrived behind two meaningless tokens.
        lf = POSITIONAL.sub(" ", lf)
    words = _words(lf)

    # Strip structural scaffolding, but only while it is a PREFIX: a word
    # like `section` can be the field itself further in.
    while words and words[0] in _STRUCTURAL:
        words.pop(0)
    # A trailing ordinal is the sibling index; hold it aside so the type
    # marker lands before it, as the convention writes it.
    ordinal = None
    while words and words[-1].isdigit():
        ordinal = words.pop()
    words = [w for w in words if w not in _STRUCTURAL and not w.isdigit()]
    if not words:
        return None

    # Collapse immediate repeats (`name_name`) and any duplicate word.
    seen: set[str] = set()
    kept = [w for w in words if not (w in seen or seen.add(w))]

    # The last word usually states the type; fold it into the marker rather
    # than writing it twice (`postal_code` -> `postal_cd`, not
    # `postal_code_cd`).
    marker = None
    if kept[-1] in _SUFFIX_FOR and len(kept) > 1:
        marker = _SUFFIX_FOR[kept.pop()]
    elif declared_type in ("boolean",):
        marker = "ind"
    elif declared_type in ("date",):
        marker = "dt"

    parts = [w for w in kept if w not in _BARE_MARKERS] or kept
    slug = "_".join(parts)
    if marker:
        slug += f"_{marker}"
    if ordinal:
        slug += f"_{ordinal}"
    return re.sub(r"_+", "_", slug).strip("_") or None


# The last word of a publisher name states what the field HOLDS. This is the
# part of the name the publisher is reliably authoritative about -- unlike the
# entity, which the name often omits entirely (`Pt7Line3_ZipCode` does not say
# whose zip) and which the labeler gets from the page.
_ASSERTS_TYPE = {
    "date": "date", "dt": "date", "year": "integer", "yr": "integer",
    "month": "integer", "day": "integer",
    "amount": "number", "amt": "number", "total": "number",
    "rate": "number", "premium": "number", "balance": "number",
    "percent": "number", "pct": "number",
    "count": "integer", "cnt": "integer", "quantity": "integer",
    "qty": "integer", "number": "string", "nbr": "string", "no": "string",
    "code": "string", "cd": "string", "name": "string", "nm": "string",
    "text": "string", "txt": "string", "description": "string",
    "checkbox": "boolean", "check": "boolean", "yesno": "boolean",
    "indicator": "boolean", "ind": "boolean", "signature": "string",
    "email": "string", "telephone": "string", "phone": "string",
    "zipcode": "string", "address": "string", "city": "string",
    "state": "string", "initial": "string",
}


def asserted_type(path: str) -> str | None:
    """The bpt `type` the publisher's own name implies, or None.

    Deliberately narrow: only the FINAL word counts, because that is what
    names the content. `EffectiveDate` asserts date; `DateSignedYear`
    asserts integer, not date.
    """
    lf = leaf(path)
    if not lf or not is_readable(lf):
        return None
    words = _words(lf)
    while words and words[-1].isdigit():
        words.pop()
    if not words:
        return None
    # `YesNo` is a mutex pair, not the word "number". Without this the whole
    # i-485 family read as 395 boolean->string contradictions, all spurious.
    # `_words` has already expanded `no` to `number` by the time we see it,
    # so both spellings have to be checked.
    if len(words) >= 2 and words[-2:] in (["yes", "no"], ["yes", "number"]):
        return "boolean"
    return _ASSERTS_TYPE.get(words[-1])


# An ordinal the publisher separated from the stem: `insBrokerName_03`, not
# the trailing digit of `descriptiona1`, which is part of a COLUMN id.
_ORD_SUFFIX = re.compile(r"^(?P<stem>.*?)[ _-](?P<ord>\d{1,3})$")


def _block_key(lf: str) -> tuple[str, int] | None:
    m = _ORD_SUFFIX.match(lf.strip())
    return (m.group("stem").lower(), int(m.group("ord"))) if m else None


def _slug_ordinal(field: str) -> int | None:
    """The row index OUR slug claims, if it carries one."""
    m = re.search(r"_(\d{1,3})[a-z]?(?:_|$)", field)
    return int(m.group(1)) if m else None


def repeating_blocks(bp: dict, min_members: int = 3
                     ) -> list[tuple[str, list[tuple[int, str]]]]:
    """Groups of publisher names identical but for a separated ordinal.

    This is the only safe way to read a row index off a publisher name, and
    it took two wrong tries to get here. Comparing any trailing digit found
    77.8% "disagreement" because IRS names like `f1_6` and `c2_1` are
    sequential widget indices. Using the XFA subscript is worse: on cbp7501
    every widget in a column is `descriptiona1[0..N]` and the subscripts do
    not follow row order at all -- `manifest_qty_row5` is [2] while `row1` is
    [6].

    A run of >=3 distinct ordinals over one stem is different. It means the
    publisher laid out a repeating block and numbered it, so the number IS
    the row.
    """
    groups: dict[str, list[tuple[int, str]]] = collections.defaultdict(list)
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        w = spec.get("widget")
        path = w.get("path") if isinstance(w, dict) else None
        if not path or classify(path) != "prose":
            continue
        key = _block_key(leaf(path))
        if key:
            groups[key[0]].append((key[1], str(name)))
    out = []
    for stem, members in groups.items():
        ords = sorted({o for o, _ in members})
        if len(ords) < min_members:
            continue
        # A run, allowing the odd gap: 1,2,3,4,5 or 1,2,3,5.
        if ords[-1] - ords[0] > len(ords) * 2:
            continue
        out.append((stem, sorted(members)))
    return sorted(out)


def block_verdict(members: list[tuple[int, str]]) -> str:
    """Does our numbering of this block contradict the publisher's?

    Disagreeing ordinals are not enough. Two innocent patterns produce them:

      base offset   the publisher counts from 0 and we count from 1. i-9's
                    `Addtl Info 0/1/2` against `additional_information_1/2/3`
                    is correct labelling and was 104 of the first 194 hits.
      2D block      the publisher numbers CELLS across a grid while we name
                    them semantically. form_1005's `Past Year_1..8` covers
                    (year, base pay, overtime) x 2 years, so our ordinals
                    repeat 1,2,1,2 legitimately.

    What is NOT innocent is our sequence RESTARTING inside one publisher
    block while every member names the same thing, which means two rows claim
    the same index -- f5500sa numbers the publisher's brokers 3..7 as 1..5
    while brokers 1..2 already hold those indices.
    """
    pairs = [(o, _slug_ordinal(n)) for o, n in sorted(members)]
    pairs = [(o, s_) for o, s_ in pairs if s_ is not None]
    if len(pairs) < 3:
        return "too few"

    # A GRID, not a series. When the publisher numbers cells across a table
    # our slugs name them semantically, so several distinct stems each carry
    # the SAME small ordinal set. form_1005's `Past Year_1..8` covers base
    # pay, overtime, commissions and bonus x two years, so
    # base_pay_past_year_{1,2}, overtime_past_year_{1,2} and the rest all
    # hold {1, 2} -- correct labelling that this check must not touch. It
    # renamed overtime_past_year_1_amt to _5_amt before this guard existed.
    #
    # A real restart looks different: the stems partition the publisher's
    # range into UNEQUAL pieces. On 2025-schedule-a one family holds {1, 2}
    # and the other {1, 2, 3, 4, 5}.
    by_stem: dict[str, set[int]] = collections.defaultdict(set)
    for o, n in sorted(members):
        so = _slug_ordinal(n)
        if so is None:
            continue
        by_stem[re.sub(r"_\d{1,3}(?=[a-z]?(?:_|$))", "_", str(n), count=1)
                ].add(so)
    sets = list(by_stem.values())
    if len(sets) >= 2 and all(x == sets[0] for x in sets):
        return "grid"
    offsets = {o - s_ for o, s_ in pairs}
    if len(offsets) == 1:
        return "consistent offset"      # includes the 0-vs-1 base case
    ours = [s_ for _, s_ in pairs]
    if ours == sorted(ours):
        return "monotonic"              # ordered, just not evenly offset
    return "RESTARTS"


def _report_blocks(args) -> int:
    """Where our row index disagrees with the publisher's."""
    tot = bad = 0
    byform: collections.Counter = collections.Counter()
    ex: list[tuple[str, str, str, int, int]] = []
    for bpf in sorted(args.dir.glob("*.bpt")):
        try:
            bp = yaml.safe_load(bpf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(bp, dict):
            continue
        for stem, members in repeating_blocks(bp):
            verdict = block_verdict(members)
            for o, name in members:
                so = _slug_ordinal(name)
                if so is None:
                    continue
                tot += 1
                if so != o and verdict == "RESTARTS":
                    bad += 1
                    byform[bpf.stem] += 1
                    ex.append((bpf.stem, name, stem, o, so))
    print(f"fields inside a detected repeating block, carrying both "
          f"ordinals: {tot}")
    print(f"  our numbering RESTARTS inside a publisher block: {bad} "
          f"({bad/max(tot,1)*100:.1f}%) across {len(byform)} forms")
    print("  (consistent offsets and monotonic runs are excluded — a 0-based "
          "publisher\n   against 1-based slugs is correct labelling)\n")
    for f, c in byform.most_common(12):
        print(f"    {f:26s} {c:4d}")
    print()
    for form, name, stem, o, so in ex[:18]:
        print(f"    {form:18s} {name[:38]:38s} ours={so:<3d} "
              f"publisher={o:<3d} ({stem})")
    return 0


def _report_types(args) -> int:
    """Where does the publisher's name contradict the declared type?

    This is `mistyped_field` with an independent witness. The blueprint's
    type came from the labeler's inference; the assertion here came from the
    document. Where they disagree, the document wins.
    """
    tally: collections.Counter = collections.Counter()
    clashes: list[tuple[str, str, str, str, str]] = []
    for bpf in sorted(args.dir.glob("*.bpt")):
        try:
            bp = yaml.safe_load(bpf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(bp, dict):
            continue
        for n, spec in (bp.get("fields") or {}).items():
            if not isinstance(spec, dict):
                continue
            w = spec.get("widget")
            path = w.get("path") if isinstance(w, dict) else None
            if not path:
                continue
            want = asserted_type(path)
            if not want:
                tally["no_assertion"] += 1
                continue
            have = spec.get("type") or "string"
            tally["asserted"] += 1
            if have == want:
                tally["agrees"] += 1
            else:
                tally["contradicts"] += 1
                clashes.append((bpf.stem, str(n), have, want, leaf(path)))

    a = tally["asserted"]
    print(f"fields whose publisher name asserts a type: {a} "
          f"(no assertion: {tally['no_assertion']})")
    print(f"  declared type agrees:      {tally['agrees']:5d} "
          f"{tally['agrees']/a*100:5.1f}%")
    print(f"  declared type CONTRADICTS: {tally['contradicts']:5d} "
          f"{tally['contradicts']/a*100:5.1f}%")
    by_form = collections.Counter(c[0] for c in clashes)
    print(f"  across {len(by_form)} forms; worst: "
          + ", ".join(f"{f} {c}" for f, c in by_form.most_common(6)))
    pairs = collections.Counter((c[2], c[3]) for c in clashes)
    print("\n  declared -> asserted")
    for (h, wt), c in pairs.most_common(10):
        print(f"    {h:10s} -> {wt:10s} {c:5d}")
    random.Random(args.seed).shuffle(clashes)
    print("\n--- 20 contradictions ---")
    for f, n, have, want, lf in clashes[:20]:
        print(f"  {f:13s} {n[:30]:30s} {have:8s} -> {want:8s}  {lf[:24]}")
    return 0


def _report_derived(args) -> int:
    """Derive a slug for every nameable field; compare with the library's.

    Three verdicts, and the distinction matters:

      same        the labeler already wrote the publisher's name. Deriving
                  it costs nothing and removes a model call.
      equivalent  same words, different order or type marker. A convention
                  difference, not an error -- but deriving makes it uniform.
      differs     different words. Either the labeler read the page and
                  disagreed, or the publisher's name is misleading. This is
                  the only bucket that needs adjudication.
    """
    from petey import semantic_types as st

    tally: collections.Counter = collections.Counter()
    diffs: list[tuple[str, str, str, str]] = []
    for bpf in sorted(args.dir.glob("*.bpt")):
        try:
            bp = yaml.safe_load(bpf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(bp, dict):
            continue
        for n, spec in (bp.get("fields") or {}).items():
            if not isinstance(spec, dict):
                continue
            w = spec.get("widget")
            path = w.get("path") if isinstance(w, dict) else None
            if not path:
                continue
            got = derive_slug(path, spec.get("type"))
            if not got:
                tally["not_nameable"] += 1
                continue
            tally["derived"] += 1
            if st.lookup(got):
                tally["registry_classifies"] += 1
            if st.lookup(str(n)) and not st.lookup(got):
                tally["lost_semantic_type"] += 1
            if got == n:
                tally["same"] += 1
            elif set(got.split("_")) == set(str(n).split("_")):
                tally["equivalent"] += 1
            else:
                tally["differs"] += 1
                diffs.append((bpf.stem, str(n), got, leaf(path)))

    d = tally["derived"]
    print(f"nameable fields: {d}   (not nameable: {tally['not_nameable']})\n")
    for k in ("same", "equivalent", "differs"):
        print(f"  {k:22s} {tally[k]:6d}  {tally[k]/d*100:5.1f}%")
    print(f"\n  registry assigns a semantic_type to "
          f"{tally['registry_classifies']} ({tally['registry_classifies']/d*100:.0f}%)")
    print(f"  the library slug resolves but the derived one does not: "
          f"{tally['lost_semantic_type']}")
    random.Random(args.seed).shuffle(diffs)
    print("\n--- 30 that differ: library slug | DERIVED | publisher name ---")
    for f, n, got, lf in diffs[:30]:
        print(f"  {f:13s} {n[:31]:31s} | {got[:31]:31s} | {lf[:22]}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", type=Path, default=BLUEPRINTS)
    ap.add_argument("--sample", help="print 25 examples from this bucket")
    ap.add_argument("--blocks", action="store_true",
                    help="repeating blocks whose row index disagrees with "
                         "the publisher's")
    ap.add_argument("--types", action="store_true",
                    help="where the publisher name contradicts declared type")
    ap.add_argument("--derive", action="store_true",
                    help="derive slugs and compare against the library's")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    tally = collections.Counter()
    by_bucket: dict[str, list[tuple[str, str, str]]] = (
        collections.defaultdict(list))
    for bpf in sorted(args.dir.glob("*.bpt")):
        try:
            bp = yaml.safe_load(bpf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(bp, dict):
            continue
        for n, spec in (bp.get("fields") or {}).items():
            if not isinstance(spec, dict):
                continue
            w = spec.get("widget")
            path = w.get("path") if isinstance(w, dict) else None
            if not path:
                continue
            b = classify(path)
            tally[b] += 1
            by_bucket[b].append((bpf.stem, n, leaf(path)))

    tot = sum(tally.values())
    print(f"{tot} bound fields across {len(list(args.dir.glob('*.bpt')))} "
          f"blueprints\n")
    for b, v in tally.most_common():
        mark = "  <- nameable from the publisher" if b in NAMEABLE else ""
        print(f"  {b:18s} {v:6d}  {v/tot*100:5.1f}%{mark}")
    nameable = sum(tally[b] for b in NAMEABLE)
    print(f"\n  nameable deterministically: {nameable} "
          f"({nameable/tot*100:.1f}%)")
    print(f"  falls through to tooltip / Sensible / text / VLM: "
          f"{tot - nameable} ({(tot-nameable)/tot*100:.1f}%)")

    if args.blocks:
        return _report_blocks(args)
    if args.types:
        return _report_types(args)
    if args.derive:
        return _report_derived(args)

    if args.sample:
        rows = by_bucket.get(args.sample) or []
        print(f"\n--- {len(rows)} in {args.sample!r}, 25 at random ---")
        random.Random(args.seed).shuffle(rows)
        for f, n, lf in rows[:25]:
            print(f"  {f:14s} {n[:38]:38s} | {lf[:34]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
