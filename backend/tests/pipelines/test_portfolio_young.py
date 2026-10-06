"""Newer holdings in the portfolio's risk figures: estimated on the history they have."""

import numpy as np
import pandas as pd
import pytest

from radar.features.panels import MixedPanel
from radar.models import portfolio as model
from radar.models.holdings import Holding
from radar.pipelines import portfolio as job
from radar.universe import Universe


def asset(symbol: str, primary: bool = False) -> dict[str, object]:
    base: dict[str, object] = {
        "symbol": symbol,
        "name": f"{symbol} name",
        "asset_class": "stock",
        "bars_symbol": symbol,
        "history_start": "2022-01-03",
    }
    if primary:
        base |= {"is_primary": True, "news_symbols": [symbol], "news_start": "2022-01-03"}
    return base


UNIVERSE = Universe.model_validate(
    {
        "crypto_location": "us-1",
        "timeframes": {"crypto": ["1Day"], "stock": ["1Day"]},
        "assets": [asset("OLD", primary=True), asset("STEADY"), asset("NEW"), asset("DAYONE")],
    }
)
DAYS = 600


def panel() -> MixedPanel:
    """OLD and STEADY have the full record. NEW was listed 100 sessions ago, swings three
    times as much as OLD and moves with it. DAYONE has ten sessions."""
    rng = np.random.default_rng(12)
    closes = pd.bdate_range("2022-01-03", periods=DAYS, tz="UTC") + pd.Timedelta(hours=21)
    old = rng.normal(0, 0.01, DAYS)
    returns = pd.DataFrame(
        {
            "OLD": old,
            "STEADY": rng.normal(0, 0.004, DAYS),
            "NEW": 2.4 * old + rng.normal(0, 0.018, DAYS),
            "DAYONE": rng.normal(0, 0.05, DAYS),
        },
        index=closes,
    )
    returns.loc[closes[: DAYS - 100], "NEW"] = np.nan
    returns.loc[closes[: DAYS - 10], "DAYONE"] = np.nan
    levels = pd.DataFrame(100 * np.exp(returns.fillna(0).cumsum()), index=closes)
    prices = levels.where(returns.notna())
    return MixedPanel(
        prices=prices,
        returns=returns,
        filled=pd.DataFrame(False, index=closes, columns=returns.columns),
        sessions=pd.DatetimeIndex(closes.tz_localize(None).normalize()),
    )


def held(*symbols: str) -> list[Holding]:
    return [Holding(symbol=s, quantity=1.0) for s in symbols]


def test_the_pieces_fit_into_one_valid_covariance() -> None:
    returns = panel().returns
    cov = model.covariance_with_young(returns[["OLD", "STEADY"]], returns[["NEW"]])
    assert cov.shape == (3, 3)
    np.testing.assert_allclose(cov, cov.T)
    assert np.linalg.eigvalsh(cov).min() > 0
    # The established block is the long-history estimate, untouched by the newcomer.
    np.testing.assert_allclose(cov[:2, :2], model.covariance(returns[["OLD", "STEADY"]]), rtol=1e-6)
    # The newcomer's own swings and its link to OLD come from its hundred sessions.
    assert np.sqrt(cov[2, 2]) == pytest.approx(returns["NEW"].dropna().std(), rel=0.02)
    correlation = cov[0, 2] / np.sqrt(cov[0, 0] * cov[2, 2])
    assert correlation == pytest.approx(0.8, abs=0.1)


def test_a_newer_holding_is_in_the_risk_figures_and_raises_them() -> None:
    data = panel()
    without = job.analyse(held("OLD", "STEADY"), data, UNIVERSE)
    with_new = job.analyse(held("OLD", "STEADY", "NEW"), data, UNIVERSE)

    assert with_new.unmeasured == []
    (young,) = with_new.young
    assert (young.symbol, young.name, young.days) == ("NEW", "NEW name", 100)
    assert with_new.covered_value == pytest.approx(with_new.value)

    shares = {h.symbol: h.risk_share for h in with_new.xray.holdings}
    assert sum(shares.values()) == pytest.approx(1.0)
    assert shares["NEW"] > 0.5  # the wildest holding carries most of the risk
    assert with_new.xray.daily_volatility > with_new.xray.established_volatility
    assert with_new.xray.n_days == DAYS  # the established record is not cut short

    # Loss limits are those of the established part, scaled up by what NEW adds.
    lift = with_new.xray.daily_volatility / with_new.xray.established_volatility
    assert lift > 1.5
    limit = with_new.limits[0].levels[0].methods[0]
    plain = (
        model.loss_limits(
            model.mix_returns(
                data.returns[["OLD", "STEADY"]],
                np.array([p.weight for p in with_new.positions if p.symbol != "NEW"]),
            )
        )[0]
        .levels[0]
        .methods[0]
    )
    assert limit.var == pytest.approx(plain.var * lift)
    assert limit.backtest == plain.backtest
    assert with_new.limits[0].levels[0].methods[0].var > 0

    # The trust mark says a short history was used.
    assert without.trust.xray.grade in {"solid", "fair"}
    assert with_new.trust.xray.grade == "fair"
    assert "newer holding" in with_new.trust.xray.reason


def test_a_holding_days_old_is_counted_in_money_and_left_out_of_risk() -> None:
    analysis = job.analyse(held("OLD", "DAYONE"), panel(), UNIVERSE)
    (left_out,) = analysis.unmeasured
    assert (left_out.symbol, left_out.days) == ("DAYONE", 10)
    assert analysis.young == []
    assert [h.symbol for h in analysis.xray.holdings] == ["OLD"]
    assert analysis.covered_value < analysis.value
    assert {p.symbol for p in analysis.positions} == {"OLD", "DAYONE"}
    assert sum(p.weight for p in analysis.positions) == pytest.approx(1.0)


def test_with_only_new_holdings_there_is_nothing_to_measure_against() -> None:
    with pytest.raises(model.NotEnoughHistoryError, match="250 sessions"):
        job.analyse(held("NEW"), panel(), UNIVERSE)
