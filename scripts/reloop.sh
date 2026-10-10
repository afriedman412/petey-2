#!/bin/zsh
# usage: scripts/reloop.sh <form> <blank path under source_pdfs/>
# Re-run only the loop of a form scripts/rerun_library.sh already took through label and validate: restore the
# pre-loop copy (<form>_v0.bpt), loop, page check the result. The previous post-loop blueprint is kept as
# <form>_prev.bpt and its loop log / summary as <form>_loop_prev.*. Used when the loop changes (2026-10-06: review
# rounds until every flagged field is reviewed as it stands).
form=$1; rel=$2
cd /Users/user/Documents/code/petey-2
export PYTHONPATH=.
bdir=runs/judge_eval/blueprints; blank="source_pdfs/$rel"; e=runs/judge_eval
prog=$e/old_library_progress.log
[ -f $bdir/${form}_v0.bpt ] || { echo "$form reloop: no _v0; skipped $(date)" >> $prog; exit 1; }
cp $bdir/${form}.bpt $bdir/${form}_prev.bpt
[ -f $e/${form}_loop.json ] && cp $e/${form}_loop.json $e/${form}_loop_prev.json
[ -f $e/${form}_loop.log ] && cp $e/${form}_loop.log $e/${form}_loop_prev.log
cp $bdir/${form}_v0.bpt $bdir/${form}.bpt
echo "$form reloop start $(date)" >> $prog
echo "== $form loop $(date)" > $e/${form}_loop.log
nice venv/bin/python -u -m petey.validate.iterate --form $form --blank "$blank" --bpt $bdir/${form}.bpt \
    --gen-model bank --case-set 1 --methods native,judge:pymupdf --n-flat 0 --review flagged --apply-correct \
    --allow-dirty --out $e/${form}_loop.json >> $e/${form}_loop.log 2>&1
echo "loop exit $?" >> $e/${form}_loop.log
venv/bin/python -u -m petey.validate.page_check $bdir/${form}.bpt >> $e/${form}.log 2>&1
echo "page check (after reloop) exit $?" >> $e/${form}.log
echo "$form reloop done $(date)" >> $prog
