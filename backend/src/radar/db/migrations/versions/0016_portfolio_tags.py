"""Core and satellite tags, kept by symbol so a new read of holdings keeps them.

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("portfolios", sa.Column("tags", JSONB, nullable=False, server_default="{}"))
    # Tags already on stored holdings move to the new place.
    op.execute(
        """
        UPDATE portfolios p SET tags = COALESCE(
            (SELECT jsonb_object_agg(h.symbol, h.tag) FROM holdings h
             WHERE h.portfolio_id = p.id AND h.tag IS NOT NULL),
            '{}'::jsonb)
        """
    )


def downgrade() -> None:
    op.drop_column("portfolios", "tags")
