"""The model each pipeline step uses, in one place. `PETEY_MODEL_<STEP>` swaps one step and leaves the rest at their
defaults, so models can be compared one at a time (Andrew, 2026-10-12):

    PETEY_MODEL_CLASSIFIER=local-qwen3vl scripts/run_form.sh acord25 acord25_blank.pdf

The environment reaches every subprocess a run starts (labeler, validate, review), and `form_run.pipeline_config`
records each step's model in the run record. A model id picks its provider by prefix (`generate.PROVIDERS`):
`claude-*` Anthropic, `gemini-*` Google, `local-*` a llama.cpp server at PETEY_LOCAL_LLM_URL. Steps that send a
page image (page check, classifier, adjudicator) need a vision model.
"""
from __future__ import annotations

import os

DEFAULTS = {
    "labeler": "gemini-3.8-flash",           # 2026-10-06: Gemini, within noise of Sonnet 4.6 at a third of the price
    "page_check_first": "gemini-3.8-flash",  # round 0: every field
    "page_check_loop": "claude-opus-5",      # the loop's checks of changed fields and their neighbours
    "classifier": "claude-sonnet-4-6",       # the page classifier (synthetic cases, class check)
    "generator": "claude-sonnet-4-6",        # the synthetic case generator (blind values from the page)
    "reader": "claude-sonnet-4-6",           # the loop's meaning-based reader (validate's judge)
    "reviewer": "claude-opus-5",             # the loop's LLM reviewer
    "adjudicator": "claude-sonnet-4-6",      # contested renames, judged on the page
}


def model_for(step: str) -> str:
    return os.environ.get(f"PETEY_MODEL_{step.upper()}") or DEFAULTS[step]


def overrides() -> dict[str, str]:
    """The steps whose model the environment changed."""
    return {s: model_for(s) for s in DEFAULTS if model_for(s) != DEFAULTS[s]}
