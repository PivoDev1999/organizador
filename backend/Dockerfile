# syntax=docker/dockerfile:1
# Organizador API: production image (FastAPI + uvicorn), used by the `api` service of docker-compose.yml.
#
# Base: Debian slim (glibc), not Alpine (musl). psycopg[binary], bcrypt, uvloop, httptools and pydantic-core
# ship manylinux wheels, so nothing is compiled; on Alpine some of them would need a toolchain or use
# musllinux wheels that are released less often. Debian slim also ships tzdata, which zoneinfo needs for
# APP_TIMEZONE (checked below at build time).
# Both stages use the same image: python:3.12.15-slim-trixie (Python 3.12.15, released 2026-09-30), pinned
# by tag and digest. Written in each FROM (not in an ARG) so Dependabot can update them.

# ---------------------------------------------------------------------------------------------------------
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS build

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Project rule: only releases at least two weeks old. The direct dependencies are pinned in pyproject.toml;
# this cutoff also covers the transitive ones (P14D = uploaded at least 14 days before the build).
ARG PIP_UPLOADED_PRIOR_TO=P14D

RUN python -m venv /opt/venv \
    # pip 26.2.1 (2026-08-04): first pip in the image with --uploaded-prior-to durations.
    && /opt/venv/bin/pip install pip==26.2.1

# Only the dependency list: this layer is rebuilt when pyproject.toml changes, not on every code change.
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml', 'rb'))['project']['dependencies']))" \
        > requirements.txt \
    && /opt/venv/bin/pip install --only-binary=:all: --uploaded-prior-to="${PIP_UPLOADED_PRIOR_TO}" \
        -r requirements.txt

# ---------------------------------------------------------------------------------------------------------
FROM python:3.12.15-slim-trixie@sha256:a0f57064cbdcd6285fa45f51237ab0b35ea8ebaed06a1f5973e89e19dfb86704 AS runtime

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # No .env inside the image: every setting comes from the environment (docker compose env_file).
    ENV_FILE=/dev/null

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app

COPY --from=build /opt/venv /opt/venv

WORKDIR /app
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY scripts ./scripts
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

# Fail the build if the time zone database is missing (APP_TIMEZONE would be rejected at startup).
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Sao_Paulo')"

USER app
EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4).status != 200)"]

ENTRYPOINT ["docker-entrypoint.sh"]
