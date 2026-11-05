---
name: update-key
description: Rebuild the flat-structure benchmark's answer key (runs/benchmark/key) and the tuning set (runs/benchmark/dev_key, the hold-out training set the local models are fitted on) from the STRUCTURE VALIDATED blueprints and report what changed. Build only, no predictions and no scoring. Use whenever Andrew asks to update, rebuild, refresh or regenerate the key, the benchmark, the benchmark set, the tuning set, the holdout / training set or the dev key, or says new forms were accepted and should go into the benchmark.
---

# Update the benchmark key and the tuning set

Two sets, built from the same forms (those the review page counts as STRUCTURE VALIDATED, in the benchmark's sets):

- **benchmark key** (`runs/benchmark/key`): each form's picked pages, the two fullest. For confirming a finished
  change only, never for tuning.
- **tuning set** (`runs/benchmark/dev_key`): the same forms' other pages with ten or more fields. The type, printed
  and split models are trained on it, so it is the "training" set; the key is held out from it.

**The pick is permanent** (Andrew, 2026-11-04: "the benchmark pages should be stable between builds"; "all that
building the key should do is select pages from new forms and encode them to the appropriate set").
`runs/benchmark/picks.json` records each form's key pages and tuning pages the first time it is built; later builds
reuse that whatever the pages' field counts are now, and whether or not the form still has its S or has been ignored
since. So a rebuild does three things only: picks pages for forms new to the key, re-encodes every picked page from
its current blueprint (fields added or retyped on the review page, printed tags, Split Field tags, ignored fields),
and leaves out pages ignored on the review page (they return when un-ignored; nothing replaces them).

**Build only** (Andrew, 2026-11-04: "just build, no need to rescore"). The skill stops at the rebuilt sets and the
report. Running the light path on the new pages, deriving, scoring and retraining are separate asks; until the
light path is run, the new pages have no prediction and the scorer counts them as empty answers, so say that if
numbers come up.

A rebuild is Andrew's to ask for; once asked, run it without further confirmation. It writes nothing to blueprints.

## 1. Keep the sets as they stand

Copy both indexes and page JSONs (not the PDFs) to the session scratchpad, so step 3 can say what changed and
nothing is lost:

    mkdir -p <scratchpad>/key_before && cp -r runs/benchmark/key runs/benchmark/dev_key <scratchpad>/key_before/ && rm -rf <scratchpad>/key_before/*/pages

## 2. Build both sets

    PYTHONPATH=. venv/bin/python eval/benchmark_key.py --pdfs
    PYTHONPATH=. venv/bin/python eval/benchmark_key.py --spare --pdfs

`--pdfs` rewrites every page's flat PDF (the system's input); each build takes under a minute. Each run ends with
the counts per set, a "left out" line (forms with no S, ignored forms and pages, ignored fields), the number of forms
picked for the first time, and "picked and kept" counts for picked forms that lost their S or were ignored since
(report those to Andrew; the pick stands). The line about "printed candidates not confirmed on the printed sheet"
is a leftover of the retired printed sheet: ignore it. MuPDF's "skipping bad link" warnings are harmless.

## 3. Say what changed

    venv/bin/python .claude/skills/update-key/scripts/key_diff.py --before <scratchpad>/key_before --prune

Per set: forms and pages before and after, the forms that came in, pages out (only ignored pages), pages kept whose
fields changed, and totals of fields, option groups, printed fields and split values. `--prune` removes page JSONs
and PDFs the index no longer lists (the builder does not). Pages never move between the two sets.

## 4. Report to Andrew

Short and plain, no command lines ([[feedback-no-cli-flags]]). S counts first ([[feedback-benchmark-structure-only]]):

1. Forms and pages per set before -> after, in a small table with printed fields and split values.
2. Forms in (count, and which sets they came from); pages ignored since; picked forms that lost their S or were
   ignored (counts, and the ids if a handful, each a link `http://localhost:5005/#review/<id>`).
3. Pages kept whose fields changed, with the field delta, if any.
4. One line: the new pages have no light-path prediction yet.

## 5. Record it

Put the date and the forms / pages per set in the flat-structure-benchmark memory and the RESUME HERE memory, so
the next session knows which build it is working on. Don't commit anything ([[feedback-working-preferences]]).
