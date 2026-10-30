"""Semantic types: the name-suffix matcher the standard scheme types fields with, the kind answer the simple scheme
types them with (docs/PLAN_SIMPLE_NAMES.md), and the list of kinds the labeler is offered."""
import json

import pytest

from petey.semantic_types import enrich_field, enrich_from_kind, prompt_vocabulary, registered_names


# ---------------------------------------------------------------------------
# enrich_field: a type read from the name (standard scheme)
# ---------------------------------------------------------------------------

class TestEnrichField:
    @pytest.mark.parametrize("name, want", [
        ("gross_rents_amt", {"type": "number", "semantic_type": "money"}),
        ("state_tax_amt", {"type": "number", "semantic_type": "money"}),      # _amt beats the _state address token
        ("fees_pct", {"type": "number", "semantic_type": "percent"}),
        ("remarks_txt", {"type": "string", "semantic_type": "text"}),
    ])
    def test_suffix_sets_type(self, name, want):
        assert enrich_field(name, "text") == want

    def test_pattern_comes_with_patterned_types(self):
        f = enrich_field("taxpayer_ssn", "text")
        assert f["semantic_type"] == "ssn" and f["pattern"] == r"^\d{3}-\d{2}-\d{4}$"

    def test_date_part_is_a_string_not_a_date(self):
        # 526EZ: birth_dt_mm matched _dt and was typed date (79 of 328 fields contradicted their values)
        f = enrich_field("birth_dt_mm", "text")
        assert f["type"] == "string" and f["semantic_type"] == "date_month"
        assert enrich_field("birth_dt", "text")["type"] == "date"

    def test_nm_is_not_a_person_name(self):
        # 2026-10-13: '_nm' anywhere typed county, plan, firm and facility names person_name
        assert enrich_field("county_nm", "text") == {"type": "string"}

    def test_name_and_address_before_business_name(self):
        # 2026-10-17: payer_name_address matched business_name's _payer_name
        assert enrich_field("payer_name_address", "text")["semantic_type"] == "name_and_address"

    def test_checkbox_is_boolean_indicator(self):
        assert enrich_field("signed_ind", "checkbox") == {"type": "boolean", "semantic_type": "indicator"}


# ---------------------------------------------------------------------------
# enrich_from_kind: a type from the labeler's kind answer (simple scheme)
# ---------------------------------------------------------------------------

class TestEnrichFromKind:
    def test_identifier_is_a_plain_string(self):
        # 2026-10-19: no identifier kind made ACORD 90 NY's location / vehicle numbers integer counts
        assert enrich_from_kind("identifier", "text") == {"type": "string"}

    def test_indicator_on_a_text_box_is_a_string(self):
        # a Y / N written in a text box, as `_ind` on a text box gives
        assert enrich_from_kind("indicator", "text") == {"type": "string"}
        assert enrich_from_kind("indicator", "checkbox") == {"type": "boolean"}

    def test_checkbox_widget_is_boolean_whatever_the_kind(self):
        assert enrich_from_kind("text", "checkbox") == {"type": "boolean"}

    @pytest.mark.parametrize("kind", ["text", "description"])
    def test_text_kinds_keep_their_semantic_type(self, kind):
        assert enrich_from_kind(kind, "text") == {"type": "string", "semantic_type": kind}

    def test_name_kind(self):
        assert enrich_from_kind("name", "text") == {"type": "string", "semantic_type": "name"}

    def test_registered_kind_brings_type_and_pattern(self):
        assert enrich_from_kind("money", "text") == {"type": "number", "semantic_type": "money"}
        z = enrich_from_kind("zip", "text")
        assert z["semantic_type"] == "zip" and z["pattern"]

    @pytest.mark.parametrize("kind", ["", None, "nonsense_kind", "signature"])
    def test_unknown_or_missing_kind_is_a_string(self, kind):
        assert enrich_from_kind(kind, "text") == {"type": "string"}

    def test_kind_is_case_and_space_insensitive(self):
        assert enrich_from_kind("  Money ", "text")["semantic_type"] == "money"


# ---------------------------------------------------------------------------
# prompt_vocabulary: the kinds the labeler chooses from
# ---------------------------------------------------------------------------

class TestVocabulary:
    def offered(self):
        return set(json.loads(prompt_vocabulary()))

    def test_one_name_kind(self):
        # Andrew, 2026-10-20: "name is probably fine for type. more specific than that is just noise"
        v = self.offered()
        assert "name" in v
        assert not v & {"first_name", "last_name", "entity_name", "business_name", "person_name"}

    def test_label_kinds_stay_offered(self):
        # "those label options are fine (and common)"
        assert {"city", "country", "street_address", "name_and_address", "description", "text"} <= self.offered()

    def test_dates_that_equal_iso_date_are_not_offered(self):
        v = self.offered()
        assert "iso_date" in v and not v & {"birth_date", "service_date"}

    def test_not_offered_types_stay_registered(self):
        # blueprints that carry them stay valid
        assert {"first_name", "business_name", "person_name", "birth_date", "name"} <= set(registered_names())


# ---------------------------------------------------------------------------
# Postal codes and phone numbers outside the US (2026-10-20)
# ---------------------------------------------------------------------------

import re                                                     # noqa: E402

from petey.semantic_types import pattern_for                  # noqa: E402


@pytest.mark.parametrize("kind, good, bad", [
    ("ca_postal_code", ["K1A 0B1", "M5V3L9", "h0h 0h0", "T2P-1J9"], ["12345", "K1A 0B", "SW1A 1AA"]),
    ("uk_postcode", ["SW1A 1AA", "M1 1AE", "B33 8TH", "CR2 6XH", "DN55 1PT", "EC1A1BB"], ["12345", "K1A 0B1", "SW1A"]),
    ("uk_phone", ["020 7946 0958", "+44 20 7946 0958", "07700 900123", "01632 960001"], ["555-123-4567", "123"]),
    ("intl_phone", ["+852 2123 4567", "+61 2 9374 4000", "2123 4567", "+353 1 234 5678"], ["12", "phone"]),
    ("zip", ["20500", "20500-0003"], ["K1A 0B1", "SW1A 1AA"]),                 # the US pattern, unchanged
])
def test_patterns(kind, good, bad):
    pat = pattern_for(kind)
    assert pat and all(re.fullmatch(pat, v) for v in good) and not any(re.fullmatch(pat, v) for v in bad)


def test_non_us_kinds_are_offered_and_carry_their_patterns():
    v = set(json.loads(prompt_vocabulary()))
    assert {"ca_postal_code", "uk_postcode", "uk_phone", "intl_phone"} <= v
    assert enrich_from_kind("uk_postcode", "text")["pattern"] == pattern_for("uk_postcode")


def test_names_are_not_typed_by_the_new_kinds():
    # no slug matcher: the standard scheme's name inference is unchanged
    assert enrich_field("mailing_postal_code", "text")["semantic_type"] == "zip"
    assert enrich_field("home_phone", "text")["semantic_type"] == "phone"


class TestDatetime:
    """A date and time in one box (2026-10-21): a string with an ISO pattern; extraction writes ISO, never makes up
    a time or a date."""

    def test_named_and_offered(self):
        assert enrich_field("hearing_date_time", "text")["semantic_type"] == "datetime"
        assert enrich_field("hearing_dt", "text")["semantic_type"] == "iso_date"
        assert "datetime" in json.loads(prompt_vocabulary())

    @pytest.mark.parametrize("raw, want", [
        ("10/21/2026 2:30 PM", "2026-10-21T14:30"), ("Oct 21, 2026 at 14:30", "2026-10-21T14:30"),
        ("2026-10-21T14:30:15", "2026-10-21T14:30:15"), ("10/21/2026", "2026-10-21"),
        ("9:30 AM", None), ("Oct 21 2:30 PM", None), ("garbage", None)])
    def test_extraction_reads_iso(self, raw, want):
        from petey.extract import _coerce_typed
        assert _coerce_typed(raw, "string", semantic_type="datetime") == want

    def test_iso_output_fits_the_pattern(self):
        from petey.extract import _iso_datetime
        rx = re.compile(pattern_for("datetime"))
        assert all(rx.fullmatch(_iso_datetime(v)) for v in ("10/21/2026 2:30 PM", "10/21/2026", "2026-10-21 09:05:07"))
