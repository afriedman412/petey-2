"""Declare `bpt_version` from blueprint content, not from tooling.

BPT spec §8: a producer SHOULD declare `"1.1"` only when a v1.1 feature is
actually used, so the version reflects what the document contains rather
than which version of the emitter happened to write it. Every emitter in
this repo previously stamped `"1.1"` unconditionally (spec §14, deviation 4).

The v1.1 surface is the document layer and the semantic layer — see spec
§14's "Added" tables. A blueprint using none of it is a valid v1.0
blueprint and should say so.
"""
from __future__ import annotations

from typing import Any

# Top-level keys introduced by v1.1 (spec §7.5, §7.6).
V11_TOPLEVEL_KEYS = (
    "source_pdf",
    "source_pdf_hash",
    "source_pages",
    "form_version",
    "authoring",
)

# Per-field keys introduced by v1.1 (spec §5.8, §5.9.1, §5.9.3).
V11_FIELD_KEYS = ("widget", "widgets", "semantic_type")


def uses_v11_features(bp: dict[str, Any]) -> bool:
    """True if `bp` uses any construct v1.0 has no meaning for.

    A key present but null/empty does not count — an emitter that writes
    `form_version: None` for a form with no version has not thereby used
    a v1.1 feature.
    """
    for key in V11_TOPLEVEL_KEYS:
        if bp.get(key):
            return True
    for spec in (bp.get("fields") or {}).values():
        if not isinstance(spec, dict):
            continue
        if any(spec.get(k) for k in V11_FIELD_KEYS):
            return True
    return False


def declared_version(bp: dict[str, Any]) -> str:
    """The `bpt_version` string this blueprint's content warrants."""
    return "1.1" if uses_v11_features(bp) else "1.0"


def stamp_version(bp: dict[str, Any]) -> dict[str, Any]:
    """Set `bp["bpt_version"]` from its content, in place. Returns `bp`.

    Call after the `fields` dict is fully populated — the answer depends
    on what the fields ended up carrying.
    """
    bp["bpt_version"] = declared_version(bp)
    return bp
