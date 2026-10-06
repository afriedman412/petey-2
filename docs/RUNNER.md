# The GCP runner

Long batches (the launch tiers: T1 89 forms, T2 201) run on a GCP VM so they do not depend on a laptop staying
awake. Set up 2026-10-06. The runner runs the same pipeline as a local run (`scripts/run_form.sh` ->
`petey.validate.form_run`); only where it runs changes.

## The machine

| | |
|---|---|
| name | `petey-runner` (override with `RUNNER_VM`) |
| project / zone | `petey-dev` / `us-central1-a` (`RUNNER_PROJECT`, `RUNNER_ZONE`); not the gcloud default project |
| type | e2-standard-8 (8 vCPU, 32 GB), Ubuntu 24.04, 50 GB pd-balanced; about $0.27 an hour |
| packages | `python3.12-venv`, `tesseract-ocr` (the finder), `rsync`, `tmux`, `zsh` (the scripts start with `#!/bin/zsh`; Ubuntu does not ship it) |
| repo | `~/petey-2`, a copy of a working tree (no `.git`), venv at `~/petey-2/venv`, AWS CLI inside the venv |

The work is API-bound, not CPU-bound: 8 forms in parallel, each running its three validate cases in parallel
processes, keeps the load near 1-2. Raise the `-P` count before the machine size.

## Setting it up

    scripts/runner_setup.sh       # create the VM if missing, install packages, push the code, build the venv

Then place the credentials yourself (Claude Code will not copy secrets to a remote machine); the setup script
prints these three commands:

    gcloud compute ssh petey-runner --project petey-dev --zone us-central1-a --command "mkdir -p ~/.aws && chmod 700 ~/.aws"
    gcloud compute scp ~/.aws/credentials ~/.aws/config petey-runner:~/.aws/ --project petey-dev --zone us-central1-a
    grep -E "^(ANTHROPIC_API_KEY|GEMINI_API_KEY)=" ~/Documents/code/petey-master/.env | gcloud compute ssh petey-runner --project petey-dev --zone us-central1-a --command "cat > ~/petey-2/.env && chmod 600 ~/petey-2/.env"

- AWS (default profile): read access to `s3://petey-source-pdfs-2026`, where the blank PDFs live.
- `.env` with `ANTHROPIC_API_KEY` and `GEMINI_API_KEY` only; `petey.synth.generate._load_keys` reads it.

Gotcha: right after `instances create`, SSH is refused (publickey) for up to a minute while the guest agent
installs the key; the setup script waits for it.

Gotcha, open: **the runner's Tesseract is not the laptop's.** Ubuntu 24.04 ships 5.3.4, the laptop (Homebrew) has
5.5.3, and the finder's version includes the exact Tesseract version (OCR output can move boxes), so the runner's
finder is `step2flat-3+env6af728` and its case sets are keyed under that basis. Harmless for forms only the runner
runs (T1 / T2 on 2026-10-06 all used 5.3.4); a case set pulled to the laptop loads there only if the laptop's finder
finds the same boxes (`validate._check_set` migrates it then), else needs `--rebuild-set`. The PPA
`ppa:alex-p/tesseract-ocr5` offers 5.5.1, which would still not match. To decide later: build 5.5.3 on the runner,
or have the finder's version ignore patch-level Tesseract differences (a finder-versioning change, library-wide). Until then
the runner's Tesseract packages are pinned (`sudo apt-mark hold tesseract-ocr tesseract-ocr-eng tesseract-ocr-osd
libtesseract5`) so no automatic update swaps the OCR engine mid-batch (Andrew: a different version is better than
runs that stop). `apt-mark unhold` the same list to change it on purpose.

## Running

- **Code:** `scripts/runner_sync.sh` pushes the local working tree (code only) and writes `CODE_VERSION.json` on the
  runner: the commit, the uncommitted paths and a hash of `git diff HEAD`. Every run record carries it (`code`), so a
  result can be traced to the exact code even though the runner has no `.git`. Uncommitted edits travel with the
  sync, including another session's; the record lists them. Sync while runs are going is safe: running forms keep
  the code they loaded, the next form loads the new code.
- **Blanks:** not copied. `scripts/run_form.sh` fetches each form's blank from S3 just before running it, if it
  is not on disk (`source_pdfs/<rel>`, the bucket mirrors that tree).
- **Queues:** in tmux sessions, so they survive disconnects. The 2026-10-06 setup:

      tmux new -d -s t1 'tr "|" " " < runs/judge_eval/launch_t1_remaining.txt | xargs -P 8 -L 1 scripts/run_form.sh'
      # t2 waits for "T1 finished" in the progress log, then runs runs/judge_eval/launch_t2.txt the same way;
      # "T1 finished" is written when t1's queue ends, whatever the forms' exit codes, so failed forms do not stop T2

- **Progress:** `runs/judge_eval/old_library_progress.log` on the runner, one `start` / `done (exit N)` line per form:

      gcloud compute ssh petey-runner --project petey-dev --zone us-central1-a --command "cat ~/petey-2/runs/judge_eval/old_library_progress.log"

## Results

Everything a run writes is under `runs/` (gitignored), so until it is pulled it exists only on the VM.

    scripts/runner_pull.sh        # merge the runner's runs/ into the local one (never deletes local files)

The runner's progress log arrives as `runs/judge_eval/runner_progress.log`, so the local one is not overwritten;
scratch copies (`runs/judge_eval/work/`) stay on the runner. Pull before deleting the VM.

Each form's run record (`runs/judge_eval/form_runs/<form>.json`) carries `code` (above) and `config`: every model
and setting the run depended on (labeler, page check round-0 and loop models, prompt version, strips, reasoning
effort, classifier, case basis, reader, reviewer, adjudicator, loop limits). Runs made before 2026-10-06 evening
have neither: the old-library sets 1-5 and the first 13 T1 forms (run locally) differ from the runner's T1 / T2 in
pipeline as well as place.

## The review app on the runner

`blueprint_review` binds 127.0.0.1 only, so it is not exposed; reach it through an SSH tunnel:

    gcloud compute ssh petey-runner --project petey-dev --zone us-central1-a -- -N -L 5015:localhost:5005

and open http://localhost:5015 (5015 so it does not clash with a local server on 5005). Not set up yet: reviewing
there needs the review records (`runs/hand_review`, `runs/group_review`, `runs/field_add`) moved to the runner and
the library blanks fetched; two machines writing verdicts would diverge, so pick one home for the records.

## Tearing down

The VM holds the AWS profile and both API keys. When the batches are done: `scripts/runner_pull.sh`, then

    gcloud compute instances delete petey-runner --project petey-dev --zone us-central1-a
