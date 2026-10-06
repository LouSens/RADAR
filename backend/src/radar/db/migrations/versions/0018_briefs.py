"""The daily brief: one row per day and subject, with the payload it was written from.

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "briefs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("day", sa.Date, nullable=False),
        # A market's symbol, or "PORTFOLIO". Not a foreign key for that reason.
        sa.Column("symbol", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column("sentences", JSONB, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("writer", sa.Text, nullable=False),
        sa.Column("generated_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("day", "symbol", name="uq_briefs_day"),
    )


def downgrade() -> None:
    op.drop_table("briefs")
