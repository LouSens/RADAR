"""Mark duplicate news articles instead of deleting them.

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "news_articles",
        sa.Column(
            "duplicate_of",
            sa.BigInteger,
            sa.ForeignKey("news_articles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("news_articles", "duplicate_of")
