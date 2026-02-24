#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="${SCRIPT_DIR}/youtube_summary_mcp.py"

exec python "${SERVER_PY}"
