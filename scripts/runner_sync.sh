#!/bin/zsh
# usage: scripts/runner_sync.sh                 # push this working tree to the GCP runner (docs/RUNNER.md)
# Copies the code, not the data: no venv, .git, source_pdfs (fetched per form from S3), runs (the runner's own),
# acquisition, .env (the runner's keys are placed by hand). Writes CODE_VERSION.json there: the commit, the
# uncommitted paths and a hash of `git diff HEAD`, which provenance.code_version() reads into every run record,
# since the runner has no .git. Safe while runs are going: running processes keep the code they loaded, the next
# form loads the new code.
set -e
cd "$(dirname "$0")/.."
VM=${RUNNER_VM:-petey-runner}; PROJECT=${RUNNER_PROJECT:-petey-dev}; ZONE=${RUNNER_ZONE:-us-central1-a}
IP=$(gcloud compute instances describe $VM --project $PROJECT --zone $ZONE \
     --format='value(networkInterfaces[0].accessConfigs[0].natIP)')
SSH="ssh -i $HOME/.ssh/google_compute_engine -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR"
REMOTE=${RUNNER_USER:-$USER}@$IP
rsync -az -e "$SSH" --exclude venv --exclude .git --exclude source_pdfs --exclude source_pdfs_old --exclude runs \
      --exclude acquisition --exclude __pycache__ --exclude .env --exclude CODE_VERSION.json ./ $REMOTE:petey-2/
venv/bin/python - <<'EOF' | ${=SSH} $REMOTE "cat > petey-2/CODE_VERSION.json"
import json, time
from petey.validate.provenance import code_version
v = code_version()
v.pop("source", None)
print(json.dumps({**v, "synced": time.strftime("%Y-%m-%d %H:%M:%S %Z")}, indent=1))
EOF
echo "synced to $REMOTE:petey-2 ($(git rev-parse --short HEAD), $(git status --porcelain | wc -l | tr -d ' ') uncommitted paths)"
