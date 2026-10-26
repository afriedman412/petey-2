"""Shared fixtures for the petey-2 tests.

The suite is offline and quick: no model calls, no network, a few seconds in all. A test that needs a blank uses
the copies in tests/fixtures (source_pdfs/ is fetched from S3 and not in git)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).parent / "fixtures"
F8825 = FIXTURES / "f8825.pdf"          # IRS Form 8825: two-line address widgets the page finder sees as two cells

# eval/ scripts import each other by bare name (they run as scripts), so the tests put eval/ on the path as they do
sys.path.insert(0, str(ROOT / "eval"))


@pytest.fixture
def f8825(tmp_path):
    """A private copy of the Form 8825 blank (tests write filled copies next to it)."""
    p = tmp_path / "f8825.pdf"
    p.write_bytes(F8825.read_bytes())
    return p
