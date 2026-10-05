"""Simulator runs and calibration reports.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "simulations",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("as_of", TZ, nullable=False),
        sa.Column("model_id", sa.BigInteger, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("seed", sa.BigInteger, nullable=False),
        sa.Column("n_paths", sa.Integer, nullable=False),
        sa.Column("max_steps", sa.Integer, nullable=False),
        sa.Column("start_price", sa.Double, nullable=False),
        sa.Column("horizons", JSONB, nullable=False),
        sa.Column("fan", JSONB, nullable=False),
        sa.Column("paths", sa.LargeBinary, nullable=True),
        sa.Column("created_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "as_of", "model_id"),
    )

    op.create_table(
        "calibration_reports",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("horizon_days", sa.Integer, nullable=False),
        sa.Column("nominal", sa.Double, nullable=False),
        sa.Column("steps", sa.Integer, nullable=False),
        sa.Column("empirical", sa.Double, nullable=False),
        sa.Column("empirical_conformal", sa.Double, nullable=False),
        sa.Column("n", sa.Integer, nullable=False),
        sa.Column("conformal_miss_rate", sa.Double, nullable=False),
        sa.Column("pinball_model", sa.Double, nullable=False),
        sa.Column("pinball_baseline", sa.Double, nullable=False),
        sa.Column("first_origin", sa.Date, nullable=False),
        sa.Column("last_origin", sa.Date, nullable=False),
        sa.Column("computed_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("symbol", "model_version", "horizon_days", "nominal"),
    )


def downgrade() -> None:
    op.drop_table("calibration_reports")
    op.drop_table("simulations")
