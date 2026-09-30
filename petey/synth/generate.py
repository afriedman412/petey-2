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
import time
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


BLIND_SYSTEM_PROMPT = """You generate one realistic filled case for a blank form. \
You see the form's page image with a numbered red box drawn on every \
fillable widget, and an inventory that lists each box number with its \
control type. Nothing else about the widgets is given: read the printed \
label next to each box on the page and fill it with a value that makes \
sense there.

OUTPUT SHAPE:
- Return JSON only. No prose, no markdown, no code fences.
- Top-level shape: {"values": {"<box number>": <value>, ...}}
- One entry per box in the inventory.
- Values by type:
  * text     → string. Realistic per the printed label (name, SSN, \
address, date, money amount, etc.). Respect `maxlen` when given: the \
box holds that many characters, so write an SSN as 9 digits in a \
9-character box.
  * checkbox → true (checked) or false (unchecked). ALWAYS a JSON bool.
  * radio    → the box number of the ONE option to select, from its \
`options` list, as a string; or null to leave the group unselected.
  * combobox → one of the listed `choices`.
- Use `null` for boxes that are legitimately blank on real filings \
(optional sub-totals, "Other" description when Other isn't selected, \
reserved fields).

GROUND EVERY VALUE IN THIS DOCUMENT. You may recognize this form. Do \
not fill it from that recollection: revisions change field sets, line \
numbering and layout, and the page image supplied here is authoritative \
for THIS file. Fill a box from the label printed next to it, not from \
where you remember that field living.

UNIQUENESS:
- Every text value in the case must be recognizably unique. Do NOT reuse \
the same value across boxes. The case is used to check that extraction \
pulls the right value out of the right box, so distinct values per box \
are required.

COHERENCE:
- ZIP / state / phone area code align (e.g., MA ZIP 01xxx, area 617).
- Dates flow logically (birth < service < today; policy effective < \
expiration by 12 months).
- Related amounts have plausible relative sizes.
- Names formatted "Last, First M" unless the label describes a business, \
trust, estate, or organization.

FIDELITY:
- Use real US city names. Vary across cases.
- SSNs: area numbers 100-899. EINs: XX-XXXXXXX.
- ISO dates for date fields: YYYY-MM-DD, unless the box shows a \
different printed format (MM/DD/YYYY) or is a single date part.
- Money: dollars-and-cents for healthcare / insurance / payroll; whole \
dollars for IRS forms.
"""


BLIND_USER_TEMPLATE = """Boxes on this page:

```json
{inventory_json}
```

The page image is attached with each box number drawn at the top-left \
corner of its red rectangle. Fill every box per the label printed next \
to it. Return JSON:

{{"values": {{"<box number>": <value>, ...}}}}
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


_COMB_FLAG = 1 << 24


def blind_inventory(pdf_path: Path) -> tuple[dict[int, list[dict]], dict[str, dict]]:
    """The leak-minimized view of a form's widgets.

    Returns `(per_page_boxes, key)`. `per_page_boxes[page]` is what the
    model sees: `{id, type}` plus `maxlen` for text, `options` (member
    box ids) for a radio group, `choices` for a combobox, and the box
    rect for drawing. `key[id]` is what stays local: the AcroForm path
    and, for radio members, the on-state — the publisher's names never
    reach the model, so its values cannot be steered by the same evidence
    the labeler uses.
    """
    # Checkbox FIELDS with several kids and distinct on-states are option
    # groups too (I-765 marital status, unit types; CMS-1500 insurance
    # type). Shown as independent true/false boxes, the kids' answers
    # overwrite one another on the shared path and every blind case left
    # the group unselected (found 2026-09-30: 8 of 8 I-765 cases).
    group_paths: set[str] = set()
    scan = pymupdf.open(str(pdf_path))
    try:
        kids: dict[str, int] = {}
        states: dict[str, set] = {}
        for page in scan:
            for w in page.widgets() or []:
                if w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
                    kids[w.field_name] = kids.get(w.field_name, 0) + 1
                    try:
                        on = w.on_state()
                    except Exception:
                        on = None
                    if on:
                        states.setdefault(w.field_name, set()).add(on)
        group_paths = {n for n, k in kids.items() if k > 1 and len(states.get(n, ())) > 1}
    finally:
        scan.close()

    doc = pymupdf.open(str(pdf_path))
    per_page: dict[int, list[dict]] = {}
    key: dict[str, dict] = {}
    next_id = 1
    radio_groups: dict[str, dict] = {}
    try:
        for page_no, page in enumerate(doc, start=1):
            boxes = per_page.setdefault(page_no, [])
            for w in page.widgets() or []:
                wt = _widget_type_string(w.field_type)
                if wt in ("signature", "unknown"):
                    continue
                if (w.field_flags or 0) & (1 << 16):  # pushbutton
                    continue
                bid = str(next_id)
                next_id += 1
                rect = [round(c, 2) for c in w.rect]
                if wt == "radiobutton" or (wt == "checkbox" and w.field_name in group_paths):
                    g = radio_groups.get(w.field_name)
                    if g is None:
                        gid = str(next_id)
                        next_id += 1
                        g = {"id": gid, "type": "radio", "options": [],
                             "rect": rect, "_page": page_no}
                        radio_groups[w.field_name] = g
                        boxes.append(g)
                        key[gid] = {"path": w.field_name, "type": "radio"}
                    g["options"].append(bid)
                    boxes.append({"id": bid, "type": "radio_option",
                                  "of": g["id"], "rect": rect})
                    key[bid] = {"path": w.field_name, "type": "radio_option",
                                "on_state": _unescape_pdf_name(w.on_state())}
                    continue
                entry = {"id": bid, "type": wt, "rect": rect}
                if wt == "text":
                    maxlen = int(w.text_maxlen or 0)
                    if maxlen:
                        entry["maxlen"] = maxlen
                    if (w.field_flags or 0) & _COMB_FLAG:
                        entry["comb"] = True
                elif wt in ("combobox", "listbox") and w.choice_values:
                    entry["choices"] = list(w.choice_values)
                boxes.append(entry)
                key[bid] = {"path": w.field_name, "type": wt}
    finally:
        doc.close()
    return per_page, key


def _model_view(boxes: list[dict]) -> list[dict]:
    """Strip the drawing-only keys before the inventory goes to the model."""
    out = []
    for b in boxes:
        if b["type"] == "radio_option":
            continue
        e = {k: v for k, v in b.items() if k not in ("rect", "_page")}
        out.append(e)
    return out


def render_annotated_pages(pdf_path: Path, per_page: dict[int, list[dict]],
                           dpi: int = PAGE_DPI) -> list[bytes]:
    """Page PNGs with a numbered red box drawn on every widget."""
    doc = pymupdf.open(str(pdf_path))
    out: list[bytes] = []
    try:
        for page_no, page in enumerate(doc, start=1):
            for b in per_page.get(page_no, []):
                if b["type"] == "radio":
                    continue  # the group has no box of its own; members do
                r = pymupdf.Rect(*b["rect"])
                page.draw_rect(r, color=(1, 0, 0), width=0.6)
                fs = 5 if r.height < 9 else 6
                page.insert_text(pymupdf.Point(r.x0 + 0.8, r.y0 + fs + 0.4),
                                 b["id"], fontsize=fs, color=(1, 0, 0),
                                 fontname="helv")
            pix = page.get_pixmap(dpi=dpi)
            out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


def unblind(values: dict[str, Any], key: dict[str, dict]) -> dict[str, Any]:
    """Model output `{box id: value}` -> `{acroform_path: value}`."""
    out: dict[str, Any] = {}
    for bid, v in values.items():
        k = key.get(str(bid))
        if k is None:
            continue
        if k["type"] == "radio":
            if v in (None, ""):
                out[k["path"]] = None
                continue
            member = key.get(str(v))
            if member and member["type"] == "radio_option" \
                    and member["path"] == k["path"]:
                out[k["path"]] = member.get("on_state")
            else:
                out[k["path"]] = None
        elif k["type"] == "radio_option":
            continue
        else:
            out[k["path"]] = v
    return out


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


# Other vendors' models speak the OpenAI chat-completions dialect at their own
# endpoints; one client class covers them all. Keys come from this repo's .env,
# then petey-master's (the user keeps the non-Anthropic keys there).
PROVIDERS = {
    # prefix -> (base_url, key env var). None base_url = api.openai.com
    "gpt-": (None, "OPENAI_API_KEY"),
    "o1": (None, "OPENAI_API_KEY"),
    "o3": (None, "OPENAI_API_KEY"),
    "o4": (None, "OPENAI_API_KEY"),
    "gemini-": ("https://generativelanguage.googleapis.com/v1beta/openai/", "GEMINI_API_KEY"),
    "deepseek-": ("https://api.deepseek.com", "DEEPSEEK_API_KEY"),
    "mistral-": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "pixtral-": ("https://api.mistral.ai/v1", "MISTRAL_API_KEY"),
    "accounts/fireworks/": ("https://api.fireworks.ai/inference/v1", "FIREWORKS_API_KEY"),
}
_ENV_FILES = (Path(__file__).resolve().parents[2] / ".env",
              Path(__file__).resolve().parents[3] / "petey-master" / ".env")


def provider_for(model: str):
    """(base_url, key_env) for a non-Anthropic model id, else None."""
    for pre, cfg in PROVIDERS.items():
        if model.startswith(pre):
            return cfg
    return None


def _load_keys() -> None:
    import os
    for env in _ENV_FILES:
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def make_client(model: str):
    """An SDK client for `model`: Anthropic by default, OpenAI-compatible for
    the vendors in PROVIDERS."""
    import os
    _load_keys()
    cfg = provider_for(model)
    if cfg is None:
        import anthropic
        return anthropic.Anthropic()
    from openai import OpenAI
    base_url, key_env = cfg
    key = os.environ.get(key_env)
    if not key:
        raise RuntimeError(f"{key_env} not set (looked in {', '.join(str(e) for e in _ENV_FILES)})")
    return OpenAI(api_key=key, base_url=base_url, timeout=600)


def _call_openai_compatible_one_page(client, model: str, page_png: bytes, system: str,
                                     user_text: str, tag: str) -> str:
    """Same page, same prompt, chat-completions dialect. Returns the text."""
    from petey.label import call_log
    t0 = time.time()
    data_url = "data:image/png;base64," + base64.standard_b64encode(page_png).decode("ascii")
    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": [
                      {"type": "image_url", "image_url": {"url": data_url}},
                      {"type": "text", "text": user_text}]}],
    )
    # reasoning models take max_completion_tokens and reject temperature
    if model.startswith(("gpt-5", "o1", "o3", "o4")):
        kwargs["max_completion_tokens"] = MAX_TOKENS
    else:
        kwargs["max_tokens"] = MAX_TOKENS
        kwargs["temperature"] = 0
    resp = client.chat.completions.create(**kwargs)
    choice = resp.choices[0]
    text = choice.message.content or ""
    u = getattr(resp, "usage", None)
    call_log.record(tag, raw=text, finish_reason=getattr(choice, "finish_reason", None),
                    request={"model": model, "prompt_chars": len(user_text)},
                    usage={"input_tokens": getattr(u, "prompt_tokens", None),
                           "output_tokens": getattr(u, "completion_tokens", None)} if u else None,
                    elapsed=time.time() - t0)
    return text


def _call_llm_one_page(
    client, model: str, page_png: bytes, page_inventory: list[dict],
    blind: bool = False, tag: str = "generate",
) -> dict[str, Any]:
    """One LLM call for one page's widgets. Returns `{path: value}`
    (or `{box id: value}` in blind mode; the caller unblinds)."""
    inventory_json = json.dumps(page_inventory, indent=2)
    if blind:
        user_text = BLIND_USER_TEMPLATE.format(inventory_json=inventory_json)
        system = BLIND_SYSTEM_PROMPT
    else:
        user_text = USER_TEMPLATE.format(inventory_json=inventory_json)
        system = SYSTEM_PROMPT
    if provider_for(model) is not None:
        text = _call_openai_compatible_one_page(client, model, page_png, system, user_text, tag)
        parsed = _extract_json_object(text)
        if not parsed or "values" not in parsed:
            raise RuntimeError(f"LLM did not return {{'values': {{...}}}}.\nGot: {text[:500]}")
        if not isinstance(parsed["values"], dict):
            raise RuntimeError(f"Expected dict under 'values', got {type(parsed['values'])}")
        return parsed["values"]
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
    t0 = time.time()
    with client.messages.stream(
        model=model,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": content}],
    ) as stream:
        final = stream.get_final_message()
    text = "".join(
        b.text for b in final.content if getattr(b, "type", None) == "text"
    )
    from petey.label import call_log
    u = getattr(final, "usage", None)
    call_log.record(tag, raw=text, finish_reason=getattr(final, "stop_reason", None),
                    request={"model": model, "prompt_chars": len(user_text)},
                    usage={"input_tokens": getattr(u, "input_tokens", None),
                           "output_tokens": getattr(u, "output_tokens", None)} if u else None,
                    elapsed=time.time() - t0)
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
    blind: bool = True,
    client: Any = None,
    cache_only: bool = False,
) -> list[dict[str, Any]]:
    """Generate N cases. Each case is `{path: value}` covering every widget.

    `blind` (default) shows the model numbered boxes on the page image and
    an inventory of ids and control types only — no AcroForm names, no
    export values — and maps ids back to paths here (`blind_inventory`,
    `unblind`). `blind=False` is the original prompt with the full
    inventory. `client` lets a test inject a stand-in for the API.

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
        if blind:
            h.update(b"\x00blind")
        h.update(b"\x00")
        h.update((cache_key_prefix or "").encode("utf-8"))
        h.update(b"\x00")
        h.update(str(case_index).encode("utf-8"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir / f"{h.hexdigest()}.json"

    if cache_only:
        hits = [_cache_path_for(i) for i in range(n)]
        if not all(cp is not None and cp.exists() for cp in hits):
            return []
        return [json.loads(cp.read_text(encoding="utf-8")) for cp in hits]

    key: dict[str, dict] = {}
    if blind:
        per_page, key = blind_inventory(pdf_path)
        page_pngs = render_annotated_pages(pdf_path, per_page)
        by_page = {p: _model_view(b) for p, b in per_page.items() if b}
    else:
        inventory = enumerate_widgets(pdf_path)
        page_pngs = render_page_pngs(pdf_path)
        by_page = {}
        for entry in inventory:
            by_page.setdefault(entry["page"], []).append(entry)

    cases: list[dict[str, Any]] = []
    for i in range(n):
        cp = _cache_path_for(i)
        if cp is not None and cp.exists():
            cases.append(json.loads(cp.read_text(encoding="utf-8")))
            continue
        if cache_only:
            return []  # caller decides; no API call is made
        if client is None:
            client = make_client(model)
        merged: dict[str, Any] = {}
        tag = f"generate/{cache_key_prefix or pdf_path.stem}/{model.replace('/', '_')}"
        for page_no in sorted(by_page.keys()):
            page_inventory = by_page[page_no]
            page_png = page_pngs[page_no - 1]
            values = _call_llm_one_page(
                client, model, page_png, page_inventory, blind=blind, tag=tag,
            )
            if blind:
                values = unblind(values, key)
            merged.update(values)
        if cp is not None:
            cp.write_text(json.dumps(merged, indent=2))
        cases.append(merged)
    return cases


def dry_run(pdf_path: Path, out_dir: Path) -> dict:
    """Write exactly what the blind generator would send: one annotated
    PNG per page and the per-page inventory; the id->path key separately.
    Lets the leak surface be eyeballed without an API call."""
    out_dir.mkdir(parents=True, exist_ok=True)
    per_page, key = blind_inventory(pdf_path)
    pngs = render_annotated_pages(pdf_path, per_page)
    payload = {}
    for page_no, png in enumerate(pngs, start=1):
        boxes = per_page.get(page_no, [])
        if not boxes:
            continue
        (out_dir / f"page_{page_no:02d}.png").write_bytes(png)
        payload[page_no] = _model_view(boxes)
    (out_dir / "model_view.json").write_text(json.dumps(payload, indent=1))
    (out_dir / "key.json").write_text(json.dumps(key, indent=1))
    n_boxes = sum(len(v) for v in payload.values())
    return {"pages": len(payload), "boxes": n_boxes, "out": str(out_dir)}


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Synthetic ground truth from a blank form (multimodal LLM).")
    ap.add_argument("pdf", type=Path)
    ap.add_argument("--dry-run", type=Path, metavar="DIR",
                    help="write the blind payload (annotated pages + inventory) "
                         "to DIR and stop; no API call")
    ap.add_argument("--n", type=int, default=1)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--full-inventory", action="store_true",
                    help="original prompt: paths and export values go to the model")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    if args.dry_run:
        print(dry_run(args.pdf, args.dry_run))
        return 0
    cases = generate_from_pdf(args.pdf, n=args.n, model=args.model,
                              blind=not args.full_inventory)
    text = json.dumps(cases, indent=2)
    if args.out:
        args.out.write_text(text)
        print(f"[ok] {len(cases)} case(s) -> {args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
