"""Article sentiment and its aggregates.

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "news_sentiment",
        sa.Column(
            "article_id",
            sa.BigInteger,
            sa.ForeignKey("news_articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("p_pos", sa.Double, nullable=False),
        sa.Column("p_neg", sa.Double, nullable=False),
        sa.Column("p_neu", sa.Double, nullable=False),
        sa.Column("score", sa.Double, nullable=False),
        sa.PrimaryKeyConstraint("article_id", "model_version"),
    )

    op.create_table(
        "sentiment_agg",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("bucket", sa.Text, nullable=False),
        sa.Column("ts", TZ, nullable=False),
        sa.Column("model_version", sa.Text, nullable=False),
        sa.Column("article_count", sa.Integer, nullable=False),
        sa.Column("score_mean", sa.Double, nullable=True),
        sa.Column("score_decayed", sa.Double, nullable=True),
        sa.PrimaryKeyConstraint("symbol", "bucket", "ts"),
    )
    op.execute(
        "SELECT create_hypertable('sentiment_agg', 'ts',"
        " chunk_time_interval => INTERVAL '365 days', create_default_indexes => FALSE)"
    )


def downgrade() -> None:
    op.drop_table("sentiment_agg")
    op.drop_table("news_sentiment")
