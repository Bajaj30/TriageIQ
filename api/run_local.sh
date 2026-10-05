#!/bin/sh
# Start the API on the Mac against the local Postgres (port 5433):   sh api/run_local.sh   (from any folder)
# Keep this terminal open — the server stops when it closes. Stop it with Ctrl+C.
# The password is read from .env into the environment — never printed, never in code.
cd "$(dirname "$0")/.." || exit 1                       # the repo root, wherever you ran this from
if ! docker exec triageiq-postgres pg_isready -q -U triageiq -d triageiq 2>/dev/null; then
    echo "The database isn't reachable: start Docker Desktop, then run  docker compose up -d  and try again."
    exit 1
fi
set -a; . ./.env; set +a
export PGHOST=localhost PGPORT=5433 PGUSER="$POSTGRES_USER" PGDATABASE="$POSTGRES_DB" PGPASSWORD="$POSTGRES_PASSWORD"
echo "Starting TriageIQ API → open http://localhost:8000/docs (Postman: http://localhost:8000)"
exec .venv-api/bin/uvicorn api.main:app --port 8000 "$@"
