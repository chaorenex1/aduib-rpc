#!/usr/bin/env bash
set -euo pipefail

python_only=0
rust_only=0

for arg in "$@"; do
  case "$arg" in
    --python-only) python_only=1 ;;
    --rust-only) rust_only=1 ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/interop.sh [--python-only] [--rust-only]

Runs Python tests and Rust tests for interop (Rust tests will spawn Python test servers).
- Prefers .venv/bin/python if present and exports ADUIB_RPC_PYTHON.
EOF
      exit 0
      ;;
    *)
      echo "Unknown arg: $arg" >&2
      exit 2
      ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
venv_python="$repo_root/.venv/bin/python"

if [[ -x "$venv_python" ]]; then
  export ADUIB_RPC_PYTHON="$venv_python"
  python_bin="$venv_python"
  echo "Using Python: $ADUIB_RPC_PYTHON"
else
  python_bin="python3"
  echo "Warning: .venv not found; falling back to $python_bin"
fi

if [[ "$rust_only" -eq 0 ]]; then
  (cd "$repo_root" && "$python_bin" -m pytest -q)
fi

if [[ "$python_only" -eq 0 ]]; then
  (cd "$repo_root/rust-sdk" && cargo test -q)
fi
