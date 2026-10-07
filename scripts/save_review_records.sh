#!/bin/zsh
# usage: scripts/save_review_records.sh ["message"]
# Commit the person's review records (hand review verdicts, group review, field add / remove) to the data-only
# branch `review-records` and push it (Andrew, 2026-10-07: keep them in git, on a branch). runs/ is gitignored and
# was the only copy. Built with a temporary index, so this working tree, its branch and its staged changes are not
# touched (another session works in the same folder): the commit's tree is exactly runs/hand_review,
# runs/group_review and runs/field_add as they are on disk now, its parent the branch's previous commit.
#   git log review-records                 # history of the records
#   git show review-records:runs/hand_review/lib__acord25.json
set -e
cd "$(dirname "$0")/.."
BRANCH=review-records
IDX=$(mktemp -t review-index)
trap 'rm -f "$IDX"' EXIT
rm -f "$IDX"
GIT_INDEX_FILE=$IDX git read-tree --empty
GIT_INDEX_FILE=$IDX git add -f runs/hand_review runs/group_review runs/field_add
TREE=$(GIT_INDEX_FILE=$IDX git write-tree)
PARENT=$(git rev-parse -q --verify refs/heads/$BRANCH || true)
if [ -n "$PARENT" ] && [ "$(git rev-parse "$PARENT^{tree}")" = "$TREE" ]; then
  echo "$BRANCH: no change since $(git rev-parse --short $PARENT)"
  exit 0
fi
MSG=${1:-"Review records $(date '+%Y-%m-%d %H:%M')"}
COMMIT=$(git commit-tree $TREE ${PARENT:+-p $PARENT} -m "$MSG")
git update-ref refs/heads/$BRANCH $COMMIT ${PARENT:-}
git push -q origin $BRANCH
echo "$BRANCH -> $(git rev-parse --short $COMMIT) ($(git ls-tree -r --name-only $COMMIT | wc -l | tr -d ' ') files), pushed"
