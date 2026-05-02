"""affiliate codes + referrals

Revision ID: 20260502_0027
Revises: 20260502_0026
Create Date: 2026-05-02 20:00:00

Affiliate / referral plumbing. ``affiliate_codes`` is the partner's
bag of slugs they share publicly; ``referrals`` records each signup
that arrived through one of those slugs. Revenue-share resolution
happens later when Stripe is wired (Phase 7) — this commit only
tracks attribution.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260502_0027"
down_revision = "20260502_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "affiliate_codes",
        sa.Column("code", sa.String(length=64), primary_key=True),
        sa.Column("owner_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=True),
        sa.Column(
            "percent_share",
            sa.SmallInteger(),
            server_default=sa.text("30"),
            nullable=False,
        ),
        sa.Column(
            "active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"], ["users.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_affiliate_codes_owner",
        "affiliate_codes",
        ["owner_user_id"],
    )

    op.create_table(
        "referrals",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column(
            "referred_user_id", sa.BigInteger(), nullable=False
        ),
        sa.Column(
            "signed_up_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "first_paid_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.ForeignKeyConstraint(
            ["code"], ["affiliate_codes.code"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["referred_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        # One signup attributes to at most one code — re-using the
        # same email through a different /r/ link doesn't double-count.
        sa.UniqueConstraint(
            "referred_user_id", name="uq_referrals_referred_user"
        ),
    )
    op.create_index(
        "ix_referrals_code", "referrals", ["code"]
    )


def downgrade() -> None:
    op.drop_index("ix_referrals_code", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index(
        "ix_affiliate_codes_owner", table_name="affiliate_codes"
    )
    op.drop_table("affiliate_codes")
