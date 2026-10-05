"""Keep the `assets` table in step with the configured universe."""

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from radar.db.models import Asset
from radar.universe import Universe


def sync_assets(session: Session, universe: Universe) -> int:
    """Upsert every asset in the universe. Returns the number of assets written.

    Assets removed from the universe are left in place: their bars and news still
    reference them.
    """
    rows = [
        {
            "symbol": asset.symbol,
            "name": asset.name,
            "asset_class": asset.asset_class,
            "is_primary": asset.is_primary,
            "provider_symbols": {"bars": asset.bars_symbol, "news": list(asset.news_symbols)},
            "history_start": asset.history_start,
            "news_start": asset.news_start,
        }
        for asset in universe.assets
    ]
    statement = insert(Asset).values(rows)
    updatable = [c for c in rows[0] if c != "symbol"]
    session.execute(
        statement.on_conflict_do_update(
            index_elements=[Asset.symbol],
            set_={column: statement.excluded[column] for column in updatable},
        )
    )
    return len(rows)
