"""The test forms: the five documents every comparison in this repo runs on.

Chosen for the relabel test (docs/RELABEL_PLAN_v1.md, 2026-09-29), one per
family, smallest first, and used since for every model sweep and reader
change. Codified 2026-09-30 so a harness names a tier instead of re-listing
blanks.

    from petey.validate.test_forms import TEST_FORMS, forms
    for f in forms("core"):      # W-9, ACORD 25, I-765
        f.stem, f.blank, f.reader, f.blueprint()

Tiers: `smoke` is the W-9 alone (one page, cheapest); `core` is the three
forms the model sweeps use; `full` adds the two radio-heavy XFA forms that
cost the most and only matter when the question is about option groups or
the whole gamut.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from petey.paths import BLUEPRINTS, RUNS, SOURCE_PDFS


@dataclass(frozen=True)
class TestForm:
    stem: str            # blueprint stem and the ground-truth cache key
    blank: str           # under source_pdfs/
    pages: int
    fields: int          # committed blueprint's field count (or the side copy's)
    reader: str          # "petey:pymupdf" or "petey:image" (values missing from the text layer)
    tier: str            # smoke | core | full
    side_copy: Optional[str] = None   # blueprint kept outside the library, under runs/
    why: str = ""

    @property
    def blank_path(self) -> Path:
        return SOURCE_PDFS / self.blank

    def blueprint(self) -> Path:
        """The blueprint to run: the committed one, else the side copy."""
        p = BLUEPRINTS / f"{self.stem}.bpt"
        if p.exists():
            return p
        if self.side_copy:
            return RUNS / self.side_copy
        raise FileNotFoundError(f"no blueprint for {self.stem}")

    @property
    def in_library(self) -> bool:
        return (BLUEPRINTS / f"{self.stem}.bpt").exists()


TEST_FORMS: tuple[TestForm, ...] = (
    TestForm("fw9", "tax/fw9.pdf", 1, 23, "petey:pymupdf", "smoke",
             why="one page, cheapest; the smoke check"),
    TestForm("acord25", "acord25_blank.pdf", 1, 128, "petey:pymupdf", "core",
             why="insurance certificate with a dense coverage grid; five automobile boxes named one row off (name_slide)"),
    TestForm("i765", "immigration/i-765.pdf", 7, 140, "petey:pymupdf", "core",
             why="XFA hybrid; repeated sections; the hard reference form"),
    TestForm("vba21526ez", "vba-21-526ez-are.pdf", 15, 328, "petey:image", "full",
             why="XFA hybrid; 35 date parts, 23 radio groups; filled values missing from its text layer"),
    TestForm("va_form_10_10ez", "VA Form 10-10EZ.pdf", 6, 122, "petey:pymupdf", "full",
             side_copy="relabel/blueprints/va_form_10_10ez_relabel2.bpt",
             why="XFA; 22 radio groups; not in the library yet (per-option side copy from the relabel test)"),
)

TIERS = {"smoke": ("smoke",), "core": ("smoke", "core"), "full": ("smoke", "core", "full")}


def forms(tier: str = "core") -> list[TestForm]:
    """The forms of a tier, cumulative: core includes smoke, full includes both."""
    want = TIERS[tier]
    return [f for f in TEST_FORMS if f.tier in want]


def by_stem(stem: str) -> TestForm:
    for f in TEST_FORMS:
        if f.stem == stem or (f.side_copy and stem.startswith(f.stem)):
            return f
    raise KeyError(stem)
