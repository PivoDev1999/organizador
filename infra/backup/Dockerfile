# syntax=docker/dockerfile:1
# Organizador backup: pg_dump/pg_restore 16 + Python (boto3) + supercronic. Used by the `backup` service of
# docker-compose.yml: every day at 03:00 (TZ = APP_TIMEZONE) it dumps PostgreSQL, copies the files bucket
# of Garage to ./backups and applies the GFS retention (see backuptool/ and the "Backups" section of the
# README).
#
# Base: the same postgres:16.10-alpine of the `postgres` service (Alpine 3.22), pinned by tag and digest,
# so pg_dump/pg_restore are exactly the server's major (a newer pg_dump writes dumps that 16 cannot
# restore). Written in the FROM (not in an ARG) so Dependabot can update it.
# Python is Alpine's python3 3.12 (same minor as the backend); boto3 and its dependencies are pinned in
# requirements.txt to the backend's versions.
FROM postgres:16.10-alpine@sha256:029660641a0cfc575b14f336ba448fb8a75fd595d42e1fa316b9fb4378742297

ARG TARGETARCH
# Project rule: only releases at least two weeks old (P14D = uploaded at least 14 days before the build).
ARG PIP_UPLOADED_PRIOR_TO=P14D
# supercronic v0.2.49 (2026-08-14): cron for containers. Runs as any uid, logs to stdout and never starts
# a job while the previous one is still running. Verified by the SHA-256 published in the GitHub release.
ARG SUPERCRONIC_VERSION=v0.2.49
ARG SUPERCRONIC_SHA256_AMD64=a53ae236602c7338aba3fbaff40bda6300eae3b9fedb8261eb06cfe3724430c1
ARG SUPERCRONIC_SHA256_ARM64=02aa0cb229ba09050cba6638059dadb9eedc2276632ea43d6a57a2f8c1629dd5

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN set -eu; \
    apk add --no-cache 'python3~3.12'; \
    arch="${TARGETARCH:-amd64}"; \
    case "$arch" in \
        amd64) sha="$SUPERCRONIC_SHA256_AMD64" ;; \
        arm64) sha="$SUPERCRONIC_SHA256_ARM64" ;; \
        *) echo "unsupported architecture: $arch" >&2; exit 1 ;; \
    esac; \
    wget -q -O /usr/local/bin/supercronic \
        "https://github.com/aptible/supercronic/releases/download/${SUPERCRONIC_VERSION}/supercronic-linux-${arch}"; \
    echo "${sha}  /usr/local/bin/supercronic" | sha256sum -c -; \
    chmod 0755 /usr/local/bin/supercronic; \
    python3 -m venv /opt/venv; \
    # pip 26.2.1 (2026-08-04): first pip with --uploaded-prior-to durations.
    /opt/venv/bin/pip install pip==26.2.1

COPY requirements.txt /tmp/requirements.txt
RUN /opt/venv/bin/pip install --only-binary=:all: --uploaded-prior-to="${PIP_UPLOADED_PRIOR_TO}" \
        -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/opt/backup \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # No passwd entry for BACKUP_UID: libpq and boto3 look for their config files here (none exist).
    HOME=/tmp \
    BACKUP_DIR=/backups

COPY backuptool /opt/backup/backuptool
COPY --chmod=0755 bin/backup-now /usr/local/bin/backup-now
COPY crontab /etc/backup/crontab

# Fail the build if a piece is missing: pg_dump of another major, the crontab, boto3 or the time zones.
RUN pg_dump --version | grep -q ' 16\.' \
    && supercronic -test /etc/backup/crontab \
    && python -c "import boto3, backuptool.core; from zoneinfo import ZoneInfo; ZoneInfo('America/Sao_Paulo')"

# Default uid/gid of the repository owner; docker-compose.yml sets BACKUP_UID/BACKUP_GID.
USER 1000:1000
WORKDIR /tmp
# The postgres image stops with SIGINT; supercronic waits for a running job on SIGTERM too.
STOPSIGNAL SIGTERM
# Not the postgres entrypoint: this container never runs a server.
ENTRYPOINT []
CMD ["supercronic", "-passthrough-logs", "/etc/backup/crontab"]
