#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="${SCRIPT_DIR}/ds_qa_agent_mcp.py"

if [[ -z "${CONFLUENCE_BASE_URL:-}" ]]; then
  echo "CONFLUENCE_BASE_URL is required (set via environment variable)" >&2
  exit 1
fi

if [[ -z "${CONFLUENCE_BEARER_TOKEN:-}" && -z "${CONFLUENCE_PAT:-}" ]]; then
  echo "CONFLUENCE_BEARER_TOKEN (or legacy CONFLUENCE_PAT) is required" >&2
  exit 1
fi

exec python "${SERVER_PY}"
