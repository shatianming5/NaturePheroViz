#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "error: not inside a git repository" >&2
  exit 1
fi
cd "$repo_root"

git config core.hooksPath .githooks
echo "Enabled hooks: core.hooksPath=$(git config core.hooksPath)"
