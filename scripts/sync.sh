#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/sync.sh [-m "commit message"] [--no-pull]

What it does:
  - (optional) git pull --rebase --autostash
  - git add -A  (respects .gitignore)
  - git commit
  - git push
EOF
}

message=""
no_pull=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--message)
      message="${2:-}"
      shift 2
      ;;
    --no-pull)
      no_pull=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      if [[ -z "$message" ]]; then
        message="$1"
      else
        message="${message} $1"
      fi
      shift
      ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$repo_root" ]]; then
  echo "error: not inside a git repository" >&2
  exit 1
fi
cd "$repo_root"

if [[ -z "$message" ]]; then
  message="sync: $(date -Is)"
fi

if [[ "$no_pull" -eq 0 ]]; then
  if git rev-parse --abbrev-ref --symbolic-full-name '@{u}' >/dev/null 2>&1; then
    git pull --rebase --autostash
  fi
fi

git add -A

if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi

git commit -m "$message"
git push
