#!/bin/zsh
# usage: scripts/runner_pull.sh [--lean]        # bring the GCP runner's results to this machine (docs/RUNNER.md)
# --lean leaves the loop's per-round run directories (runs/<form>_<date>_<time>/: filled PDFs and readouts, ~95% of
# the bytes; 1.7 of 1.8 GB after T1 + T2) on the runner; blueprints, run records, logs, caches and case sets come.
# Without them the review page's witness tiers lack the judge witness for those forms.
# Everything the runner writes is under runs/ (gitignored) and exists only on that VM until pulled. This merges the
# runner's runs/ into the local one without deleting anything local: blueprints, run records (form_runs/), logs,
# the loop's run directories, case sets and the page-check and classifier caches. Two exceptions, so local files are
# not overwritten: the runner's progress log lands as runs/judge_eval/runner_progress.log, and the scratch copies
# under runs/judge_eval/work/ are left on the runner.
set -e
cd "$(dirname "$0")/.."
VM=${RUNNER_VM:-petey-runner}; PROJECT=${RUNNER_PROJECT:-petey-dev}; ZONE=${RUNNER_ZONE:-us-central1-a}
IP=$(gcloud compute instances describe $VM --project $PROJECT --zone $ZONE \
     --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
SSH="ssh -i $HOME/.ssh/google_compute_engine -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
REMOTE=${RUNNER_USER:-$USER}@$IP
LEAN=(); [ "$1" = "--lean" ] && LEAN=(--exclude '/*_20[0-9][0-9][0-9][0-9][0-9][0-9]_[0-9][0-9][0-9][0-9][0-9][0-9]/')
rsync -az -e "$SSH" --exclude judge_eval/old_library_progress.log --exclude judge_eval/work/ "${LEAN[@]}" \
      $REMOTE:petey-2/runs/ runs/
rsync -az -e "$SSH" $REMOTE:petey-2/runs/judge_eval/old_library_progress.log runs/judge_eval/runner_progress.log
echo "pulled from $REMOTE: $(grep -c 'done (exit 0)' runs/judge_eval/runner_progress.log) forms done on the runner"
