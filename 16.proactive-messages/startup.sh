#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}"

# Load .env values for App Service/local runs.
ENV_FILE="${NANOBOT_ENV_FILE:-.env}"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

PYTHON_BIN="python3"
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

: "${PORT:=3978}"
: "${WEB_CONCURRENCY:=1}"
: "${GUNICORN_TIMEOUT:=610}"
: "${VENV_DIR:=${SCRIPT_DIR}/antenv}"
: "${GUNICORN_BIND:=:${PORT}}"

if [[ ! -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate"

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

exec gunicorn \
  --bind "${GUNICORN_BIND}" \
  --worker-class aiohttp.worker.GunicornWebWorker \
  --workers "${WEB_CONCURRENCY}" \
  --timeout "${GUNICORN_TIMEOUT}" \
  app:APP
