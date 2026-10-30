"""Slim semantic-type registry for widget-mapper.

Given a snake_case field slug (like `payer_ein` or `wages_amt`), infer:
- `bpt_type` — string / number / integer / boolean / date / category
- `pattern` — regex for validation (nullable)
- `semantic_type` — canonical slug (SSN, EIN, ISO date, ...)
- `ocr_whitelist` — character-class hint for zonal OCR (nullable)

Used by auto_label.py to enrich the auto-derived field labels with a
semantic layer, and by extract.py to constrain OCR + post-validate.

Deliberately narrow: this is a starter set for the most common form
fields (IRS + insurance + healthcare + basic contact info). Extend as
the library grows.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SemanticType:
    name: str
    matches: tuple[str, ...]        # token-boundary suffix / substring
    whole_names: tuple[str, ...] = ()  # exact-name match
    bpt_type: str = "string"
    pattern: Optional[str] = None
    ocr_whitelist: Optional[str] = None


# Order matters — more specific entries first. NUMERIC + DATE suffixes
# beat address-token modifiers (state, city, country) to avoid
# `state_tax_amt` routing via `_state`.
REGISTRY: tuple[SemanticType, ...] = (
    # --- parts of a date or an ID, before the whole-value rules ---
    # A month box named `birth_dt_mm` matched `_dt` and was typed `date`;
    # on 526EZ that was 79 of 328 fields, every one a generation-time
    # contradiction (RESULTS.md, gt_shape_mismatch). Parts are strings
    # with their own shape; the whole-value rules stay for whole values.
    SemanticType(
        name="date_month", matches=("_mm",), whole_names=("mm", "month"),
        pattern=r"^\d{1,2}$", ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="date_day", matches=("_dd",), whole_names=("dd", "day"),
        pattern=r"^\d{1,2}$", ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="date_year", matches=("_yyyy", "_yy"), whole_names=("yyyy", "yy"),
        pattern=r"^\d{2,4}$", ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="id_part",
        matches=("_part1", "_part2", "_part3", "_part4", "_part_1", "_part_2",
                 "_part_3", "_first_three", "_second_two", "_last_four",
                 "_first3", "_middle2", "_last4"),
        pattern=r"^\d{1,5}$", ocr_whitelist="0123456789",
    ),

    # --- distinctive IDs ---
    SemanticType(
        name="ssn", matches=("_ssn",), whole_names=("ssn",),
        pattern=r"^\d{3}-\d{2}-\d{4}$",
        ocr_whitelist="0123456789-",
    ),
    SemanticType(
        name="ein", matches=("_ein",), whole_names=("ein",),
        pattern=r"^\d{2}-\d{7}$",
        ocr_whitelist="0123456789-",
    ),
    SemanticType(
        name="itin", matches=("_itin",), whole_names=("itin",),
        pattern=r"^9\d{2}-(7\d|8[0-8])-\d{4}$",
        ocr_whitelist="0123456789-",
    ),
    SemanticType(
        name="npi", matches=("_npi",), whole_names=("npi",),
        pattern=r"^\d{10}$",
        ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="routing_number",
        matches=("_routing_number", "_routing_no"),
        whole_names=("routing_number",),
        pattern=r"^\d{9}$",
        ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="account_number",
        matches=("_account_number", "_account_no", "_account_num",
                 "_acct_number"),
        whole_names=("account_number",),
        pattern=r"^\d{8,17}$",
        ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="naics", matches=("_naics",), whole_names=("naics",),
        pattern=r"^\d{6}$",
        ocr_whitelist="0123456789",
    ),
    SemanticType(
        name="tin",
        matches=("_tin",),
        whole_names=("tin",),
        # TIN can be SSN- or EIN-formatted; require XX-XXXXXXX or XXX-XX-XXXX
        pattern=r"^\d{2,3}-\d{2,7}(-\d{4})?$",
        ocr_whitelist="0123456789-",
    ),

    # --- money / percent / count (must beat _state, _city, _country) ---
    # An `_amt` name is a sum of money (the labeler's convention); whole dollars only where the form asks for them,
    # and an amount of something else (barrels, miles) is not money: both decided at emit by
    # `petey.validate.retype.money_kind` (Andrew, 2026-10-07).
    SemanticType(
        name="money",
        matches=("_amt", "_amount"),
        bpt_type="number",
        ocr_whitelist="0123456789.,-",
    ),
    SemanticType(
        name="percent",
        matches=("_pct", "_percent", "_rate", "_percentage"),
        bpt_type="number",
        ocr_whitelist="0123456789.,",
    ),
    SemanticType(
        name="count",
        matches=("_cnt", "_count", "_qty", "_quantity"),
        bpt_type="integer",
        ocr_whitelist="0123456789",
    ),

    # --- dates ---
    SemanticType(
        name="birth_date",
        matches=("_birth_date", "_birth_dt", "_dob", "_date_of_birth"),
        whole_names=("dob", "birth_date"),
        bpt_type="date",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        ocr_whitelist="0123456789-/",
    ),
    SemanticType(
        name="service_date",
        matches=("_service_date", "_service_dt", "_dos",
                 "_date_of_service"),
        bpt_type="date",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        ocr_whitelist="0123456789-/",
    ),
    # a date with its time of day in one box (Andrew, 2026-10-21; a hearing's DATE AND TIME, AO 88's testimony):
    # a string, as the `date` type keeps the day only; extraction writes it as ISO, the time when one is shown
    SemanticType(
        name="datetime",
        matches=("_datetime", "_date_time", "_dt_time"),
        pattern=r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$",
        ocr_whitelist="0123456789-/:. APMapm",
    ),
    SemanticType(
        name="iso_date",
        matches=("_dt", "_date"),
        bpt_type="date",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        ocr_whitelist="0123456789-/",
    ),
    SemanticType(
        name="year",
        matches=("_yr", "_year", "calendar_yr", "tax_year"),
        whole_names=("year",),
        pattern=r"^\d{4}$",
        ocr_whitelist="0123456789",
    ),

    # --- contact ---
    SemanticType(
        name="phone",
        matches=("_phone", "_telephone", "_phone_number", "_phone_no",
                 "_fax", "_fax_number"),
        whole_names=("phone", "telephone", "fax"),
        pattern=r"^(?:\(\d{3}\)\s?|\d{3}[-. ])\d{3}[-. ]\d{4}$",
        ocr_whitelist="0123456789-()  ",
    ),
    SemanticType(
        name="email",
        matches=("_email", "_email_address"),
        whole_names=("email",),
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    ),

    # --- address ---
    SemanticType(
        name="state_abbr",
        matches=("_state_abbreviation", "_state_abbr", "_state_cd",
                 "_state_code", "_state"),
        whole_names=("state",),
        pattern=r"^[A-Z]{2}$",
        ocr_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ),
    SemanticType(
        name="zip",
        matches=("_zip", "_postal", "_zip_cd", "_zip_code",
                 "_postal_code"),
        whole_names=("zip", "zip_code", "zipcode", "postal_code"),
        pattern=r"^\d{5}(-\d{4})?$",
        ocr_whitelist="0123456789-",
    ),
    SemanticType(
        name="city",
        matches=("_city", "_city_nm", "_city_name", "_town"),
        whole_names=("city", "town"),
    ),
    SemanticType(
        name="country_code",
        matches=("_country_code", "_country_cd"),
        pattern=r"^[A-Z]{2}$",
        ocr_whitelist="ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    ),
    SemanticType(
        name="country",
        matches=("_country_name", "_country_nm", "_country"),
        whole_names=("country",),
    ),
    # a name with its mailing address in one box (a 1099's "PAYER'S name, street address, city ..."), 395 fields over
    # 121 blueprints typed person_name / business_name / street_address or nothing (Andrew, 2026-10-16). After the
    # address parts (a ZIP box inside the block stays zip), before street_address and the names, which its slugs
    # would otherwise hit (`payer_name_address` matched business_name's `_payer_name`)
    SemanticType(
        name="name_and_address",
        matches=("_name_and_address", "_name_address", "_nm_and_address", "_nm_address",
                 "_name_and_addr", "_name_addr", "_address_and_name", "_name_and_mailing_address",
                 "_name_mailing_address"),
        whole_names=("name_and_address", "name_address"),
    ),
    SemanticType(
        name="street_address",
        matches=("_address_line_1", "_address_line", "_street",
                 "_street_address", "_addr_line_1", "_addr_line"),
        whole_names=("address", "street_address", "street"),
    ),

    # --- names (specific → generic) ---
    SemanticType(
        name="entity_name",
        matches=("_trust_name", "_estate_name", "_entity_name",
                 "_partnership_name", "_organization_name",
                 "_trust_nm", "_estate_nm", "_entity_nm"),
    ),
    SemanticType(
        name="business_name",
        matches=("_business_name", "_business_nm", "_company",
                 "_company_nm", "_payer_nm", "_payer_name",
                 "_employer_name", "_employer_nm"),
    ),
    SemanticType(
        name="first_name",
        matches=("_first_name", "_first_nm"),
    ),
    SemanticType(
        name="last_name",
        matches=("_last_name", "_last_nm"),
    ),

    # --- text catch-alls ---
    SemanticType(
        name="description",
        matches=("_desc", "_description"),
    ),
    SemanticType(
        name="text",
        matches=("_txt", "_text", "_comment", "_comments", "_note"),
    ),
)


CHECKBOX_TYPE = SemanticType(
    name="indicator",
    matches=("_ind",),
    bpt_type="boolean",
)

# Spec §5.8.1 registers values that this module has no slug matcher for.
# `money_whole_dollar` is one since 2026-10-07: an amount slug resolves to
# plain `money`, and whole dollars come from the form's own words at emit
# (`retype.money_kind`), never from the name.
#
# Kept out of REGISTRY deliberately. REGISTRY is ordered for `lookup`,
# and adding an entry there changes what slugs match; this tuple carries
# vocabulary membership only.
SPEC_ONLY_TYPES: tuple[SemanticType, ...] = (
    SemanticType(name="money_whole_dollar", matches=(), bpt_type="number", ocr_whitelist="0123456789.,-"),
    # no longer matched from the name (Andrew, 2026-10-13): '_nm' / '_name' anywhere gave county, plan, firm and
    # facility names a person type, and the type says nothing a string does not. Still valid where it is set.
    SemanticType(name="person_name", matches=()),
    # any name, a person's or an organization's, whole or part: the one name kind the labeler is offered (Andrew,
    # 2026-10-20). No matcher, so names are not typed from slugs.
    SemanticType(name="name", matches=()),
    # postal codes and phone numbers outside the US (Andrew, 2026-10-20: "we can just use different patterns"): the
    # `zip` and `phone` patterns are American (Canada's phone numbers fit `phone`, its postal codes do not). No slug
    # matcher: the labeler picks them, as the page shows the country.
    SemanticType(name="ca_postal_code", matches=(), pattern=r"^[A-Za-z]\d[A-Za-z][ -]?\d[A-Za-z]\d$"),
    SemanticType(name="uk_postcode", matches=(), pattern=r"^[A-Za-z]{1,2}\d[A-Za-z\d]?\s?\d[A-Za-z]{2}$"),
    SemanticType(name="uk_phone", matches=(), pattern=r"^(?:\+44\s?|0)(?:\d[\s-]?){9,10}$",
                 ocr_whitelist="0123456789+-() "),
    SemanticType(name="intl_phone", matches=(), pattern=r"^\+?(?:\d[\s().-]?){6,15}$",
                 ocr_whitelist="0123456789+-() "),
)

# Every value registered by spec §5.8.1 — the canonical vocabulary, as
# distinct from REGISTRY's matcher ordering.
ALL_TYPES: tuple[SemanticType, ...] = (
    REGISTRY + (CHECKBOX_TYPE,) + SPEC_ONLY_TYPES
)


def _normalize(name: str) -> str:
    return name.lower().replace(".", "_").replace("-", "_")


def _matches_slug(name: str, slug: str) -> bool:
    n = _normalize(name)
    s = slug.lower().lstrip("_")
    return ("_" + s + "_") in ("_" + n + "_")


def _matches_whole(name: str, whole: str) -> bool:
    return _normalize(name) == whole.lower()


def lookup(field_name: str,
           widget_type: Optional[str] = None) -> Optional[SemanticType]:
    """Find the semantic type for a field. Returns None if nothing matches."""
    if widget_type == "checkbox":
        return CHECKBOX_TYPE
    for st in REGISTRY:
        for w in st.whole_names:
            if _matches_whole(field_name, w):
                return st
        for m in st.matches:
            if _matches_slug(field_name, m):
                return st
    return None


def enrich_field(label: str, widget_type: str) -> dict:
    """Return `{type, semantic_type?, pattern?}` for a labeled widget."""
    st = lookup(label, widget_type=widget_type)
    if st is None:
        return {"type": "boolean"} if widget_type == "checkbox" else {
            "type": "string"
        }
    spec: dict = {"type": st.bpt_type, "semantic_type": st.name}
    # `pattern` is only valid on `type: string` (spec §5.6); the registry
    # keeps canonical shapes for date/number types as documentation.
    if st.pattern and st.bpt_type == "string":
        spec["pattern"] = st.pattern
    return spec


def enrich_from_kind(kind: Optional[str], widget_type: str) -> dict:
    """`{type, semantic_type?, pattern?}` from a KIND the labeler named apart from the field name (the simple naming
    scheme, docs/PLAN_SIMPLE_NAMES.md, 2026-10-19): a registered semantic type, or text / checkbox / signature."""
    k = (kind or "").strip().lower()
    # level with what the standard scheme's suffixes give (enrich_field): `_ind` on a text box is a string (Y / N
    # written in), `_txt` / `_desc_txt` keep their semantic type, `_nbr` / `_cd` (an identifier) is a plain string
    if widget_type == "checkbox" or (k in ("checkbox", "boolean") or k == "indicator" and widget_type != "text"):
        return {"type": "boolean"}
    if k in ("text", "description"):
        return {"type": "string", "semantic_type": k}
    st = next((t for t in ALL_TYPES if t.name == k), None)
    if st is None or k in ("identifier", "indicator", ""):
        return {"type": "string"}
    spec: dict = {"type": st.bpt_type, "semantic_type": st.name}
    if st.pattern and st.bpt_type == "string":
        spec["pattern"] = st.pattern
    return spec


def pattern_for(name: Optional[str]) -> Optional[str]:
    """The registry's pattern for a semantic type, where it applies (a string field; spec §5.6), else None."""
    st = next((t for t in ALL_TYPES if t.name == name), None) if name else None
    return st.pattern if st is not None and st.pattern and st.bpt_type == "string" else None


def registered_names() -> list[str]:
    """Every `semantic_type` name registered by spec §5.8.1, plus the date and ID parts."""
    return [st.name for st in ALL_TYPES]


def prompt_vocabulary() -> str:
    """The registry rendered as a JSON array, for embedding in a prompt.

    The vision-labeling path used to carry its own hardcoded list, which
    drifted from this registry — it emitted `address`/`date` where the
    registry has `street_address`/`iso_date`, so blueprints from flat
    documents spoke a different dialect than the rest of the library
    (spec §14, deviation 3). Prompts draw from here instead.
    """
    return "[" + ", ".join(f'"{n}"' for n in registered_names() if n not in NOT_OFFERED) + "]"


# valid where a blueprint has them, never offered to a model (person_name: Andrew, 2026-10-13, says nothing a string
# does not)
NOT_OFFERED = {"person_name",
               # names: one kind, `name`, for any name, a person's or an organization's, whole or part (Andrew,
               # 2026-10-20: "name is probably fine for type. more specific than that is just noise"; offering
               # first_name / last_name and no whole name got SBA 413's full-name box, sba413_2_1, typed first_name)
               "first_name", "last_name", "entity_name", "business_name",
               # dates with the same type, pattern and charset as iso_date (IMM 5645's dates of birth came back as
               # either, a disagreement about nothing)
               "birth_date", "service_date"}


def ocr_whitelist_for(semantic_type: Optional[str]) -> Optional[str]:
    """Return the character whitelist for OCR of this semantic type."""
    if not semantic_type:
        return None
    for st in ALL_TYPES:
        if st.name == semantic_type:
            return st.ocr_whitelist
    return None
