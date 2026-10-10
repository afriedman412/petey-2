"""Extract data from a filled PDF using a blueprint (`.bpt`).

Dispatches per-field across three strategies, in order:

1. **AcroForm-native** — if the input PDF still has AcroForm structure
   AND the field's AcroForm path is present, read the interactive
   field value directly. No text extraction, no OCR.

2. **Rect-clipped text** — if the PDF has an embedded text layer
   (flattened AcroForm, print-to-PDF, or OCR-underlaid scan), clip the
   page text to the field's rect. No AcroForm needed, no OCR.

2b. **Ink** — an option box on a blueprint with no form layer (a flat
   form, widget `path: null`): the box's rect rendered from the filled
   page against the same rect on the blank; added ink is a mark
   (`petey.validate.ink`, the detector the judge's `[x]` tokens use).
   A drawn X or check is not text, so text_clip cannot see it. Needs
   the blank, resolved from the blueprint's `source_pdf`.
3. **Zonal OCR** — if the field's rect has no embedded text (pure image
   scan), rasterize the widget rect at 300 DPI and run Tesseract on
   the crop via `tesserocr` (C-API bindings, no subprocess overhead).
   Applies the field's `ocr_whitelist` (from `semantic_type`) to
   constrain output.

No LLM at extraction time — the extraction primitives are entirely
local. LLM fallback for form-version drift or genuinely broken inputs
is a higher-level orchestration concern.

Usage:
    python extract.py --blueprint <file.bpt> --pdf <input.pdf> \\
        --output <values.json>
"""
from __future__ import annotations

import argparse
import difflib
import io
import json
import os
import re
from pathlib import Path
from typing import Any, Optional

import pymupdf
import yaml

try:
    import tesserocr
    from PIL import Image
    _TESSEROCR_OK = True
except ImportError:
    _TESSEROCR_OK = False


TRUTHY_CHECKBOX = {"yes", "on", "true", "/yes", "1"}
FALSY_ANSWER = {"n", "no", "false", "0", "off", "/off"}     # an explicit negative typed into a yes/no text box
TRUTHY_CHECKBOX |= {"y"}

# Characters that plausibly represent a check-mark when Tesseract OCRs a
# filled checkbox/radio widget. Whitelist approach: anything outside this
# set is treated as noise (misread border glyphs, bleed from adjacent
# labels). Grows only when new check-glyph conventions surface.
_CHECK_INDICATORS = frozenset(
    "Xx"        # US/EU convention
    "✓"    # ✓ check mark
    "✔"    # ✔ heavy check mark
    "✗"    # ✗ ballot X
    "✘"    # ✘ heavy ballot X
    "☑"    # ☑ ballot box with check
    "☒"    # ☒ ballot box with X
    "■"    # ■ black square
    "●"    # ● black circle
    "█"    # █ full block (heavy fill)
)
OCR_DPI = 300


def _unescape_pdf_name(s: Any) -> Any:
    """Decode PDF name-object hex escapes (`#XX` → the byte).

    pymupdf returns raw AcroForm names — a radio value of "N/A" comes
    through as "N#2FA". Un-escape so the extract output aligns with the
    .bpt's `values:` list and the LLM's ground truth.
    """
    if not isinstance(s, str) or "#" not in s:
        return s
    return re.sub(
        r"#([0-9A-Fa-f]{2})",
        lambda m: chr(int(m.group(1), 16)),
        s,
    )


def _tessdata_path() -> Optional[str]:
    """Find a usable tessdata dir. Check `TESSDATA_PREFIX` first, then
    a handful of common install locations."""
    env = os.environ.get("TESSDATA_PREFIX")
    if env and (Path(env) / "eng.traineddata").exists():
        return env
    candidates = [
        "/usr/local/share/tessdata/",
        "/opt/homebrew/share/tessdata/",
        "/opt/homebrew/opt/tesseract/share/tessdata/",
        "/usr/share/tesseract-ocr/5/tessdata/",
        "/usr/share/tesseract-ocr/4.00/tessdata/",
        "/usr/share/tessdata/",
    ]
    for c in candidates:
        p = Path(c)
        if p.exists() and (p / "eng.traineddata").exists():
            return c
    return None


def _selected_states(doc, widget: dict) -> Optional[set[str]]:
    """On-states currently selected on the field at `widget["path"]`, read
    from every widget of that field on the page (each kid reports its own
    state; the selected kid reports its on-state, the others `Off`).
    None when the path is not in the AcroForm layer."""
    page_no = int(widget.get("page", 1)) - 1
    if page_no < 0 or page_no >= len(doc):
        return None
    matches = [pw for pw in doc[page_no].widgets()
               if pw.field_name == widget.get("path")]
    if not matches:
        return None
    out: set[str] = set()
    for pw in matches:
        v = _unescape_pdf_name(pw.field_value)
        if v not in (None, "", "Off"):
            out.add(str(v))
    return out


def _coerce_checkbox(v: Any) -> bool:
    """True if the widget value represents 'selected/checked'.

    Covers both checkbox and radio-button semantics:
    - Checkboxes: 'Yes' / 'On' / boolean True → selected
    - Radio buttons: any non-empty non-'Off' export value → selected
    """
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if not s or s == "off":
            return False
        if s in TRUTHY_CHECKBOX:
            return True
        # Radio button export values (e.g., "Choice1", "Married")
        return True
    return False


_LEADING_NUM_RE = re.compile(r"^\s*([-+]?\d+(?:\.\d+)?)\s*")
_ANY_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?")


# Suffix conventions the labeler emits, expanded so a slug compares against
# prose: `_cd` against "Code", `_nm` against "Name".
_LABEL_SUFFIX = {
    "nm": "name", "txt": "text", "dt": "date", "cd": "code", "no": "number",
    "amt": "amount", "ind": "indicator", "qty": "quantity", "pct": "percent",
    "num": "number", "yr": "year", "mo": "month", "addr": "address",
    "desc": "description", "cnt": "count", "tel": "telephone",
}


def _label_tokens(*parts: Optional[str]) -> set[str]:
    out: set[str] = set()
    for part in parts:
        if not part:
            continue
        spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(part))
        for t in re.split(r"[^A-Za-z0-9]+", spaced.lower()):
            if len(t) < 2:
                continue
            out.add(_LABEL_SUFFIX.get(t, t))
    return out


def _looks_like_label(line: str, hint: set[str]) -> bool:
    """Is this clipped line the field's own printed caption?

    Compared against the field's NAME and DESCRIPTION, which is the one
    description of the caption available at extraction time. Tokens are
    matched fuzzily because the clip often shears the caption: `type of`
    arrives as `ype o` when the rect cuts its first glyphs.
    """
    if not hint:
        return False
    toks = _label_tokens(line)
    if not toks:
        return False
    # Numbers are matched EXACTLY, never fuzzily. An OSHA-301 tooltip opens
    # with the form number, so `301` lands in the hint, and `'30'` from the
    # value `'06:30'` scores 0.8 against it — which judged the value a label
    # and dropped it, keeping the stub `'y'` instead. Digits carry no
    # morphology for a ratio to measure.
    alpha_hint = {h for h in hint if not h.isdigit()}
    hits = 0
    for t in toks:
        if t in hint:
            hits += 1
            continue
        if t.isdigit():
            continue
        if any(difflib.SequenceMatcher(None, t, h).ratio() >= 0.75
               for h in alpha_hint):
            hits += 1
    return hits / len(toks) >= 0.5


_RULE_RUN_RE = re.compile(r"_{3,}|\.{4,}|-{4,}")


def _clean_text_clip(txt: str, label_hint: Optional[set] = None) -> str:
    """Filter text_clip's raw output for common capture artifacts.

    text_clip on a flattened PDF captures whatever text lands within
    the widget's rect. Common noise:

    - Adjacent form-template ink: mask decimals `.`/`.00`, `$`, `%`
      or stray label glyphs (`i`, `*`, `†`) that happen to fall inside
      or overlap the widget rect.
    - Per-line stray characters: `'i\\nMargaret'` (VA-760) —
      one-character line preceding the actual value.

    Rule: split by newline, drop lines that are pure punctuation OR
    single alphabetic chars OR pure-numeric of length <= 2 that don't
    look like the value (heuristic: value-line has the most content).

    Never returns empty for non-empty input — if everything got
    filtered, return the original stripped text. Downstream numeric
    coercion still has _parse_leading_number as a fallback.
    """
    # Printed underlines and dot leaders are text on many flat forms (`_____`,
    # `.....`): the line a filer writes on, never the value. Dropped first, so a
    # box that holds only its underline reads as empty (TX RRC EP-3, 2026-10-05).
    txt = _RULE_RUN_RE.sub(" ", txt)
    # a caption's trailing colon or separator bar clipped with the value (ACORD 25's "INSURER A :" rows)
    lines = [ln.strip().strip(":;|").strip() for ln in txt.split("\n")]
    lines = [ln for ln in lines if ln]
    if not lines:
        return ""
    if len(lines) <= 1:
        return lines[0]

    # A widget rect frequently encloses its own printed caption, so the clip
    # returns `'City\nWilliston'` or `'Zip Code\n58801'`. The rules below
    # cannot reach those: a caption is neither punctuation nor a short
    # fragment, it is a real word. On nd_ncid form1 that cost 54 of 88 fields
    # on the flattened variant, while a meaning-based reader was unaffected —
    # the value was always there, with the label glued to it.
    #
    # Drop a line only when it matches THIS field's own name or description
    # and some other line does not, so a caption is removed and a genuinely
    # multi-line value is kept whole. If every line looks like the caption,
    # nothing is dropped — better to return the label than to return
    # nothing.
    if label_hint:
        keep = [ln for ln in lines if not _looks_like_label(ln, label_hint)]
        if keep and len(keep) < len(lines):
            lines = keep
        elif len(keep) == 0:
            # Every line matched, which happens when the VALUE contains the
            # caption's word: `'City\nWatford City'` for a `..._city_nm`
            # field. Both look like the label, so the caption cannot be
            # picked out by matching alone — but a caption adds no
            # information the value lacks, so prefer the line whose tokens
            # strictly contain another's.
            toks = [_label_tokens(ln) for ln in lines]
            survivors = [
                ln for ln, t in zip(lines, toks)
                if not any(t < other for other in toks)
            ]
            if survivors and len(survivors) < len(lines):
                lines = survivors
        if len(lines) == 1:
            return lines[0]

    # Sheared caption ink. A rect that clips its own caption often cuts the
    # glyphs, so what survives is a run of one- and two-character stubs:
    # `'e ep o e'` from "Telephone", `'t Su ace'` from "at Surface". No
    # dictionary or hint reaches those, but the shape is distinctive — every
    # alphanumeric run is tiny — and a real value on another line is not.
    if len(lines) > 1:
        def _sheared(ln: str) -> bool:
            runs = re.findall(r"[A-Za-z0-9]+", ln)
            return bool(runs) and all(len(r) <= 2 for r in runs)
        longest = max(len(ln) for ln in lines)
        keep = [ln for ln in lines
                if not (_sheared(ln) and len(ln) * 2 <= longest)]
        if keep and len(keep) < len(lines):
            lines = keep
            if len(lines) == 1:
                return lines[0]

    max_len = max(len(ln) for ln in lines)
    # Drop lines that look like mask/label ink alongside the value.
    filtered = []
    for ln in lines:
        # Pure punctuation (no alphanumerics)
        if not any(c.isalnum() for c in ln):
            continue
        # Short non-digit fragment that's dominated by another line:
        # covers `i` (1 char) and `yp` / `iL` / etc. (2-3 chars) when
        # there's a substantive sibling line. The digit escape hatch
        # preserves per-cell numeric captures like "5\n2\n4".
        # Was `< 0.25 * max_len`, which missed by a hair exactly where it
        # mattered: `'N\n152N'` is 1 char against 4, and 1 < 1.0 is false.
        # A stub beside a sibling at least twice its length is ink.
        if (len(ln) <= 3
                and not ln.isdigit()
                and len(ln) * 2 <= max_len):
            continue
        filtered.append(ln)
    if not filtered:
        return txt  # keep original if we'd drop everything
    # Joined with a newline deliberately. A space join looks tidier and was
    # tried: it moved NOTHING across 137 runs, because `score._canonicalize`
    # already strips all whitespace including newlines for the default case
    # ("kills the text_clip vertical-splitting class without needing an
    # extract-side fix"). So the wrapping never reached a verdict, and a
    # space join only adds the risk of asserting `'5 2 4'` for a rect that
    # encloses three numeric cells.
    return "\n".join(filtered)


def _parse_leading_number(s: str) -> Optional[float]:
    """Extract the value's numeric content from a possibly-noisy string.

    Handles three cases:
    - Clean leading: `'175 KGS'` → 175 (class 8: labeler-mistyped widget
      holds unit-suffixed value).
    - Multi-line with mask garnish: `'.\\n87450'` or `'87450\\n.00'`
      → 87450 (text_clip captured the widget rect + adjacent printed
      `.00` mask ink from the form template).
    - Also handles `'1,200'` after upstream comma-strip.

    Returns None if no numeric token is present. Picks the LONGEST
    numeric token when several appear — mask ink is single/double-digit
    (`.`, `.00`, `$`); real values are usually longer.
    """
    m = _LEADING_NUM_RE.match(s)
    if m:
        try:
            return float(m.group(1))
        except (ValueError, TypeError):
            pass
    # Fallback: pick the longest numeric token anywhere in the string.
    # For `.\n87450`: matches `.` (would parse as 0.0) and `87450`.
    # Longest wins → 87450. Handles text_clip mask garnish universally.
    tokens = _ANY_NUM_RE.findall(s)
    numeric_tokens = [(t, len(t.lstrip("+-").rstrip("."))) for t in tokens]
    if not numeric_tokens:
        return None
    best = max(numeric_tokens, key=lambda x: x[1])[0]
    try:
        return float(best)
    except (ValueError, TypeError):
        return None


def _coerce_typed(
    raw: Any, type_hint: str,
    allowed_values: Optional[list] = None,
    widget_type: Optional[str] = None,
) -> Any:
    """Best-effort coerce a raw string to the declared bpt type.

    Date fields go through `dateutil.parser.parse` and are emitted as
    canonical `YYYY-MM-DD`. Any parseable date input (`3/14/2025`,
    `March 14, 2025`, ISO with time, etc.) canonicalizes; anything that
    isn't a date raises rather than silently degrading — extraction is
    supposed to produce a canonical value or fail loudly.

    Category fields with `values:` reject any raw string not in the
    declared enum → returns None. Guards against OCR/text_clip noise
    registering as a valid category selection. Match is case-insensitive
    on whitespace-stripped strings; returns the canonical value from the
    enum (preserving the .bpt's casing).
    """
    if raw is None or raw == "":
        return None
    if type_hint == "boolean":
        # A yes/no answer typed into a text box (ACORD's Y / N columns): an explicit negative is False. Without this,
        # "N" fell through to the radio-button rule (any other export value is a selection) and read as True
        # (2026-10-07). Text boxes only: on a checkbox the value is its export value, and a ticked "No" box
        # (`..._no_ind`) stores "No" and is selected.
        if (widget_type not in ("checkbox", "radiobutton") and isinstance(raw, str)
                and raw.strip().lower() in FALSY_ANSWER):
            return False
        return _coerce_checkbox(raw)
    if type_hint == "integer":
        s = str(raw).replace(",", "").strip()
        try:
            return int(s)
        except (ValueError, TypeError):
            n = _parse_leading_number(s)
            return int(n) if n is not None else None
    if type_hint == "number":
        s = str(raw).replace(",", "").strip()
        # Percentage: "4%" or "4.00%" → 0.04. Canonical for rate fields.
        if s.endswith("%"):
            try:
                return float(s[:-1].strip()) / 100.0
            except (ValueError, TypeError):
                pass
        try:
            return float(s)
        except (ValueError, TypeError):
            return _parse_leading_number(s)
    if type_hint == "date":
        from dateutil import parser as _date_parser
        s = str(raw).strip()
        try:
            dt = _date_parser.parse(s, fuzzy=False)
        except (ValueError, TypeError, OverflowError):
            # Unparseable input (garbage OCR into a date-typed widget,
            # LLM emitting a non-date string, etc.) → treat as missing
            # rather than killing the whole extract. The scorer will
            # register this as extract_miss vs whatever gt says.
            return None
        return dt.date().isoformat()
    if type_hint == "category" and allowed_values:
        s = str(raw).strip().lower()
        for allowed in allowed_values:
            if str(allowed).strip().lower() == s:
                return allowed
        return None
    return raw


def load_blueprint(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _extract_widget(
    doc, widget: dict, *,
    ocr_api=None, whitelist: Optional[str] = None,
    page_img_cache: Optional[dict] = None,
    label_hint: Optional[set] = None,
) -> tuple[Any, str]:
    """Extract a single widget's value.

    Returns `(raw_value, path)` where `path ∈ {"acroform",
    "acroform_empty", "text_clip", "ocr", "missing"}`. The
    `acroform_empty` path fires when the AcroForm layer has this
    widget but the user left it blank — we return None and do NOT
    fall through to OCR (which would happily read background template
    text and return noise).
    """
    page_no = widget["page"] - 1
    if page_no >= len(doc):
        return (None, "missing")
    page = doc[page_no]

    # Path 1: AcroForm-native lookup — the interactive layer is
    # authoritative when it's present.
    #
    # Radio groups are special: multiple widgets share `field_name` (one
    # per selectable option). `widget.field_value` returns the individual
    # widget's on/off state, not the group's currently-selected value.
    # So for radios, iterate every widget with the matching field_name
    # and return the first non-Off state (that's the selected option).
    is_radio = widget.get("widget_type") == "radiobutton"
    matches = [pw for pw in page.widgets()
               if pw.field_name == widget.get("path")]
    if matches:
        if is_radio:
            for pw in matches:
                v = _unescape_pdf_name(pw.field_value)
                if v not in (None, "", "Off"):
                    return (v, "acroform")
            return (None, "acroform_empty")
        pw = matches[0]
        v = _unescape_pdf_name(pw.field_value)
        if v not in (None, ""):
            return (v, "acroform")
        # Widget found in AcroForm but empty → intentionally blank.
        # Suppress OCR fallback (which would read template noise).
        return (None, "acroform_empty")

    # Path 2: rect-clipped text extraction — the PDF is flattened or
    # the widget path drifted; try the embedded text layer.
    rect = pymupdf.Rect(*widget["rect"])
    txt = page.get_text("text", clip=rect).strip()
    if txt:
        txt = _clean_text_clip(txt, label_hint)
    if txt:
        return (txt, "text_clip")

    # Path 3: zonal OCR fallback — pure image scan, no text layer.
    if not _TESSEROCR_OK or ocr_api is None:
        return (None, "missing")

    if page_img_cache is None:
        page_img_cache = {}
    if page_no not in page_img_cache:
        pix = page.get_pixmap(dpi=OCR_DPI)
        page_img_cache[page_no] = Image.open(
            io.BytesIO(pix.tobytes("png"))
        )
    img = page_img_cache[page_no]

    scale = OCR_DPI / 72.0
    x0, y0, x1, y1 = widget["rect"]
    px0 = max(0, int(x0 * scale) - 2)
    py0 = max(0, int(y0 * scale) - 2)
    px1 = min(img.width, int(x1 * scale) + 2)
    py1 = min(img.height, int(y1 * scale) + 2)
    crop = img.crop((px0, py0, px1, py1))
    ocr_api.SetVariable(
        "tessedit_char_whitelist", whitelist or ""
    )
    ocr_api.SetImage(crop)
    text = ocr_api.GetUTF8Text().strip()

    # For checkbox / radiobutton widgets, use a check-indicator whitelist:
    # only characters that plausibly represent a check-mark survive. Anything
    # else Tesseract returns (misread border glyphs like `|`, `H`, `!`, `Bp`,
    # letters/digits from adjacent labels) → stripped → empty → unchecked.
    # More resilient than a growing blocklist of noise glyphs.
    if widget.get("widget_type") in ("checkbox", "radiobutton"):
        kept = "".join(c for c in text if c in _CHECK_INDICATORS)
        return (kept or None, "ocr")

    return (text or None, "ocr")


def _resolve_blank(blueprint: dict) -> Optional[Path]:
    try:
        from petey.validate.retype import resolve_blank      # imported here: retype imports the labeler
        return resolve_blank(blueprint)
    except Exception:
        return None


def _flat_option_blocks(blueprint: dict) -> bool:
    """Does any option box of this blueprint lack a widget path (a flat blueprint)? Marks there are ink."""
    for field in blueprint.get("fields", {}).values():
        if not isinstance(field, dict):
            continue
        for wb in (field.get("widgets") or {}).values():
            if isinstance(wb, dict) and not wb.get("path"):
                return True
        w = field.get("widget")
        if isinstance(w, dict) and not w.get("path") and (
                field.get("type") == "boolean" or w.get("widget_type") in ("checkbox", "radiobutton")):
            return True
    return False


def _ink_marked(doc, blank_doc, widget: dict) -> Optional[bool]:
    """Path 2b: is there added ink in this box, against the blank? None when the blank cannot be compared."""
    if blank_doc is None:
        return None
    page_no = int(widget.get("page", 0)) - 1
    if page_no < 0 or page_no >= len(doc) or page_no >= len(blank_doc) or not widget.get("rect"):
        return None
    from petey.validate.ink import is_marked
    try:
        return bool(is_marked(doc[page_no], blank_doc[page_no], widget["rect"]))
    except Exception:
        return None


def extract(blueprint: dict, pdf_path: Path, blank_pdf: Optional[Path] = None) -> dict:
    """Extract every field from the input PDF using the blueprint.

    `blank_pdf`: the blank the blueprint describes, for the ink read of
    option boxes that have no widget path (a flat blueprint). Resolved
    from the blueprint's `source_pdf` when not given; without a blank such
    boxes fall through to text_clip and OCR as before."""
    doc = pymupdf.open(str(pdf_path))
    blank_doc = None
    if _flat_option_blocks(blueprint):
        bp_blank = Path(blank_pdf) if blank_pdf else _resolve_blank(blueprint)
        if bp_blank is not None and Path(bp_blank).exists():
            blank_doc = pymupdf.open(str(bp_blank))

    tessdata = _tessdata_path() if _TESSEROCR_OK else None
    ocr_api = None
    if _TESSEROCR_OK and tessdata:
        ocr_api = tesserocr.PyTessBaseAPI(
            path=tessdata, psm=tesserocr.PSM.SINGLE_LINE,
        )

    values: dict[str, Any] = {}
    path_counts = {
        "acroform": 0, "acroform_empty": 0,
        "text_clip": 0, "ink": 0, "ocr": 0, "missing": 0,
    }
    # Per-field dispatch record — for scalar fields it's a single path
    # string; for mutex (`widgets:`) fields it's `{value: path}`. Lets the
    # scorer distinguish "extract reached the widget and saw it empty" from
    # "extract never touched the widget."
    dispatch_per_field: dict[str, Any] = {}
    page_img_cache: dict = {}

    from .semantic_types import ocr_whitelist_for

    try:
        for field_name, field in blueprint.get("fields", {}).items():
            # Category groups have multiple widgets keyed by value
            if "widgets" in field:
                selected: list[str] = []
                per_value_dispatch: dict[str, str] = {}
                for value, w_block in field["widgets"].items():
                    if w_block.get("on_state"):
                        # Option of a group: selected when the field at
                        # this path holds THIS option's on-state. Radio
                        # options share one path and differ only by
                        # on-state, so "is the path checked" would select
                        # every option at once.
                        states = _selected_states(doc, w_block)
                        path_counts["acroform" if states is not None else "acroform_empty"] += 1
                        per_value_dispatch[value] = "acroform"
                        if states and w_block["on_state"] in states:
                            selected.append(value)
                        continue
                    if not w_block.get("path") and blank_doc is not None:
                        marked = _ink_marked(doc, blank_doc, w_block)
                        if marked is not None:
                            path_counts["ink"] += 1
                            per_value_dispatch[value] = "ink"
                            if marked:
                                selected.append(value)
                            continue
                    raw, path = _extract_widget(
                        doc, w_block,
                        ocr_api=ocr_api,
                        page_img_cache=page_img_cache,
                    )
                    path_counts[path] += 1
                    per_value_dispatch[value] = path
                    if _coerce_checkbox(raw):
                        selected.append(value)
                dispatch_per_field[field_name] = per_value_dispatch
                if len(selected) == 1:
                    values[field_name] = selected[0]
                elif len(selected) > 1:
                    values[field_name] = selected
                else:
                    values[field_name] = None
                continue

            w_block = field.get("widget")
            if w_block is None:
                values[field_name] = None
                dispatch_per_field[field_name] = "no_widget"
                continue

            if (not w_block.get("path") and blank_doc is not None
                    and (field.get("type") == "boolean" or w_block.get("widget_type") in ("checkbox", "radiobutton"))):
                marked = _ink_marked(doc, blank_doc, w_block)
                if marked is not None:
                    path_counts["ink"] += 1
                    dispatch_per_field[field_name] = "ink"
                    values[field_name] = marked
                    continue
            whitelist = ocr_whitelist_for(field.get("semantic_type"))
            raw, path = _extract_widget(
                doc, w_block,
                ocr_api=ocr_api,
                whitelist=whitelist,
                page_img_cache=page_img_cache,
                label_hint=_label_tokens(field_name,
                                         field.get("description")),
            )
            path_counts[path] += 1
            dispatch_per_field[field_name] = path
            values[field_name] = _coerce_typed(
                raw, field.get("type", "string"),
                allowed_values=field.get("values"),
                widget_type=w_block.get("widget_type"),
            )
    finally:
        if ocr_api is not None:
            ocr_api.End()
        doc.close()
        if blank_doc is not None:
            blank_doc.close()

    values["_meta"] = {
        "dispatch_counts": path_counts,
        "dispatch_per_field": dispatch_per_field,
        "blueprint_source_pdf": blueprint.get("source_pdf"),
        "blueprint_form_version": blueprint.get("form_version"),
        "blueprint_source_pdf_hash": blueprint.get("source_pdf_hash"),
    }
    return values


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--blueprint", required=True, type=Path,
                    help="blueprint .bpt path")
    ap.add_argument("--pdf", required=True, type=Path,
                    help="input filled PDF")
    ap.add_argument("--output", type=Path, default=None,
                    help="output JSON path")
    args = ap.parse_args()

    bp = load_blueprint(args.blueprint)
    values = extract(bp, args.pdf)

    n_populated = sum(
        1 for k, v in values.items()
        if k != "_meta" and v is not None
    )
    n_total = sum(1 for k in values if k != "_meta")
    print(f"[extract] {n_populated} / {n_total} fields populated")
    d = values["_meta"]["dispatch_counts"]
    print(
        f"  dispatch: acroform={d['acroform']} "
        f"acroform_empty={d['acroform_empty']} "
        f"text_clip={d['text_clip']} ink={d.get('ink', 0)} ocr={d['ocr']} "
        f"missing={d['missing']}"
    )

    out_path = args.output or args.pdf.with_name(
        args.pdf.stem + "_extracted.json"
    )
    out_path.write_text(
        json.dumps(values, indent=2, default=str), encoding="utf-8"
    )
    print(f"[ok] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
