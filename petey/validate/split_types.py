"""The split-value taxonomy: the kinds of value written in several fields on one line (Andrew, 2026-10-28: "sequential
fields on a single line that can be combined logically"; 2026-11-04: "a taxonomy of defined types that can be added
and removed"). One list, read by everything that names a kind:

    the Groups tab's entity-type dropdown (`group_review.ENTITY_TYPES`)
    the page-only detector (`compound_values.find`, which reports the counted kinds only)
    the benchmark key (`eval/benchmark_key.py`: a tagged value of an uncounted kind is not a split value there)

Each kind: its parts in reading order, and whether it `counts` as a split value for the benchmark (Andrew,
2026-10-30: dates, phones and ID numbers; names, addresses, signature lines, times and money are grouped on the
review page for other reasons and are not scored). Adding a kind is one entry here; turning one on or off is its flag.
No imports, so any module may read it.
"""
from __future__ import annotations

TYPES: dict[str, dict] = {
    "date": {"parts": ("month", "day", "yr"), "counts": True},
    "time": {"parts": ("hour", "minute", "ampm"), "counts": False},
    "address_line_1": {"parts": ("street", "unit"), "counts": False},
    "address_line_2": {"parts": ("city", "county", "state", "zip", "country"), "counts": False},
    "full_address": {"parts": ("street", "unit", "city", "county", "state", "zip", "country"), "counts": False},
    "signature_complex": {"parts": ("signature", "name", "title", "date"), "counts": False},
    "phone": {"parts": ("area", "prefix", "line"), "counts": True},
    "id_number": {"parts": (), "counts": True},           # 1 / 2 / 3 ... (SSN, EIN, routing, account numbers)
    "money": {"parts": ("dollars", "cents"), "counts": False},
    "name": {"parts": ("first", "middle", "last", "suffix"), "counts": False},
    "other": {"parts": (), "counts": False},
}


def names() -> tuple[str, ...]:
    return tuple(TYPES)


def parts() -> dict[str, tuple[str, ...]]:
    return {k: v["parts"] for k, v in TYPES.items() if k != "other"}


def counted() -> tuple[str, ...]:
    """The kinds that are split values for the benchmark."""
    return tuple(k for k, v in TYPES.items() if v["counts"])


def counts(kind) -> bool:
    return bool(kind) and TYPES.get(kind, {}).get("counts", False)
