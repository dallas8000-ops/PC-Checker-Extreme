#!/bin/sh
set -e

echo "[pc-checker] migrate..."
# Do not swallow migrate failures — a bad DB means the app is broken.
# Let the non-zero exit kill the container so Railway marks the deploy failed.
python manage.py migrate --noinput

PORT="${PORT:-8080}"
echo "[pc-checker] gunicorn on 0.0.0.0:${PORT}"
exec gunicorn pc_checker_extreme.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
