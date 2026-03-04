#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_PY="${SCRIPT_DIR}/jira_mcp.py"

if [[ -z "${JIRA_BASE_URL:-}" ]]; then
  echo "JIRA_BASE_URL is required (set via environment variable)" >&2
  exit 1
fi

if [[ -z "${JIRA_BEARER_TOKEN:-}" && -z "${JIRA_PAT:-}" ]]; then
  echo "JIRA_BEARER_TOKEN (or legacy JIRA_PAT) is required" >&2
  exit 1
fi

exec python "${SERVER_PY}"
