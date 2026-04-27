"""assistant_memories — Henry's persistent memory between sessions

Revision ID: 20260427_0016
Revises: 20260426_0015
Create Date: 2026-04-27 02:50:00

Adds the table backing the floating-Henry memory feature: every N
user messages Henry distills the recent dialogue into a short
``summary`` plus a handful of durable ``fact`` rows. They're loaded
back into the system prompt on every subsequent request so Henry
keeps continuity without us having to ship the entire chat history.

Scoped per user; team-mode rows additionally carry ``team_id`` so
team members share Henry's understanding of the team while keeping
their personal memories private.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260427_0016"
down_revision = "20260426_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_memories",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "team_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("meta", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_assistant_memories_user_id",
        "assistant_memories",
        ["user_id"],
    )
    op.create_index(
        "ix_assistant_memories_team_id",
        "assistant_memories",
        ["team_id"],
    )
    # Composite for the hot read path: "give me the most recent N
    # memories for this user (and team)".
    op.create_index(
        "ix_assistant_memories_user_team_recent",
        "assistant_memories",
        ["user_id", "team_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_assistant_memories_user_team_recent",
        table_name="assistant_memories",
    )
    op.drop_index(
        "ix_assistant_memories_team_id", table_name="assistant_memories"
    )
    op.drop_index(
        "ix_assistant_memories_user_id", table_name="assistant_memories"
    )
    op.drop_table("assistant_memories")
