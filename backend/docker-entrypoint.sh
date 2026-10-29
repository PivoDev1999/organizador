#!/bin/sh
# Startup of the `api` container: wait for PostgreSQL, migrate once, then start uvicorn.
set -eu

python -m scripts.wait_for_db --timeout "${DB_WAIT_TIMEOUT:-60}"

# Runs here, in a single process, before uvicorn forks its workers: no race between workers migrating.
alembic upgrade head

# --proxy-headers: trust X-Forwarded-For/-Proto only from the Nginx network (FORWARDED_ALLOW_IPS, set by
# docker-compose.yml to the subnet of the `proxy` network shared only by `web` and `api`).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${API_WORKERS:-2}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --no-server-header \
    "$@"
