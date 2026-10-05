"""Article topics.

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "news_topics",
        sa.Column(
            "article_id",
            sa.BigInteger,
            sa.ForeignKey("news_articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("topic", sa.Text, nullable=False),
        sa.Column("confidence", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint("article_id", "model_version"),
    )
    op.create_index("ix_news_topics_topic", "news_topics", ["model_version", "topic"])


def downgrade() -> None:
    op.drop_table("news_topics")
