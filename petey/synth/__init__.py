"""Step 2: blank form -> synthetic values -> filled PDF (never sees the .bpt)."""
from .generate import generate_from_pdf
from .render import render_pdf
from .local import generate_local, seed_from_key
