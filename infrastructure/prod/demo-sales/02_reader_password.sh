#!/bin/sh
# Runs once when the demo-sales database is created (after 01_sales.sql):
# replaces the local, throwaway password of eka_reader with the one made on
# the server (DEMO_SALES_READER_PASSWORD in .env, by make-env.sh).
set -eu
if [ -z "${DEMO_SALES_READER_PASSWORD:-}" ]; then
  echo "PAROU: DEMO_SALES_READER_PASSWORD is not set in .env." >&2
  exit 1
fi
psql -v ON_ERROR_STOP=1 -v reader_password="$DEMO_SALES_READER_PASSWORD" \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
ALTER ROLE eka_reader PASSWORD :'reader_password';
SQL
