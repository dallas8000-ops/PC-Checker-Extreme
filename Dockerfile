# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD sh -c "python manage.py migrate accounts 0001_initial --fake 2>/dev/null; python manage.py migrate --noinput && gunicorn pc_checker_extreme.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120"
