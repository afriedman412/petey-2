#!/bin/zsh
# Mirror the local source_pdfs/ tree into the blanks bucket (see fetch_blanks.sh). Sync never deletes: a blank
# removed locally stays in the bucket, and the bucket is versioned, so an overwrite keeps the previous object.
# _inbox/ is a local drop folder (unsorted downloads), never pushed. Manifests live in registry/sources/, not here.
set -e
cd "$(dirname "$0")/.."
BUCKET=${PETEY_BLANKS_BUCKET:-petey-source-pdfs-2026}
aws s3 sync source_pdfs "s3://$BUCKET/source_pdfs" --exclude ".DS_Store" --exclude "*/.DS_Store" --exclude "_inbox/*" --exclude "*/_manifest.json"
