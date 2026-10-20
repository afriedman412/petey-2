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

import re
from pathlib import Path
from typing import Any, Optional

import pymupdf


def _unescape_pdf_name(s):
    """`#20APT#20` -> ` APT `: pymupdf reports a kid's on-state as the raw PDF
    name, but checks the kid only when given the decoded string (I-765 unit
    types stayed Off in every case until 2026-09-30)."""
    if not isinstance(s, str):
        return s
    import re
    return re.sub(r"#([0-9A-Fa-f]{2})", lambda m: chr(int(m.group(1), 16)), s)


def _coerce_checkbox_value(
    widget: pymupdf.Widget, value: Any,
) -> str:
    """Return the string pymupdf wants for a checkbox `field_value`.

    Checked → widget's on_state (usually "Yes", but forms may declare
    "1", "On", "Married", or any custom string). Unchecked → "Off"
    (universal PDF constant).
    """
    if value:
        on = _unescape_pdf_name(widget.on_state())
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
                            on = _unescape_pdf_name(w.on_state())
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
                    on = _unescape_pdf_name(w.on_state())
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


# --------------------------------------------------------------- by rect

def _widgets_by_page(doc) -> dict[int, list[dict]]:
    out: dict[int, list[dict]] = {}
    for page_no, page in enumerate(doc, start=1):
        rows = []
        for w in page.widgets() or []:
            if w.field_type in (pymupdf.PDF_WIDGET_TYPE_SIGNATURE, pymupdf.PDF_WIDGET_TYPE_BUTTON):
                continue
            rows.append({"rect": [float(c) for c in w.rect], "xref": w.xref, "path": w.field_name,
                         "type": w.field_type})
        out[page_no] = rows
    return out


def _inside(inner, outer, tol: float = 2.0) -> bool:
    return (inner[0] >= outer[0] - tol and inner[1] >= outer[1] - tol
            and inner[2] <= outer[2] + tol and inner[3] <= outer[3] + tol)


_FLAT_FONT = "helv"
_FLAT_MIN_FS = 5.0


def _draw_text(page, rect, value: str) -> str:
    """Flat blank: put the value on the page inside the rect. Returns what was
    drawn (the ground truth), which is the value cut to what fits the box's
    width at the smallest font, as a widget's MaxLen cuts it on an AcroForm
    blank. `insert_text` at a baseline always draws; `insert_textbox` was
    used until 2026-10-05 and silently drew nothing when the text missed the
    box by a fraction of a point (TX RRC EP-3: 27 of 34 values never reached
    the page while the fill report said they had)."""
    r = pymupdf.Rect(*rect)
    s = str(value)
    fs = min(10.0, max(_FLAT_MIN_FS, r.height * 0.7))
    avail = max(r.width - 3.0, 1.0)
    while fs > _FLAT_MIN_FS and pymupdf.get_text_length(s, fontname=_FLAT_FONT, fontsize=fs) > avail:
        fs = max(_FLAT_MIN_FS, fs - 0.5)
    while len(s) > 1 and pymupdf.get_text_length(s, fontname=_FLAT_FONT, fontsize=fs) > avail:
        s = s[:-1]
    # baseline so the glyphs (cap height ~0.72 em, descenders ~0.2 em) sit inside the rect
    baseline = r.y0 + (r.height + fs * 0.72) / 2.0
    baseline = min(baseline, r.y1 - fs * 0.22)
    page.insert_text(pymupdf.Point(r.x0 + 1.5, baseline), s, fontsize=fs, fontname=_FLAT_FONT, color=(0, 0, 0))
    return s


def _draw_mark(page, rect) -> None:
    """Flat blank: an X across the option box."""
    r = pymupdf.Rect(*rect)
    inset = min(r.width, r.height) * 0.2
    page.draw_line(pymupdf.Point(r.x0 + inset, r.y0 + inset), pymupdf.Point(r.x1 - inset, r.y1 - inset),
                   color=(0, 0, 0), width=1.0)
    page.draw_line(pymupdf.Point(r.x0 + inset, r.y1 - inset), pymupdf.Point(r.x1 - inset, r.y0 + inset),
                   color=(0, 0, 0), width=1.0)


_MULTILINE = 1 << 12          # text field flags (PDF 32000-1, table 228)
_COMB = 1 << 24
_PAD = 2.0                    # points a viewer keeps clear inside a text field's border, each side


def fit_widget(value: str, rect, fontsize: float, *, multiline: bool = False, comb: bool = False) -> str:
    """The part of `value` a widget shows: what fits its width at its own font size (one line), or its lines (a
    multi-line field, words wrapped), cut at a word and else a character, as a filer types only what the box takes.
    2026-10-20: a test value drawn for the page finder's box, wider than the widget inside it, overflowed ACORD 90 NY's
    22 pt state boxes ("REF97533" read back "EF975") and was scored as the blueprint's miss (69 of ~100 wrong values
    there). A comb field is left to its MaxLen."""
    s = str(value)
    if comb or not s:
        return s
    fs = float(fontsize or 0) or 12.0          # auto size: a viewer shrinks; pymupdf draws about 12 pt
    r = pymupdf.Rect(rect)
    avail = max(r.width - 2 * _PAD, 1.0)
    width = lambda t: pymupdf.get_text_length(t, fontname="helv", fontsize=fs)     # noqa: E731
    n_lines = max(1, int((r.height - 2 * _PAD + 0.5) // (fs * 1.15))) if multiline else 1
    lines, cur = [], ""
    for word in s.split(" "):
        trial = f"{cur} {word}" if cur else word
        if width(trial) <= avail:
            cur = trial
            continue
        if cur:
            lines.append(cur)
        cur = word
        if width(cur) > avail:                         # a word longer than a line is not broken: it is cut there
            while len(cur) > 1 and width(cur) > avail:
                cur = cur[:-1]
            lines.append(cur)
            cur = ""
            break
    if cur:
        lines.append(cur)
    out = " ".join(lines[:n_lines])
    return out if s.startswith(out) else s[:len(out)]


def widget_cells(case: dict[str, Any], widgets: dict[int, list[dict]], n_pages: int) -> dict[str, list[str]]:
    """{widget: [case keys]} for every widget that holds more than one of the case's text cells (a widget the page
    finder split: a comb, a two-line box), the keys in reading order. Only a CELL inside the widget counts; a box
    larger than the widget is the split rule's business (`_parts_for`)."""
    from petey.synth.boxes import match_rect, parse_rect_key
    owners: dict[str, list[tuple[float, float, str]]] = {}
    for key, value in case.items():
        page_no, rect = parse_rect_key(key)
        m = match_rect(rect, widgets.get(page_no, [])) if 1 <= page_no <= n_pages else None
        if m is None or not isinstance(value, str):
            continue
        if (rect[2] - rect[0]) * (rect[3] - rect[1]) < 0.9 * (m["rect"][2] - m["rect"][0]) * (m["rect"][3] - m["rect"][1]):
            owners.setdefault(f"{page_no}:{m['xref']}", []).append((rect[1], rect[0], key))
    out = {}
    for xk, members in owners.items():
        if len(members) > 1:
            members.sort(key=lambda t: (round(t[0] / 4), t[1]))
            out[xk] = [k for _, _, k in members]
    return out


def _join_cells(cells: list[tuple[float, str]]) -> str:
    """One widget's string from the values drawn for the page cells inside it, in reading order ((top, value)
    pairs). Cells side by side on one line (a comb the finder split) run together: "1", "2", "3" -> "123". Cells on
    different lines (a two-line box the finder saw as two) are lines of one answer: joined with a space, and a line
    that repeats the line above is written once (the bank draws the same kind of value for both lines of an address
    box: Form 8825's "Omar Fischer, 1120" twice, run together, 2026-10-20)."""
    lines: list[list[str]] = []
    last_y: Optional[float] = None
    for y, v in cells:
        if last_y is None or round(y / 4) != round(last_y / 4):
            lines.append([])
        lines[-1].append(v)
        last_y = y
    out: list[str] = []
    for line in ("".join(parts) for parts in lines):
        if line and (not out or line != out[-1]):
            out.append(line)
    return " ".join(out)


def _parts_for(value: str, cls: Optional[str], n: int) -> list[str]:
    """How a filer spreads one value over `n` boxes that the page shows as
    one: a date by month / day / year, an amount by dollars / cents, a
    phone by area / exchange / line, an SSN 3-2-4, anything else by commas.
    The last part absorbs the remainder."""
    v = value.strip()
    if cls in ("date", "birth_date") and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        y, m, d = v.split("-")
        parts = [m, d, y] if n == 3 else ([m, y] if n == 2 else [v])
    elif cls in ("date", "birth_date") and re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", v):
        m, d, y = v.split("/")
        parts = [m, d, y] if n == 3 else ([m, y] if n == 2 else [v])
    elif cls == "money" and n == 2:
        whole, _, cents = v.partition(".")
        parts = [whole.replace(",", ""), (cents or "00")[:2].ljust(2, "0")]
    elif cls in ("phone", "phone_part") and n in (2, 3):
        d = re.sub(r"\D", "", v)
        parts = [d[:3], d[3:6], d[6:]] if n == 3 else [d[:3], d[3:]]
    elif cls in ("ssn", "itin") and n == 3:
        d = re.sub(r"\D", "", v)
        parts = [d[:3], d[3:5], d[5:]]
    elif cls == "ein" and n == 2:
        d = re.sub(r"\D", "", v)
        parts = [d[:2], d[2:]]
    else:
        parts = [pt.strip() for pt in v.split(",") if pt.strip()]
    if len(parts) > n:
        parts = parts[:n - 1] + [", ".join(parts[n - 1:])]
    return parts


def render_case(
    case: dict[str, Any], blank_pdf: str | Path, out: str | Path,
    classes: Optional[dict[str, str]] = None,
) -> tuple[dict[str, Any], dict]:
    """Fill a blank from a case keyed by page and rect (`synth.boxes.rect_key`):
    strings for text boxes, True / False marks for option boxes.

    The only step of the synthetic path that touches the AcroForm layer, and
    only to write: each rect is matched to the widget that best overlaps it
    (`boxes.match_rect`), and the value is written through that widget by
    its type. A widget's MaxLen or a combobox's choice list can change what
    lands on the page, so the EFFECTIVE values are returned and are the
    ground truth. A blank with no widgets at all (a flat form) gets the
    text drawn at the rect and an X drawn across marked option boxes.

    `classes` (rect key -> the classifier's class) lets a value that lands
    over several widgets split by its natural parts (`_parts_for`).

    Returns `(effective_case, report)`.
    """
    from petey.synth.boxes import match_rect, parse_rect_key
    classes = classes or {}

    blank_pdf = Path(blank_pdf)
    out = Path(out)
    doc = pymupdf.open(str(blank_pdf))
    effective: dict[str, Any] = {}
    # where each value landed: {rect_key: [{"page", "rect", "value"}, ...]};
    # the scorer joins blueprint fields to THESE rects, so a field is
    # credited with what was written into its own widget and nothing else
    targets: dict[str, list[dict]] = {}
    report: dict[str, Any] = {"text_filled": 0, "marks_on": 0, "marks_off": 0, "drawn": 0,
                              "unmatched": [], "truncated": [], "choice_substituted": [],
                              "split_across": [], "rewrite_skipped": 0, "errors": {}}
    try:
        widgets = _widgets_by_page(doc)
        flat = not any(widgets.values())
        # A widget that spans several page cells (a comb the finder split)
        # holds their concatenation in reading order; the scorer's join
        # applies the same rule (validate.rect_join).
        joined: dict[str, Any] = {}
        if not flat:
            for members in widget_cells(case, widgets, len(doc)).values():
                joined_text = _join_cells([(parse_rect_key(k)[1][1], str(case[k])) for k in members])
                for k in members:
                    joined[k] = joined_text
        written: set[str] = set()
        marked_on: set[str] = set()
        text_written: dict[str, str] = {}     # "page:xref" -> the value on the page
        for key, value in case.items():
            page_no, rect = parse_rect_key(key)
            if page_no < 1 or page_no > len(doc):
                report["unmatched"].append(key)
                continue
            page = doc[page_no - 1]
            if flat:
                if isinstance(value, bool):
                    if value:
                        _draw_mark(page, rect)
                        report["drawn"] += 1
                    effective[key] = value
                elif value not in (None, ""):
                    drawn = _draw_text(page, rect, str(value))
                    report["drawn"] += 1
                    if drawn != str(value):
                        report["truncated"].append({"key": key, "wanted": str(value), "wrote": drawn, "maxlen": None})
                    effective[key] = drawn
                else:
                    effective[key] = ""
                targets[key] = [{"page": page_no, "rect": rect, "value": effective[key]}]
                continue
            # One page box over several stacked text widgets (ACORD 25's
            # PRODUCER block: one bordered cell, four line widgets): a filer
            # writes the parts on successive lines, so split on commas.
            if isinstance(value, str) and value.strip():
                inside = [w for w in widgets.get(page_no, [])
                          if w["type"] == pymupdf.PDF_WIDGET_TYPE_TEXT
                          and _inside(w["rect"], rect)
                          and (w["rect"][2] - w["rect"][0]) * (w["rect"][3] - w["rect"][1])
                          < 0.9 * (rect[2] - rect[0]) * (rect[3] - rect[1])]
                if len(inside) > 1:
                    # reading order: rows (by top edge, 4pt bands), then left to right
                    inside.sort(key=lambda w: (round(w["rect"][1] / 4), w["rect"][0]))
                    parts = _parts_for(value, classes.get(key), len(inside))
                    tg = []
                    for w, part in zip(inside, parts):
                        xk = f"{page_no}:{w['xref']}"
                        if xk in text_written:
                            # a page box over a widget another box already filled: the
                            # page holds the first value; report that, write nothing
                            tg.append({"page": page_no, "rect": w["rect"], "value": text_written[xk]})
                            report["rewrite_skipped"] += 1
                            continue
                        wid = next((x for x in page.widgets() if x.xref == w["xref"]), None)
                        if wid is None:
                            continue
                        maxlen = int(wid.text_maxlen or 0)
                        if maxlen and len(part) > maxlen:
                            part = part[:maxlen]
                        elif not maxlen:            # a part fits its own widget too (ACORD 90 NY's state boxes)
                            fitted = fit_widget(part, wid.rect, wid.text_fontsize,
                                                multiline=bool(wid.field_flags & _MULTILINE),
                                                comb=bool(wid.field_flags & _COMB))
                            if fitted != part:
                                report["truncated"].append({"key": key, "wanted": part, "wrote": fitted,
                                                            "maxlen": None, "width": round(wid.rect.width, 1)})
                                part = fitted
                        wid.field_value = part
                        wid.update()
                        text_written[xk] = part
                        report["text_filled"] += 1
                        tg.append({"page": page_no, "rect": w["rect"], "value": part})
                    effective[key] = ", ".join(t["value"] for t in tg)
                    targets[key] = tg
                    report["split_across"].append({"key": key, "lines": len(tg)})
                    continue
            m = match_rect(rect, widgets.get(page_no, []))
            if m is None:
                report["unmatched"].append(key)
                continue
            targets[key] = [{"page": page_no, "rect": m["rect"], "value": None}]
            w = next((x for x in page.widgets() if x.xref == m["xref"]), None)
            if w is None:
                report["unmatched"].append(key)
                continue
            wt = w.field_type
            try:
                if wt in (pymupdf.PDF_WIDGET_TYPE_CHECKBOX, pymupdf.PDF_WIDGET_TYPE_RADIOBUTTON):
                    on = _unescape_pdf_name(w.on_state()) or "Yes"
                    if value in (True, "X", "x", "Yes", "true"):
                        w.field_value = on
                        w.update()
                        marked_on.add(f"{page_no}:{m['xref']}")
                        report["marks_on"] += 1
                        effective[key] = True
                    else:
                        # never write Off to a radio member (siblings share one
                        # value and the last write would win), nor over a mark a
                        # duplicate page box already set on this widget
                        xk = f"{page_no}:{m['xref']}"
                        if wt == pymupdf.PDF_WIDGET_TYPE_CHECKBOX and xk not in marked_on:
                            w.field_value = "Off"
                            w.update()
                        report["marks_off"] += 1
                        effective[key] = False
                elif wt in (pymupdf.PDF_WIDGET_TYPE_COMBOBOX, pymupdf.PDF_WIDGET_TYPE_LISTBOX):
                    if value in (None, "", False):
                        effective[key] = ""
                        continue
                    choices = [c[0] if isinstance(c, (list, tuple)) else c for c in (w.choice_values or [])]
                    choices = [c for c in choices if str(c).strip()]
                    want = str(value)
                    pick = next((c for c in choices if str(c).lower() == want.lower()), None)
                    if pick is None and choices:
                        pick = next((c for c in choices if want.lower() in str(c).lower()), choices[0])
                        report["choice_substituted"].append({"key": key, "wanted": want, "wrote": pick})
                    w.field_value = str(pick if pick is not None else want)
                    w.update()
                    report["text_filled"] += 1
                    effective[key] = str(pick if pick is not None else want)
                elif wt == pymupdf.PDF_WIDGET_TYPE_TEXT and isinstance(value, bool):
                    # a mark on a text cell: the filer types an X (ACORD 25's
                    # ADDL INSD / SUBR WVD squares)
                    if value:
                        w.field_value = "X"
                        w.update()
                        report["marks_on"] += 1
                    else:
                        report["marks_off"] += 1
                    effective[key] = value
                elif wt == pymupdf.PDF_WIDGET_TYPE_TEXT:
                    xk = f"{page_no}:{m['xref']}"
                    if key in joined:
                        value = joined[key]
                        effective[key] = value
                        if xk in written:
                            continue          # the shared widget was written once
                        written.add(xk)
                    elif xk in text_written:
                        # another page box already filled this widget: the page
                        # holds that value, so this box reports it and writes nothing
                        effective[key] = text_written[xk]
                        targets[key] = [{"page": page_no, "rect": m["rect"], "value": text_written[xk]}]
                        report["rewrite_skipped"] += 1
                        continue
                    if value in (None, "", False):
                        effective[key] = ""
                        continue
                    s = str(value)
                    maxlen = int(w.text_maxlen or 0)
                    if maxlen and len(s) > maxlen:
                        compact = re.sub(r"[^A-Za-z0-9]", "", s) or s
                        s2 = compact[:maxlen]
                        report["truncated"].append({"key": key, "wanted": s, "wrote": s2, "maxlen": maxlen})
                        s = s2
                    elif not maxlen:
                        fitted = fit_widget(s, w.rect, w.text_fontsize, multiline=bool(w.field_flags & _MULTILINE),
                                            comb=bool(w.field_flags & _COMB))
                        if fitted != s:
                            report["truncated"].append({"key": key, "wanted": s, "wrote": fitted, "maxlen": None,
                                                        "width": round(w.rect.width, 1)})
                            s = fitted
                    w.field_value = s
                    w.update()
                    text_written[xk] = s
                    report["text_filled"] += 1
                    if key not in joined:
                        effective[key] = s
                    else:
                        for k2 in [k for k, v in joined.items() if v == joined[key]]:
                            effective[k2] = s
                else:
                    report["unmatched"].append(key)
            except Exception as exc:
                report["errors"][key] = f"{type(exc).__name__}: {exc}"
        doc.save(str(out), incremental=False, deflate=True)
    finally:
        doc.close()
    for key, tg in targets.items():
        for t in tg:
            if t["value"] is None:
                t["value"] = effective.get(key)
    # Two page boxes over one mark widget (the finder's duplicate of a
    # checkbox): the widget holds the OR of their marks, and every target
    # reports that final state, so the scorer sees what is on the page.
    by_widget: dict[tuple, list[dict]] = {}
    for key, tg in targets.items():
        for t in tg:
            if isinstance(t["value"], bool):
                by_widget.setdefault((t["page"], tuple(round(c, 1) for c in t["rect"])), []).append(t)
    for ts in by_widget.values():
        if len(ts) > 1:
            final = any(t["value"] for t in ts)
            for t in ts:
                t["value"] = final
    report["targets"] = targets
    report["input"] = str(blank_pdf)
    report["output"] = str(out)
    report["flat"] = flat
    report["n_unmatched"] = len(report["unmatched"])
    return effective, report
