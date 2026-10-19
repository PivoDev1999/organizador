#!/bin/sh
# Runs only on the first start of an empty data volume.
# Creates the database used by pytest, owned by the same user.
set -eu

if [ -n "${POSTGRES_TEST_DB:-}" ]; then
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
    -c "CREATE DATABASE \"$POSTGRES_TEST_DB\" OWNER \"$POSTGRES_USER\";"
fi
