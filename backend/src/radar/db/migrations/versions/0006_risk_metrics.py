"""Tail-risk estimates.

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "risk_metrics",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("level", sa.Double, nullable=False),
        sa.Column("method", sa.Text, nullable=False),
        sa.Column("ts", TZ, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("var", sa.Double, nullable=False),
        sa.Column("expected_shortfall", sa.Double, nullable=False),
        sa.Column("realised_loss", sa.Double, nullable=True),
        sa.PrimaryKeyConstraint("symbol", "horizon_days", "level", "method", "ts"),
    )
    op.execute(
        "SELECT create_hypertable('risk_metrics', 'ts',"
        " chunk_time_interval => INTERVAL '365 days', create_default_indexes => FALSE)"
    )


def downgrade() -> None:
    op.drop_table("risk_metrics")
