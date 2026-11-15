#!/bin/sh
# Exit 0 when extract / model / data-service code changed between two commits.
# Exit 1 when a site-only (or unrelated) change can skip refine/personnel/check.
#
# Run from the git checkout (Jenkins workspace). 
# Usage: scripts/data-code-changed.sh [base] [head]
# Default: HEAD~1 .. HEAD. With only one commit of history, exits 0 (refresh).
set -eu

if ! git rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "data-code-changed: not a git checkout; refresh" >&2
  exit 0
fi

head_ref=${2:-HEAD}
if [ "${1-}" != "" ]; then
  base_ref=$1
elif git rev-parse --verify -q HEAD~1 >/dev/null; then
  base_ref=HEAD~1
else
  echo "data-code-changed: no parent commit; refresh"
  exit 0
fi

changed=$(git diff --name-only "$base_ref" "$head_ref" || true)
if [ -z "$changed" ]; then
  echo "data-code-changed: no file diff; skip refresh"
  exit 1
fi

# Data-service / model paths. Site modules under pa_edu/ are excluded below.
matched=$(
  printf '%s\n' "$changed" | grep -E '^(Dockerfile\.data|pyproject\.toml|sources/|sql/|pa_edu/)' \
    | grep -Ev '^pa_edu/(web/|publish\.py|portal\.py|export_site\.py|app\.py|load\.py|tuition\.py|budget\.py|enrollment\.py)' \
    || true
)

if [ -n "$matched" ]; then
  echo "data-code-changed: refresh needed"
  printf '%s\n' "$matched"
  exit 0
fi

echo "data-code-changed: site-only (or unrelated); skip refresh"
printf '%s\n' "$changed"
exit 1
