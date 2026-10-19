# BPT Spec — v1.1 (Draft)

**Status:** Draft, version 1.1
**Date:** 2026-09-08
**Supersedes:** v1.0 (2026-06-01) — additive MINOR revision, see §14
**Stewardship:** Petey, Inc. (the project that originated the format)
**Canonical URL (planned):** `petey.cc/spec`
**File extension:** `.bpt`

## Abstract

The `.bpt` file format is a portable, vendor-neutral, language-neutral specification for declaring **what to extract from a document** — a blueprint of fields with their types, semantics, and structural relationships. It is designed to be authored once and consumed by any system that performs LLM-assisted document extraction: a desktop tool, a Python library, an agent's tool-use schema, a downstream validator, or another `.bpt` consumer not yet built.

A `.bpt` file does not describe a parser, a model, an extraction strategy, or a pipeline. It describes the *target shape* — the data the user wants out — at a layer above the extraction engine. The same blueprint should produce conforming output whether the underlying engine is OCR-plus-regex, a frontier LLM, a small local model, or a human typing into a form.

## 1. Status of This Document

This is version 1.1 of the BPT Spec. The format is in active use today inside the Petey extraction toolchain, and this document is the second formalization of that format as a public, versioned specification.

v1.1 is an **additive MINOR revision** of v1.0. It adds an optional *document layer* — per-field widget geometry (§5.9) and semantic typing (§5.8) — that lets a blueprint carry not just *what* to extract but *where on the page it lives*. Every v1.0 blueprint is a valid v1.1 blueprint without modification. The new keys are all optional; a consumer that ignores them behaves exactly as it did under v1.0. See §14 for the full changelog and §10 for revised conformance criteria.

The motivating use case is **deterministic extraction**: when a blueprint carries exact widget rectangles for a known form, a consumer can read field values by geometry — AcroForm lookup, text clipped to the rect, or zonal OCR — without invoking a language model at extraction time. The blueprint becomes a reusable template for a form rather than a prompt evaluated per document.

Petey stewards the spec. Stewardship here means: Petey publishes the canonical version, decides what changes between versions, and maintains the reference implementation. The spec itself is published openly and is free for any tool, library, or service to implement. Issues, proposals, and reference blueprints from the community are welcomed; a lightweight governance process may be added in a future version if and when ecosystem participation warrants it. The spec is **not** under a standards-body process today.

## 2. Conventions

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119).

Throughout this document, the terms *blueprint* and *`.bpt` document* are used interchangeably to refer to a conforming instance of the format.

## 3. File Format

### 3.1 Encoding

A `.bpt` document MUST be encoded as UTF-8.

### 3.2 Syntax

A `.bpt` document MUST be a valid [YAML 1.2](https://yaml.org/spec/1.2.2/) document. Producers SHOULD use the safe subset of YAML (no custom tags, no language-specific type hints). Consumers MUST refuse to load documents containing unsafe YAML constructs.

### 3.3 File Extension

The canonical file extension is `.bpt`. Earlier Petey versions used `.yaml`/`.yml`; those extensions are deprecated and consumers MAY accept them with a warning. New files MUST use `.bpt`.

### 3.4 Top-Level Type

The root of a `.bpt` document MUST be a YAML mapping (object). The root MUST NOT be a sequence or scalar.

## 4. Document Structure

A blueprint is a mapping with the following top-level keys.

| Key            | Type    | Required | Default     | Description                                                                  |
| -------------- | ------- | -------- | ----------- | ---------------------------------------------------------------------------- |
| `bpt_version`  | string  | No       | `"1.0"`     | The spec version this document conforms to.                                  |
| `name`         | string  | Yes      | —           | Short identifier, snake_case recommended.                                    |
| `record_type`  | string  | No       | `"single"`  | One of `"single"` or `"array"`. See §6.                                      |
| `description`  | string  | No       | —           | Human-readable summary of what the blueprint extracts.                       |
| `instructions` | string  | No       | —           | Free-form natural-language instructions for the comprehension step. See §7.1. |
| `header_pages` | integer | No       | `0`         | Number of leading pages treated as document headers. See §7.2.               |
| `fields`       | mapping | Yes      | —           | Field definitions. See §5.                                                   |
| `source`       | mapping | No       | —           | Optional metadata about blueprint provenance. See §7.3.                      |
| `binding`      | mapping | No       | —           | Optional declaration of the canonical schema the blueprint's field identifiers come from. See §7.4. |
| `form_version` | string  | No       | `null`      | **v1.1.** Revision identifier of the source form (e.g., `"2025"`, `"Rev. March 2024"`). See §7.5. |
| `source_pdf`   | string  | No       | —           | **v1.1.** Filename of the blank source document the widget layer was derived from. See §7.5. |
| `source_pdf_hash` | string | No     | —           | **v1.1.** Hash of that source document, pinning the geometry to an exact file. See §7.5. |
| `source_pages` | array   | No       | —           | **v1.1.** 1-based page numbers carrying labeled widgets. See §7.5.           |

Any key not listed above is **reserved**: consumers MUST ignore unknown top-level keys for forward compatibility, and producers SHOULD NOT emit unknown keys without prefixing them with a vendor namespace (e.g., `x_myorg_...`).

### 4.1 `bpt_version`

A `.bpt` document SHOULD declare the spec version it conforms to via `bpt_version`. The value MUST be a string of the form `"MAJOR.MINOR"`. A document without `bpt_version` is interpreted as conforming to spec **v1.0**. See §8 for versioning policy.

### 4.2 `name`

`name` is the identifier for the blueprint. It is also used as the model name in implementations that generate language-level types (e.g., a Pydantic class). It SHOULD be `snake_case` and SHOULD NOT contain spaces or punctuation other than `_`, `-`, or `.`. Consumers MAY sanitize names that violate downstream API constraints.

### 4.3 Deprecated Aliases

The following keys are recognized as deprecated aliases for backwards compatibility and SHOULD NOT be used in new blueprints:

| Deprecated     | Canonical                            | Notes                                       |
| -------------- | ------------------------------------ | ------------------------------------------- |
| `mode: table`  | `record_type: array`                 | "Table" framing predates the unified term.  |
| `mode: query`  | `record_type: single`                | Same.                                       |

Consumers MUST accept the deprecated forms but SHOULD emit a deprecation warning. Producers MUST NOT emit the deprecated forms in new blueprints.

Type-name aliases (§5.3) are a separate concern — they are interchangeable synonyms, not deprecations, and emit no warnings.

## 5. Field Definitions

The `fields` mapping is the heart of a blueprint. Each key is the name of a field to extract; each value is a mapping that describes that field.

### 5.1 Field Object

| Key           | Type    | Required | Description                                                              |
| ------------- | ------- | -------- | ------------------------------------------------------------------------ |
| `type`        | string  | Yes      | One of the types in §5.3.                                                |
| `description` | string  | No       | Natural-language description of the field, passed to the comprehension step. |
| `required`    | boolean | No       | Whether the field MUST be present in a successful extraction. Default `false`. See §5.4. |
| `values`      | array   | Cond.    | REQUIRED if `type` is `category` or `multi_category`. Forbidden otherwise. |
| `pattern`     | string  | Cond.    | OPTIONAL if `type` is `string`. Forbidden otherwise. Regular expression validating the canonical output form. See §5.6. |
| `fields`      | mapping | Cond.    | OPTIONAL if `type` is `array`. Forbidden otherwise. See §5.5 for the alternative.        |
| `parent`      | string  | No       | Name of an array field in the same blueprint that this field belongs to. See §5.5.       |
| `path`        | string  | No       | Canonical-schema addressing path for fields whose canonical identifier is a path rather than a flat name. See §5.7. |
| `semantic_type` | string | No      | **v1.1.** Canonical semantic classification of the field's value (`ssn`, `iso_date`, `money_whole_dollar`, …). See §5.8. |
| `widget`      | mapping | Cond.    | **v1.1.** Physical location of this field on the source document. Forbidden if `widgets` is present. See §5.9. |
| `widgets`     | mapping | Cond.    | **v1.1.** OPTIONAL if `type` is `category` or `multi_category`. Maps each member of `values` to its own widget. Forbidden if `widget` is present. See §5.9.3. |

### 5.2 Field Names

Field names MUST be strings. They SHOULD be `snake_case`. They MAY contain ASCII letters, digits, `_`, `-`, and `.`. Consumers MAY sanitize field names for downstream API compatibility; when they do, they MUST preserve the original name as an alias for round-trip serialization.

#### 5.2.1 Name parts (draft for v1.2, 2026-10-19)

A producer MAY record the parts a field name was printed from, under the extension key `x_petey_identifiers` on the field (the shape and vocabulary are in `docs/NAMING.md`):

| Key | Meaning |
| --- | ------- |
| `subject` | What the field is about, in the form's own words (`first_name`). |
| `suffix` | The kind of value the box holds (`txt`, `nm`, `nbr`, `dt`, `amt`, ...). An option group has none. |
| `iteration` | Which one of a series the field is (`3`, `4a`, `b`); absent when the thing occurs once. |
| `grid`, `block_group`, `block` | The table or repeated block the field is a cell of, and for a block group which block. |
| `part` | Which box of a value written in several boxes (`month`, `area`, `dollars`, `1`). |

When the key is present the field name is derived from it: `[subject]_[suffix]_[iteration]_[part]`, absent parts skipped. A consumer that renames a field for its own purposes keeps the original name as an alias (above) and MUST NOT edit the parts. A blueprint with no `x_petey_identifiers` anywhere is unchanged by this section.

### 5.3 Type System

A `.bpt` v1.0 document supports the following field types.

#### 5.3.1 `string`

Free-text value. Maps to a nullable string in implementations. Use this for names, descriptions, identifiers, and any free-form content with no further structure.

```yaml
business_name:
  type: string
  description: Legal name of the business as it appears on the document.
```

#### 5.3.2 `number`

Numeric value. Maps to a nullable double-precision floating-point value. Use this for monetary amounts, counts, measurements, and any numeric quantity.

```yaml
total_amount:
  type: number
  description: Total amount in the document's stated currency.
```

#### 5.3.3 `date`

A calendar date. The stored form is an ISO 8601 date string (`YYYY-MM-DD`). The comprehension step is expected to normalize human date forms ("December 8, 1986", "DEC 30 1993", "12/8/86") to ISO. Producers MAY store dates without normalization; consumers SHOULD normalize on load.

```yaml
filing_date:
  type: date
  description: Date the document was filed.
```

#### 5.3.4 `category`

A value drawn from a fixed set. The `values` key MUST be present and MUST be a non-empty array of strings. Comparison SHOULD be case-insensitive; the canonical-cased value from `values` SHOULD be returned.

The names **`category`**, **`cat`**, and **`enum`** are interchangeable aliases for this type and encode identically. `category` is the canonical name in this specification and is preferred for new blueprints — blueprint authoring is intended for domain experts (medical billers, journalists, mortgage brokers, compliance staff), not exclusively for programmers, and `category` reads as plain English. The aliases exist because `enum` matches the term used in JSON Schema / OpenAPI / many programming languages, and `cat` is the natural shorthand. Consumers MUST accept all three; producers MAY emit whichever fits the audience. No deprecation warning is emitted for the aliases.

```yaml
currency:
  type: category
  description: ISO 4217 currency code.
  values:
    - USD
    - EUR
    - CAD
```

For yes/no fields, use the `boolean` type (§5.3.5) rather than a category with `["true", "false"]` values.

#### 5.3.5 `boolean`

A true/false value. Maps to a nullable boolean. Comprehension engines SHOULD accept the conventional written forms and coerce them: `true`/`false`, `True`/`False`, `"true"`/`"false"`, `"yes"`/`"no"`, `"y"`/`"n"`, `1`/`0`, `"1"`/`"0"`. Output SHOULD be canonical YAML/JSON `true` or `false` (or `null` if not determinable).

The names **`boolean`** and **`bool`** are interchangeable aliases and encode identically. `boolean` is the canonical form; `bool` is accepted for authors who prefer the shorter programmer-conventional name. No deprecation warning is emitted for `bool`.

```yaml
filer_is_dependent:
  type: boolean
  description: Whether the filer is claimed as a dependent.
```

Use `boolean` for any yes/no, checked/unchecked, true/false, or present/absent field — values whose semantics are fundamentally binary. Use `category` (§5.3.4) when the value space is a closed set of distinct labels regardless of count, including 2-value cases where the labels carry meaning that "true/false" would lose (Checking/Savings, Male/Female, SSN/EIN, KG/LB, AM/PM, etc.).

#### 5.3.6 `array`

A repeating structure: each item in the array has the same shape, defined by a nested `fields` mapping. The nested `fields` mapping follows the same rules as the top-level `fields` (§5.1), including the type system.

```yaml
line_items:
  type: array
  description: Itemized transactions on the statement.
  fields:
    description:
      type: string
      description: Item description as printed.
    amount:
      type: number
      description: Item amount.
    posted_date:
      type: date
      description: Date the item was posted.
```

Arrays MAY be nested inside arrays, but consumers MAY impose implementation limits on nesting depth. Producers SHOULD avoid nesting beyond two levels.

#### 5.3.7 `multi_category`

A set of zero or more values drawn from a fixed set — the multi-select counterpart to `category` (§5.3.4). The `values` key MUST be present and MUST be a non-empty array of strings. The output is an array of strings; each element MUST be one of the declared values. Comprehension engines SHOULD deduplicate selected values before output; order is not significant.

Use `multi_category` for "select any that apply" or "check all that apply" fields where multiple options may be marked simultaneously and the answer space is a fixed closed set.

```yaml
condition_related_to:
  type: multi_category
  description: Boxes 10a, 10b, and 10c on the CMS-1500 — conditions the patient's claim is related to. Any combination of the listed values may be checked.
  values:
    - Employment
    - Auto accident
    - Other accident
```

Output shape (illustrative):

```json
{"condition_related_to": ["Employment", "Auto accident"]}
```

An extraction determining that no values apply SHOULD return an empty array (`[]`), not `null`. `null` SHOULD be reserved for the case where the field could not be determined from the source document at all.

For a single-select field (exactly one value from the set), use `category` (§5.3.4) instead. For a list of free-form values not constrained to a fixed set, use `array` (§5.3.6) with a single nested `string` field.

### 5.4 Nullability and `required`

These are two distinct concepts and v1.0 treats them as such.

**Nullability** is a property of the *output type*. Every v1.0 field is nullable: the output schema permits `null` for any field whose value cannot be determined from the source document. This is non-negotiable — it's the only way the comprehension step can honestly represent absent information. There is no way to make a field type non-nullable in v1.0.

**`required`** is a property of the *extraction contract*. When `required: true`, a `null` value in the output indicates an **extraction failure**, not a successful "no value present" determination. Producers MAY set `required: true` to mark fields whose presence is essential — the blueprint author is asserting that a conforming document MUST yield a non-null value for this field, and a comprehension engine returning null SHOULD surface that as a problem (review queue, retry with a different parser, lower confidence score, error in batch reporting).

The two together: `total_amount` on a receipt blueprint is naturally nullable in the output type (the comprehension step may not find it), but a blueprint author would likely set `required: true` to mark that a receipt without an extracted total is a failed extraction, not a successful one.

`required` defaults to `false`. v1.0 does not specify what consumers MUST do with `required: true` fields beyond surfacing failures; downstream review UIs, audit logs, and validators are free to implement their own policies on top.

### 5.5 Field Composition via `parent`

An array field (§5.3.6) can be populated in either of two equivalent ways:

1. **Inline** — the array declares its row shape directly via its own `fields` mapping.
2. **By reference** — the array declares no `fields`, and is populated by other top-level fields whose `parent` key names it.

The two forms produce identical output schemas. Producers MUST use exactly one mode per array.

#### 5.5.1 Inline form (recap)

```yaml
fields:
  line_items:
    type: array
    description: Itemized purchases.
    fields:
      description:
        type: string
      amount:
        type: number
```

#### 5.5.2 Parent-reference form

```yaml
fields:
  line_items:
    type: array
    description: Itemized purchases.
    # no `fields` key

  description:
    type: string
    parent: line_items

  amount:
    type: number
    parent: line_items
```

Both produce an output schema with a `line_items` array of `{description, amount}` row objects.

#### 5.5.3 Rules

1. The `parent` value MUST be the name of a field defined at the top level of the same blueprint.
2. The named field MUST have `type: array`.
3. The named field MUST NOT also declare an inline `fields` key — exactly one composition mode per array.
4. A field with a `parent` key MUST be declared at the top level of `fields`. `parent` is not valid on nested fields (the row shape of an array cannot itself use parent references; nest a child array inline if you need a second level).
5. A field with a `parent` key does NOT appear as a top-level field in the extracted output — it becomes part of the row schema of its parent array.
6. Multiple top-level fields MAY share the same `parent` — together they constitute the row shape.
7. A field name used at the top level may be reused as a row field via `parent` without collision (the two are in different scopes), but producers SHOULD avoid this for readability.

#### 5.5.4 When to use which

Inline is more compact and visually communicates hierarchy. Parent-reference is useful for authoring flows where fields are conceptually a flat list with grouping applied later (drag-and-drop UIs, generated blueprints, bulk reorganization). Both round-trip through any conforming consumer to the same internal representation.

### 5.6 Pattern

A field of `type: string` MAY declare a `pattern` key. The value MUST be a regular expression string. Patterns serve two purposes:

1. **Comprehension-time signal.** The comprehension engine SHOULD include the pattern in the LLM context for the field so extraction respects the shape constraint. This is especially load-bearing for smaller models that cannot reliably infer the shape from prose descriptions alone.
2. **Validation gate.** A non-null value extracted for the field that does not match the pattern MUST be treated as an extraction failure (analogous to `required: true` semantics in §5.4). `null` extractions are not subject to pattern validation — the pattern constrains the shape of non-null values only.

The pattern describes the **canonical output form**, not the form as it appears in the source document. The comprehension engine is expected to normalize varied input to the canonical form before returning: e.g., a Social Security Number printed as `123-45-6789`, `123 45 6789`, or `123456789` should all be normalized to the canonical pattern (typically `^\d{3}-\d{2}-\d{4}$`).

```yaml
billing_provider_npi:
  type: string
  description: Box 33a. NPI of the billing provider.
  pattern: '^\d{10}$'
  required: true
```

**Regex grammar.** Patterns SHOULD use the ECMA-262 (JavaScript) regular expression grammar, restricted to features broadly supported across implementations: anchors (`^` `$`), character classes (`\d` `\w` `[...]`), quantifiers (`*` `+` `?` `{n}` `{n,m}`), alternation (`|`), and basic groups (`(...)`). Producers SHOULD NOT use lookbehinds, named groups, or implementation-specific extensions. Consumers MUST treat the pattern as an anchored full-string match — a pattern of `\d{10}` and `^\d{10}$` are equivalent in their effect on validation.

`pattern` is only valid when `type` is `string`. Consumers MUST reject a blueprint that declares `pattern` on a field of any other type.

### 5.7 Path

A field MAY declare a `path` key. The value MUST be a string. `path` carries the **canonical-schema addressing path** that locates the field within its bound schema (§7.4).

`path` accommodates the two shapes canonical schemas come in, and a producer may choose between two style conventions:

1. **Name-based** (IRS MeF: `WagesAmt`; ACORD: `ACORD25`; Peppol: `cbc:DocumentCurrencyCode`) — the canonical identifier is a flat name. Two equally valid styles:
   - **Verbatim style.** Use the canonical identifier directly as the field's `name`, preserving its native case (`WagesAmt:`, `ACORD25:`, `cbc:DocumentCurrencyCode:`). `path` MAY be omitted in this style since the field's name IS the canonical identifier.
   - **Snake-case + path style** (Petey-house style). Use a snake_case version of the canonical identifier as the field's `name` (`wages_amt:`) and carry the canonical identifier (or its nested XPath if the element sits under a wrapper group like `EmployerUSAddress/AddressLine1Txt`) in `path:`. Keeps YAML keys uniformly snake_case across the library while preserving the canonical identifier losslessly.
2. **Path-based** (X12, FHIR, XBRL) — the canonical identifier is a coordinate. Forcing it into `name` would make the prompt and CSV unreadable. The field MUST keep a human-readable snake_case `name` and carry the canonical address in `path`.

The interpretation of `path` is determined by the blueprint's `binding` declaration (§7.4). A consumer that does not understand the bound schema SHOULD treat `path` as opaque metadata.

```yaml
# Path-based (X12, FHIR, XBRL): human-readable name + canonical path.
diagnosis_pointer:
  type: string
  path: loop_2400.SV1.07
  description: "Box 24E — diagnosis pointer (A, B, C, or D referencing the diagnosis list)."
  pattern: '^[A-D](,[A-D]){0,3}$'

# Name-based, snake_case + path style (Petey-house):
wages_amt:
  type: number
  path: WagesAmt
  description: "Box 1 — total taxable wages, tips, and other compensation."
  required: true

# Name-based, verbatim style — equally valid:
WagesAmt:
  type: number
  description: "Box 1 — total taxable wages, tips, and other compensation."
  required: true
```

`path` is OPTIONAL on every field type. `path` and `name` are independent — a blueprint MAY declare both `path` and a canonical `name` for the same field if the bound schema offers both. **v1.0 scope:** a field MAY declare at most one `path`. Multi-schema bindings (a single field mapping into both X12 and FHIR addresses) are out of scope for v1.0.

A blueprint MAY declare `path` on fields without a top-level `binding`. In that case, `path` is informational metadata; consumers MUST NOT reject the blueprint and SHOULD preserve `path` for round-trip.

> **Note on the two `path` keys.** Field-level `path` (this section) addresses a field within a *canonical schema* — an X12 loop, a FHIR element, an MeF element name. Widget-level `path` (§5.9.1) addresses a field within a *PDF document* — an AcroForm field path. They occupy different nesting levels, carry unrelated values, and MUST NOT be conflated. A field may carry both.

### 5.8 `semantic_type`

**Added in v1.1.**

`semantic_type` declares what a field's value *means* in a vocabulary shared across blueprints, independent of its `type`. Where `type` says "this is a string" and `pattern` says "it looks like `^\d{3}-\d{2}-\d{4}$`", `semantic_type: ssn` says "this is a US Social Security Number" — a single token that a consumer can dispatch on.

`semantic_type` is OPTIONAL on every field, and valid on every `type`. Its value MUST be a `snake_case` string.

Its purpose is to let consumers apply behavior uniformly without re-deriving intent from field names. Concretely, a consumer MAY use `semantic_type` to select a character whitelist when running OCR on a field, to choose a normalization routine (date reformatting, currency parsing, whitespace collapsing), to pick a comparison function when scoring extractions against ground truth, or to drive redaction and classification policy over field classes rather than field names.

`semantic_type` is **advisory**. A consumer MUST NOT reject a blueprint because it does not recognize a `semantic_type` value, and MUST NOT treat `semantic_type` as a validation constraint — `pattern` (§5.6) is the normative shape constraint. Where the two disagree, `pattern` governs.

#### 5.8.1 Registered values

The following values are registered in v1.1. The `type` column gives the `type` a producer SHOULD pair with each value; the `pattern` column gives the canonical output shape where one is defined.

| `semantic_type` | Paired `type` | Canonical `pattern` |
| --------------- | ------------- | ------------------- |
| `ssn` | `string` | `^\d{3}-\d{2}-\d{4}$` |
| `ein` | `string` | `^\d{2}-\d{7}$` |
| `itin` | `string` | `^9\d{2}-(7\d\|8[0-8])-\d{4}$` |
| `tin` | `string` | `^\d{2,3}-\d{2,7}(-\d{4})?$` |
| `npi` | `string` | `^\d{10}$` |
| `routing_number` | `string` | `^\d{9}$` |
| `account_number` | `string` | `^\d{8,17}$` |
| `naics` | `string` | `^\d{6}$` |
| `money_whole_dollar` | `number` | — |
| `money` | `number` | — |
| `percent` | `number` | — |
| `count` | `integer` | — |
| `iso_date` | `date` | `^\d{4}-\d{2}-\d{2}$` |
| `birth_date` | `date` | `^\d{4}-\d{2}-\d{2}$` |
| `service_date` | `date` | `^\d{4}-\d{2}-\d{2}$` |
| `year` | `string` | `^\d{4}$` |
| `phone` | `string` | `^\d{3}-\d{3}-\d{4}$` |
| `email` | `string` | `^[^@\s]+@[^@\s]+\.[^@\s]+$` |
| `zip` | `string` | `^\d{5}(-\d{4})?$` |
| `state_abbr` | `string` | `^[A-Z]{2}$` |
| `country_code` | `string` | `^[A-Z]{2}$` |
| `country` | `string` | — |
| `city` | `string` | — |
| `street_address` | `string` | — |
| `name_and_address` | `string` | — |
| `person_name` | `string` | — |
| `first_name` | `string` | — |
| `last_name` | `string` | — |
| `entity_name` | `string` | — |
| `business_name` | `string` | — |
| `description` | `string` | — |
| `text` | `string` | — |
| `indicator` | `boolean` | — |

`indicator` denotes a boolean drawn from a checkbox or radio button — a field whose positive signal is the presence of a mark. See §5.9.4 for how consumers SHOULD treat absent values on `indicator` fields.

Producers MAY emit `semantic_type` values outside this table. Unregistered values are forward-compatible by the rule above: consumers ignore what they do not recognize. Producers introducing a value they expect others to interpret SHOULD propose it for registration rather than relying on private agreement.

### 5.9 `widget` — the document layer

**Added in v1.1.**

A `widget` declares **where on the source document a field physically lives**. It is the key addition of v1.1 and the reason the version exists.

A blueprint carrying widgets is a *template for a specific form*, not merely a description of desired output. Given a widget rectangle, a consumer can read a field's value from a filled instance of that form deterministically — by AcroForm field lookup, by clipping the embedded text layer to the rectangle, or by rasterizing the rectangle and running OCR on it — with no language model in the extraction path. This changes the cost model: the expensive step (deciding what each field is) happens once per form, not once per document.

`widget` is OPTIONAL. A blueprint with no widgets anywhere is an ordinary v1.0-style blueprint and remains fully valid.

#### 5.9.1 Widget object

| Key           | Type    | Required | Description                                                              |
| ------------- | ------- | -------- | ------------------------------------------------------------------------ |
| `page`        | integer | Yes      | 1-based page number within the source document.                          |
| `rect`        | array   | Yes      | Bounding box as `[x0, y0, x1, y1]`. See §5.9.2.                          |
| `widget_type` | string  | Yes      | The kind of form control. See the table below.                           |
| `path`        | string  | No       | Addressing path for the control within the document's form layer. `null` when the source has no form layer. |

`widget_type` values registered in v1.1:

| Value | Meaning |
| ----- | ------- |
| `text` | Free-text entry field. |
| `checkbox` | Independently toggleable box. |
| `radiobutton` | Member of a mutually exclusive group. |
| `signature` | Signature control; consumers typically extract presence, not content. |

Consumers MUST ignore `widget_type` values they do not recognize and SHOULD fall back to treating the field as `text`.

For PDF sources, `path` is the fully-qualified AcroForm field name (e.g., `topmostSubform[0].Page1[0].f1_01[0]`). Producers deriving widgets from a document with no form layer — a flat scan, a vector-drawn form — MUST set `path` to `null` and SHOULD record the derivation method (§7.6), because in that case `rect` is an estimate rather than a value read from the document.

#### 5.9.2 Coordinate system

`rect` is `[x0, y0, x1, y1]` where `(x0, y0)` is the top-left corner and `(x1, y1)` the bottom-right.

- Units are **PDF points** (1/72 inch).
- The origin is the **top-left of the page**, with **y increasing downward**.
- Coordinates are expressed in **unrotated page space**. A consumer rendering a page with a non-zero `/Rotate` MUST apply the same rotation to the rectangle.
- `x0 < x1` and `y0 < y1` MUST hold.
- Values are real numbers and SHOULD NOT be rounded by producers; sub-point precision is meaningful for small controls such as checkboxes.

This is the convention used by PDF renderers that report widget rectangles in top-left space. Producers working in a bottom-left-origin space (the PDF imaging model's native convention) MUST convert before emitting.

#### 5.9.3 `widgets` — grouped controls

A `category` or `multi_category` field is often rendered as a cluster of controls rather than one — seven checkboxes for seven tax classifications, a radio group for filing status. For these, a field declares `widgets` (plural): a mapping from each member of `values` to its own widget object.

```yaml
return_type:
  type: category
  values:
    - amended_return_ind
    - final_return_ind
    - first_return_ind
    - short_plan_year_ind
  widgets:
    first_return_ind:
      page: 1
      rect: [140.509, 140.509, 149.509, 149.509]
      widget_type: checkbox
      path: Check P1-A1
    amended_return_ind:
      page: 1
      rect: [140.509, 153.927, 149.509, 162.927]
      widget_type: checkbox
      path: Check P1-A2
    final_return_ind:
      page: 1
      rect: [333.181, 140.509, 342.181, 149.509]
      widget_type: checkbox
      path: Check P1-A3
```

Rules:

- Every key of `widgets` MUST appear in that field's `values` array.
- `values` MAY contain members with no corresponding widget; such a member is selectable but has no known location.
- `widget` and `widgets` MUST NOT both be present on the same field.
- `widgets` is meaningful only on `category` and `multi_category`. Producers MUST NOT emit it on other types.

For `category`, the extracted value is the single member whose control is marked. For `multi_category`, it is the set of all marked members.

#### 5.9.4 Extraction semantics

A consumer that honors widgets SHOULD resolve a field's value by trying, in order: the document's form layer at `path`; the embedded text layer clipped to `rect`; optical recognition of the rasterized `rect`. A consumer MAY skip any tier it does not implement, and MAY fall back to language-model comprehension when all tiers fail.

Widgets are a **hint about location, not a guarantee about content**. A consumer MUST NOT assume a rectangle contains only the intended field's value: adjacent printed text, ruling lines, and neighboring controls routinely bleed into a clipped region. Producers SHOULD pair widgets with `pattern` and `semantic_type` so consumers can constrain and validate what they read.

For fields with `semantic_type: indicator`, an absent or unreadable mark is a negative signal, not a missing value. Consumers SHOULD treat `null` and `false` as equivalent for such fields, and MUST NOT report an unmarked checkbox as an extraction failure on that basis alone.

When a blueprint declares `source_pdf_hash` (§7.5) and the document being extracted does not match it, a consumer SHOULD warn that the geometry may not apply, and MAY decline the widget path entirely and fall back to comprehension.

#### 5.9.5 Division of labor between keys

A field's keys declare what a consumer must do to resolve it. Two independent questions decide which keys a field needs:

- **Can the value be located mechanically?** If so, the field carries `widget` or `widgets`.
- **Does position and type determine its meaning?** If so, the field carries `semantic_type` and/or `pattern`. If the value must be read to be understood, the field carries `description`.

The four combinations are all valid and all meaningful:

| Keys present | Resolution |
| ------------ | ---------- |
| `widget` + `semantic_type` | Read at the rectangle; shape is known. No comprehension required. |
| `widget` + `description` | Read at the rectangle, then interpret the clipped span. Comprehension is scoped to that span rather than the page. |
| `description` only | Locate and interpret by comprehension over the document. |
| `widget` only | Read at the rectangle and return the value verbatim. |

These are properties of the **field**, not the document: a single form routinely mixes checkbox rows that need no comprehension with free-text boxes that need it. Producers SHOULD classify per field.

A blueprint is therefore not incomplete because its fields lack `description`. A field whose meaning is fully determined by its location and type has nothing for a description to add, and populating one is redundant rather than thorough. Conversely, a free-text field carrying only a `widget` is under-specified: a consumer can return its contents but cannot know what to make of them.

## 6. Record Types

`record_type` declares the cardinality of the extracted output.

### 6.1 `single`

The document contains exactly one record matching the blueprint. The output is a single object whose keys are the top-level field names. This is the default.

### 6.2 `array`

The document contains zero or more records matching the blueprint. The output is an object with a single key, `items`, whose value is an array of objects, each matching the top-level field shape. The `items` wrapper is part of the contract — it gives downstream consumers a predictable handle for streaming or pagination.

```yaml
record_type: array
fields:
  member_name:
    type: string
    description: Name of the filing member.
  transaction_date:
    type: date
    description: Date the transaction occurred.
```

Output shape (illustrative):

```json
{
  "items": [
    {"member_name": "...", "transaction_date": "2024-03-12"},
    {"member_name": "...", "transaction_date": "2024-03-15"}
  ]
}
```

## 7. Auxiliary Fields

### 7.1 `instructions`

A free-form natural-language string passed to the comprehension step alongside the field definitions. Use `instructions` for guidance that doesn't fit cleanly into a per-field `description` — for example, document-wide normalization rules, hints about which page contains which data, or instructions to ignore certain sections.

`instructions` is a hint, not a contract. Different comprehension engines may weight it differently. Producers SHOULD keep `instructions` short and SHOULD prefer per-field `description` text when the guidance is field-specific.

### 7.2 `header_pages`

An integer count of leading pages that contain document-level metadata as distinct from per-record content. Used by inference and chunking strategies to avoid treating header pages as repeating-record content. Defaults to `0`. Has no effect on output shape.

### 7.3 `source`

An optional mapping with provenance metadata. Recommended keys (all optional):

| Key       | Type   | Description                                                  |
| --------- | ------ | ------------------------------------------------------------ |
| `author`  | string | Person or organization that authored the blueprint.          |
| `license` | string | SPDX identifier or license URL for the blueprint itself.     |
| `url`     | string | Canonical URL where this blueprint is published.             |
| `derived_from` | string | URL or identifier of a parent blueprint, if forked.     |

Consumers MUST ignore unknown keys inside `source` (per the forward-compatibility rule in §4).

### 7.4 `binding`

An optional mapping declaring the **canonical schema** that the blueprint's field identifiers come from. `binding` is the contract that lets downstream consumers interpret the blueprint's field names (and `path` values, §5.7) under a known external vocabulary — for example, IRS Modernized e-File (MeF) for U.S. federal tax forms, X12 837 or FHIR R5 Claim for medical billing, MISMO v3.4 or ULAD for U.S. mortgage origination, UBL / Peppol BIS Billing for European invoicing, ACORD numbered field IDs for insurance, or the US-GAAP XBRL taxonomy for financial reporting.

| Key       | Type   | Required | Description                                                                       |
| --------- | ------ | -------- | --------------------------------------------------------------------------------- |
| `schema`  | string | Yes      | Identifier of the canonical schema. SHOULD be a stable, short slug (snake_case).  |
| `version` | string | No       | Version identifier within the bound schema (e.g., tax year, spec revision).       |
| `url`     | string | No       | Canonical URL for the bound schema, where applicable.                             |

```yaml
binding:
  schema: irs_mef
  version: "2025"
  url: https://www.irs.gov/e-file-providers/modernized-e-file-mef-schemas-and-business-rules
```

When `binding` is declared, the field identifiers in the blueprint SHOULD be drawn from the bound schema where a canonical identifier exists. Fields without a canonical counterpart in the bound schema retain Petey-conventional naming and SHOULD be flagged either by omission of a `path` (for path-based schemas) or by author convention.

When `binding` is **not** declared, all field identifiers are interpreted as Petey-conventional — no claim is made about external schema alignment.

**v1.0 scope.** A blueprint MAY declare at most one `binding`. Multi-schema bindings (a CMS-1500 blueprint that maps simultaneously to X12 837 and FHIR R5 Claim) are out of scope for v1.0; if downstream interop needs both, ship two blueprints with different `binding` declarations.

**Recommended `schema` slugs.** These are the slugs in use by the Petey blueprint library; producers MAY use others where appropriate, but SHOULD prefer these where the domain matches:

| Slug             | Domain                                  |
| ---------------- | --------------------------------------- |
| `irs_mef`        | U.S. federal tax (IRS Modernized e-File)|
| `x12_837p`       | U.S. medical billing — professional     |
| `x12_837i`       | U.S. medical billing — institutional    |
| `fhir_r5_claim`  | Healthcare claims (FHIR R5)             |
| `mismo_v3_4`     | U.S. mortgage origination               |
| `ulad`           | Uniform Loan Application Dataset (GSE)  |
| `peppol_bis_3`   | EU e-invoicing (UBL 2.1 / Peppol BIS 3) |
| `acord`          | Insurance (ACORD numbered field IDs)    |
| `us_gaap_xbrl`   | U.S. financial reporting (XBRL US-GAAP) |

Consumers MUST ignore unknown keys inside `binding` (per §4).

### 7.5 Source-document binding

**Added in v1.1.**

Widget geometry (§5.9) is only meaningful relative to a specific document. A rectangle on page 1 of the 2025 revision of a form may address a different field on the 2024 revision. These four top-level keys pin the widget layer to the document it was derived from.

| Key               | Type    | Description                                                                 |
| ----------------- | ------- | --------------------------------------------------------------------------- |
| `source_pdf`      | string  | Filename of the blank source document. Identification only — not a resolvable locator. |
| `source_pdf_hash` | string  | Hash of that document's bytes, hex-encoded. Producers SHOULD use SHA-1 or stronger and SHOULD NOT vary the algorithm within a library. |
| `source_pages`    | array   | 1-based page numbers that carry labeled widgets. Lets a consumer skip pages known to hold none. |
| `form_version`    | string  | Revision identifier of the form as the issuing authority labels it — `"2025"`, `"Rev. March 2024"`. `null` when unknown. |

All four are OPTIONAL. A blueprint that declares any `widget` or `widgets` SHOULD declare `source_pdf_hash` and `form_version`, because without them a consumer cannot tell whether the geometry applies to the document in hand.

`form_version` is the human-facing revision label; `source_pdf_hash` is the machine-facing exact-match check. They answer different questions — "is this the same edition of the form?" versus "is this byte-identical to what I measured?" — and a producer SHOULD emit both.

### 7.6 `authoring`

**Added in v1.1.**

An OPTIONAL mapping recording how the blueprint's field and widget layers were derived. Recommended keys (all optional):

| Key      | Type   | Description                                                              |
| -------- | ------ | ------------------------------------------------------------------------ |
| `method` | string | Derivation method — e.g. reading a form layer, vision-model labeling, manual authoring. |
| `model`  | string | Identifier of the model used, if any.                                    |
| `notes`  | string | Free-form caveats about the result's reliability.                        |

`authoring` matters because widget precision varies by derivation path. Widgets read from a document's form layer are exact. Widgets estimated by a vision model from a rendered page are approximate, and consumers may reasonably want to loosen clipping tolerances or decline the deterministic path entirely. Recording the method lets a consumer make that judgment rather than guess.

Consumers MUST ignore unknown keys inside `authoring`, and MUST NOT reject a blueprint that omits it.

## 8. Versioning

The spec uses two-part `MAJOR.MINOR` semantic versioning, applied to the spec document itself:

- **MAJOR** bumps when a change breaks consumers of a prior version (e.g., a previously valid `.bpt` file becomes invalid, or its meaning changes).
- **MINOR** bumps when a change is additive and backwards-compatible (e.g., a new optional field type, a new top-level key with a safe default).

A `.bpt` document SHOULD declare the version it conforms to. Documents without a version are interpreted as v1.0.

A producer SHOULD declare `bpt_version: "1.1"` only when the blueprint actually uses a v1.1 feature (`semantic_type`, `widget`, `widgets`, or the §7.5 / §7.6 keys). A blueprint using none of them SHOULD declare `"1.0"`, so that the version number carries information about content rather than about the tool that emitted it.

Consumers SHOULD accept any `bpt_version` whose MAJOR equals their supported MAJOR and whose MINOR is less than or equal to their supported MINOR. Consumers MAY accept higher MINOR versions if they ignore unknown keys (per §4).

Because v1.1 is additive, a v1.0-only consumer that follows the forward-compatibility rule in §4 will load a v1.1 blueprint correctly, ignoring the document layer and behaving exactly as it would on a v1.0 blueprint. Producers SHOULD NOT rely on this: a consumer is permitted to reject a higher MINOR, and one that silently discards widget geometry gives no signal that it has done so.

The spec is versioned independently of the Petey reference implementation. A blueprint conforming to BPT v1.x is portable across any v1.x-compatible consumer regardless of who built it.

## 9. Compatibility and Portability

A blueprint is a **declarative** description of a target output shape. It can be translated to other ecosystem-specific schema formats:

| Target format              | Translation                                                                  |
| -------------------------- | ---------------------------------------------------------------------------- |
| JSON Schema                | Each field becomes a property; `enum` and `array` map directly.              |
| Pydantic model             | Each field becomes a typed attribute on a generated `BaseModel`.             |
| OpenAI function/tool schema| The blueprint becomes the `parameters` JSON Schema of a function/tool.       |
| Anthropic tool input schema| Same as above; `input_schema` is a JSON Schema subset.                       |
| Instructor / LangChain     | Blueprint compiles to the library's preferred Pydantic / BaseModel form.    |

These translations are non-normative in v1.0 — they describe the intended interoperability surface, not formal mappings. Reference converters are expected to ship alongside the Petey reference implementation. Implementers building independent converters SHOULD publish the translation rules they use.

## 10. Conformance

A consumer is **v1.0-conforming** if it:

1. Accepts UTF-8 YAML 1.2 input with the `.bpt` extension (and MAY accept `.yaml`/`.yml` with a deprecation warning).
2. Implements the type system in §5.3 (`string`, `number`, `date`, `category`, `boolean`, `array`) with the nullability semantics in §5.4.
3. Accepts the type-name aliases (`enum`/`cat` for `category`; `bool` for `boolean`) as interchangeable synonyms, with no warning.
4. Implements both record types in §6.
5. Implements both field-composition modes in §5.5 (inline `fields` and parent reference), producing equivalent output schemas.
6. Respects the `required` flag per §5.4 by surfacing null values in required fields as extraction failures.
7. Ignores unrecognized top-level keys per §4.
8. Accepts the deprecated `mode` aliases per §4.3 with a deprecation warning.
9. Accepts blueprints declaring `binding` (§7.4) and field-level `path` (§5.7) without rejection. A consumer that does not interpret a particular bound schema MUST still load the blueprint and preserve `binding` and `path` for round-trip serialization.

A consumer MAY restrict the blueprints it accepts (for example, to `record_type: single` only) provided it reports this restriction clearly.

A producer is **v1.0-conforming** if every blueprint it emits satisfies the structural rules in §§3–7 with `bpt_version: "1.0"` or no version declared.

A consumer is **v1.1-conforming** if it satisfies every v1.0 clause above and additionally:

10. Loads blueprints declaring `semantic_type` (§5.8) without rejection, preserving the value for round-trip, whether or not it acts on it.
11. Loads blueprints declaring `widget` or `widgets` (§5.9) without rejection, preserving the geometry for round-trip.
12. If it resolves values by geometry, interprets `rect` per the coordinate system in §5.9.2, and enforces the `widget`/`widgets` mutual exclusion and the `widgets`-keys-subset-of-`values` rule in §5.9.3.
13. Treats `null` and `false` as equivalent for fields declaring `semantic_type: indicator` (§5.9.4).

A consumer MAY be v1.1-conforming without implementing geometric extraction at all: clauses 10–11 require only that the document layer is loaded and preserved, not acted upon. Such a consumer SHOULD report that it ignores widget geometry, so producers are not misled into thinking a deterministic path was taken.

A producer is **v1.1-conforming** if every blueprint it emits satisfies §§3–7, declares `bpt_version: "1.1"` when it uses any v1.1 feature, and — when it emits widget geometry — also emits the source-document binding of §7.5.

## 11. Appendix A: Worked Examples

### A.1 Single-record blueprint (receipt)

```yaml
bpt_version: "1.0"
name: receipt
record_type: single
description: A retail receipt with totals and a list of line items.
instructions: >
  Treat the merchant name as the topmost text block. Currency may be
  inferred from country if not stated explicitly.
fields:
  business:
    type: string
    description: Store or restaurant name.
    required: true
  amount:
    type: number
    description: Total amount paid, in the document's stated currency.
    required: true
  currency:
    type: category
    description: ISO 4217 currency code.
    values: [USD, EUR, CAD, GBP, JPY]
  purchase_date:
    type: date
    description: Date of the transaction.
  tax_included:
    type: boolean
    description: Whether the listed amount already includes sales tax.

  # Inline-array form: row shape declared under the array itself.
  line_items:
    type: array
    description: Itemized purchases.
    fields:
      description:
        type: string
        description: Item description as printed.
      amount:
        type: number
        description: Item amount.
```

The same blueprint authored with the **parent-reference form** for `line_items` (§5.5.2) is equivalent:

```yaml
bpt_version: "1.0"
name: receipt
record_type: single
fields:
  business: {type: string, required: true}
  amount: {type: number, required: true}
  currency: {type: category, values: [USD, EUR, CAD, GBP, JPY]}
  purchase_date: {type: date}
  tax_included: {type: boolean}

  line_items:
    type: array
    description: Itemized purchases.
    # no `fields` key — populated by reference below

  item_description:
    type: string
    description: Item description as printed.
    parent: line_items

  item_amount:
    type: number
    description: Item amount.
    parent: line_items
```

### A.2 Multi-record blueprint (congressional stock transactions)

```yaml
bpt_version: "1.0"
name: house_stock_transaction_report
record_type: array
description: U.S. House periodic transaction report (PTR) — per-transaction rows.
header_pages: 1
fields:
  member_name:
    type: string
    description: Name of the House member filing the report.
    required: true
  asset:
    type: string
    description: Description of the security or asset transacted.
    required: true
  transaction_type:
    type: category
    description: Type of transaction. P = purchase, S = sale, E = exchange.
    values: [P, S, "S (partial)", E]
    required: true
  transaction_date:
    type: date
    description: Date the transaction occurred.
    required: true
  amount_range:
    type: category
    description: Disclosed dollar range of the transaction.
    values:
      - "$1,001 - $15,000"
      - "$15,001 - $50,000"
      - "$50,001 - $100,000"
      - "$100,001 - $250,000"
      - "$250,001 - $500,000"
      - "$500,001 - $1,000,000"
      - "Over $1,000,000"
  capital_gains_over_200:
    type: boolean
    description: Whether capital gains exceeded $200.
source:
  author: Petey blueprint library
  license: CC-BY-4.0
  url: https://petey.cc/blueprints/house-stock-transaction-report
```

### A.3 Blueprint with a document layer (v1.1)

A form template carrying widget geometry. Extraction from a filled instance needs no language model: each value is read from the form layer at `widget.path`, or from the text clipped to `widget.rect`.

```yaml
bpt_version: "1.1"
name: w_9
record_type: single
form_version: "Rev. March 2024"
source_pdf: fw9.pdf
source_pdf_hash: 3c265a136ba7fa236cdfc7b8f8b7853ed6c63e08
source_pages: [1]
description: >-
  IRS Form W-9, Request for Taxpayer Identification Number and Certification.
binding:
  schema: mef
  version: "TY2025"
authoring:
  method: acroform
  notes: Widget rects read from the source PDF's form layer; exact.
fields:
  name_of_entity_individual_nm:
    type: string
    semantic_type: person_name
    description: "Line 1 — name as shown on the filer's income tax return."
    widget:
      page: 1
      rect: [58.6, 118.001, 576.0, 132.001]
      widget_type: text
      path: topmostSubform[0].Page1[0].f1_01[0]

  taxpayer_identification_number_ssn:
    type: string
    semantic_type: ssn
    pattern: "^\\d{3}-\\d{2}-\\d{4}$"
    description: "Part I — Social Security Number, if the filer is an individual."
    widget:
      page: 1
      rect: [396.0, 545.28, 528.0, 561.6]
      widget_type: text
      path: topmostSubform[0].Page1[0].f1_11[0]

  federal_tax_classification:
    type: category
    values:
      - individual_sole_proprietor_ind
      - c_corporation_ind
      - s_corporation_ind
      - partnership_ind
      - trust_estate_ind
    description: "Line 3a — the filer's federal tax classification."
    widgets:
      individual_sole_proprietor_ind:
        page: 1
        rect: [59.04, 194.4, 68.04, 203.4]
        widget_type: checkbox
        path: topmostSubform[0].Page1[0].c1_1[0]
      c_corporation_ind:
        page: 1
        rect: [149.76, 194.4, 158.76, 203.4]
        widget_type: checkbox
        path: topmostSubform[0].Page1[0].c1_1[1]
      s_corporation_ind:
        page: 1
        rect: [235.44, 194.4, 244.44, 203.4]
        widget_type: checkbox
        path: topmostSubform[0].Page1[0].c1_1[2]
```

## 12. Appendix B: Open Issues for Future Versions

The following are deliberately out of scope for v1.0 and may be addressed in v1.1 or v2.0:

- **Confidence thresholds and evaluation metrics.** v1.0 does not encode per-field confidence thresholds or comparison functions (edit distance, Levenshtein, numeric tolerance, etc.). A future version may add `confidence_threshold` for engine-reported confidence and an `evaluation` block for ground-truth comparison rules — both are interop-friendly if the semantics are well-specified.
- **Reusable / referenced array definitions.** v1.0 defines array contents inline only. A future version may add a way to declare an array's row shape once and reference it from multiple places (analogous to JSON Schema's `$ref` / `definitions`).
- **Conditional / dependent fields.** v1.0 has no equivalent of JSON Schema's `if`/`then`/`else`. Composition is via nested `array` types only.
- **Field-level validation beyond pattern and category.** v1.0 covers regex shape (`pattern`, §5.6) and closed-set membership (`category` / `multi_category` values). Numeric ranges, cross-field invariants, and conditional constraints are not in v1.0; implementers needing them today SHOULD push into a downstream layer (Pydantic, JSON Schema).
- **Multi-schema bindings.** A blueprint that binds to more than one canonical schema simultaneously (e.g., CMS-1500 mapping to both X12 837P and FHIR R5 Claim). v1.0 permits exactly one `binding` (§7.4) and one `path` per field (§5.7). A future version may add a way to declare multiple bindings with disambiguating addresses.
- **Multi-document blueprints.** A blueprint that spans multiple input documents (e.g., a claim and its supporting attachments). Currently out of scope; one blueprint, one document.
- **Localization.** `description` and `instructions` are single-language. A future version may add per-locale field metadata.
- **Formal contributor / governance terms.** Stewardship in v1.0 is "Petey publishes, community welcomed." A future version may add an open-contribution process, signing terms, or RFC-style proposal flow.

## 13. References

- [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) — Key words for use in RFCs to Indicate Requirement Levels.
- [YAML 1.2.2](https://yaml.org/spec/1.2.2/) — Specification of the YAML serialization format.
- [JSON Schema](https://json-schema.org/) — Related schema-description format; a translation target for portability.
- [ISO 8601](https://www.iso.org/iso-8601-date-and-time-format.html) — Date and time format.
- [SPDX License List](https://spdx.org/licenses/) — License identifiers for `source.license`.

## 14. Changelog

### v1.1 (2026-09-08)

Additive MINOR revision. Every v1.0 blueprint is a valid v1.1 blueprint unchanged; no v1.0 construct changed meaning.

**Added — the document layer**

| Addition | Section |
| -------- | ------- |
| `widget` on a field — `page`, `rect`, `widget_type`, `path` | §5.9.1 |
| Coordinate system for `rect` — PDF points, top-left origin, unrotated page space | §5.9.2 |
| `widgets` on `category` / `multi_category` — one widget per member of `values` | §5.9.3 |
| Extraction semantics, tier order, and the bleed caveat | §5.9.4 |
| `source_pdf`, `source_pdf_hash`, `source_pages`, `form_version` top-level keys | §7.5 |
| `authoring` — how the field and widget layers were derived | §7.6 |

**Added — the semantic layer**

| Addition | Section |
| -------- | ------- |
| `semantic_type` on a field, advisory, valid on every type | §5.8 |
| 33 registered `semantic_type` values with paired `type` and canonical `pattern` | §5.8.1 |
| `indicator` semantics: `null` and `false` equivalent | §5.9.4 |

**Changed**

- §8 — a producer SHOULD declare `"1.1"` only when a v1.1 feature is actually used, so the version reflects content rather than tooling.
- §10 — added consumer clauses 10–13 and a v1.1 producer clause. A consumer may conform without implementing geometric extraction, provided it says so.
- §5.7 — added a note distinguishing field-level `path` (canonical schema address) from widget-level `path` (document form-layer address). Same key name, unrelated meanings, different nesting levels.

**Not addressed**

Nothing in Appendix B was resolved by v1.1. Confidence thresholds, reusable array definitions, conditional fields, numeric-range validation, multi-schema bindings, multi-document blueprints, localization, and formal governance all remain open.

**Migration required by the Petey reference producer**

v1.1 was written against blueprints the Petey toolchain already emits. Validating those blueprints against this document surfaced four deviations the producer must fix to be v1.1-conforming. They are recorded here because the spec is normative and the current producer is not yet aligned with it.

1. **Unnamespaced diagnostic keys.** The producer emits `dedup_log` (52 blueprints) and `copy_pages_log` (17) as bare top-level keys. §4 requires vendor-specific keys be namespaced. These SHOULD become `x_petey_dedup_log` and `x_petey_copy_pages_log`.
2. **`_authoring` vs `authoring`.** The producer emits `_authoring`; §7.6 specifies `authoring`. The leading underscore has no meaning in this format and SHOULD be dropped.
3. **Divergent semantic vocabularies.** The vision-labeling path carries its own hardcoded list of `semantic_type` values in its prompt, which has drifted from the registry the AcroForm path uses. It emits `address` (66 occurrences) and `date` (61) where §5.8.1 registers `street_address` and `iso_date`. Both paths SHOULD draw from one registry; the prompt list SHOULD be generated from it rather than maintained in parallel. This affects exactly the four blueprints derived from flat documents.
4. **Version declared unconditionally.** The producer stamps `bpt_version: "1.1"` on every blueprint it emits regardless of content. Per §8 it SHOULD declare `"1.0"` for blueprints using no v1.1 feature.

None of these affect a consumer that follows the forward-compatibility rule in §4 — unknown keys are ignored and unregistered `semantic_type` values are advisory. They matter for portability and for the spec being an honest description of what the library contains.

### v1.0 (2026-06-01)

First formalization of the format: file format, document structure, field definitions, the type system, record types, auxiliary fields, versioning policy, portability surface, and conformance criteria. Within the v1.0 line, and prior to any public release, the following landed inline rather than as versioned revisions: relaxed two-value `category`, `multi_category`, `pattern` (2026-06-03), and `binding` plus field-level `path` (2026-06-24).

---

*BPT Spec v1.1 (Draft) — stewarded by Petey, Inc. Feedback and proposals welcome; see `petey.cc/spec` for the canonical version.*
