"""Tag registry forms with their launch tier from a ranking CSV (registry/launch_ranking_v*.csv).

Each row's blank (source_pdfs/<dir>/<file>) is looked up in the registry's source_pdfs table and its form gets the
tag launch:t1 .. launch:t4. Existing launch:* tags are cleared first, so a rerun with a new ranking replaces them.

    venv/bin/python registry/tag_launch.py registry/launch_ranking_v2.csv
"""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "registry"))
import registry as R  # noqa: E402


def main() -> int:
    ranking = Path(sys.argv[1])
    conn = R.connect()
    conn.execute("DELETE FROM form_tags WHERE tag LIKE 'launch:%'")
    c, missing = Counter(), []
    for r in csv.DictReader(ranking.open()):
        hit = conn.execute("SELECT form_id FROM source_pdfs WHERE path = ?",
                           (f"source_pdfs/{r['dir']}/{r['file']}",)).fetchone()
        if not hit or not hit[0]:
            missing.append(f"{r['dir']}/{r['file']}")
            continue
        conn.execute("INSERT OR IGNORE INTO form_tags (form_id, tag) VALUES (?, ?)", (hit[0], f"launch:t{r['tier']}"))
        c[f"t{r['tier']}"] += 1
    conn.commit()
    print(f"{ranking.name}: tagged {dict(sorted(c.items()))}; no registry form for {len(missing)}: {missing[:10]}")
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
