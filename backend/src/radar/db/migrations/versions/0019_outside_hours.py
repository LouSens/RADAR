"""Hourly prices of an asset read from a second, public source, kept apart from `bars`.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "outside_hours",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), primary_key=True),
        # Where the prices were read, and under what name there: "binance:PAXGUSDT".
        sa.Column("source", sa.Text, primary_key=True),
        sa.Column("ts", TZ, primary_key=True),
        sa.Column("open", sa.Double, nullable=False),
        sa.Column("high", sa.Double, nullable=False),
        sa.Column("low", sa.Double, nullable=False),
        sa.Column("close", sa.Double, nullable=False),
        sa.Column("volume", sa.Double, nullable=False),
        sa.Column("received_at", TZ, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("outside_hours")
