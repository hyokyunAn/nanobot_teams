#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="${SCRIPT_DIR}/atlassian_confluence_mcp.py"

if [[ -z "${CONFLUENCE_BASE_URL:-}" ]]; then
  echo "CONFLUENCE_BASE_URL is required (example: https://<site>.atlassian.net/wiki)" >&2
  exit 1
fi

if [[ -z "${CONFLUENCE_PAT:-}" ]]; then
  echo "CONFLUENCE_PAT is required" >&2
  exit 1
fi

exec python "${SERVER_PY}"
