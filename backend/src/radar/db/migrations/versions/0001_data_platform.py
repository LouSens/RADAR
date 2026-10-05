"""Data platform tables: assets, bars, news, ingestion runs, data quality reports.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TZ = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")

    op.create_table(
        "assets",
        sa.Column("symbol", sa.Text, primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("asset_class", sa.Text, nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("provider_symbols", JSONB, nullable=False),
        sa.Column("history_start", sa.Date, nullable=False),
        sa.Column("news_start", sa.Date, nullable=True),
    )

    op.create_table(
        "bars",
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.Column("timeframe", sa.Text, nullable=False),
        sa.Column("loc", sa.Text, nullable=False),
        sa.Column("ts", TZ, nullable=False),
        sa.Column("open", sa.Double, nullable=False),
        sa.Column("high", sa.Double, nullable=False),
        sa.Column("low", sa.Double, nullable=False),
        sa.Column("close", sa.Double, nullable=False),
        sa.Column("volume", sa.Double, nullable=False),
        sa.Column("trade_count", sa.BigInteger, nullable=False),
        sa.Column("vwap", sa.Double, nullable=False),
        sa.Column("is_quote_only", sa.Boolean, nullable=False),
        sa.Column("is_outlier", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("received_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("symbol", "timeframe", "loc", "ts"),
    )
    op.execute(
        "SELECT create_hypertable('bars', 'ts', chunk_time_interval => INTERVAL '90 days',"
        " create_default_indexes => FALSE)"
    )

    op.create_table(
        "news_articles",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=False),
        sa.Column("created_at", TZ, nullable=False),
        sa.Column("updated_at", TZ, nullable=False),
        sa.Column("headline", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("author", sa.Text, nullable=False, server_default=""),
        sa.Column("url", sa.Text, nullable=True),
        sa.Column("source", sa.Text, nullable=False, server_default=""),
        sa.Column("received_at", TZ, nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_news_articles_created_at", "news_articles", ["created_at"])

    op.create_table(
        "news_symbols",
        sa.Column(
            "article_id",
            sa.BigInteger,
            sa.ForeignKey("news_articles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.Text, sa.ForeignKey("assets.symbol"), nullable=False),
        sa.PrimaryKeyConstraint("article_id", "symbol"),
    )
    op.create_index("ix_news_symbols_symbol", "news_symbols", ["symbol"])

    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("job", sa.Text, nullable=False),
        sa.Column("key", sa.Text, nullable=False),
        sa.Column("window_start", TZ, nullable=False),
        sa.Column("window_end", TZ, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("rows", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("finished_at", TZ, nullable=True),
        sa.UniqueConstraint("job", "key", "window_start", "window_end"),
    )

    op.create_table(
        "data_quality_reports",
        sa.Column("id", sa.BigInteger, primary_key=True),
        sa.Column("ts", TZ, nullable=False, server_default=sa.func.now()),
        sa.Column("symbol", sa.Text, nullable=True),
        sa.Column("check", sa.Text, nullable=False),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("detail", JSONB, nullable=False, server_default="{}"),
    )
    op.create_index("ix_data_quality_reports_ts", "data_quality_reports", ["ts"])


def downgrade() -> None:
    op.drop_table("data_quality_reports")
    op.drop_table("ingestion_runs")
    op.drop_table("news_symbols")
    op.drop_table("news_articles")
    op.drop_table("bars")
    op.drop_table("assets")
