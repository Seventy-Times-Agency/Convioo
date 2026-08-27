"""email_suppressions (do-not-contact list)

Revision ID: 20260626_0056
Revises: 20260621_0055
Create Date: 2026-06-26 04:00:00

Adds the per-user recipient-level suppression list. The outreach send
paths consult it before every send so an unsubscribed / opted-out
recipient is never contacted again, even if the same business email is
re-scraped in a later search.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260626_0056"
down_revision = "20260621_0055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_suppressions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id", "email", name="uq_email_suppressions_user_email"
        ),
    )
    op.create_index(
        "ix_email_suppressions_user_id",
        "email_suppressions",
        ["user_id"],
    )
    op.create_index(
        "ix_email_suppressions_email",
        "email_suppressions",
        ["email"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_email_suppressions_email", table_name="email_suppressions"
    )
    op.drop_index(
        "ix_email_suppressions_user_id", table_name="email_suppressions"
    )
    op.drop_table("email_suppressions")
