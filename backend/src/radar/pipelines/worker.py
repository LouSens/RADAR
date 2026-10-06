"""The worker process: live streams plus scheduled jobs.

Only this process opens Alpaca stream connections. Alpaca allows one connection per
stream endpoint per account, so run a single worker per set of keys.
"""

import threading
from collections.abc import Callable
from functools import partial
from typing import Any

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from radar.config import Settings, load_settings
from radar.db.session import make_engine
from radar.ingest.live import BarHandler, LiveConsumer, NewsHandler, StreamSpec, Syncer, notify
from radar.ingest.raw_store import RawStore
from radar.logging import get_logger
from radar.pipelines import discover
from radar.pipelines import event_study as event_study_job
from radar.pipelines import portfolio as portfolio_job
from radar.pipelines import regime as regime_job
from radar.pipelines import relationships as relationships_job
from radar.pipelines import risk as risk_job
from radar.pipelines import sentiment as sentiment_job
from radar.pipelines import simulation as simulation_job
from radar.pipelines import track as track_job
from radar.pipelines import volatility as volatility_job
from radar.pipelines.quality import run_quality
from radar.providers.alpaca_rest import AlpacaDataClient
from radar.providers.alpaca_stream import (
    NEWS_STREAM_URL,
    STOCK_STREAM_URL,
    StreamSession,
    crypto_stream_url,
)
from radar.universe import Universe, get_universe

log = get_logger(__name__)


def stream_specs(universe: Universe) -> list[StreamSpec]:
    crypto = [a.bars_symbol for a in universe.of_class("crypto")]
    stocks = [a.bars_symbol for a in universe.of_class("stock")]
    specs = []
    if crypto:
        url = crypto_stream_url(universe.crypto_location)
        specs.append(StreamSpec("crypto", url, {"bars": crypto}))
    if stocks:
        specs.append(StreamSpec("stocks", STOCK_STREAM_URL, {"bars": stocks}))
    if universe.news_symbols:
        specs.append(StreamSpec("news", NEWS_STREAM_URL, {"news": list(universe.news_symbols)}))
    return specs


def run_worker(settings: Settings | None = None, universe: Universe | None = None) -> int:
    settings = settings or load_settings()
    universe = universe or get_universe()
    key_id, secret_key = settings.alpaca_api_key_id, settings.alpaca_api_secret_key
    if key_id is None or secret_key is None:
        log.error("missing_alpaca_keys", hint="copy .env.example to .env and fill in paper keys")
        return 1

    engine = make_engine(settings=settings)
    stop = threading.Event()
    publish = partial(notify, engine)

    with AlpacaDataClient(key_id, secret_key) as client:
        client.on_page = RawStore().record
        syncer = Syncer(client, engine, universe)
        syncer.sync()  # close any gap left since the worker last ran

        handlers: dict[str, Callable[[dict[str, Any]], None]] = {
            "crypto": BarHandler(universe, publish),
            "stocks": BarHandler(universe, publish),
            "news": NewsHandler(universe, engine, publish),
        }
        # After a (re)connect, refetch what that stream covers.
        refill = {
            "crypto": partial(syncer.sync, news=False),
            "stocks": partial(syncer.sync, news=False),
            "news": partial(syncer.sync, bars=False),
        }
        threads = []
        for spec in stream_specs(universe):
            consumer = LiveConsumer(
                spec,
                key_id,
                secret_key,
                on_message=handlers[spec.name],
                on_connect=refill[spec.name],
                connect=StreamSession,
                stop=stop,
            )
            thread = threading.Thread(target=consumer.run, name=f"stream-{spec.name}", daemon=True)
            thread.start()
            threads.append(thread)

        scheduler = BlockingScheduler(timezone="UTC")

        # One minute past each hour: the hour that just ended is now a finished bar.
        def sync_everything() -> None:
            # Assets discovered from the user's holdings are kept up to date too.
            with Session(engine) as session:
                syncer.universe = discover.extend(universe, session)
            syncer.sync()

        scheduler.add_job(
            sync_everything, "cron", minute=1, id="sync", max_instances=1, coalesce=True
        )
        scheduler.add_job(
            partial(run_quality, engine, universe),
            "cron",
            minute=10,
            id="quality",
            max_instances=1,
            coalesce=True,
        )
        # Regimes: score a few minutes after each hourly sync; refit once a week.
        scheduler.add_job(
            partial(regime_job.run, engine, universe),
            "cron",
            minute=5,
            id="regime-score",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            partial(regime_job.run, engine, universe, retrain=True),
            "cron",
            day_of_week="sun",
            hour=2,
            minute=30,
            id="regime-refit",
            max_instances=1,
            coalesce=True,
        )
        # Outlook: a new run once a day's regime reading exists; coverage measured weekly.
        scheduler.add_job(
            partial(simulation_job.run, engine, universe),
            "cron",
            minute=15,
            id="simulate",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            partial(simulation_job.run, engine, universe, recalibrate=True),
            "cron",
            day_of_week="sun",
            hour=3,
            minute=30,
            id="calibrate",
            max_instances=1,
            coalesce=True,
        )
        # Volatility: forecasts for each newly completed day.
        scheduler.add_job(
            partial(volatility_job.run, engine, universe),
            "cron",
            minute=20,
            id="volatility",
            max_instances=1,
            coalesce=True,
        )
        # Tail risk: after the volatility forecasts it depends on.
        scheduler.add_job(
            partial(risk_job.run, engine, universe),
            "cron",
            minute=30,
            id="risk",
            max_instances=1,
            coalesce=True,
        )
        # News: tone and topics every ten minutes; the tone-versus-price study daily.
        scheduler.add_job(
            sentiment_job.NewsJob(engine, universe),
            "cron",
            minute="2-59/10",
            id="news",
            max_instances=1,
            coalesce=True,
        )
        scheduler.add_job(
            partial(event_study_job.run, engine, universe),
            "cron",
            hour=1,
            minute=40,
            id="event-study",
            max_instances=1,
            coalesce=True,
        )
        # Live track record: write down what is being shown, score what has come due.
        scheduler.add_job(
            partial(track_job.run, engine, universe),
            "cron",
            minute=40,
            id="track-record",
            max_instances=1,
            coalesce=True,
        )
        # How the markets move together: hourly, so the weekend reading stays current.
        scheduler.add_job(
            partial(relationships_job.run, engine, universe),
            "cron",
            minute=50,
            id="relationships",
            max_instances=1,
            coalesce=True,
        )
        # The portfolio's analysis follows the prices: refreshed once an hour.
        scheduler.add_job(
            partial(
                portfolio_job.run,
                engine,
                universe,
                portfolio_job.binance_reader(),
                portfolio_job.asset_finder(engine),
            ),
            "cron",
            minute=45,
            id="portfolio",
            max_instances=1,
            coalesce=True,
        )
        log.info("worker_started", streams=[t.name for t in threads])
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("worker_stopping")
        finally:
            stop.set()
            for thread in threads:
                thread.join(timeout=5)
    return 0
