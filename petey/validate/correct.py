"""Propose and apply blueprint corrections from value identity.

The validation loop detects and classifies; this is the half that edits a
`.bpt`. It handles exactly one family of defect — a name bound to the wrong
widget — and refuses everything else.

## The signal is a permutation, not a shift

`method_delta` reports a field as a candidate defect when `gt == native !=
petey`: the value is readable where the generator put it, so nothing is
wrong with the fill or the extract, and only the NAME can have sent the
meaning-based reader elsewhere. Read one step further and the report says
where it went:

    norm(petey[A]) == norm(gt[path_B])

petey, asked for the meaning of name `A`, returned the value that was
written into `B`'s widget. So the page position that means `A` is the
position `B` currently occupies, and `A` belongs on `B`'s widget. Each such
observation is a directed edge `A -> B`, and the defect is the structure
those edges form.

On `cf_1_fillable` they close a four-name cycle that spans two pages:

    surety_nm -> surety_mailing_address_line_1_txt -> surety_name_title_txt
              -> surety_signature_nm -> surety_nm

A cycle is the strong case, and for the same reason `detect_swaps` needs no
threshold: a reciprocal pair demands an exact double fit, and an n-cycle
demands n exact fits that close. Independent errors do not close loops. A
cycle is also a TOTAL permutation of the widgets it touches — every name
receives exactly one widget and no widget is left nameless — so applying it
is lossless.

An open chain is the weaker case. `2022_rev_form_1014r` has

    email_address_txt -> city_nm -> state_abbreviation_cd
                      -> state_abbreviation_cd_2

Rebinding along it leaves the ends dangling: the widget at the tail loses
its name, and the value at the head belongs to no name we hold. Those
orphans are not guessable from value identity, and naming them from the
page is precisely what the VLM escalation tier is for. So chains are
reported, and applied only under `--chains`.

## Why geometry is not used

`cluster_misalignment.py` groups spatially adjacent widgets and scores
shift hypotheses with `fits()`, a type-plausibility margin. That pass keeps
its own job — it finds candidate misalignment with no extraction run at
all. But it cannot serve here: `cf_1_fillable`'s cycle crosses a page
boundary, and no spatial chain builder can span that. Value identity needs
no adjacency, so it sees the rotation whole.

## What this refuses to touch

Three guards, each for an observed failure class that superficially
resembles a rebinding and is not one:

  - **Ambiguous targets.** A value appearing at more than one path cannot
    identify a widget. `cf_2_fillable` writes `'LC-2024-TX-00847'` into
    both `established_loc_no` and `footer_loc_no`; an edge to "the path
    holding that value" is not well defined, so both are dropped.

  - **Compound widgets (class 5).** `spreading_location_sec` holds
    `'14 / 18N / 07W'` and petey splits it across `_sec` / `_twn` / `_rge`.
    Each part looks like a neighbour's value. Requiring full equality is
    not enough, because the parts are equal to nothing; the guard is to
    drop any edge whose value is a substring of the source field's own
    ground truth. The blueprint is right and the GENERATOR is wrong.

  - **Formatting differences.** `'Hargrove, Dale R.'` vs `'Dale R.
    Hargrove'` is a scorer normalisation gap, not a defect. Comparison is
    on case- and whitespace-normalised strings only; reordering is not
    normalised away, so such a pair forms no edge.

Only the `widget` block moves. `type`, `semantic_type`, `description` and
`pattern` are properties of the name's meaning, not of the position, and
stay with the name.

Usage:
    python correct.py                          # report, change nothing
    python correct.py --form cf_1_fillable --verbose
    python correct.py --apply                  # rewrite .bpt for cycles
    python correct.py --apply --chains         # cycles and open chains
    python correct.py --out runs/corrections.json
"""
from __future__ import annotations

import argparse
import collections
import difflib
import json
import re
import shutil
from pathlib import Path
from typing import Any, Optional

import yaml

from petey.validate.name_sources import is_readable, leaf

from petey.paths import RUNS, BLUEPRINTS
HERE = Path(__file__).resolve().parent

# Shared with worklist.py: below this ratio two strings are genuinely
# different rather than one misread copy of the other.
FUZZY_MIN = 0.86


def norm(v: Any) -> Optional[str]:
    """Case- and whitespace-normalised string, or None if empty.

    Deliberately does NOT reorder tokens or strip punctuation: a name
    written `'Last, First'` against `'First Last'` must NOT compare equal,
    or a scorer-normalisation gap would be mistaken for a rebinding.
    """
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip().lower()
    return s or None


def load_case(run_dir: Path) -> Optional[tuple[dict, dict, dict]]:
    """(blueprint, ground_truth, petey_values) for a run's intact case.

    Intact only. A flattened case adds extraction difficulty on top of
    naming, and this pass is about naming.
    """
    bp_path = run_dir / "blueprint.bpt"
    cases = sorted(run_dir.glob("case_*_intact"))
    if not bp_path.exists() or not cases:
        return None
    case = cases[0]
    gt_path = case / "ground_truth.json"
    pet = next(iter(sorted(case.glob("extract_petey:*.json"))), None)
    if not gt_path.exists() or pet is None:
        return None
    try:
        bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
        gt = json.loads(gt_path.read_text(encoding="utf-8"))
        pv = json.loads(pet.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(bp, dict) or "fields" not in bp:
        return None
    return bp, gt, pv


def field_paths(bp: dict) -> dict[str, str]:
    """name -> AcroForm path, for single-widget fields only.

    A `type: category` field carries a `widgets:` map keyed by export value
    rather than one `widget`, so it binds to several paths and cannot be
    rebound as a unit. Excluded rather than guessed at.
    """
    out: dict[str, str] = {}
    for name, spec in (bp.get("fields") or {}).items():
        if not isinstance(spec, dict):
            continue
        w = spec.get("widget")
        if not isinstance(w, dict):
            continue
        path = w.get("path")
        if isinstance(path, str) and path:
            out[name] = path
    return out


def norm_punct(v: Any) -> Optional[str]:
    """Alphanumerics only, lowercased.

    Text extraction inserts and drops punctuation and spaces:
    `'compliance@redtailenergyok.com'` comes back as
    `'compliance@redtailenergy ok.com'`. Those are the same value seen
    through a lossy instrument, and under this normalisation they compare
    equal, so an edge survives that `norm` alone loses. Applied as a
    separate tier rather than replacing `norm`, because it also collapses
    genuinely distinct short values and needs the uniqueness guard
    recomputed against its own index.
    """
    if v is None:
        return None
    s = re.sub(r"[^a-z0-9]", "", str(v).lower())
    return s or None


def is_noise(a: Any, b: Any) -> bool:
    """Right field, misread character or two.

    Borrowed from `worklist.is_transcription_noise` — same threshold, same
    normalisation — so the loop uses one definition of "the instrument
    slipped" rather than two that can drift.
    """
    x, y = norm_punct(a), norm_punct(b)
    if not x or not y or x == y:
        return False
    if abs(len(x) - len(y)) > 3:
        return False
    return difflib.SequenceMatcher(None, x, y).ratio() >= FUZZY_MIN


# Comparison tiers, strongest first. An edge records the tier that found
# it, so a cycle closed on exact identity can be told apart from one held
# together by a fuzzy match.
_TIERS = (("exact", norm), ("punct", norm_punct))


# Suffix conventions the labeler emits, expanded so a blueprint slug can be
# compared with a publisher's prose name: `surety_nm` against `Surety Name`.
_SUFFIX_WORDS = {
    "nm": "name", "txt": "text", "dt": "date", "cd": "code", "no": "number",
    "amt": "amount", "ind": "indicator", "qty": "quantity", "pct": "percent",
    "addr": "address", "desc": "description", "cnt": "count", "yr": "year",
    "mo": "month", "dy": "day", "rge": "range", "twn": "township",
    "sec": "section", "loc": "location", "org": "organization",
    # Morphological variants the plural rule cannot reach. `sign` against
    # `Signature` and `print` against `Printed` are the difference between
    # confirming a correct rebinding and escalating it.
    "sign": "signature", "printed": "print", "signed": "signature",
    "num": "number", "nbr": "number", "st": "state", "zip": "zipcode",
    "tel": "telephone", "phone": "telephone", "email": "email",
    "addr1": "address", "dob": "birthdate",
}
# Words carrying no discriminating power in either vocabulary.
_STOP = {
    "the", "of", "a", "an", "and", "or", "type", "print", "please", "if",
    "this", "form", "text", "box", "field", "line", "no", "number", "name",
    "date", "enter", "for", "to", "in", "on", "at", "by", "is", "are",
    "full", "or", "and", "of", "line", "1", "2", "3", "4", "5", "6", "7",
    "8", "9", "0",
}


def _tokens(s: str) -> set[str]:
    """Comparable tokens from either vocabulary.

    Four normalisations, each for a mismatch observed on real pairs that a
    naive split reports as disagreement:

      CamelCase       `DateOfSignature` is ONE token under a
                      non-alphanumeric split, so it matches nothing.
      single letters   `E-Mail` splits to {e, mail} and never yields
                      `email`; a one-character token is joined forward.
      plurals          `SURETYS FULL MAILING ADDRESS` against
                      `surety_mailing_address_...`.
      suffix words     `_nm` against `Name`.

    Getting these wrong is not neutral: this function gates which
    corrections are independently confirmed, so a tokenizer artifact reads
    as a bad rebinding and sends a correct one to the escalation tier.
    """
    # Split CamelCase before folding case, or the boundaries are lost.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", s)
    raw = [t for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()) if t]

    # Join a single character onto the token after it: e + mail -> email.
    joined: list[str] = []
    i = 0
    while i < len(raw):
        if len(raw[i]) == 1 and raw[i].isalpha() and i + 1 < len(raw):
            joined.append(raw[i] + raw[i + 1])
            i += 2
        else:
            joined.append(raw[i])
            i += 1

    out: set[str] = set()
    for t in joined:
        t = _SUFFIX_WORDS.get(t, t)
        if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
            t = t[:-1]
        out.add(t)
    return out


# Abbreviations publishers use inside unsegmented names, beyond the suffix
# conventions in _SUFFIX_WORDS. Only ones observed in the corpus.
_ABBREV = {
    "imp": "importing", "exp": "exporting", "amt": "amount", "qty": "quantity",
    "addr": "address", "org": "organization", "rep": "representative",
    "ins": "insured", "insr": "insurer", "cert": "certificate",
    "desc": "description", "dept": "department", "govt": "government",
    "mfr": "manufacturer", "ctry": "country", "prov": "province",
    "emp": "employee", "empr": "employer", "acct": "account",
}


# Reverse of _SUFFIX_WORDS: expanded word -> the short forms publishers write.
# Needed because tiling works from the FIELD's expanded tokens back onto the
# publisher's compound, so it has to be able to spell `number` as `no`.
_SHORT_FORMS: dict[str, set[str]] = {}
for _k, _v in _SUFFIX_WORDS.items():
    _SHORT_FORMS.setdefault(_v, set()).add(_k)
for _k, _v in _ABBREV.items():
    _SHORT_FORMS.setdefault(_v, set()).add(_k)


def _forms(token: str) -> set[str]:
    """A token and every shorter spelling a publisher might use for it."""
    out = {token}
    out |= _SHORT_FORMS.get(token, set())
    out |= {token[:k] for k in range(3, min(len(token), 6))}
    return out


def _prefix_eq(a: str, b: str) -> bool:
    """`export` and `exporting` are the same word abbreviated."""
    if a == b:
        return True
    lo, hi = (a, b) if len(a) <= len(b) else (b, a)
    return len(lo) >= 4 and hi.startswith(lo)


def _tile(compound: str, tokens: frozenset[str]) -> int:
    """Fewest tokens needed to spell `compound` end to end, else 0.

    A publisher writes `entrytype`, `portcode`, `suretyno`, `impcarrier` — no
    separator and no CamelCase — so a tokeniser yields one opaque word and
    `entrytype` never matches `{entry, type, cd}`, marking a CORRECT labeling
    as a disagreement. cbp7501 scored 5% that way while its labels were
    largely right.

    Tiling asks the exact question instead: can the field's own tokens spell
    the publisher's word? That is stricter than substring coverage, which an
    earlier version used — coverage accepted any 70% overlap, where this
    demands the whole word be accounted for, so it adds true matches without
    admitting loose ones.

    A token may match an ABBREVIATED prefix of itself (>= 3 characters), which
    is what lets `imp` stand for `importing` in `impcarrier`.
    """
    n = len(compound)
    best = [0] * (n + 1)          # best[i] = fewest tokens to spell [0:i]
    for i in range(1, n + 1):
        for t in tokens:
            if len(t) < 3:
                continue
            # the token, a known short form of it, or an abbreviated prefix
            for cand in _forms(t):
                if len(cand) < 2:
                    continue
                j = i - len(cand)
                if j < 0 or compound[j:i] != cand:
                    continue
                if j == 0 or best[j]:
                    prev = 0 if j == 0 else best[j]
                    if not best[i] or prev + 1 < best[i]:
                        best[i] = prev + 1
    return best[n]


def name_agrees(field: str, path: str) -> bool:
    """Does the blueprint's name for this widget match the publisher's own?

    An independent confirmation that a binding is already correct, drawn
    from a source the labeler used only as an opaque id. Where it holds, no
    value-identity edge may move the field.

    This guard is not optional. `cf_1_fillable` carries two surety company
    names, so `petey[surety_nm]` returned the wrong one and produced an
    edge off a field that was bound correctly. That single false edge closed
    an otherwise-open chain into a four-cycle, and applying it fixed two
    bindings and broke two. The cycle argument — n exact fits that close,
    which independent errors do not satisfy — holds only against
    INDEPENDENT error. `similar_entity` is systematic: the values most
    likely to appear elsewhere on a form are precisely same-kind
    duplicates, so it manufactures exactly the edges that close loops.

    Deliberately conservative. Requires both that the discriminating tokens
    of the shorter side are contained in the longer, and that at least one
    such token exists — so `Text16` or a bare `Name` pins nothing.
    """
    if not is_readable(path):
        return False
    a = _tokens(field) - _STOP
    b = _tokens(leaf(path)) - _STOP
    if not a or not b:
        return False
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if short <= long:
        return True

    # Unsegmented compound names — see `_tile`. Uses the UNFILTERED tokens:
    # `_STOP` removes `type`, `number`, `code`, `name`, which is right for the
    # overlap tests above where those words are too generic to carry a match,
    # and exactly wrong here, where they are the halves of the compound.
    ua, ub = _tokens(field), _tokens(leaf(path))
    for whole_set, parts_set in ((ua, ub), (ub, ua)):
        for whole in (w for w in whole_set if len(w) >= 7):
            if _tile(whole, frozenset(parts_set - {whole})) >= 2:
                return True
    # Containment is too strict when BOTH sides carry words the other does
    # not: `surety mailing address line 1` against `suretys full mailing
    # address`. Two shared discriminating tokens is not something an
    # unrelated pair produces.
    #
    # Compared prefix-tolerantly, because a publisher abbreviates mid-word as
    # well as at the end: `ExportCountry` against `exporting_country_cd`
    # shares `country` outright and `export`/`exporting` only as a prefix, and
    # exact set intersection saw one shared token where there are two.
    shared = sum(1 for x in a if any(_prefix_eq(x, y) for y in b))
    return shared >= 2


def build_edges(bp: dict, gt: dict, pv: dict) -> tuple[list[dict], dict]:
    """Edges `A -> B`: petey's answer for A is the value written into B.

    Each tier gets its own value index, because uniqueness is tier-
    relative: two values distinct under `norm` can collide under
    `norm_punct`, and an ambiguous target identifies no widget.

    Returns (edges, stats) counting what each guard rejected, so a form
    that produced no edges can be told apart from one whose edges were all
    discarded.
    """
    paths = field_paths(bp)
    path_owner = {path: name for name, path in paths.items()}

    indices: dict[str, dict[str, list[str]]] = {}
    for tier, fn in _TIERS:
        idx: dict[str, list[str]] = collections.defaultdict(list)
        for name, path in paths.items():
            nv = fn(gt.get(path))
            if nv is not None:
                idx[nv].append(path)
        indices[tier] = idx

    stats = collections.Counter()
    edges: list[dict] = []
    for a, a_path in paths.items():
        raw_p = pv.get(a)
        if norm(raw_p) is None:
            continue
        # Independently confirmed binding: the publisher's own name for
        # this widget agrees with the blueprint's. Nothing may move it.
        if name_agrees(a, a_path):
            stats["pinned_by_acroform_name"] += 1
            continue
        own_raw = gt.get(a_path)
        if norm(raw_p) == norm(own_raw) or norm_punct(raw_p) == norm_punct(own_raw):
            continue                      # agrees in place; not a defect
        # A substring relation between what petey returned and this field's
        # own ground truth is NOT a rebinding, but it is two different
        # things and they need different names.
        #
        # `compound_widget` (class 5) — the generator crammed several
        # values into one widget and petey returned one part:
        # `spreading_location_sec` holds `'14 / 18N / 07W'` and petey
        # returns `'14'`. Both sides substantial, and the part is a real
        # share of the whole. The blueprint is right; the GENERATOR is.
        #
        # `format_variance` (class 4) — same value, different shape:
        # `'1'` against `'0001'`, `'4%'` against `'0.04'`. Containment here
        # is incidental to the padding, and calling it a compound widget
        # would attribute a generator defect to a scorer gap.
        op, ow = norm_punct(raw_p), norm_punct(own_raw)
        if op and ow and (op in ow or ow in op):
            short, long = sorted((op, ow), key=len)
            if len(short) >= 4 and len(short) / len(long) <= 0.75:
                stats["compound_widget"] += 1
            else:
                stats["format_variance"] += 1
            continue

        hit = None
        for tier, fn in _TIERS:
            key = fn(raw_p)
            if key is None:
                continue
            targets = [t for t in indices[tier].get(key, []) if t != a_path]
            if not targets:
                continue
            if len(targets) > 1:
                stats[f"ambiguous_target_{tier}"] += 1
                break
            hit = (tier, targets[0])
            break

        if hit is None:
            # Last tier: a single fuzzy partner, if exactly one exists.
            cands = [p for p in paths.values()
                     if p != a_path and is_noise(raw_p, gt.get(p))]
            if len(cands) == 1:
                hit = ("fuzzy", cands[0])
            elif len(cands) > 1:
                stats["ambiguous_target_fuzzy"] += 1
            else:
                stats["no_target"] += 1

        if hit is None:
            continue
        tier, b_path = hit
        if name_agrees(path_owner[b_path], b_path):
            stats["target_pinned"] += 1
            continue
        edges.append({
            "from": a, "to": path_owner[b_path],
            "from_path": a_path, "to_path": b_path,
            "value": raw_p, "tier": tier,
        })
        stats[f"edge_{tier}"] += 1
    return edges, stats


def decompose(edges: list[dict]) -> tuple[list[list[str]], list[list[str]]]:
    """Split the edge set into closed cycles and open chains.

    The graph is a partial function name -> name (each name claims at most
    one position), so following successors from any node either closes a
    cycle or runs out. Nodes with in-degree zero are chain heads.
    """
    succ = {e["from"]: e["to"] for e in edges}
    targets = {e["to"] for e in edges}

    cycles: list[list[str]] = []
    chains: list[list[str]] = []
    seen: set[str] = set()

    # Chains first, from every node nothing points at.
    for head in [n for n in succ if n not in targets]:
        walk, cur = [], head
        while cur is not None and cur not in walk:
            walk.append(cur)
            cur = succ.get(cur)
        seen.update(walk)
        if len(walk) >= 2:
            chains.append(walk)

    # Whatever is left and still has a successor lies on a cycle.
    for node in succ:
        if node in seen:
            continue
        walk, cur = [], node
        while cur is not None and cur not in walk:
            walk.append(cur)
            cur = succ.get(cur)
        seen.update(walk)
        if cur == walk[0] and len(walk) >= 2:
            cycles.append(walk)
    return cycles, chains


def propose_orphan_name(path: str) -> Optional[str]:
    """A slug for an orphaned widget, from its own AcroForm field name.

    A rebinding chain leaves the widget at its tail with no name. Value
    identity cannot supply one — the evidence only ever says where an
    EXISTING name belongs. But the widget frequently carries a
    publisher-written name of its own: `E-Mail`, `Printed Name`,
    `Pool Code`, `Issuing Bank`. `name_sources.py` measures this at 54% of
    data widgets corpus-wide, complementary to `/TU` (union 67%).

    So most orphans resolve locally and never need the escalation tier.
    Returns None when the name is a generator default (`Text16`,
    `Button1`), which is the residue that genuinely needs a look at the
    page.
    """
    if not is_readable(path):
        return None
    l = leaf(path)
    s = re.sub(r"[^a-z0-9]+", "_", l.lower()).strip("_")
    s = re.sub(r"_+", "_", s)
    return s or None


def plan_rebinds(group: list[str], closed: bool,
                 edges: list[dict]) -> list[dict]:
    """name -> the path it should hold, per the edges in `group`.

    `A -> B` means A belongs on B's widget, so each name takes the path its
    successor currently holds. For a closed cycle that is a total
    permutation. For an open chain the tail keeps nothing and is reported
    as orphaned.
    """
    succ = {e["from"]: e for e in edges if e["from"] in group}
    out: list[dict] = []
    for name in group:
        e = succ.get(name)
        if e is None:
            continue
        # Grade the proposal against the one source that took no part in
        # building the edge. `confirmed` is two independent sources
        # agreeing. `contradicted` is them disagreeing, which is not a
        # correction to apply — it is a question for the escalation tier.
        # cbp_form_3299_0's 2-cycle lands `..._merchandise_txt` on
        # `ForeignMerchandise2` and `..._2_txt` on `ForeignMerchandise1`,
        # exactly inverted, and only this grade catches it.
        if not is_readable(e["to_path"]):
            grade = "unconfirmed"
        elif name_agrees(name, e["to_path"]):
            grade = "confirmed"
        else:
            grade = "contradicted"
        out.append({"field": name, "old_path": e["from_path"],
                    "new_path": e["to_path"], "takes_from": e["to"],
                    "grade": grade})
    if not closed:
        held = {r["new_path"] for r in out}
        for name in group:
            e = succ.get(name)
            if e and e["from_path"] not in held:
                out.append({
                    "field": None, "orphan_path": e["from_path"],
                    "was_named": name,
                    "proposed_name": propose_orphan_name(e["from_path"]),
                })
    return out


def analyse_run(form: str, run_dir: Path) -> Optional[dict]:
    loaded = load_case(run_dir)
    if loaded is None:
        return None
    bp, gt, pv = loaded
    edges, stats = build_edges(bp, gt, pv)
    if not edges:
        return {"form": form, "run": run_dir.name, "edges": [],
                "cycles": [], "chains": [], "stats": dict(stats)}
    cycles, chains = decompose(edges)
    return {
        "form": form, "run": run_dir.name, "edges": edges,
        "stats": dict(stats),
        "cycles": [{"names": c, "rebinds": plan_rebinds(c, True, edges)}
                   for c in cycles],
        "chains": [{"names": c, "rebinds": plan_rebinds(c, False, edges)}
                   for c in chains],
    }


def apply_rebinds(bp_path: Path, rebinds: list[dict]) -> int:
    """Move `widget` blocks between field names. Returns fields changed.

    Read-modify-write on the parsed YAML, keeping key order. The old file
    is preserved as `<name>.bpt.bak` so a bad correction is recoverable
    without going through git.
    """
    bp = yaml.safe_load(bp_path.read_text(encoding="utf-8"))
    fields = bp["fields"]
    # Snapshot every widget block by path before mutating, so a rotation
    # does not read a value it has already overwritten.
    by_path: dict[str, Any] = {}
    for spec in fields.values():
        if isinstance(spec, dict) and isinstance(spec.get("widget"), dict):
            p = spec["widget"].get("path")
            if p:
                by_path[p] = spec["widget"]

    n = 0
    for r in rebinds:
        name = r.get("field")
        if not name or name not in fields:
            continue
        w = by_path.get(r["new_path"])
        if w is None:
            continue
        fields[name]["widget"] = dict(w)
        n += 1
    if n:
        shutil.copy2(bp_path, bp_path.with_suffix(".bpt.bak"))
        with open(bp_path, "w") as fh:
            yaml.safe_dump(bp, fh, sort_keys=False, allow_unicode=True)
    return n


def latest_runs(form_filter: Optional[str]) -> dict[str, Path]:
    """Newest run directory per form."""
    out: dict[str, Path] = {}
    for p in sorted(RUNS.glob("*_2*/blueprint.bpt")):
        d = p.parent
        form = re.sub(r"_\d{8}_\d{6}$", "", d.name)
        if form_filter and form != form_filter:
            continue
        out[form] = d          # sorted ascending, so last wins
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--form", default=None)
    ap.add_argument("--apply", action="store_true",
                    help="rewrite blueprints for closed cycles")
    ap.add_argument("--chains", action="store_true",
                    help="also apply open chains (leaves orphaned widgets)")
    ap.add_argument("--contradicted", action="store_true",
                    help="also apply rebinds the AcroForm name contradicts "
                         "(default: hold them for tier 3)")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    results = []
    for form, run_dir in latest_runs(args.form).items():
        r = analyse_run(form, run_dir)
        if r:
            results.append(r)

    n_cyc = sum(len(r["cycles"]) for r in results)
    n_chn = sum(len(r["chains"]) for r in results)
    cyc_fields = sum(len(c["rebinds"]) for r in results for c in r["cycles"])
    chn_fields = sum(
        len([x for x in c["rebinds"] if x.get("field")])
        for r in results for c in r["chains"])
    orphans = sum(
        len([x for x in c["rebinds"] if not x.get("field")])
        for r in results for c in r["chains"])

    print("=" * 74)
    print("BLUEPRINT CORRECTIONS — rebindings from value identity")
    print("=" * 74)
    print(f"forms examined: {len(results)}")
    print(f"closed cycles : {n_cyc:3d}  ->  {cyc_fields} fields "
          f"rebindable losslessly")
    orphan_recs = [x for r in results for c in r["chains"]
                   for x in c["rebinds"] if not x.get("field")]
    local = len([x for x in orphan_recs if x.get("proposed_name")])
    print(f"open chains   : {n_chn:3d}  ->  {chn_fields} fields, "
          f"{orphans} widgets orphaned")
    print(f"  of those orphans: {local} namable from the AcroForm name, "
          f"{orphans - local} need Tier 3")
    grades = collections.Counter(
        rb["grade"] for r in results
        for g in r["cycles"] + r["chains"] for rb in g["rebinds"]
        if rb.get("field"))
    print()
    print("  rebind proposals, graded by the independent oracle "
          "(the AcroForm name):")
    for k in ("confirmed", "unconfirmed", "contradicted"):
        if grades[k]:
            tail = "  -> held for tier 3" if k == "contradicted" else ""
            print(f"    {grades[k]:>5}  {k}{tail}")
    guards = collections.Counter()
    for r in results:
        guards.update(r["stats"])
    print()
    print("  edge candidates by disposition:")
    for k, v in guards.most_common():
        print(f"    {v:>5}  {k}")

    for r in results:
        if not (r["cycles"] or r["chains"]):
            continue
        print()
        print("-" * 74)
        print(f"{r['form']}   ({r['run']})")
        for c in r["cycles"]:
            tiers = sorted({e["tier"] for e in r["edges"]
                            if e["from"] in c["names"]})
            print(f"  CYCLE  len={len(c['names'])}  (lossless)  "
                  f"tier={'+'.join(tiers)}")
            for rb in c["rebinds"]:
                g = {"confirmed": "[confirmed]",
                     "unconfirmed": "[  no sig  ]",
                     "contradicted": "[CONTRADICTED -> T3]"}[rb["grade"]]
                print(f"    {g:21s} {rb['field'][:38]:38s} takes widget "
                      f"of {rb['takes_from']}")
                if args.verbose:
                    print(f"        {rb['old_path']}  ->  {rb['new_path']}")
        for c in r["chains"]:
            print(f"  CHAIN  len={len(c['names'])}  (ends dangle)")
            for rb in c["rebinds"]:
                if rb.get("field"):
                    g = {"confirmed": "[confirmed]",
                         "unconfirmed": "[  no sig  ]",
                         "contradicted": "[CONTRADICTED -> T3]"}[rb["grade"]]
                    print(f"    {g:21s} {rb['field'][:38]:38s} takes widget "
                          f"of {rb['takes_from']}")
                elif rb.get("proposed_name"):
                    print(f"    {rb['proposed_name'][:44]:44s} <- ORPHAN, "
                          f"named from AcroForm {rb['orphan_path']!r}")
                else:
                    print(f"    {'(TIER 3: needs the page)':44s} orphan "
                          f"{rb['orphan_path']!r}  [was {rb['was_named']}]")

    if args.apply:
        print()
        print("-" * 74)
        total = 0
        for r in results:
            groups = list(r["cycles"]) + (list(r["chains"])
                                          if args.chains else [])
            rebinds = [rb for g in groups for rb in g["rebinds"]
                       if rb.get("field")
                       and (args.contradicted
                            or rb.get("grade") != "contradicted")]
            if not rebinds:
                continue
            bp_path = BLUEPRINTS / f"{r['form']}.bpt"
            if not bp_path.exists():
                print(f"  [skip] no library blueprint: {bp_path.name}")
                continue
            n = apply_rebinds(bp_path, rebinds)
            total += n
            print(f"  [ok] {r['form']}: rebound {n} fields "
                  f"(backup {bp_path.name}.bak)")
        print(f"\n  {total} fields rebound. Re-run the loop to confirm the "
              f"defect count falls.")
    else:
        print()
        print("  (report only — pass --apply to rewrite blueprints)")

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(results, indent=2, default=str))
        print(f"\n[ok] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
