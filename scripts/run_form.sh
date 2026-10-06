#!/bin/zsh
# usage: scripts/run_form.sh <form> <blank path under source_pdfs/> [--reloop] [--page-check-model gemini-3.8-flash]
# Extra arguments go to petey.validate.form_run; PAGE_CHECK_MODEL in the environment sets the page-check model.
# One form through petey.validate.form_run (label, full page check, validate, loop with per-round spot checks,
# .bpt when the loop stops, library comparison check). Log runs/judge_eval/<form>.log; progress in
# runs/judge_eval/old_library_progress.log. Run a set:  tr '|' ' ' < list.txt | xargs -P 5 -L 1 scripts/run_form.sh
form=$1; rel=$2; shift 2
cd "$(dirname "$0")/.."
export PYTHONPATH=.
prog=runs/judge_eval/old_library_progress.log
echo "$form start $(date)" >> $prog
[ -n "$PAGE_CHECK_MODEL" ] && set -- "$@" --page-check-model "$PAGE_CHECK_MODEL"
nice venv/bin/python -u -m petey.validate.form_run --form $form --blank "source_pdfs/$rel" "$@" > runs/judge_eval/${form}.log 2>&1
echo "$form done (exit $?) $(date)" >> $prog
