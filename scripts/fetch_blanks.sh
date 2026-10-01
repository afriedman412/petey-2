#!/bin/zsh
# The blank forms live in S3, not in git (2026-10-01): s3://petey-source-pdfs-2026/source_pdfs/ mirrors the
# repo's source_pdfs/ tree (same relative paths, so every blueprint's `source_pdf` and every list under
# runs/judge_eval/*.txt resolves unchanged). Private bucket, versioned; needs AWS credentials (aws configure).
#
#   scripts/fetch_blanks.sh                          # everything (about 290 MB)
#   scripts/fetch_blanks.sh runs/judge_eval/forms44.txt [more lists]   # only the blanks a form list names
#   scripts/push_blanks.sh                           # the other direction, after adding blanks locally
set -e
cd "$(dirname "$0")/.."
BUCKET=${PETEY_BLANKS_BUCKET:-petey-source-pdfs-2026}
if [ $# -eq 0 ]; then
  aws s3 sync "s3://$BUCKET/source_pdfs" source_pdfs --exclude ".DS_Store"
  exit
fi
for list in "$@"; do
  while IFS='|' read -r form rel; do
    [ -z "$rel" ] && continue
    dest="source_pdfs/$rel"
    [ -f "$dest" ] && continue
    mkdir -p "$(dirname "$dest")"
    aws s3 cp "s3://$BUCKET/source_pdfs/$rel" "$dest"
  done < "$list"
done
