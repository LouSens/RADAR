"""The risk level and split the user chose to hold the portfolio against.

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("target", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("portfolios", "target")
