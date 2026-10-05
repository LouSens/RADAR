# %% [markdown]
# # Expected swings and downside risk
#
# Two questions, answered one after the other because the second uses the first.
#
# 1. **How large are the price swings likely to be next?** (volatility forecast)
# 2. **How much could be lost in a bad period, and how often has that limit been
#    broken?** (Value at Risk and expected shortfall)
#
# Everything shown is "walk-forward": each forecast was made from data up to its own day
# by a model fitted on earlier days, then compared with what happened.
#
# Rebuild with `uv run python backend/scripts/build_notebooks.py 04_volatility_and_risk`.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import select

from radar.db.models import RiskMetric, VolatilityForecast
from radar.db.session import make_engine, session_scope
from radar.models import tail_risk, volatility
from radar.pipelines import risk as risk_job
from radar.pipelines import volatility as volatility_job
from radar.pipelines.datasets import build_regime_observations
from radar.universe import get_universe

plt.rcParams.update({"figure.figsize": (11, 3.4), "axes.grid": True, "grid.alpha": 0.3})
pd.set_option("display.float_format", lambda v: f"{v:.4f}")
engine, universe = make_engine(), get_universe()
symbols = [a.symbol for a in universe.primary]
NAMES = {"har": "HAR regression", "gbt": "Tree model", "carry": "Yesterday repeated", "regime": "Regime average"}

with session_scope(engine) as session:
    forecasts = pd.read_sql(select(VolatilityForecast), session.connection())
    risk = pd.read_sql(select(RiskMetric), session.connection())
    vol_metrics = {s: volatility_job.current_model(session, s).metrics["horizons"] for s in symbols}
    vol_params = {s: volatility_job.current_model(session, s).params for s in symbols}
    risk_metrics = {s: risk_job.current_model(session, s).metrics for s in symbols}
    btc = build_regime_observations(session, universe.get("BTC/USD"))

# %% [markdown]
# ## Part 1. The volatility forecast
#
# ### The idea behind HAR
#
# Tomorrow's swings look like a blend of three things: how rough **yesterday** was, how
# rough the **last week** was, and how rough the **last month** was. HAR is a plain
# regression on those three numbers. It is simple and famously hard to beat.

# %%
features = volatility.har_features(btc["rv"]).dropna()
fig, ax = plt.subplots()
recent = features.iloc[-400:]
for column, label in (("log_day", "last day"), ("log_week", "last week"), ("log_month", "last month")):
    ax.plot(recent.index, np.exp(recent[column]), label=label, linewidth=1)
ax.set(title="BTC/USD: the three inputs to HAR, last 400 days (daily swing size)", yscale="log")
ax.legend();

# %%
# The fitted weights of the latest model, for the one-day horizon. A larger weight means
# that input matters more for the next day's swings.
pd.DataFrame({s: vol_params[s]["1"]["coefficients"] for s in symbols}).T.rename(
    columns={"log_day": "last day", "log_week": "last week", "log_month": "last month"}
)

# %% [markdown]
# ### Forecast against what happened

# %%
fig, axes = plt.subplots(1, 3, figsize=(14, 3.4))
for ax, s in zip(axes, symbols):
    part = forecasts[(forecasts["symbol"] == s) & (forecasts["horizon_days"] == 1) & (forecasts["model"] == "har")].sort_values("ts").iloc[-365:]
    ax.plot(part["ts"], part["realised"], color="lightgrey", linewidth=0.8, label="what happened")
    ax.plot(part["ts"], part["forecast"], color="tab:blue", linewidth=1.2, label="forecast")
    ax.set(title=f"{s}: next-day swing, last {len(part)} forecasts")
    ax.tick_params(axis="x", rotation=30)
axes[0].legend();

# %% [markdown]
# ### Is it better than the alternatives?
#
# Four methods are scored on the same unseen days with QLIKE, a standard loss for
# volatility forecasts (0 is perfect; lower is better). The Diebold-Mariano test then
# asks whether each method's difference from HAR could be chance: a p-value under 0.05
# means the difference is real.

# %%
rows = []
for s in symbols:
    for horizon, evaluation in vol_metrics[s].items():
        for score in evaluation["scores"]:
            rows.append({"market": s, "horizon (days)": int(horizon), "unseen days": evaluation["n"],
                         "method": NAMES[score["model"]], "QLIKE": score["qlike"],
                         "p-value against HAR": score.get("dm_p_value_vs_har"),
                         "shown in the app": score["model"] == evaluation["shown"]})
scores = pd.DataFrame(rows).set_index(["market", "horizon (days)", "method"])
scores

# %%
one_day = scores.xs(1, level="horizon (days)")["QLIKE"].unstack("method")[list(NAMES.values())]
ax = one_day.plot.bar(figsize=(9, 3.4), rot=0)
ax.set(title="Next-day forecast error by method (QLIKE, lower is better)", xlabel="");

# %% [markdown]
# **What this says.** HAR beats "yesterday repeated" by a wide margin everywhere. The
# tree model, which also sees the regime probabilities, is never better than HAR on
# unseen days, so the app shows HAR. The tree model does not yet have news tone as an
# input; that comparison is repeated once it does.
#
# ## Part 2. Downside risk
#
# - **Value at Risk (95%)**: the loss that should be exceeded in only 1 period in 20.
# - **Expected shortfall**: the average loss in the periods that do exceed it.
#
# Three ways to estimate them are compared:
#
# - *historical*: take the worst outcomes of the last 500 periods as they were;
# - *filtered*: scale those past outcomes to today's expected swings (from Part 1), so
#   calm history counts for more in rough markets;
# - *simulator*: read the limit off the outlook simulation.

# %%
fig, axes = plt.subplots(1, 3, figsize=(14, 3.4))
for ax, s in zip(axes, symbols):
    part = risk[(risk["symbol"] == s) & (risk["horizon_days"] == 1) & (risk["level"] == 0.95)].sort_values("ts")
    recent = part[part["ts"] >= part["ts"].max() - pd.Timedelta(days=730)]
    filtered = recent[recent["method"] == "filtered"]
    ax.bar(filtered["ts"], filtered["realised_loss"].clip(lower=0), color="lightgrey", width=1, label="loss that followed")
    for method, colour in (("historical", "tab:orange"), ("filtered", "tab:blue")):
        line = recent[recent["method"] == method]
        ax.plot(line["ts"], line["var"], color=colour, linewidth=1.1, label=f"{method} limit")
    ax.set(title=f"{s}: 1-day 95% loss limit, last two years")
    ax.tick_params(axis="x", rotation=30)
axes[0].legend(fontsize=8);

# %% [markdown]
# The filtered limit (blue) moves with market conditions; the historical one (orange)
# reacts slowly. A grey bar poking above a line is a **breach**: the loss was larger
# than the limit said it should be.
#
# ### Counting breaches
#
# A 95% limit should be broken about 5% of the time. Kupiec's test checks whether the
# actual rate is close enough to that; a p-value under 0.05 marks the limit as
# unreliable. A second test (clustering) checks whether breaches arrive in bunches.

# %%
rows = []
for s in symbols:
    for horizon, stored in risk_metrics[s]["horizons"].items():
        for b in stored["backtests"]:
            rows.append({"market": s, "horizon (days)": int(horizon), "method": b["method"], "level": b["level"],
                         "periods": b["n"], "breaches": b["breaches"], "expected": round(b["expected_breaches"], 1),
                         "Kupiec p": b["kupiec_p_value"], "clustering p": b["clustering_p_value"],
                         "reliable": b["reliable"], "shown": b["method"] == stored["shown"]})
backtests = pd.DataFrame(rows).set_index(["market", "horizon (days)", "level", "method"]).sort_index()
backtests

# %%
rate = backtests.assign(ratio=backtests["breaches"] / backtests["expected"]).xs(1, level="horizon (days)")["ratio"].unstack("method")
ax = rate.plot.bar(figsize=(10, 3.4), rot=0)
ax.axhline(1.0, color="black", linewidth=0.8)
ax.set(title="1-day limits: breaches divided by expected breaches (1.0 is ideal)", xlabel="");

# %% [markdown]
# Bars near 1.0 are limits that held as stated. Well above 1.0 means the limit was too
# tight (broken too often); well below means too loose.
#
# ### The deepest falls on record

# %%
pd.concat({s: pd.DataFrame(risk_metrics[s]["drawdowns"]) for s in symbols}).droplevel(1)

# %% [markdown]
# ## What to take from this
#
# - Swings are forecastable to a useful degree, and a three-number regression does it
#   better than a more complex model here.
# - Scaling past losses to expected swings gives the most reliable loss limits for most
#   markets and horizons. The app shows whichever method had the best backtest and marks
#   any limit that failed its test.
# - The 7-day test uses periods that do not overlap, so it has few of them (about 190
#   for Bitcoin). A 99% limit judged on that few periods is rough.
