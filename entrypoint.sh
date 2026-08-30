#!/bin/sh
# Two-stage startup with loud diagnostics.
#
# Stage 1: try to apply migrations. If alembic fails (most often "relation
# already exists" because an old deploy created the tables via metadata
# instead of migrations), try to stamp head and continue.
#
# Stage 2: exec the supplied command (Railway "Custom Start Command" lands
# here as positional arguments — that's how the arq worker service runs
# `arq leadgen.queue.worker.WorkerSettings` instead of the API). When no
# args are passed we fall back to `python -m leadgen` for the API service.
#
# `exec` at the end replaces the shell process with python so signals
# (SIGTERM from Railway redeploys) reach the bot directly.
#
# RUN_MIGRATIONS=0 skips stage 1 entirely. Set it on every service that
# is NOT the migration owner — in practice the arq worker. Two services
# booting the same image would otherwise both run `alembic upgrade head`
# against one database at the same time; the loser hits a duplicate-object
# error and falls into the `stamp head` recovery below, which marks the
# schema as current WITHOUT having applied it. That failure is silent and
# leaves the database half-migrated, so the worker must never migrate.

set -u

ts() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

# Stage 2, shared by every path out of stage 1.
run_app() {
    if [ "$#" -gt 0 ]; then
        echo "[$(ts)] === STAGE 2: exec $* ==="
        exec "$@"
    else
        echo "[$(ts)] === STAGE 2: exec python -m leadgen ==="
        exec python -m leadgen
    fi
}

# Explicit opt-out: this service does not own the schema.
case "${RUN_MIGRATIONS:-1}" in
    0|false|False|FALSE|no|off)
        echo "[$(ts)] === STAGE 1: skipped — RUN_MIGRATIONS=${RUN_MIGRATIONS} ==="
        echo "[$(ts)] === STAGE 1: this service does not migrate; the API does ==="
        run_app "$@"
        ;;
esac

# Zero-config first run: no DATABASE_URL (or a sqlite one) means the
# app bootstraps its own schema from the models at startup — the
# alembic chain targets Postgres and is skipped entirely.
case "${DATABASE_URL:-}" in
    ""|sqlite*)
        echo "[$(ts)] === STAGE 1: sqlite/zero-config — skipping alembic ==="
        run_app "$@"
        ;;
esac

echo "[$(ts)] === STAGE 1: alembic upgrade head ==="
if alembic upgrade head; then
    echo "[$(ts)] === STAGE 1: migrations OK ==="
else
    rc=$?
    echo "[$(ts)] === STAGE 1: alembic upgrade FAILED (rc=$rc) ==="
    echo "[$(ts)] === STAGE 1: attempting 'alembic stamp head' to recover ==="
    if alembic stamp head; then
        echo "[$(ts)] === STAGE 1: stamped head; assuming schema is current ==="
    else
        echo "[$(ts)] === STAGE 1: stamp also failed; continuing to bot anyway ==="
    fi
fi

run_app "$@"
