#!/usr/bin/env bash
set -e

python -m venv antenv
source antenv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt

exec gunicorn --bind 0.0.0.0:8000 \
              --worker-class aiohttp.worker.GunicornWebWorker \
              --timeout 610 \
              app:APP