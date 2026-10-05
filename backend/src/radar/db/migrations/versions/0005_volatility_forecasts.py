"""Volatility forecasts.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "volatility_forecasts",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("model", sa.Text, nullable=False),
        sa.Column("ts", TZ, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("forecast", sa.Double, nullable=False),
        sa.Column("realised", sa.Double, nullable=True),
        sa.PrimaryKeyConstraint("symbol", "horizon_days", "model", "ts"),
    )
    op.execute(
        "SELECT create_hypertable('volatility_forecasts', 'ts',"
        " chunk_time_interval => INTERVAL '365 days', create_default_indexes => FALSE)"
    )


def downgrade() -> None:
    op.drop_table("volatility_forecasts")
