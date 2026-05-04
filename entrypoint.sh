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

set -u

ts() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

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

if [ "$#" -gt 0 ]; then
    echo "[$(ts)] === STAGE 2: exec $* ==="
    exec "$@"
else
    echo "[$(ts)] === STAGE 2: exec python -m leadgen ==="
    exec python -m leadgen
fi
