#!/bin/zsh
# usage: scripts/rerun_library.sh <form> <blank path under source_pdfs/>
# One old library form through the current code, as a side copy (Andrew, 2026-10-06): the library file is never
# written. Same pipeline as the judge-eval batches (runs/judge_eval/worker_c.sh) with the page check added:
#   label        fresh, current labeler, no registry or retrieval   -> runs/judge_eval/blueprints/<form>.bpt
#   page check   on the fresh label, stamped, so the loop's reviewer gets its wrong_name / wrong_type flags
#   validate     bank case set 1, native + judge
#   loop         iterate --review flagged --apply-correct (reviewer, adjudicator); pre-loop copy kept as <form>_v0.bpt
#   page check   on the post-loop blueprint, stamped
#   page check   on the old library blueprint, record only (--no-stamp): the comparison
# Logs: runs/judge_eval/<form>.log (label, validate, page checks), <form>_loop.log; progress in old_library_progress.log
form=$1; rel=$2
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
bdir=runs/judge_eval/blueprints; blank="source_pdfs/$rel"; log=runs/judge_eval/${form}.log
prog=runs/judge_eval/old_library_progress.log
echo "$form start $(date)" >> $prog
echo "== $form $(date)" > $log
nice venv/bin/python -u -m petey.label.auto_label --blank "$blank" --output $bdir/${form}.bpt \
    --name $form --no-register --no-retrieval >> $log 2>&1
echo "label exit $?" >> $log
[ -f $bdir/${form}.bpt ] || { echo "$form no blueprint; skipped $(date)" >> $prog; exit 1; }
venv/bin/python -u -m petey.validate.page_check $bdir/${form}.bpt >> $log 2>&1
echo "page check (label) exit $?" >> $log
nice venv/bin/python -u -m petey.validate.validate --blank "$blank" --form-id $form --bpt $bdir/${form}.bpt \
    --gen-model bank --case-set 1 --n-flat 0 --methods native,judge:pymupdf >> $log 2>&1
echo "validate exit $?" >> $log
cp $bdir/${form}.bpt $bdir/${form}_v0.bpt
llog=runs/judge_eval/${form}_loop.log
echo "== $form loop $(date)" > $llog
nice venv/bin/python -u -m petey.validate.iterate --form $form --blank "$blank" --bpt $bdir/${form}.bpt \
    --gen-model bank --case-set 1 --methods native,judge:pymupdf --n-flat 0 --review flagged --apply-correct \
    --allow-dirty --out runs/judge_eval/${form}_loop.json >> $llog 2>&1
echo "loop exit $?" >> $llog
venv/bin/python -u -m petey.validate.page_check $bdir/${form}.bpt >> $log 2>&1
echo "page check (after loop) exit $?" >> $log
venv/bin/python -u -m petey.validate.page_check blueprints/${form}.bpt --no-stamp >> $log 2>&1
echo "page check (library) exit $?" >> $log
echo "$form done $(date)" >> $prog
