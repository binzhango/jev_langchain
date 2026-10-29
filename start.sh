#!/usr/bin/env bash
# One command for macOS, Linux, and WSL: bash start.sh
set -Eeuo pipefail
trap 'printf "\nStartup failed. Check the error above, then run bash start.sh again.\n" >&2' ERR

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

for program in uv node npm; do
  if ! command -v "$program" >/dev/null 2>&1; then
    printf 'Missing %s. Install uv from https://docs.astral.sh/uv/getting-started/installation/ and Node.js (with npm) from https://nodejs.org/ then run bash start.sh again.\n' "$program" >&2
    exit 1
  fi
done

node -e 'const [major, minor] = process.versions.node.split(".").map(Number);
if (!((major === 20 && minor >= 19) || (major === 22 && minor >= 12) || major > 22)) {
  console.error("Please install Node.js 20.19+, 22.12+, or a newer release, then run bash start.sh again."); process.exit(1);
}'

export UV_CACHE_DIR="${UV_CACHE_DIR:-$PROJECT_DIR/.cache/uv}"
printf '\n[1/3] Setting up Python with uv…\n'
uv sync --frozen
printf '\n[2/3] Installing and building the dashboard…\n'
npm --prefix dashboard ci --no-audit --no-fund --cache "$PROJECT_DIR/.cache/npm"
npm --prefix dashboard run build
printf '\n[3/3] Starting Jev Decision Lab…\n'
# exec keeps Ctrl+C and the exit status attached to the single server process.
exec uv run --no-sync python -m jev_harness.launch "$@"
