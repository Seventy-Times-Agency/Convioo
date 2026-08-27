#!/bin/sh
# Pre-deploy migration runner with retry on transient errors.
#
# Why this exists: Railway's pre-deploy container occasionally fails
# to resolve the postgres.railway.internal hostname for a few seconds
# right after the build container hands off. A naked `alembic upgrade
# head` then dies and Railway marks the whole deploy FAILED — even
# though the next attempt usually succeeds within a minute.
#
# This wrapper retries alembic up to 5 times with 5s, 15s, 30s, 60s,
# 90s pauses. It only retries when alembic exits non-zero (covers DNS
# / connection-refused / TLS handshake hiccups). A real schema bug
# still kills the deploy on the first try — alembic prints the same
# error repeatedly, but at least we logged it 5 times before giving up.

set -u

ts() {
    date -u +"%Y-%m-%dT%H:%M:%SZ"
}

ATTEMPTS=5
SLEEPS="5 15 30 60 90"
i=0

for sleep_for in $SLEEPS; do
    i=$((i + 1))
    echo "[$(ts)] migrate.sh: attempt $i/$ATTEMPTS — alembic upgrade head"
    if alembic upgrade head; then
        echo "[$(ts)] migrate.sh: migrations OK on attempt $i"
        exit 0
    fi
    rc=$?
    if [ "$i" -ge "$ATTEMPTS" ]; then
        echo "[$(ts)] migrate.sh: giving up after $ATTEMPTS attempts (rc=$rc)"
        exit "$rc"
    fi
    echo "[$(ts)] migrate.sh: attempt $i failed (rc=$rc) — sleeping ${sleep_for}s"
    sleep "$sleep_for"
done
