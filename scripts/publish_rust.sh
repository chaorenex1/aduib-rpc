#!/usr/bin/env bash
set -euo pipefail

# Bash publish helper for crates.io
# Mirrors scripts/publish_rust.ps1 capabilities.

dry_run=0
skip_tests=0
allow_dirty=0
package="aduib-rpc"
version=""
tag=0
tag_prefix="aduib-rpc-v"
# Prefer env var CARGO_REGISTRY_TOKEN; optionally set via --token.
token=""

usage() {
  cat <<'EOF'
Usage: scripts/publish_rust.sh [options]

Options:
  --dry-run           Run cargo publish --dry-run (no upload)
  --skip-tests        Skip cargo test
  --allow-dirty       Allow dirty git working tree
  --package NAME      Package name (default: aduib-rpc)
  --version X.Y.Z     Update crates/<pkg>/Cargo.toml version before publishing
  --tag               Create git tag after publishing (tag points to current HEAD)
  --tag-prefix STR    Tag prefix (default: aduib-rpc-v)
  --token TOKEN       Set CARGO_REGISTRY_TOKEN for this process
  -h, --help          Show help

Notes:
- If you use --version, this edits Cargo.toml but does not commit it.
- If you use --tag with a dirty tree, pass --allow-dirty (tag still points to HEAD).
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) dry_run=1; shift ;;
    --skip-tests) skip_tests=1; shift ;;
    --allow-dirty) allow_dirty=1; shift ;;
    --package) package="$2"; shift 2 ;;
    --version) version="$2"; shift 2 ;;
    --tag) tag=1; shift ;;
    --tag-prefix) tag_prefix="$2"; shift 2 ;;
    --token) token="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
rust_sdk="$repo_root/rust-sdk"
crate_toml="$rust_sdk/crates/$package/Cargo.toml"

if [[ -n "$token" ]]; then
  export CARGO_REGISTRY_TOKEN="$token"
fi

if [[ -z "${CARGO_REGISTRY_TOKEN:-}" ]]; then
  echo "Hint: set CARGO_REGISTRY_TOKEN (crates.io API token) before publishing." >&2
fi

assert_git_clean() {
  if [[ "$allow_dirty" -eq 1 ]]; then
    return 0
  fi
  if ! command -v git >/dev/null 2>&1; then
    echo "Warning: git not found; skipping clean working tree check." >&2
    return 0
  fi
  (cd "$repo_root" && [[ -z "$(git status --porcelain)" ]]) || {
    echo "Working tree is dirty. Commit/stash changes or pass --allow-dirty." >&2
    exit 1
  }
}

set_crate_version() {
  if [[ ! -f "$crate_toml" ]]; then
    echo "Cargo.toml not found: $crate_toml" >&2
    exit 1
  fi

  # Use python for a robust multi-line edit.
  local py="python3"
  if command -v python3 >/dev/null 2>&1; then
    py="python3"
  elif command -v python >/dev/null 2>&1; then
    py="python"
  else
    echo "python3/python not found; cannot bump version." >&2
    exit 1
  fi

  "$py" - <<PY
import re
from pathlib import Path
p = Path(r"$crate_toml")
text = p.read_text(encoding="utf-8")
pattern = re.compile(r"(?ms)(\[package\][^\[]*?\bversion\s*=\s*\")([^"]+)(\")")
new = pattern.sub(r"\g<1>$version\g<3>", text, count=1)
if new == text:
    raise SystemExit(f"Failed to update version in {p} (pattern not found)")
p.write_text(new, encoding="utf-8")
PY
}

new_git_tag() {
  local name="$1"
  if ! command -v git >/dev/null 2>&1; then
    echo "git not found; cannot create tag." >&2
    exit 1
  fi
  (cd "$repo_root" && git tag "$name")
}

cd "$rust_sdk"
echo "Rust SDK dir: $rust_sdk"

if [[ -n "$version" ]]; then
  assert_git_clean
  echo "Bumping crate version to $version in $crate_toml"
  set_crate_version
fi

if [[ "$skip_tests" -eq 0 ]]; then
  echo "Running cargo test..."
  cargo test
fi

# Always do a dry-run verification before actual upload.
echo "Running cargo publish --dry-run verification..."
cargo publish -p "$package" --dry-run >/dev/null

if [[ "$dry_run" -eq 1 ]]; then
  echo "Publishing (dry-run) package: $package"
  cargo publish -p "$package" --dry-run
else
  echo "Publishing package: $package"
  cargo publish -p "$package"
fi

if [[ "$tag" -eq 1 ]]; then
  if [[ -z "$version" ]]; then
    echo "--tag requires --version so the tag name is deterministic." >&2
    exit 1
  fi
  tag_name="${tag_prefix}${version}"
  if [[ "$allow_dirty" -eq 0 ]] && command -v git >/dev/null 2>&1; then
    if [[ -n "$(cd "$repo_root" && git status --porcelain)" ]]; then
      echo "Working tree is dirty; commit version bump before tagging, or pass --allow-dirty." >&2
      exit 1
    fi
  else
    echo "Warning: creating tag on current HEAD; uncommitted changes are not included." >&2
  fi
  echo "Creating git tag: $tag_name"
  new_git_tag "$tag_name"
fi
