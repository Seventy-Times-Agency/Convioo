"""stripe billing fields on users

Revision ID: 20260503_0031
Revises: 20260502_0030
Create Date: 2026-05-03 09:00:00

Adds the columns Stripe webhooks need to mutate. ``plan`` is
purely informational (``free`` / ``pro`` / ``agency``); the
authoritative source of truth lives in Stripe. ``plan_until``
is the period-end stamp from the active subscription so the
quota service can short-circuit when a paid window is open.
``trial_ends_at`` lets us hand every new account a 14-day
preview without forcing a card. ``stripe_customer_id`` lets us
look the user back up from a webhook payload.

A second tiny table — ``stripe_events`` — stores the IDs we've
already processed so a webhook retry doesn't double-count an
upgrade or refund.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260503_0031"
down_revision = "20260502_0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("stripe_customer_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "plan",
            sa.String(length=32),
            server_default=sa.text("'free'"),
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("plan_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "trial_ends_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_index(
        "ix_users_stripe_customer", "users", ["stripe_customer_id"]
    )

    op.create_table(
        "stripe_events",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("stripe_events")
    op.drop_index("ix_users_stripe_customer", table_name="users")
    op.drop_column("users", "trial_ends_at")
    op.drop_column("users", "plan_until")
    op.drop_column("users", "plan")
    op.drop_column("users", "stripe_customer_id")
