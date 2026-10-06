"""Signals and the track record of each kind of signal.

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "signal_track_records",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("variant", sa.Text, nullable=False),
        sa.Column("computed_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("n", sa.Integer, nullable=False),
        sa.Column("verdict", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("type", "symbol", "variant", name="uq_signal_track_records_type"),
    )
    op.create_table(
        "signals",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("ts", TZ, nullable=False),
        sa.Column("type", sa.Text, nullable=False),
        sa.Column("variant", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
        sa.Column(
            "track_record_id",
            sa.BigInteger,
            sa.ForeignKey("signal_track_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("symbol", "ts", "type", name="uq_signals_symbol"),
    )
    op.create_index("ix_signals_ts", "signals", ["ts"])


def downgrade() -> None:
    op.drop_table("signals")
    op.drop_table("signal_track_records")
