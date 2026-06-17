# Railway production image — PC Checker Extreme
# WSGI: pc_checker_extreme.wsgi:application

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN DJANGO_SECRET_KEY=build-placeholder-not-used-at-runtime \
    DJANGO_DEBUG=False \
    python manage.py collectstatic --noinput

EXPOSE 8080

RUN chmod +x scripts/docker-start.sh

CMD ["scripts/docker-start.sh"]
