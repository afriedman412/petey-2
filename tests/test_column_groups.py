"""One question's options wrapped into side-by-side columns join into one group (eval/cell_groups.py `_column_joins`,
2026-10-31, Andrew: "groups of choice fields that are far apart but should all be connected"; the FAFSA's federal
benefits question came out as one group per column)."""
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import cell_groups as cg  # noqa: E402


def _form(tmp_path, boxes, lines=()):
    """boxes: [(name, x, y, caption)] 12 pt squares with their caption printed after them; lines: [(x, y, text)]."""
    doc = pymupdf.open()
    page = doc.new_page(width=612, height=792)
    fields = {}
    for name, x, y, cap in boxes:
        page.draw_rect(pymupdf.Rect(x, y, x + 12, y + 12), color=(0, 0, 0), width=0.8)
        page.insert_text((x + 16, y + 10), cap, fontsize=9)
        fields[name] = {"type": "boolean", "widget": {"page": 1, "rect": [x, y, x + 12, y + 12],
                                                      "widget_type": "checkbox", "path": None}}
    for x, y, text in lines:
        page.insert_text((x, y), text, fontsize=9)
    pdf = tmp_path / "form.pdf"
    doc.save(str(pdf))
    return {"fields": fields}, pdf


def _sorted(groups):
    return sorted(sorted(g) for g in groups)


def test_three_columns_under_one_heading_are_one_group(tmp_path):
    # FAFSA p16 question 36: 4 + 3 + 3 options, columns about 200 pt apart, the rows lining up like a table's
    caps = [["Medicaid", "SNAP", "School lunch", "EITC"], ["Lower premiums", "WIC", "SSI"],
            ["Housing assistance", "TANF", "None of these apply"]]
    boxes = [(f"c{i}r{j}", 20 + 200 * i, 200 + 18 * j, c) for i, col in enumerate(caps) for j, c in enumerate(col)]
    bp, pdf = _form(tmp_path, boxes, [(20, 185, "Did anyone in the family get benefits? Select all that apply.")])
    assert _sorted(cg.groups(bp, pdf)) == [sorted(n for n, *_ in boxes)]


def test_side_by_side_questions_with_their_own_headings_stay_apart(tmp_path):
    # Form 1008: Loan Type / Amortization Type, each column under its own heading
    boxes = [("a1", 20, 200, "Conventional"), ("a2", 20, 218, "FHA"),
             ("b1", 220, 200, "Fixed-rate"), ("b2", 220, 218, "ARM")]
    bp, pdf = _form(tmp_path, boxes, [(20, 192, "Loan Type"), (220, 192, "Amortization Type")])
    assert not any({"a1", "b1"} <= g for g in cg.groups(bp, pdf))


def test_a_question_printed_between_rows_breaks_the_columns(tmp_path):
    # N-400: eye colour options, then "6. Hair color" printed above the hair colour options in the same columns
    boxes = [("e1", 40, 200, "Black"), ("e2", 40, 216, "Blue"), ("f1", 240, 200, "Brown"), ("f2", 240, 216, "Gray"),
             ("h1", 40, 248, "Bald"), ("h2", 40, 264, "Blond"), ("i1", 240, 248, "Red"), ("i2", 240, 264, "White")]
    bp, pdf = _form(tmp_path, boxes, [(20, 192, "5. Eye color"), (20, 242, "6. Hair color (select only one)")])
    got = _sorted(cg.groups(bp, pdf))
    assert ["e1", "e2", "f1", "f2"] in got and ["h1", "h2", "i1", "i2"] in got


def test_yes_no_columns_are_not_joined_down_the_page(tmp_path):
    # a Yes column beside a No column: each row is its own question
    boxes = [(f"{k}{j}", x, 200 + 16 * j, cap) for j in range(3) for k, x, cap in (("y", 300, "Yes"), ("n", 360, "No"))]
    bp, pdf = _form(tmp_path, boxes)
    assert _sorted(cg.groups(bp, pdf)) == [[f"n{j}", f"y{j}"] for j in range(3)]
