#!/usr/bin/env bash
set -euo pipefail

expected_root="$(pwd)"
git_root="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "ERROR: current directory is not inside a Git repository." >&2
  exit 1
}

if [[ "$git_root" != "$expected_root" ]]; then
  echo "ERROR: current directory is not the Git repository root." >&2
  echo "Current directory: $expected_root" >&2
  echo "Git root: $git_root" >&2
  exit 1
fi

if [[ ! -x ./.venv/bin/python ]]; then
  echo "ERROR: ./.venv/bin/python does not exist or is not executable." >&2
  exit 1
fi

python_version="$(./.venv/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')"
case "$python_version" in
  3.11.*) ;;
  *)
    echo "ERROR: .venv Python version must be 3.11.x, got $python_version." >&2
    exit 1
    ;;
esac

./.venv/bin/python -m pip --version >/dev/null

echo "Git branch:"
git branch --show-current

echo "Git status:"
git status --short

echo "Preflight checks passed."
