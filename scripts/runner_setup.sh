#!/bin/zsh
# usage: scripts/runner_setup.sh                # create and provision the GCP runner (docs/RUNNER.md)
# Creates the VM if it does not exist, installs the system packages, pushes the code (scripts/runner_sync.sh) and
# builds the venv. It does not place credentials: the last lines print the three commands that copy your AWS
# profile and the two API keys, for you to run yourself.
set -e
cd "$(dirname "$0")/.."
VM=${RUNNER_VM:-petey-runner}; PROJECT=${RUNNER_PROJECT:-petey-dev}; ZONE=${RUNNER_ZONE:-us-central1-a}
if ! gcloud compute instances describe $VM --project $PROJECT --zone $ZONE >/dev/null 2>&1; then
  gcloud compute instances create $VM --project $PROJECT --zone $ZONE --machine-type e2-standard-8 \
    --image-family ubuntu-2404-lts-amd64 --image-project ubuntu-os-cloud --boot-disk-size 50GB --boot-disk-type pd-balanced
fi
# a new VM refuses SSH keys for the first minute or so, until its guest agent has run
for i in $(seq 1 30); do
  gcloud compute ssh $VM --project $PROJECT --zone $ZONE --quiet --command true 2>/dev/null && break
  sleep 10
done
# zsh: the scripts start with #!/bin/zsh and Ubuntu does not ship it
gcloud compute ssh $VM --project $PROJECT --zone $ZONE --quiet --command \
  "sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3.12-venv python3-pip tesseract-ocr rsync tmux zsh >/dev/null"
scripts/runner_sync.sh
# the AWS CLI goes into the venv (Ubuntu 24.04 has no apt package); run_form.sh finds it at venv/bin/aws
gcloud compute ssh $VM --project $PROJECT --zone $ZONE --quiet --command \
  "cd petey-2 && python3 -m venv venv && venv/bin/pip install -q --upgrade pip && venv/bin/pip install -q -r requirements.txt awscli"
cat <<EOF

Runner ready except credentials. Run these yourself (they copy your default AWS profile and the two API keys):

gcloud compute ssh $VM --project $PROJECT --zone $ZONE --command "mkdir -p ~/.aws && chmod 700 ~/.aws"
gcloud compute scp ~/.aws/credentials ~/.aws/config $VM:~/.aws/ --project $PROJECT --zone $ZONE
grep -E "^(ANTHROPIC_API_KEY|GEMINI_API_KEY)=" ~/Documents/code/petey-master/.env | gcloud compute ssh $VM --project $PROJECT --zone $ZONE --command "cat > ~/petey-2/.env && chmod 600 ~/petey-2/.env"
EOF
