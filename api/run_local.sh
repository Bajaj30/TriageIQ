#!/bin/sh
# Start the API on the Mac against the local Postgres (port 5433), from the repo root:  sh api/run_local.sh
# The password is read from .env into the environment — never printed, never in code.
set -a; . ./.env; set +a
export PGHOST=localhost PGPORT=5433 PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" PGPASSWORD="$POSTGRES_PASSWORD"
exec .venv-api/bin/uvicorn api.main:app --port 8000 "$@"
