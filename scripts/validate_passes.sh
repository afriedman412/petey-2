#!/bin/zsh
# usage: scripts/validate_passes.sh <review id> ...   (je__boat_application lib__fw9 ...)
# The passes after generation (2026-10-15), on each form's review-page working copy, in order:
#   1. mechanical pass   person_name / pattern fixes, Yes / No pairs, row groups; checks (eval/mechanical_pass.py)
#   2. naming standard   renames recorded as Claude's corrections (eval/standardize_names.py --apply)
#   3. re-read captions  every group's option captions read again from the page (eval/reread_captions.py)
#   4. page check        Opus 5 on the working copy, stamped (eval/page_check_working.py)
#   5. Jev               name_fits / one_question with the page image (eval/jev_forms.py)
# Reports: runs/mechanical/passes_<date>.json, runs/standardized/applied_<date>.json,
# runs/group_review/reread_captions_<date>.json, runs/jev/passes_<date>.json. Then add the forms to the picker's top
# section (runs/hand_review/focus.json).
cd "$(dirname "$0")/.."
export PYTHONPATH=.
d=$(date +%Y-%m-%d)
py=venv/bin/python
$py eval/mechanical_pass.py "$@" --save runs/mechanical/passes_$d.json
$py eval/standardize_names.py --apply "$@"
$py eval/reread_captions.py "$@" --save runs/group_review/reread_captions_$d.json
$py eval/page_check_working.py "$@"
$py eval/jev_forms.py "$@" --save runs/jev/passes_$d.json
