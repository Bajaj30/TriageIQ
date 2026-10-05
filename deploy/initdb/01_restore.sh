#!/bin/sh
# Runs ONCE, on the database container's very first start (empty volume) — the official Postgres image runs
# every script in /docker-entrypoint-initdb.d/ before it opens to the network. Loads the serving schema
# (sql/06_serving, exported with pg_dump) and refreshes the planner's statistics.
set -e
echo "TriageIQ: restoring the serving schema from /seed/serving_db.dump ..."
pg_restore --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-owner --exit-on-error /seed/serving_db.dump
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -v ON_ERROR_STOP=1 -c "ANALYZE;" \
     -c "SELECT count(*) AS demo_complaints FROM serving.test_complaints;"
echo "TriageIQ: serving schema ready."
