#!/bin/sh
# Startup of the `api` container: wait for PostgreSQL, migrate once, then start uvicorn.
set -eu

python -m scripts.wait_for_db --timeout "${DB_WAIT_TIMEOUT:-60}"

# Runs here, in a single process, before uvicorn forks its workers: no race between workers migrating.
alembic upgrade head

# Logs in logfmt with the request id (app/core/logs.py), the same for the uvicorn parent process and every
# worker. /tmp is the container's RAM disk (the image is read-only). --no-access-log: the app writes its own
# access line per request (app/api/request_id.py), with the request id and without the query string.
LOG_CONFIG=/tmp/log_config.json
python -c "import json; from app.core.logs import LOGGING_CONFIG; print(json.dumps(LOGGING_CONFIG))" > "$LOG_CONFIG"

# --proxy-headers: trust X-Forwarded-For/-Proto only from the Nginx network (FORWARDED_ALLOW_IPS, set by
# docker-compose.yml to the subnet of the `proxy` network shared only by `web` and `api`).
exec uvicorn app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers "${API_WORKERS:-2}" \
    --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}" \
    --no-server-header \
    --log-config "$LOG_CONFIG" \
    --no-access-log \
    "$@"
