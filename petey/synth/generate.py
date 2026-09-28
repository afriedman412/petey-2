"""LLM-driven synthetic case generator that reads the blank PDF directly.

The LLM sees:
  - The blank form's page images (multimodal), so it can associate widget
    positions with the visible labels on the page.
  - An AcroForm inventory: `[{path, widget_type, export_values, page,
    rect}, ...]` derived from `pymupdf.Document.widgets()`.

The LLM returns:
  - `{path: value}` — one entry per AcroForm field. `path` is the AcroForm
    `field_name` (the shared name for radio groups). `value` is:
      * text            → string
      * checkbox        → bool (true = checked)
      * radiobutton     → one of the group's export_values (string)
      * combobox        → one of the choice strings

The output is both the fill payload (for `render_pdf`) AND the ground
truth (for scoring). No .bpt involved — this pipeline exists to validate
extraction against the .bpt without letting the .bpt shape the ground
truth (which would mask labeler bugs).
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Optional

import pymupdf

MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 32768
PAGE_DPI = 150


SYSTEM_PROMPT = """You generate one realistic filled case for a blank form. \
You see the form's page images AND an AcroForm widget inventory. Your \
job: fill every widget with a value that makes sense given its visible \
label on the page.

OUTPUT SHAPE:
- Return JSON only. No prose, no markdown, no code fences.
- Top-level shape: {"values": {"<acroform_path>": <value>, ...}}
- One entry per widget in the inventory.
- Values by widget_type:
  * text        → string. Realistic per the visible label (name, SSN, \
address, date, money amount, etc.).
  * checkbox    → true (checked) or false (unchecked). ALWAYS a JSON \
bool, never a string — even if the widget's `export_value` is a \
semantically-loaded label like "Yes", "No", or "Married". The \
export_value is metadata about the underlying widget; the value you \
emit for a checkbox is ONLY the bool.
  * radiobutton → one of the export_values listed for that widget (as \
a string).
  * combobox    → one of the choice strings.
- Use `null` for widgets that are legitimately blank on real filings \
(optional sub-totals, "Other" description when Other isn't selected, \
reserved fields).

GROUND EVERY VALUE IN THIS DOCUMENT. You may recognize this form. Do \
not fill it from that recollection: revisions change field sets, line \
numbering and layout, and the page images plus widget inventory \
supplied here are authoritative for THIS file. Fill a widget from the \
label visible next to it on the page, not from where you remember that \
field living. Where memory of the form conflicts with what you were \
given, what you were given wins.

UNIQUENESS:
- Every text value in the case must be recognizably unique. Do NOT reuse \
the same value across widgets (e.g., don't put the same name in two \
text fields). This is critical: the case is used to check that \
extraction pulls the right value out of the right widget, so distinct \
values per widget are required.

COHERENCE:
- ZIP / state / phone area code align (e.g., MA ZIP 01xxx, area 617).
- Dates flow logically (birth < service < today; policy effective < \
expiration by 12 months).
- Related amounts have plausible relative sizes (fed tax withheld ~10-25% \
of taxable amount).
- Names formatted "Last, First M" unless the widget describes a business, \
trust, estate, or organization.

FIDELITY:
- Use real US city names. Vary across cases.
- SSNs: area numbers 100-899. EINs: XX-XXXXXXX.
- ISO dates for date fields: YYYY-MM-DD.
- Money: dollars-and-cents for healthcare / insurance / payroll; whole \
dollars for IRS forms.
"""


USER_TEMPLATE = """Widget inventory:

```json
{inventory_json}
```

The form's page images are attached. Fill every widget in the inventory \
with a realistic value per its visible label. Return JSON:

{{"values": {{"<path>": <value>, ...}}}}
"""


def _unescape_pdf_name(s: Optional[str]) -> Optional[str]:
    """Decode PDF name-object hex escapes (`#XX`).

    PDF names encode reserved bytes (`/`, ` `, `(`, `)`, etc.) as `#XX`
    hex escapes. pymupdf returns the raw name — `N/A` comes through as
    `N#2FA`. Downstream (LLM prompt, fill_pdf's `RadioGroup.select`,
    extract's value comparison) all want the decoded form.
    """
    if not s or "#" not in s:
        return s
    return re.sub(
        r"#([0-9A-Fa-f]{2})",
        lambda m: chr(int(m.group(1), 16)),
        s,
    )


def _widget_type_string(field_type: int) -> str:
    """Map pymupdf widget type int → canonical string."""
    return {
        pymupdf.PDF_WIDGET_TYPE_TEXT: "text",
        pymupdf.PDF_WIDGET_TYPE_CHECKBOX: "checkbox",
        pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON: "radiobutton",
        pymupdf.PDF_WIDGET_TYPE_COMBOBOX: "combobox",
        pymupdf.PDF_WIDGET_TYPE_LISTBOX: "listbox",
        pymupdf.PDF_WIDGET_TYPE_SIGNATURE: "signature",
    }.get(field_type, "unknown")


def enumerate_widgets(pdf_path: Path) -> list[dict]:
    """Return the AcroForm inventory used both by the LLM and by fill.

    Radio widgets that share a `field_name` are collapsed into one entry
    (the group), with `export_values` = the union of per-widget on-states.
    Everything else appears once per widget.
    """
    doc = pymupdf.open(str(pdf_path))
    per_widget: list[dict] = []
    try:
        for page_no, page in enumerate(doc, start=1):
            for w in page.widgets() or []:
                wt = _widget_type_string(w.field_type)
                per_widget.append({
                    "path": w.field_name,
                    "widget_type": wt,
                    "page": page_no,
                    "rect": [round(c, 2) for c in w.rect],
                    "on_state": (_unescape_pdf_name(w.on_state())
                                 if wt in ("checkbox", "radiobutton")
                                 else None),
                    "choices": (list(w.choice_values)
                                if wt in ("combobox", "listbox")
                                and w.choice_values else None),
                })
    finally:
        doc.close()

    # Group radios by shared field_name.
    grouped: list[dict] = []
    radio_groups: dict[str, dict] = {}
    for w in per_widget:
        if w["widget_type"] == "radiobutton":
            g = radio_groups.get(w["path"])
            if g is None:
                g = {
                    "path": w["path"],
                    "widget_type": "radiobutton",
                    "page": w["page"],
                    "rect": w["rect"],
                    "export_values": [],
                }
                radio_groups[w["path"]] = g
                grouped.append(g)
            on = w.get("on_state")
            if on and on not in g["export_values"]:
                g["export_values"].append(on)
            continue
        entry = {
            "path": w["path"],
            "widget_type": w["widget_type"],
            "page": w["page"],
            "rect": w["rect"],
        }
        if w["widget_type"] == "checkbox" and w.get("on_state"):
            entry["export_value"] = w["on_state"]
        if w.get("choices"):
            entry["choices"] = w["choices"]
        grouped.append(entry)
    return grouped


def render_page_pngs(pdf_path: Path, dpi: int = PAGE_DPI) -> list[bytes]:
    """Render each page to PNG bytes for the multimodal prompt."""
    doc = pymupdf.open(str(pdf_path))
    out: list[bytes] = []
    try:
        for page in doc:
            pix = page.get_pixmap(dpi=dpi)
            out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


def _extract_json_object(text: str) -> Optional[dict]:
    """Extract the outermost JSON object from the LLM response."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start >= 0:
                blob = text[start:i + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError:
                    start = -1
    return None


def _call_llm_one_page(
    client, model: str, page_png: bytes, page_inventory: list[dict],
) -> dict[str, Any]:
    """One LLM call for one page's widgets. Returns `{path: value}`."""
    inventory_json = json.dumps(page_inventory, indent=2)
    user_text = USER_TEMPLATE.format(inventory_json=inventory_json)
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": base64.standard_b64encode(page_png).decode("ascii"),
            },
        },
        {"type": "text", "text": user_text},
    ]
    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        final = stream.get_final_message()
    text = "".join(
        b.text for b in final.content if getattr(b, "type", None) == "text"
    )
    parsed = _extract_json_object(text)
    if not parsed or "values" not in parsed:
        raise RuntimeError(
            f"LLM did not return {{'values': {{...}}}}.\nGot: {text[:500]}"
        )
    values = parsed["values"]
    if not isinstance(values, dict):
        raise RuntimeError(
            f"Expected dict under 'values', got {type(values)}"
        )
    return values


def generate_from_pdf(
    pdf_path: str | Path,
    *,
    n: int = 1,
    model: str = MODEL,
    cache_dir: Optional[Path] = None,
    cache_key_prefix: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Generate N cases. Each case is `{path: value}` covering every widget.

    One LLM call per page, so total response tokens scale with widgets-per-
    page, not widgets-per-form. Necessary for forms like 990-PF (1147 widgets
    over 13 pages) that overflow a single call's MAX_TOKENS. Paths are unique
    across pages (they're AcroForm field_names), so a plain `dict.update`
    merges the per-page responses safely.

    If `cache_dir` is provided, per-case output is cached to disk keyed on
    `sha256(pdf_bytes + model + cache_key_prefix + case_index)`. Reruns with
    the same inputs skip the LLM entirely. `cache_key_prefix` disambiguates
    when the same blank PDF is generated against multiple times (e.g., pass
    the form_id so different validation runs don't collide).
    """
    import anthropic
    import hashlib

    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"blank PDF not found: {pdf_path}")

    pdf_bytes = pdf_path.read_bytes()

    def _cache_path_for(case_index: int) -> Optional[Path]:
        if cache_dir is None:
            return None
        h = hashlib.sha256()
        h.update(pdf_bytes)
        h.update(b"\x00")
        h.update(model.encode("utf-8"))
        h.update(b"\x00")
        h.update((cache_key_prefix or "").encode("utf-8"))
        h.update(b"\x00")
        h.update(str(case_index).encode("utf-8"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{h.hexdigest()}.json"

    inventory = enumerate_widgets(pdf_path)
    page_pngs = render_page_pngs(pdf_path)

    by_page: dict[int, list[dict]] = {}
    for entry in inventory:
        by_page.setdefault(entry["page"], []).append(entry)

    client: Any = None
    cases: list[dict[str, Any]] = []
    for i in range(n):
        cp = _cache_path_for(i)
        if cp is not None and cp.exists():
            cases.append(json.loads(cp.read_text(encoding="utf-8")))
            continue
        if client is None:
            client = anthropic.Anthropic()
        merged: dict[str, Any] = {}
        for page_no in sorted(by_page.keys()):
            page_inventory = by_page[page_no]
            page_png = page_pngs[page_no - 1]
            values = _call_llm_one_page(
                client, model, page_png, page_inventory,
            )
            merged.update(values)
        if cp is not None:
            cp.write_text(json.dumps(merged, indent=2))
        cases.append(merged)
    return cases
