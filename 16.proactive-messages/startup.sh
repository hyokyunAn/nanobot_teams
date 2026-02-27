#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

export PYTHONUNBUFFERED=1
: "${PORT:=3978}"
: "${WEB_CONCURRENCY:=1}"
: "${GUNICORN_TIMEOUT:=120}"
: "${GUNICORN_GRACEFUL_TIMEOUT:=30}"
: "${VENV_DIR:=${SCRIPT_DIR}/.venv}"

echo "[startup] working dir: ${SCRIPT_DIR}"
echo "[startup] PORT=${PORT}"
echo "[startup] VENV_DIR=${VENV_DIR}"

if [[ -z "${MicrosoftAppId:-}" ]]; then
  echo "[startup][warn] MicrosoftAppId is not set"
fi
if [[ -z "${MicrosoftAppPassword:-}" ]]; then
  echo "[startup][warn] MicrosoftAppPassword is not set"
fi
if [[ -z "${MicrosoftAppTenantId:-}" ]]; then
  echo "[startup][warn] MicrosoftAppTenantId is not set"
fi
if [[ -z "${NANOBOT_INBOUND_URL:-}" ]]; then
  echo "[startup][warn] NANOBOT_INBOUND_URL is not set (default will be used by app)"
fi

PYTHON_BIN="python3"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[startup] creating virtualenv at ${VENV_DIR}"
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"

echo "[startup] installing dependencies"
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python -m pip install gunicorn

echo "[startup] starting gunicorn"
exec gunicorn app:APP \
  --bind "0.0.0.0:${PORT}" \
  --worker-class aiohttp.GunicornWebWorker \
  --workers "${WEB_CONCURRENCY}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT}" \
  --access-logfile "-" \
  --error-logfile "-"
