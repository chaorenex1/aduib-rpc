#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Prefer workspace venv if present.
if [[ -x "$repo_root/.venv/bin/python" ]]; then
  py="$repo_root/.venv/bin/python"
else
  py="python3"
fi

exec "$py" "$repo_root/scripts/compile_protos.py" "$@"
