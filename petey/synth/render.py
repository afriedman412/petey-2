"""Fill an AcroForm PDF with path-keyed values via pymupdf.

`render_pdf()` consumes:
  - `values`: `{acroform_path: value}` — the LLM's per-widget output
    from `generate_from_pdf()`.
  - `blank_pdf`: the blank template to fill.
  - `out`: output path for the filled PDF.

Split routing by widget type (from the blank PDF's AcroForm layer):
  * text        → `widget.field_value = str(v)`
  * checkbox    → `widget.field_value = widget.on_state() or "Yes"` / `"Off"`
  * radiobutton → the export value string (`widget.field_value = v`)

Values whose path doesn't appear in the AcroForm inventory are silently
dropped (LLM hallucinated a path). Widgets in the AcroForm that don't
appear in `values` stay at their default state.

Previously this shelled out to a Node/pdf-lib script. Swapped to pymupdf
because pdf-lib fails on two structural pathologies we hit in the wild:
  1. Widgets missing the N (Normal) appearance stream (Adobe LiveCycle
     output). pdf-lib requires N; pymupdf regenerates on write.
  2. XFA-hybrid PDFs (LiveCycle-authored USCIS/ACORD forms). pdf-lib
     strips XFA on load, leaving dangling object refs that crash fill.
     pymupdf handles the hybrid without stripping.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pymupdf


def _coerce_checkbox_value(
    widget: pymupdf.Widget, value: Any,
) -> str:
    """Return the string pymupdf wants for a checkbox `field_value`.

    Checked → widget's on_state (usually "Yes", but forms may declare
    "1", "On", "Married", or any custom string). Unchecked → "Off"
    (universal PDF constant).
    """
    if value:
        on = widget.on_state()
        return on if on else "Yes"
    return "Off"


def render_pdf(
    values: dict[str, Any],
    blank_pdf: str | Path,
    out: str | Path,
) -> dict:
    """Fill `blank_pdf` with `values`, write to `out`. Returns the fill report."""
    blank_pdf = Path(blank_pdf)
    out = Path(out)

    doc = pymupdf.open(str(blank_pdf))
    n_text_filled = n_text_skipped = 0
    n_checkbox_filled = n_checkbox_skipped = 0
    n_radio_filled = n_radio_skipped = 0

    try:
        # Radio groups: pymupdf exposes each radio widget individually with
        # the shared field_name. Selecting one means setting its value to
        # the on_state and setting siblings in the group to Off, so the
        # group has to be handled together rather than widget by widget.
        #
        # Only the NAMES are collected here, never the widget objects. A
        # pymupdf Widget holds a weak reference to its page, and iterating
        # `page.widgets()` again invalidates every handle yielded earlier:
        # touching one then raises `ReferenceError: weakly-referenced object
        # no longer exists`. The text pass below iterates every page, so
        # handles collected now are dead by the time the radio pass runs —
        # and the pass caught `Exception` broadly, so every group silently
        # counted as skipped and nothing was ever filled.
        #
        # That failure is worse than a crash. Ground truth says 'Male', the
        # page holds nothing, `native` honestly reports None and is scored a
        # miss, while a meaning-based reader guesses 'Male' from the field
        # name and is scored as agreeing. The eval rewarded the hallucination
        # and penalised the correct answer.
        radio_group_names: set[str] = set()
        # Checkbox FIELDS with several kids and distinct on-states are option
        # groups too (CMS-1500 insurance type: Medicare / Medicaid / ...).
        # The value is an on-state; only the kid carrying it goes on, the
        # others go Off. Treating each kid as its own checkbox turned every
        # kid on whenever the value was truthy.
        checkbox_states: dict[str, set[str]] = {}
        checkbox_kids: dict[str, int] = {}
        for page in doc:
            for w in page.widgets() or []:
                if w.field_type == pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    radio_group_names.add(w.field_name)
                elif w.field_type == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
                    checkbox_kids[w.field_name] = checkbox_kids.get(w.field_name, 0) + 1
                    try:
                        on = w.on_state()
                    except Exception:
                        on = None
                    if on:
                        checkbox_states.setdefault(w.field_name, set()).add(on)
        checkbox_groups = {n for n, k in checkbox_kids.items()
                           if k > 1 and len(checkbox_states.get(n, ())) > 1}

        for page in doc:
            for w in page.widgets() or []:
                name = w.field_name
                if name not in values:
                    continue
                value = values[name]
                wt = w.field_type

                try:
                    if wt == pymupdf.PDF_WIDGET_TYPE_TEXT:
                        if value is None or value == "":
                            continue
                        w.field_value = str(value)
                        w.update()
                        n_text_filled += 1
                    elif wt == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
                        if name in checkbox_groups:
                            on = w.on_state()
                            w.field_value = on if (value not in (None, "", False) and str(value) == str(on)) else "Off"
                        else:
                            w.field_value = _coerce_checkbox_value(w, value)
                        w.update()
                        n_checkbox_filled += 1
                    elif wt == pymupdf.PDF_WIDGET_TYPE_COMBOBOX:
                        if value is None or value == "":
                            continue
                        w.field_value = str(value)
                        w.update()
                        n_text_filled += 1
                    # Radios handled in the group pass below.
                except Exception:
                    if wt == pymupdf.PDF_WIDGET_TYPE_TEXT:
                        n_text_skipped += 1
                    elif wt == pymupdf.PDF_WIDGET_TYPE_CHECKBOX:
                        n_checkbox_skipped += 1

        # Radio pass: re-resolve the widgets by a fresh iteration, then set
        # the member whose on_state matches the requested export value and
        # turn its siblings off. Resolving here rather than reusing handles
        # from the collection pass is the whole point — see above.
        wanted = {g: str(values[g]) for g in radio_group_names
                  if g in values and values[g] not in (None, "")}
        matched_groups: set[str] = set()
        errored_groups: dict[str, str] = {}
        for page in doc:
            for w in page.widgets() or []:
                if w.field_type != pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON:
                    continue
                name = w.field_name
                if name not in wanted:
                    continue
                try:
                    on = w.on_state()
                    if on != wanted[name]:
                        # Do NOT write to siblings. Every member of a radio
                        # group shares one AcroForm /V, so selecting the
                        # match already deselects the rest — and a later
                        # write to a sibling overwrites that selection. The
                        # earlier code set non-matching members to "Off"
                        # after setting the match, so the LAST member of the
                        # group won every time: asking for Gender='Male'
                        # produced 'Female', and 'AM' produced 'Unsure'.
                        continue
                    w.field_value = on
                    w.update()
                    matched_groups.add(name)
                except Exception as exc:          # narrow, and RECORDED
                    errored_groups[name] = f"{type(exc).__name__}: {exc}"
        n_radio_filled = len(matched_groups)
        n_radio_skipped = len(wanted) - len(matched_groups)

        doc.save(str(out), incremental=False, deflate=True)
    finally:
        doc.close()

    report_extra = {}
    if errored_groups:
        # A skipped radio group used to be indistinguishable from a group
        # nobody asked for. Callers need the reason: an unfillable group
        # silently turns into a ground-truth value with nothing behind it.
        report_extra["radio_errors"] = errored_groups
    if wanted and len(matched_groups) < len(wanted):
        report_extra["radio_unmatched"] = sorted(set(wanted) - matched_groups)

    return {
        "input": str(blank_pdf),
        "output": str(out),
        "text_filled": n_text_filled,
        "text_skipped": n_text_skipped,
        "checkbox_filled": n_checkbox_filled,
        "checkbox_skipped": n_checkbox_skipped,
        "radio_filled": n_radio_filled,
        "radio_skipped": n_radio_skipped,
        **report_extra,
    }
