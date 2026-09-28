"""Shared helper for handling duplicate labels across widgets.

Both `auto_label.py` and `migrate.py` may encounter multiple widgets
that resolve to the same slug. Policy (2025-07-01):

  1. **Sort widgets** by `(page, id)` — first-in-reading-order wins.
  2. **Log** every collision: the label, count, and rects.
  3. **Auto-suffix** all but the first occurrence: `slug`, `slug_2`,
     `slug_3`, ...

This keeps data extractable even for f8949 Part I/II style semantic
collisions (they'd otherwise be silently dropped), and gives us a
transparent audit trail via the returned collision log.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Collision:
    original_label: str
    assigned_label: str
    page: int
    rect: list[float]
    kept_first_at_page: int


@dataclass
class DedupState:
    seen_counts: dict[str, int] = field(default_factory=dict)
    collisions: list[Collision] = field(default_factory=list)

    def assign(self, label: str, page: int, rect: list[float]) -> str:
        """Return the actual label to use — either `label` or a suffixed
        variant if `label` was already assigned to an earlier widget."""
        n = self.seen_counts.get(label, 0)
        if n == 0:
            self.seen_counts[label] = 1
            return label
        # Collision — find first unused suffix and log
        suffix = n + 1
        while f"{label}_{suffix}" in self.seen_counts:
            suffix += 1
        assigned = f"{label}_{suffix}"
        self.seen_counts[label] = n + 1
        self.seen_counts[assigned] = 1
        self.collisions.append(Collision(
            original_label=label,
            assigned_label=assigned,
            page=page,
            rect=list(rect),
            kept_first_at_page=-1,  # we don't track the first page here
        ))
        return assigned

    def summary(self) -> dict:
        return {
            "duplicate_labels_reassigned": len(self.collisions),
            "collisions": [
                {
                    "original_label": c.original_label,
                    "assigned_label": c.assigned_label,
                    "page": c.page,
                    "rect": c.rect,
                }
                for c in self.collisions
            ],
        }
