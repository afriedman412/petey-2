#!/usr/bin/env python3
"""Canonical-name lookup for a Petey blueprint against an IRS MeF form XSL.

For one blueprint + one MeF XSL file, this script:

  1. Parses the XSL to extract the canonical element list: leaf element
     name, normalized XPath under the form root, and the rendered
     form-box label (the form-line text emitted next to each value in the
     rendered return). XPath resolution walks through for-each /
     apply-templates ancestors so relative selects inside iteration
     scopes are anchored back to the form root.

  2. Loads the .bpt blueprint and lists its declared fields (name, type,
     description).

  3. Sends both lists to Claude with instructions: for each blueprint
     field, pick the matching canonical element by candidate index, or
     null. Index-based matching avoids ambiguity when the same leaf
     name appears at multiple xpaths (e.g. AddressLine1Txt under both
     EmployerUSAddress and EmployeeUSAddress on W-2).

  4. Writes <out>/<form_slug>/lookup.json with renames + xpaths +
     per-field confidence + rationale, plus candidates.json for audit.

This produces the inputs for CANONICAL_NAMES_RETROFIT.md Output 1
(retrofit existing blueprints) and Output 3 (Sensible scorecard,
against a separate candidate list).

Run from inside the petey venv:

    source petey/venv/bin/activate
    python scripts/canonical_lookup.py \\
        --bpt blueprints/form_8825.bpt \\
        --xsl PY2027R1/mef/Stylesheets/2026/IRS8825.xsl \\
        --form 8825

Output lands at canonical_lookups/form_8825/lookup.json by default.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

import lxml.etree as ET
import yaml

from petey.paths import CANONICAL_LOOKUPS
DEFAULT_OUT = CANONICAL_LOOKUPS
DEFAULT_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 32768

# Inline-style noise leaks into row labels when a value sits inside a
# styled <td> without a label sibling. Strip it so the matcher does not
# see CSS as a label.
_CSS_NOISE = re.compile(
    r"(width:|border-|padding|margin|text-align|background)"
)


# ---------------------------------------------------------------------
# XSL parsing — extract the canonical element list from one form's
# stylesheet, anchoring relative selects through for-each /
# apply-templates ancestor scopes.
# ---------------------------------------------------------------------

@dataclass
class CanonicalElement:
    name: str           # leaf element name, e.g. "GrossRentsAmt"
    xpath: str          # path under form root, e.g. "Grp/GrossRentsAmt"
    label: str          # nearest <tr> text content, or "" if noisy
    parent_groups: list[str]   # intermediate group names


def _strip_namespaces(root: ET._Element) -> None:
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def _form_data_var(root: ET._Element) -> tuple[str | None, str | None]:
    """Return (param_name, form_root_element_name) for the first
    FormXData parameter declared at the top of the XSL.

    The XSL convention is:
        <xsl:param name="FormXData" select="$RtnDoc/IRSX"/>
    so we return ("FormXData", "IRSX").
    """
    for el in root.iter():
        if el.tag != "param":
            continue
        sel = (el.get("select") or "").strip()
        if sel.startswith("$RtnDoc/"):
            return el.get("name"), sel.rsplit("/", 1)[-1]
    return None, None


def _all_form_data_vars(root: ET._Element) -> list[tuple[str, str]]:
    """Return [(param_name, form_root_element_name), ...] for every
    XSL param whose select starts with $RtnDoc/.

    Some forms (e.g. IRS1120S.xsl) declare multiple data roots — one
    per inlined schedule (Form1120SData, Form1120SScheduleK,
    Form1120SScheduleL, etc.) — and elements live under different
    variables depending on which schedule they belong to.
    """
    out = []
    for el in root.iter():
        if el.tag != "param":
            continue
        sel = (el.get("select") or "").strip()
        name = el.get("name")
        if sel.startswith("$RtnDoc/") and name:
            out.append((name, sel.rsplit("/", 1)[-1]))
    return out


def _row_label_for(el: ET._Element) -> str:
    """Text content of nearest ancestor <tr>, cleaned of CSS noise."""
    p = el.getparent()
    depth = 0
    while p is not None and depth < 12:
        if p.tag == "tr":
            text = " ".join(
                t.strip() for t in p.itertext() if t.strip()
            )
            text = re.sub(r"\s+", " ", text).strip()
            if not text or _CSS_NOISE.search(text[:120]):
                return ""
            return text[:240]
        p = p.getparent()
        depth += 1
    return ""


def _looks_like_path_select(sel: str) -> bool:
    """Skip selects that are function calls / number formats / strings."""
    if not sel:
        return False
    # Function calls or expressions
    head = sel.split("/", 1)[0]
    if "(" in head or "'" in head or '"' in head:
        return False
    return True


def _strip_predicates(s: str) -> str:
    """Drop predicates like [$pos + 1], [$index], [1]."""
    return re.sub(r"\[[^\]]*\]", "", s)


def _resolve_xpath_with_context(
    el: ET._Element, form_var: str
) -> str | None:
    """Walk up for-each / apply-templates ancestors to anchor a
    relative select back to the form root.

    Returns the form-rooted xpath (relative to $FormX, no leading slash)
    or None if the select can't be anchored (e.g. it references an XSL
    variable other than the form-data param, or it's an expression).
    """
    raw = (el.get("select") or "").strip()
    if not _looks_like_path_select(raw):
        return None

    # Absolute reference to form root.
    prefix = f"${form_var}"
    if raw == prefix:
        return ""
    if raw.startswith(prefix + "/"):
        return _strip_predicates(raw[len(prefix) + 1:])

    # Reference to a different XSL variable — not a form-rooted path.
    if raw.startswith("$"):
        return None

    # Relative path: walk up looking for an ancestor whose select
    # establishes a form-rooted context.
    parts = [raw]
    p = el.getparent()
    depth = 0
    while p is not None and depth < 30:
        if p.tag in ("for-each", "apply-templates"):
            psel = (p.get("select") or "").strip()
            if not _looks_like_path_select(psel):
                p = p.getparent()
                depth += 1
                continue
            if psel == prefix:
                joined = "/".join(parts)
                return _strip_predicates(joined)
            if psel.startswith(prefix + "/"):
                head = psel[len(prefix) + 1:]
                joined = head + "/" + "/".join(parts)
                return _strip_predicates(joined)
            if psel.startswith("$"):
                return None  # different variable, not anchorable
            # Another relative ancestor — prepend and keep walking.
            parts.insert(0, psel)
        p = p.getparent()
        depth += 1
    return None  # never reached form root


def extract_canonical_elements(
    xsl_path: Path,
    form_var_filter: str | None = None,
) -> tuple[str, list[CanonicalElement]]:
    """Parse one MeF form XSL.

    Returns (form_root_element_name, canonical element list). Elements
    are deduplicated by (leaf_name, xpath).

    If `form_var_filter` is given, only elements rooted at that XSL
    param (e.g. "Form1120SScheduleK") are extracted. Otherwise all
    declared form-data roots (selects starting with $RtnDoc/) are
    walked — useful for forms like IRS1120S.xsl that contain multiple
    schedules under separate root variables.
    """
    tree = ET.parse(str(xsl_path))
    root = tree.getroot()
    _strip_namespaces(root)

    all_vars = _all_form_data_vars(root)
    if not all_vars:
        raise RuntimeError(
            f"Could not locate any FormXData params in {xsl_path.name}"
            " — expected <xsl:param name='FormXData' "
            "select='$RtnDoc/IRSX'/>"
        )

    if form_var_filter:
        all_vars = [
            (n, r) for (n, r) in all_vars if n == form_var_filter
        ]
        if not all_vars:
            raise RuntimeError(
                f"form_var '{form_var_filter}' not found in "
                f"{xsl_path.name}"
            )

    # The headline form_root is the first declared var's root (or the
    # filtered one). All extracted elements get their full xpath under
    # whichever var they're rooted at.
    headline_root = all_vars[0][1]

    seen: dict[tuple[str, str], CanonicalElement] = {}
    for form_var, _form_root in all_vars:
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            sel = el.get("select")
            if not sel:
                continue
            xpath = _resolve_xpath_with_context(el, form_var)
            if xpath is None or xpath == "":
                continue
            parts = [p for p in xpath.split("/") if p]
            if not parts:
                continue
            leaf = parts[-1]
            # XSL self/parent refs aren't elements.
            if leaf in (".", ".."):
                continue
            groups = parts[:-1]
            key = (leaf, xpath)
            if key in seen:
                if not seen[key].label:
                    lbl = _row_label_for(el)
                    if lbl:
                        seen[key].label = lbl
                continue
            seen[key] = CanonicalElement(
                name=leaf,
                xpath=xpath,
                label=_row_label_for(el),
                parent_groups=groups,
            )

    elements = sorted(
        seen.values(), key=lambda e: (e.xpath, e.name)
    )
    return headline_root, elements


# ---------------------------------------------------------------------
# Blueprint loading
# ---------------------------------------------------------------------

@dataclass
class BlueprintField:
    name: str
    type: str
    description: str
    required: bool


def load_blueprint(
    bpt_path: Path,
) -> tuple[dict, list[BlueprintField]]:
    """Load a .bpt YAML; return (full_doc, field_list)."""
    doc = yaml.safe_load(bpt_path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise RuntimeError(
            f"{bpt_path} did not parse as a YAML mapping"
        )
    raw_fields = doc.get("fields") or {}
    fields: list[BlueprintField] = []
    if isinstance(raw_fields, dict):
        for name, spec in raw_fields.items():
            spec = spec or {}
            fields.append(BlueprintField(
                name=name,
                type=str(spec.get("type", "string")),
                description=str(spec.get("description", "")).strip(),
                required=bool(spec.get("required", False)),
            ))
    elif isinstance(raw_fields, list):
        for entry in raw_fields:
            entry = entry or {}
            fields.append(BlueprintField(
                name=str(entry.get("name", "")),
                type=str(entry.get("type", "string")),
                description=str(entry.get("description", "")).strip(),
                required=bool(entry.get("required", False)),
            ))
    else:
        raise RuntimeError(
            f"{bpt_path} has unrecognised `fields` shape"
        )
    return doc, fields


# ---------------------------------------------------------------------
# LLM matcher — index-based to avoid name-duplicate ambiguity.
# ---------------------------------------------------------------------

MATCHER_SYSTEM = """You are a forms-data ontologist. Your job is to \
map descriptive blueprint field names against the canonical XML \
element names used by the IRS Modernized e-File (MeF) schema for a \
single form.

For each blueprint field you will be given:
  - its blueprint key (descriptive snake_case),
  - its declared type and required flag,
  - its description (typically references a form box number and label).

For each, you must choose from the supplied list of canonical XSD \
elements (extracted from the IRS MeF stylesheet for this exact form). \
Each candidate carries:
  - an integer index [idx] (the only way to refer to it),
  - a leaf element name (TitleCase, e.g. WagesAmt),
  - a normalized XPath under the form root,
  - the row label text the stylesheet renders next to it (often
    "<line_no> <box_label>", sometimes empty).

Match rules:
  - Prefer the candidate whose row label matches the form box
    referenced in the blueprint description.
  - When two candidates share a leaf name but have different xpaths
    (e.g. AddressLine1Txt under EmployerUSAddress vs EmployeeUSAddress),
    pick the one whose xpath matches the blueprint field's semantic
    context. The xpath disambiguates — that's why we pass indices.
  - Prefer leaf amount/value elements (XxxAmt, XxxCnt, XxxNm, XxxInd)
    over their wrapping group elements (XxxGrp). The blueprint field
    is usually a value, not a group.
  - If no candidate reasonably matches, return null. Do not guess.
  - Some blueprint fields will not match cleanly because the blueprint
    bundles what the canonical schema splits, or vice versa. In those
    cases return null and write a rationale that explicitly names the
    structural mismatch and proposes how the blueprint should be
    refactored to align with the canonical shape (e.g. "blueprint
    bundles street/city/state/zip into one string; canonical splits
    into AddressLine1Txt + CityNm + StateAbbreviationCd + ZIPCd —
    blueprint should split into 4 fields").

Return a single JSON object exactly conforming to this shape:

{
  "matches": [
    {
      "field": "<blueprint_field_name>",
      "candidate_idx": <integer> | null,
      "confidence": "high" | "medium" | "low",
      "rationale": "<one short sentence>"
    },
    ...
  ]
}

Cover every blueprint field exactly once, in the order given. Output \
JSON only — no preamble, no markdown fences.
"""


def _format_candidates(elements: list[CanonicalElement]) -> str:
    lines = ["[idx] name | xpath | row_label"]
    for i, e in enumerate(elements):
        label = e.label or "(no label)"
        lines.append(f"[{i}] {e.name} | {e.xpath} | {label}")
    return "\n".join(lines)


def _format_fields(fields: list[BlueprintField]) -> str:
    parts = []
    for f in fields:
        req = " (required)" if f.required else ""
        parts.append(
            f"- {f.name} [{f.type}]{req}\n    {f.description}"
        )
    return "\n".join(parts)


def _build_user_prompt(
    *,
    form_name: str,
    form_root: str,
    elements: list[CanonicalElement],
    fields: list[BlueprintField],
) -> str:
    return (
        f"Form: {form_name}  (XSD root element: {form_root})\n\n"
        f"CANONICAL ELEMENTS (closed candidate list extracted from "
        f"the MeF stylesheet):\n"
        f"{_format_candidates(elements)}\n\n"
        f"BLUEPRINT FIELDS (match each to a candidate index above, "
        f"or null):\n"
        f"{_format_fields(fields)}\n\n"
        "Return JSON only.\n"
    )


def _stream_text(
    client, *, model: str, system: str, user: str
) -> str:
    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        final = stream.get_final_message()
    return "".join(
        b.text for b in final.content
        if getattr(b, "type", None) == "text"
    )


def _parse_matcher_response(text: str) -> list[dict]:
    """Pull the JSON object from a model response."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise RuntimeError(
            f"No JSON object found in matcher response: {text[:200]}"
        )
    obj = json.loads(text[start:end + 1])
    matches = obj.get("matches")
    if not isinstance(matches, list):
        raise RuntimeError("Matcher response missing 'matches' array")
    return matches


def match_fields(
    *,
    form_name: str,
    form_root: str,
    elements: list[CanonicalElement],
    fields: list[BlueprintField],
    model: str,
    client,
) -> list[dict]:
    user = _build_user_prompt(
        form_name=form_name,
        form_root=form_root,
        elements=elements,
        fields=fields,
    )
    text = _stream_text(
        client, model=model, system=MATCHER_SYSTEM, user=user
    )
    matches = _parse_matcher_response(text)

    # Validate by index — each candidate has a stable position in the
    # list we sent. Name+xpath comes back authoritatively from that.
    by_field = {m.get("field"): m for m in matches}
    validated = []
    for f in fields:
        m = by_field.get(f.name, {
            "field": f.name,
            "candidate_idx": None,
            "confidence": "low",
            "rationale": (
                "Matcher did not return an entry for this field."
            ),
        })
        idx = m.get("candidate_idx")
        if idx is None or not isinstance(idx, int):
            entry = {
                "canonical": None,
                "xpath": None,
                "confidence": m.get("confidence", "low"),
                "rationale": m.get("rationale", ""),
            }
        elif 0 <= idx < len(elements):
            cand = elements[idx]
            entry = {
                "canonical": cand.name,
                "xpath": cand.xpath,
                "confidence": m.get("confidence", "medium"),
                "rationale": m.get("rationale", ""),
            }
        else:
            entry = {
                "canonical": None,
                "xpath": None,
                "confidence": "low",
                "rationale": (
                    f"Matcher returned out-of-range idx={idx} "
                    f"(candidate list size {len(elements)}). "
                    f"Original rationale: {m.get('rationale', '')}"
                ),
            }
        validated.append({"field": f.name, **entry})
    return validated


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def _slug_from_bpt(bpt_path: Path) -> str:
    return bpt_path.stem


def _rel_to_repo(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--bpt", required=True, type=Path,
        help="Path to the .bpt blueprint file",
    )
    ap.add_argument(
        "--xsl", required=True, type=Path,
        help="Path to the IRS MeF XSL stylesheet for the form",
    )
    ap.add_argument(
        "--form", default=None,
        help=(
            "Form identifier for the binding block (e.g. '8825'). "
            "Defaults to the bpt slug."
        ),
    )
    ap.add_argument(
        "--schema", default="irs_mef",
        help="Binding schema identifier (default: irs_mef)",
    )
    ap.add_argument(
        "--schema-version", default="2026",
        help="Binding schema version (default: 2026)",
    )
    ap.add_argument(
        "--out", type=Path, default=DEFAULT_OUT,
        help=f"Output root directory (default: {DEFAULT_OUT})",
    )
    ap.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"Anthropic model (default: {DEFAULT_MODEL})",
    )
    ap.add_argument(
        "--form-var", default=None,
        help=(
            "XSL param name to scope extraction to (e.g. "
            "'Form1120SScheduleK'). When the XSL declares multiple "
            "form-data roots, this picks which one's elements land "
            "in the candidate list. Default: walk all declared roots."
        ),
    )
    ap.add_argument(
        "--dry-run", action="store_true",
        help=(
            "Extract candidates + print prompt; do not call the API "
            "or write files"
        ),
    )
    args = ap.parse_args()

    if not args.bpt.exists():
        print(
            f"error: blueprint not found: {args.bpt}", file=sys.stderr
        )
        return 2
    if not args.xsl.exists():
        print(f"error: xsl not found: {args.xsl}", file=sys.stderr)
        return 2

    form_root, elements = extract_canonical_elements(
        args.xsl, form_var_filter=args.form_var,
    )
    if not elements:
        print(
            f"error: no canonical elements extracted from {args.xsl}",
            file=sys.stderr,
        )
        return 3

    doc, fields = load_blueprint(args.bpt)
    if not fields:
        print(
            f"error: no fields found in {args.bpt}", file=sys.stderr
        )
        return 3

    form_name = args.form or _slug_from_bpt(args.bpt)
    slug = _slug_from_bpt(args.bpt)
    out_dir = args.out / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    print(
        f"blueprint: {args.bpt}  fields={len(fields)}"
    )
    print(
        f"xsl:       {args.xsl}  candidates={len(elements)}  "
        f"form_root={form_root}"
    )
    print(f"out:       {out_dir}")

    if args.dry_run:
        prompt = _build_user_prompt(
            form_name=form_name,
            form_root=form_root,
            elements=elements,
            fields=fields,
        )
        print("--- USER PROMPT (dry-run) ---")
        print(prompt)
        return 0

    # Load .env from cwd-walk (not __file__-walk) so CLI invocations
    # from the repo root pick up the repo's .env regardless of where
    # the script lives.
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass

    import anthropic
    client = anthropic.Anthropic()
    matches = match_fields(
        form_name=form_name,
        form_root=form_root,
        elements=elements,
        fields=fields,
        model=args.model,
        client=client,
    )

    high = sum(
        1 for m in matches
        if m.get("canonical") and m.get("confidence") == "high"
    )
    medium = sum(
        1 for m in matches
        if m.get("canonical") and m.get("confidence") == "medium"
    )
    low = sum(
        1 for m in matches
        if m.get("canonical") and m.get("confidence") == "low"
    )
    unmatched = sum(1 for m in matches if not m.get("canonical"))
    print(
        f"matched: high={high}  medium={medium}  "
        f"low={low}  unmatched={unmatched}"
    )

    lookup = {
        "binding": {
            "schema": args.schema,
            "version": args.schema_version,
            "form": form_name,
            "form_root": form_root,
        },
        "source_xsl": _rel_to_repo(args.xsl),
        "model": args.model,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(
            timespec="seconds"
        ),
        "blueprint": {
            "path": _rel_to_repo(args.bpt),
            "name": doc.get("name"),
        },
        "fields": {
            m["field"]: {k: v for k, v in m.items() if k != "field"}
            for m in matches
        },
    }
    (out_dir / "lookup.json").write_text(
        json.dumps(lookup, indent=2) + "\n", encoding="utf-8"
    )

    candidates_dump = [asdict(e) for e in elements]
    (out_dir / "candidates.json").write_text(
        json.dumps(candidates_dump, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"wrote: {out_dir / 'lookup.json'}")
    print(f"wrote: {out_dir / 'candidates.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
