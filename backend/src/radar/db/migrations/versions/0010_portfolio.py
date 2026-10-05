"""Portfolio, holdings, and the latest portfolio analysis.

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("source", sa.Text, nullable=False),
        sa.Column("updated_at", TZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "holdings",
        sa.Column(
            "portfolio_id",
            sa.Integer,
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), primary_key=True),
        sa.Column("quantity", sa.Double, nullable=False),
        sa.Column("tag", sa.Text, nullable=True),
    )
    op.create_table(
        "portfolio_analyses",
        sa.Column(
            "portfolio_id",
            sa.Integer,
            sa.ForeignKey("portfolios.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("as_of", TZ, nullable=False),
        sa.Column("computed_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("payload", JSONB, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("portfolio_analyses")
    op.drop_table("holdings")
    op.drop_table("portfolios")
