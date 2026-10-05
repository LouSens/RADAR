"""Live forecast log.

Revision ID: 0009
Revises: 0008
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "forecast_log",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("kind", sa.Text, nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("as_of", TZ, nullable=False),
        sa.Column("made_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("steps", sa.Integer, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("forecast", JSONB, nullable=False),
        sa.Column("outcome", JSONB, nullable=True),
        sa.Column("resolved_at", TZ, nullable=True),
        sa.UniqueConstraint("symbol", "kind", "horizon_days", "key", "as_of"),
    )


def downgrade() -> None:
    op.drop_table("forecast_log")
