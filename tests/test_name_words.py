"""Name words (petey/label/text_match.py), used by the name checks and the simple-names bench: a slug as words,
abbreviations written out, and the abbreviation test that needs no list (Andrew, 2026-10-12)."""
import pytest

from petey.label.text_match import abbreviates, name_words


class TestNameWords:
    def test_known_abbreviations_written_out(self):
        assert name_words("patient_sex_cd") == "patient sex code"

    def test_number_glued_to_a_word_is_split(self):
        assert name_words("insured_policy_eff_dt2") == "insured policy effective date 2"

    def test_raw_form_keeps_abbreviations(self):
        assert name_words("insured_policy_eff_dt2", expand=False) == "insured policy eff dt 2"

    def test_unknown_part_written_out_from_the_text(self):
        assert name_words("gl_addl_insd_txt", text="named as an additional insured") == "gl additional insured text"


class TestAbbreviates:
    @pytest.mark.parametrize("short, long", [("addl", "additional"), ("insd", "insured"), ("subr", "subrogation"),
                                             ("wvd", "waived")])
    def test_yes(self, short, long):
        assert abbreviates(short, long)

    @pytest.mark.parametrize("short, long", [("ad", "additional"), ("insd", "ensured"), ("dla", "additional"),
                                             ("additional", "additional")])
    def test_no(self, short, long):
        assert not abbreviates(short, long)
