"""lead business-language verdict

Revision ID: 20260827_0058
Revises: 20260827_0057
Create Date: 2026-08-27

Wave 1 задача 6: enrichment writes a business-language verdict per
lead (generic engine; RU/UA preset uses separate labels) so the База
panel can filter the pool by community.
"""

import sqlalchemy as sa
from alembic import op

revision = "20260827_0058"
down_revision = "20260827_0057"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("business_language", sa.String(length=8), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "business_language_confidence",
            sa.String(length=8),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_leads_business_language", "leads", ["business_language"]
    )


def downgrade() -> None:
    op.drop_index("ix_leads_business_language", table_name="leads")
    op.drop_column("leads", "business_language_confidence")
    op.drop_column("leads", "business_language")
