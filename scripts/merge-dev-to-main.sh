#!/usr/bin/env bash
# Merge origin/dev into main without pushing.

set -Eeuo pipefail

MAIN_BRANCH="main"
DEV_BRANCH="dev"
REMOTE="origin"
merge_started=0

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

abort_on_error() {
  local status=$?

  if [ "$status" -ne 0 ] && [ "$merge_started" -eq 1 ] && \
    git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
    echo "Merge failed; aborting the merge started by this script." >&2
    git merge --abort || true
  fi

  exit "$status"
}

trap abort_on_error EXIT

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR/.." rev-parse --show-toplevel)"
cd "$REPO_ROOT"

current_branch="$(git branch --show-current)"
[ "$current_branch" = "$MAIN_BRANCH" ] || \
  fail "Current branch is '$current_branch'; switch to '$MAIN_BRANCH' first."

merge_active=0
if git rev-parse -q --verify MERGE_HEAD >/dev/null 2>&1; then
  merge_active=1
else
  [ -z "$(git status --porcelain)" ] || \
    fail "The worktree has uncommitted changes; commit or stash them first."
fi

echo "Fetching $REMOTE/$MAIN_BRANCH and $REMOTE/$DEV_BRANCH ..."
git fetch "$REMOTE" "$MAIN_BRANCH" "$DEV_BRANCH"

if [ "$merge_active" -eq 1 ]; then
  merge_head="$(git rev-parse MERGE_HEAD)"
  expected_merge=0

  for ref in "refs/remotes/$REMOTE/$DEV_BRANCH" "refs/heads/$DEV_BRANCH"; do
    if git show-ref --verify --quiet "$ref" && \
      [ "$(git rev-parse "$ref")" = "$merge_head" ]; then
      expected_merge=1
      break
    fi
  done

  [ "$expected_merge" -eq 1 ] || \
    fail "An unrelated merge is active. Finish or abort it before using this script."

  echo "Resuming the active $DEV_BRANCH -> $MAIN_BRANCH merge ..."
else
  if git merge-base --is-ancestor "$REMOTE/$MAIN_BRANCH" HEAD; then
    : # Local main is current or ahead of origin/main.
  elif git merge-base --is-ancestor HEAD "$REMOTE/$MAIN_BRANCH"; then
    echo "Fast-forwarding local $MAIN_BRANCH to $REMOTE/$MAIN_BRANCH ..."
    git merge --ff-only "$REMOTE/$MAIN_BRANCH"
  else
    fail "Local and remote $MAIN_BRANCH have diverged; reconcile them manually."
  fi

  if git merge-base --is-ancestor "$REMOTE/$DEV_BRANCH" HEAD; then
    echo "$MAIN_BRANCH already contains $REMOTE/$DEV_BRANCH. Nothing to merge."
    exit 0
  fi

  echo "Merging $REMOTE/$DEV_BRANCH into $MAIN_BRANCH ..."
  merge_started=1
  set +e
  git merge --no-commit --no-ff "$REMOTE/$DEV_BRANCH"
  merge_status=$?
  set -e

  if [ "$merge_status" -ne 0 ] && \
    [ -z "$(git diff --name-only --diff-filter=U)" ]; then
    fail "Git merge failed without producing resolvable conflicts."
  fi
fi

mapfile -t conflicts < <(git diff --name-only --diff-filter=U)
unsupported_conflicts=()

for path in "${conflicts[@]}"; do
  case "$path" in
    .gitignore)
      echo "Resolving .gitignore with the $DEV_BRANCH version ..."
      git checkout --theirs -- "$path"
      git add -- "$path"
      ;;
    *)
      unsupported_conflicts+=("$path")
      ;;
  esac
done

if [ "${#unsupported_conflicts[@]}" -gt 0 ]; then
  printf 'Unsupported merge conflicts:\n' >&2
  printf '  %s\n' "${unsupported_conflicts[@]}" >&2
  fail "Resolve these conflicts manually, then rerun the script."
fi

[ -z "$(git diff --name-only --diff-filter=U)" ] || \
  fail "Unresolved merge conflicts remain."

merge_head="$(git rev-parse MERGE_HEAD)"
dev_sha="$(git rev-parse --short "$merge_head")"
git commit -m "merge: $DEV_BRANCH ($dev_sha) into $MAIN_BRANCH"
merge_started=0

echo "Merge complete. Review the result, then run: git push $REMOTE $MAIN_BRANCH"
