"""Work out the example account for the film's mock API.

    uv run python demo-video/mock-api/make_account.py

The holdings are the made-up portfolio in demo-video/mock-api/example.json: its value
and shares are read from there and nothing else. The figures are then worked out
by the app's own code from stored market prices, the way a notebook does it. The stored
portfolio, plan and account record are never read, and the database is opened read-only.
Run mock-api/record.mjs first: the brief and the system page are built from what it
recorded.
"""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import text

from radar.brief.payload import PortfolioFacts
from radar.brief.writer import TemplateWriter, money
from radar.db.session import make_engine, session_scope
from radar.models.holdings import CASH, CASH_NAME, Holding
from radar.pipelines import check as check_job
from radar.pipelines import portfolio as portfolio_job
from radar.pipelines import rebalance
from radar.pipelines import steps as steps_job
from radar.pipelines.datasets import build_mixed_panel
from radar.pipelines.signals import daily_close
from radar.providers import binance_public
from radar.universe import get_universe

HERE = Path(__file__).parent
FIXTURE = HERE / "example.json"
RECORDED = HERE / "data" / "recorded"
OUT = HERE / "data" / "example"


def keep(name: str, body: BaseModel | dict[str, Any]) -> None:
    file = OUT / f"{name}.json"
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = body.model_dump(mode="json") if isinstance(body, BaseModel) else body
    file.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf8")
    sys.stdout.write(f"{name}\n")


def recorded(name: str) -> Any:
    return json.loads((RECORDED / f"{name}.json").read_text(encoding="utf8"))


def main() -> None:
    example = json.loads(FIXTURE.read_text(encoding="utf8"))
    value = float(example["value"])
    shares = {h["symbol"]: float(h["money"]) for h in example["holdings"]}
    plan = {h["symbol"]: float(h["plan"]) for h in example["holdings"] if h["symbol"] != CASH}
    universe = get_universe()
    now = datetime.now(UTC)

    with session_scope(make_engine()) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        panel = build_mixed_panel(session, universe)
        price = panel.prices[list(plan)].ffill().iloc[-1]
        holdings = [
            Holding(symbol=symbol, quantity=share * value / float(price[symbol]))
            for symbol, share in shares.items()
            if symbol != CASH
        ] + [Holding(symbol=CASH, quantity=shares[CASH] * value)]
        analysis = portfolio_job.analyse(holdings, panel, universe)
        states = portfolio_job.holding_states(session, analysis, panel, universe)
        if analysis.risk_level is None:
            raise SystemExit("No risk level: US stocks are missing from the stored prices.")
        analysis = analysis.model_copy(
            update={
                "states": states,
                "plan": rebalance.build(
                    analysis.xray,
                    analysis.risk_level,
                    [],
                    {s.symbol: s.label for s in states},
                    analysis.covered_value,
                    panel,
                    rebalance.Target(weights=plan, set_at=now - timedelta(days=21)),
                ),
            }
        )
        closes = {symbol: daily_close(session, universe.get(symbol)) for symbol in plan}

    steps = steps_job.build(analysis, plan, closes, now).model_copy(update={"checked_at": now})
    keep("portfolio/analysis", analysis)
    keep("portfolio/steps", steps)
    keep(
        "portfolio",
        {
            "source": "manual",
            "read_at": None,
            "holdings": [h.model_dump(mode="json") for h in holdings],
            "supported": [
                {"symbol": a.symbol, "name": a.name, "asset_class": a.asset_class}
                for a in universe.primary
            ]
            + [{"symbol": CASH, "name": CASH_NAME, "asset_class": "cash"}],
            "problem": None,
            "binance_available": False,
            "leveraged": [],
            "wallets": [],
            "unsupported": [],
        },
    )

    # Whether Bitcoin's price is high or low, from public prices and with no account
    # record: the part of the page that is about the reader's own trades stays empty.
    with binance_public.reader() as source:
        hours = check_job.fetch(source, "BTC")
        year = check_job.fetch_year(source, "BTC")
    keep("portfolio/check/BTC", check_job.build("BTC", hours, None, now, year))

    # The brief: the app's own wording, the portfolio lines from the example.
    level = analysis.risk_level
    facts = PortfolioFacts(
        value=analysis.value,
        risk_level=level.label,
        times_stocks=round(level.ratio, 1),
        typical_day=round(analysis.xray.daily_volatility * analysis.value),
        has_plan=steps.has_plan,
        to_buy=[f"{s.name} {money(s.amount)}" for s in steps.steps if s.kind == "buy"],
        to_trim=[f"{s.name} {money(s.amount)}" for s in steps.steps if s.kind == "trim"],
    )
    items = [
        {
            "symbol": "PORTFOLIO",
            "name": "Your portfolio",
            "sentences": [s.model_dump() for s in TemplateWriter().portfolio(facts)],
        }
    ]
    series = []
    for asset in recorded("assets"):
        at = f"assets/{asset['slug']}"
        last = recorded(f"{at}/bars.1Hour")["bars"][-1]["close"]
        before = recorded(f"{at}/bars.1Day")["bars"][-2]["close"]
        change = round((last / before - 1) * 100, 1)
        moved = (
            "unchanged since the last close"
            if change == 0
            else f"{'up' if change > 0 else 'down'} {abs(change)}% since the last close"
        )
        items.append(
            {
                "symbol": asset["symbol"],
                "name": asset["name"],
                "sentences": [
                    {"text": f"{asset['name']}: {money(last)} now, {moved}.", "section": "price"}
                ],
            }
        )
        for timeframe in ("1Hour", "1Day"):
            bars = recorded(f"{at}/bars.{timeframe}")["bars"]
            series.append(
                {
                    "symbol": asset["symbol"],
                    "timeframe": timeframe,
                    "is_primary": True,
                    "bars": len(bars),
                    "first_ts": bars[0]["ts"],
                    "last_ts": bars[-1]["ts"],
                    "lag_seconds": 600.0,
                    "missing_share": 0.0,
                    "stale": False,
                }
            )
    stamp = now.isoformat()
    keep("briefs/latest", {"day": now.date().isoformat(), "generated_at": stamp, "items": items})
    keep(
        "health",
        {
            "status": "ok",
            "database": True,
            "generated_at": stamp,
            "last_sync": stamp,
            "stream_clients": 1,
            "quality": {"failures": 0, "warnings": 0, "findings": 0, "last_run": stamp},
            "series": series,
        },
    )
    risk = {h.symbol: round(h.risk_share, 3) for h in analysis.xray.holdings}
    sys.stdout.write(f"value {analysis.value:.0f}; risk shares {risk}; level {level.label}\n")
    for step in steps.steps:
        rungs = [(round(r.price, 2), round(r.amount)) for r in step.rungs]
        sys.stdout.write(f"{step.kind} {step.name} {step.amount:.0f} {rungs}\n")


if __name__ == "__main__":
    main()
