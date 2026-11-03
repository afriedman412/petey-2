"""Option groups holding several questions split by their repeated answers (eval/repeated_captions.py, 2026-10-28,
Andrew: "lets fix the overzealous grouper for good")."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
import repeated_captions as RC  # noqa: E402


def _form(rows):
    """rows: [(name, x, y, caption)] boxes 10 pt square with their caption printed right after them."""
    boxes, words = {}, []
    for name, x, y, cap in rows:
        boxes[name] = (1, [x, y, x + 10, y + 10])
        cx = x + 14
        for w in cap.split():
            words.append((cx, y + 1, cx + 6 * len(w), y + 9, w, 0, 0, 0))
            cx += 6 * len(w) + 4
    return boxes, {1: words}


def _sorted(groups):
    return sorted(sorted(g) for g in groups)


def test_stacked_yes_no_questions_in_one_group_become_one_group_each():
    # bm__sd_2801296: one publisher field over five Yes / No questions
    rows = [r for k, y in enumerate((100, 140, 180, 220)) for r in ((f"y{k}", 300, y, "Yes"), (f"n{k}", 340, y, "No"))]
    boxes, words = _form(rows)
    got = RC.split_groups([set(boxes)], boxes, words)
    assert _sorted(got) == [[f"n{k}", f"y{k}"] for k in range(4)]


def test_one_question_with_different_answers_is_left_alone():
    boxes, words = _form([("a", 100, 100, "Single"), ("b", 170, 100, "Married"), ("c", 250, 100, "Divorced")])
    assert _sorted(RC.split_groups([set(boxes)], boxes, words)) == [["a", "b", "c"]]


def test_a_word_repeated_on_one_side_is_no_split_when_the_other_names_every_option():
    # it201's account type: "or" printed between the boxes, the types named after them
    rows = [("a", 100, 100, "Personal checking or"), ("b", 230, 100, "Personal savings or"), ("c", 360, 100, "Business checking")]
    boxes, words = _form(rows)
    words[1] = [w for w in words[1] if w[4] != "or"] + [(84, 101, 96, 109, "or", 0, 0, 0), (214, 101, 226, 109, "or", 0, 0, 0)]
    assert _sorted(RC.split_groups([set(boxes)], boxes, words)) == [["a", "b", "c"]]


def test_a_page_of_questions_comes_apart_into_them_and_far_boxes_keep_their_neighbours():
    # bm__sd_537564: Gender M / F at the top, one normal / abnormal / borderline question, three normal / abnormal rows
    rows = [("m", 400, 60, "M"), ("f", 425, 60, "F"),
            ("q2n", 200, 170, "normal"), ("q2a", 270, 170, "abnormal"), ("q2b", 345, 170, "borderline"),
            ("r1n", 230, 205, "normal"), ("r1a", 305, 205, "abnormal"),
            ("r2n", 230, 222, "normal"), ("r2a", 305, 222, "abnormal"),
            ("r3n", 230, 239, "normal"), ("r3a", 305, 239, "abnormal")]
    boxes, words = _form(rows)
    got = RC.split_groups([set(boxes)], boxes, words)
    assert _sorted(got) == [["f", "m"], ["q2a", "q2b", "q2n"], ["r1a", "r1n"], ["r2a", "r2n"], ["r3a", "r3n"]]


def test_a_column_of_one_answer_comes_apart_into_loose_boxes():
    # bm__mu_0bfb2573afdf: the publisher's "No Checkbox" over every question's No
    boxes, words = _form([(f"n{k}", 340, 100 + 80 * k, "No") for k in range(4)])
    assert RC.split_groups([set(boxes)], boxes, words) == []
