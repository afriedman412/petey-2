"""The caption reader and boxes printed as characters (fin__pb_0c0d6152cdae p1, 2026-10-29: "why did these yes and no
buttons get grouped"): "☐Yes ☐No", the box character run into its word, read Yes / No, not "☐", "☐Yes" for the No box,
or the next question. Measured 2026-10-31 on 803 validated forms: against 7,749 captions from other sources, 3,880 ->
4,082 match, one worse. Words as pymupdf gives them on that page: (x0, y0, x1, y1, text, block, line, word)."""
from petey.label import captions as C

YES, NO = [514.3, 561.1, 523.3, 567.1], [555.5, 561.1, 564.5, 567.1]
GLUED = [(514.3, 558.9, 540.9, 569.0, "☐Yes", 3, 0, 0), (555.5, 558.9, 578.2, 569.0, "☐No", 3, 0, 1)]
APART = [(514.3, 520.3, 523.3, 529.3, "☐", 2, 0, 0), (526.3, 519.9, 541.8, 530.0, "Yes", 2, 0, 1),
         (555.8, 519.9, 578.2, 530.0, "☐No", 2, 0, 2)]


def test_a_box_character_run_into_its_word():
    assert C.caption_right_of(None, YES, stop_x=NO[0], words=GLUED) == "Yes"
    assert C.caption_right_of(None, NO, words=GLUED) == "No"


def test_a_box_character_alone_is_no_caption():
    yes, no = [514.3, 522.1, 523.3, 528.1], [555.8, 522.1, 564.8, 528.1]
    assert C.caption_right_of(None, yes, stop_x=no[0], words=APART) == "Yes"
    assert C.caption_right_of(None, no, words=APART) == "No"
    below = [514.3, 561.1, 523.3, 567.1]                    # the row under it: the "☐" above is no column header
    assert C.caption_right_of(None, below, words=APART) != "☐"
    assert [w[4] for w in C._clean(APART)] == ["Yes", "No"]


def test_private_use_box_characters():
    words = [(100.0, 98.0, 125.0, 108.0, "Yes", 1, 0, 0), (140.0, 98.0, 160.0, 108.0, "No", 1, 0, 1)]
    assert C.caption_right_of(None, [100.0, 100.0, 107.0, 107.0], stop_x=140.0, words=words) == "Yes"


def test_a_letter_inside_the_box_is_not_read_from_inside():
    # a symbol font's "r" drawn as the box is a word of its own; only words a box character was taken off count
    words = [(100.0, 98.0, 108.0, 108.0, "r", 1, 0, 0), (110.0, 98.0, 150.0, 108.0, "Destroyed", 1, 0, 1)]
    assert C.caption_right_of(None, [99.0, 99.0, 105.5, 107.0], words=words) == "Destroyed"


def test_off_reads_as_printed():
    C.GLYPHS = False
    try:
        assert C.caption_right_of(None, NO, words=GLUED) == "☐Yes"        # the old misread: the word left of No
    finally:
        C.GLYPHS = True
