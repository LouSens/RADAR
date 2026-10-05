"""Model registry and regime states.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "model_registry",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=True),
        sa.Column("version", sa.Text, nullable=False),
        sa.Column("trained_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("train_start", sa.Date, nullable=False),
        sa.Column("train_end", sa.Date, nullable=False),
        sa.Column("is_current", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("params", JSONB, nullable=False),
        sa.Column("metrics", JSONB, nullable=False, server_default="{}"),
        sa.Column("artefact_path", sa.Text, nullable=True),
    )
    op.create_index(
        "ix_model_registry_name_symbol", "model_registry", ["name", "symbol", "trained_at"]
    )

    op.create_table(
        "regime_states",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("model_id", sa.BigInteger, nullable=False),
        sa.Column("ts", TZ, nullable=False),
        sa.Column("label", sa.Text, nullable=False),
        sa.Column("probability", sa.Double, nullable=False),
        sa.Column("probs", JSONB, nullable=False),
        sa.PrimaryKeyConstraint("symbol", "model_id", "ts"),
    )
    op.execute(
        "SELECT create_hypertable('regime_states', 'ts',"
        " chunk_time_interval => INTERVAL '365 days', create_default_indexes => FALSE)"
    )


def downgrade() -> None:
    op.drop_table("regime_states")
    op.drop_table("model_registry")
