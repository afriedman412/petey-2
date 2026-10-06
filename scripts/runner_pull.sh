#!/bin/zsh
# usage: scripts/runner_pull.sh                 # bring the GCP runner's results to this machine (docs/RUNNER.md)
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
rsync -az -e "$SSH" --exclude judge_eval/old_library_progress.log --exclude judge_eval/work/ \
      $REMOTE:petey-2/runs/ runs/
rsync -az -e "$SSH" $REMOTE:petey-2/runs/judge_eval/old_library_progress.log runs/judge_eval/runner_progress.log
echo "pulled from $REMOTE: $(grep -c 'done (exit 0)' runs/judge_eval/runner_progress.log) forms done on the runner"
