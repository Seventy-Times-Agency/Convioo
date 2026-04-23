#!/bin/sh
# Two-stage startup with loud diagnostics.
#
# Stage 1: try to apply migrations. If alembic fails (most often "relation
# already exists" because an old deploy created the tables via metadata
# instead of migrations), try to stamp head and continue.
#
# Stage 2: ALWAYS exec python -m leadgen. If alembic genuinely broke the
# DB the bot's startup logging will show the SQLAlchemy error in Railway
# logs instead of dying silently in the shell.
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

echo "[$(ts)] === STAGE 2: exec python -m leadgen ==="
exec python -m leadgen
