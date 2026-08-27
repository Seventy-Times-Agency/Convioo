"""oauth_consumed_nonces table for cross-replica state replay protection

Revision ID: 20260512_0050
Revises: 20260512_0049
Create Date: 2026-05-12 10:00:00

The OAuth ``state`` nonce ledger used to live in a process-local dict,
so a redeemed state could be replayed through a second web replica
(Railway runs more than one). Move it into a shared table: the nonce is
the primary key, so the first replica to INSERT wins and every replay /
concurrent redemption hits the unique constraint and is rejected.

``expires_at`` is indexed so the opportunistic GC sweep
(``DELETE WHERE expires_at < now``) stays cheap. On SQLite (test
fixture) the ORM ``metadata.create_all`` builds the same table, so this
migration is only exercised against Postgres in prod.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260512_0050"
down_revision = "20260512_0049"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oauth_consumed_nonces",
        sa.Column("nonce", sa.String(length=64), nullable=False),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.PrimaryKeyConstraint("nonce"),
    )
    op.create_index(
        "ix_oauth_consumed_nonces_expires_at",
        "oauth_consumed_nonces",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_consumed_nonces_expires_at",
        table_name="oauth_consumed_nonces",
    )
    op.drop_table("oauth_consumed_nonces")
