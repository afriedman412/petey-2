"""Geometry for a fillable form: its AcroForm widgets, read with pymupdf.

Exact rects and the publisher's field paths, for free. Lifted verbatim from
auto_label.py so the programmatic source (`programmatic.py`) can emit the
same record and the labeler stops caring where geometry came from.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import pymupdf

PUSHBUTTON_FLAG = 1 << 16


def _unescape_pdf_name(s: Optional[str]) -> Optional[str]:
    """Decode PDF name-object hex escapes (`#XX` → the byte).

    pymupdf returns raw AcroForm names — a radio on-state of "N/A"
    comes through as "N#2FA". Un-escape once at read time so the .bpt's
    `values:` list holds "N/A" and downstream (LLM prompt, fill,
    extract, score) all speak the decoded form.
    """
    if not s or "#" not in s:
        return s
    return re.sub(
        r"#([0-9A-Fa-f]{2})",
        lambda m: chr(int(m.group(1), 16)),
        s,
    )


def _widget_type_string(field_type: int) -> str:
    """Map pymupdf widget-type constants to blueprint widget_type.

    AcroForm widget type is authoritative — the VLM is never allowed to
    reclassify. Radio buttons preserve their identity so the labeler can
    group them by shared field_name and emit them as `type: category`
    at the group level (or `type: boolean` for singleton groups).
    Comboboxes / listboxes: single-choice string, treat as text.
    Signatures: no text value, treat as text.

    Pushbuttons used to land here too, and that was the bug behind
    OBSERVATIONS class 12 — 106 fields across 12 blueprints bound to
    controls that hold no value at all. They are dropped in
    `enumerate_widgets` now rather than typed.
    """
    if field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
        return "checkbox"
    if field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
        return "radiobutton"
    return "text"


# PDF field flag bit 17. A pushbutton is a control: it fires an action and
# retains no value, verified across the corpus as `field_value == ''` on
# every one. The flag is exact — of 51,919 widgets in `source_pdfs/`, all
# 548 carrying it are type Button, and no CheckBox, RadioButton, ComboBox,
# Signature or Text does.
PUSHBUTTON_FLAG = 1 << 16

# PDF field flag bit 1 (ReadOnly), combined with a non-empty default value.
# Some form-conversion tools emit the printed CAPTION as a locked form field
# sitting beside the data field it labels: Form5020 carries a widget named
# `31` holding `'31. SOCIAL SECURITY NUMBER'` next to `31_SOC_A_SECUPITi_NUMB`
# (the garbled name gives the tool away) which holds the actual number.
#
# Labeled as a data field it is poison in both directions: the generator
# writes a value into a widget that cannot hold one, and a meaning-based
# reader asked for `employee_ssn` correctly returns the real SSN and is
# scored against the caption. That is how it was found — `petey` was right
# and the blueprint was wrong.
#
# Both conditions are required. ReadOnly ALONE is a locked but real data
# field, often calculated — 1,683 of those in `source_pdfs/` against 384
# captions, so dropping on the flag alone would discard four times more
# real fields than captions.
READONLY_FLAG = 1 << 0


def _is_caption_widget(w) -> bool:
    """A locked widget whose value IS the printed label."""
    if not ((w.field_flags or 0) & READONLY_FLAG):
        return False
    return bool((w.field_value or "").strip())


def enumerate_widgets(pdf_path: Path) -> tuple[list[dict], list[dict]]:
    """Return `(widgets, dropped)`.

    Dropped widgets are REPORTED, not silently skipped. A silent filter
    would give us no way to notice the form where the assumption breaks,
    whereas `_dedup.py` logging its collisions is exactly what made class
    13 enumerable across the library without measuring anything. The
    corpus behind this filter is 482 mostly-US-government forms; non-US
    and commercial forms are where a different convention would show up.
    """
    doc = pymupdf.open(str(pdf_path))
    widgets: list[dict] = []
    dropped: list[dict] = []
    idx = 0
    for page_num, page in enumerate(doc, start=1):
        for w in page.widgets():
            tooltip = (w.field_label or "").strip() or None
            if (w.field_flags or 0) & PUSHBUTTON_FLAG:
                dropped.append({
                    "path": w.field_name,
                    "page": page_num,
                    "reason": "pushbutton",
                    "field_type": w.field_type_string,
                    "tooltip": tooltip,
                })
                continue
            if _is_caption_widget(w):
                dropped.append({
                    "path": w.field_name,
                    "page": page_num,
                    "reason": "caption",
                    "field_type": w.field_type_string,
                    "tooltip": tooltip,
                    "caption": (w.field_value or "").strip()[:80],
                })
                continue
            wt = _widget_type_string(w.field_type)
            entry = {
                "id": idx,
                "page": page_num,
                "rect": [float(x) for x in w.rect],
                "widget_type": wt,
                "path": w.field_name,
            }
            if tooltip:
                entry["tooltip"] = tooltip
            if wt in ("radiobutton", "checkbox"):
                # Every button carries its on-state. Checkbox FIELDS with
                # several kids and distinct on-states (CMS-1500 insurance
                # type: Medicare / Medicaid / ...) are option groups exactly
                # like radios; without the state they dedup to one box.
                try:
                    entry["on_state"] = _unescape_pdf_name(w.on_state())
                except Exception:
                    entry["on_state"] = None
            widgets.append(entry)
            idx += 1
    doc.close()
    return widgets, dropped
