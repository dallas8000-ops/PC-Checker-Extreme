#!/bin/sh
set -e

echo "[pc-checker] migrate..."
python manage.py migrate --noinput || echo "[pc-checker] WARN: migrate failed — starting gunicorn anyway"

PORT="${PORT:-8080}"
echo "[pc-checker] gunicorn on 0.0.0.0:${PORT}"
exec gunicorn pc_checker_extreme.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
