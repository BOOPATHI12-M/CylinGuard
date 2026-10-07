#!/bin/sh
# Seed the database, then hand over to the command.
#
# `seed.py` is idempotent - it returns early if the demo user already exists - so this runs
# on every start without duplicating data. Compose only starts this container once MySQL
# reports healthy, so the connection is expected to work; a failure here is a real problem
# and is logged rather than swallowed.
#
# Seeding runs seed.py rather than a static SQL file (see decision 2 in PROJECT_STATE):
# `database/seed.sql` is a generated export for anyone who wants pure SQL, not the source
# of truth. The schema itself is applied by the mysql container from
# docker-entrypoint-initdb.d.
set -e

if [ "${SKIP_SEED:-false}" != "true" ]; then
  echo "[entrypoint] seeding (idempotent; set SKIP_SEED=true to skip)"
  python scripts/seed.py || echo "[entrypoint] WARNING: seeding failed - continuing so the API can still start and report /health"
fi

echo "[entrypoint] starting: $*"
exec "$@"
