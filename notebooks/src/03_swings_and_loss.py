# %% [markdown]
# # How much will it move, and how bad could a bad day be?
#
# **In short.** Which way a price goes next cannot be told from its past. How *much* it
# moves can: rough days follow rough days. A forecast built from three numbers (how
# rough the last day, week and month were) beats every alternative tried here, and a
# loss limit built on past losses is broken about as often as it says it will be. The
# counts at the end of each step say where that fails.
#
# | Step | What it does | Code | Screen in the app |
# |---|---|---|---|
# | 1 | Forecasts the size of the next day's and week's movement | `radar.models.volatility` | Daily movement |
# | 2 | Turns that into a loss limit and counts how often it was broken | `radar.models.tail_risk` | Possible loss |
#
# Every forecast shown was made from prices up to its own day, by a model fitted on
# earlier days only, then compared with what happened next.
#
# Rebuild with `uv run python backend/scripts/build_notebooks.py 03_swings_and_loss`.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import select

from radar.db.models import RiskMetric, VolatilityForecast
from radar.db.session import make_engine, session_scope
from radar.models import volatility
from radar.notebooks import ACCENT, BAD, GOOD, INK, MUTED, use_style
from radar.pipelines import risk as risk_job
from radar.pipelines import volatility as volatility_job
from radar.pipelines.datasets import build_regime_observations
from radar.universe import get_universe

use_style()
engine, universe = make_engine(), get_universe()
MARKETS = {asset.symbol: asset.name for asset in universe.primary}
METHODS = {
    "har": "last day, week, month",
    "gbt": "tree model",
    "carry": "yesterday repeated",
    "regime": "average for the market's state",
}
LIMITS = {
    "historical": "past losses as they were",
    "filtered": "past losses scaled to the forecast",
    "simulator": "read off the simulation",
}

with session_scope(engine) as session:
    forecasts = pd.read_sql(select(VolatilityForecast), session.connection())
    risk = pd.read_sql(select(RiskMetric), session.connection())
    swing_scores = {
        s: volatility_job.current_model(session, s).metrics["horizons"] for s in MARKETS
    }
    swing_weights = {s: volatility_job.current_model(session, s).params for s in MARKETS}
    limit_scores = {s: risk_job.current_model(session, s).metrics for s in MARKETS}
    first = next(iter(MARKETS))
    example = build_regime_observations(session, universe.get(first))

for symbol, name in MARKETS.items():
    days = forecasts[(forecasts["symbol"] == symbol) & (forecasts["horizon_days"] == 1)]
    print(f"{name}: {days['ts'].nunique():,} days forecast, from {days['ts'].min():%Y-%m-%d}")

# %% [markdown]
# ## Step 1. The size of the next movement
#
# ### The three inputs
#
# The size of tomorrow's movement looks like a blend of how rough **yesterday** was, how
# rough the **last week** was, and how rough the **last month** was. The forecast is a
# plain regression on those three numbers (known as HAR).

# %%
inputs = volatility.har_features(example["rv"]).dropna().iloc[-400:]
fig, ax = plt.subplots()
for column, label, colour in (
    ("log_day", "last day", MUTED),
    ("log_week", "last week", ACCENT),
    ("log_month", "last month", INK),
):
    ax.plot(inputs.index, np.exp(inputs[column]) * 100, label=label, color=colour, lw=1)
ax.set(
    title=f"{MARKETS[first]}: the three inputs, last {len(inputs)} days",
    ylabel="size of a day's movement, %",
    yscale="log",
)
ax.legend(ncol=3);

# %%
# How much weight the fitted forecast puts on each input, for the next day.
weights = pd.DataFrame(
    {MARKETS[s]: swing_weights[s]["1"]["coefficients"] for s in MARKETS}
).T.rename(columns={"log_day": "last day", "log_week": "last week", "log_month": "last month"})
ax = weights[["last day", "last week", "last month"]].plot.bar(
    rot=0, color=[MUTED, ACCENT, INK], figsize=(8, 3)
)
ax.set(title="Weight on each input in the next-day forecast", xlabel="")
ax.legend(ncol=3);

# %% [markdown]
# ### The forecast beside what happened

# %%
fig, axes = plt.subplots(len(MARKETS), 1, figsize=(10, 2.3 * len(MARKETS)), sharex=True)
for ax, (symbol, name) in zip(axes, MARKETS.items()):
    part = forecasts[
        (forecasts["symbol"] == symbol)
        & (forecasts["horizon_days"] == 1)
        & (forecasts["model"] == "har")
    ].sort_values("ts").iloc[-365:]
    ax.plot(part["ts"], part["realised"] * 100, color=MUTED, lw=0.7, label="what happened")
    ax.plot(part["ts"], part["forecast"] * 100, color=ACCENT, lw=1.3, label="forecast")
    ax.set(title=f"{name}: last {len(part)} forecasts", ylabel="a day's movement, %")
axes[0].legend(ncol=2)
fig.tight_layout()

# %% [markdown]
# ### Is it better than the alternatives?
#
# Four methods are scored on the same days, none of which the method had seen. The
# score is a standard forecast error for movement size (QLIKE): 0 is perfect and lower
# is better. The last column asks whether a method's gap to the three-input forecast
# could be luck (Diebold-Mariano test): under 0.05, it is not.

# %%
rows = []
for symbol, name in MARKETS.items():
    for horizon, evaluation in swing_scores[symbol].items():
        for score in evaluation["scores"]:
            rows.append(
                {
                    "market": name,
                    "days ahead": int(horizon),
                    "days tested": evaluation["n"],
                    "method": METHODS[score["model"]],
                    "error": score["qlike"],
                    "gap could be luck (p)": score.get("dm_p_value_vs_har"),
                    "shown in the app": score["model"] == evaluation["shown"],
                }
            )
scores = pd.DataFrame(rows).set_index(["market", "days ahead", "method"])
scores

# %%
next_day = scores.xs(1, level="days ahead")["error"].unstack("method")[list(METHODS.values())]
ax = next_day.loc[list(MARKETS.values())].plot.bar(
    rot=0, color=[ACCENT, INK, MUTED, "#c9952b"], figsize=(9, 3.2)
)
ax.set(title="Next-day forecast error by method (lower is better)", xlabel="")
ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5));

# %%
# The claim in the summary, checked on the table rather than by eye.
best = scores["error"].groupby(level=["market", "days ahead"]).idxmin().map(lambda key: key[2])
print(best.value_counts().rename("times it had the lowest error").to_string())
shown = scores[scores["shown in the app"]].reset_index()["method"].value_counts()
print("\nshown in the app:", shown.to_dict())

# %% [markdown]
# **What this says.** The count above is the result: the method with the lowest error
# in each market and horizon, and the one the app shows. The tree model sees the same
# three numbers plus the market's state and does not do better for it. News tone was
# tested as a further input in a separate, pre-written test and gave no gain in any of
# twelve comparisons (`07_what_we_tested`), so it is not in the forecast.
#
# ## Step 2. A loss limit, and how often it was broken
#
# - **Loss limit (95%)**: the loss that should be exceeded on only 1 day in 20. Known
#   as Value at Risk.
# - **Average loss beyond it**: how bad the days past the limit were, on average. Known
#   as expected shortfall.
#
# Three ways of setting the limit are compared.

# %%
fig, axes = plt.subplots(len(MARKETS), 1, figsize=(10, 2.4 * len(MARKETS)), sharex=True)
for ax, (symbol, name) in zip(axes, MARKETS.items()):
    part = risk[
        (risk["symbol"] == symbol) & (risk["horizon_days"] == 1) & (risk["level"] == 0.95)
    ].sort_values("ts")
    recent = part[part["ts"] >= part["ts"].max() - pd.Timedelta(days=730)]
    scaled = recent[recent["method"] == "filtered"]
    lost = scaled["realised_loss"].clip(lower=0) * 100
    broke = scaled["realised_loss"] > scaled["var"]
    ax.bar(scaled["ts"], lost, color=np.where(broke, BAD, "#d5d8e2"), width=1)
    for method, colour in (("historical", INK), ("filtered", ACCENT)):
        line = recent[recent["method"] == method]
        ax.plot(line["ts"], line["var"] * 100, color=colour, lw=1.1, label=LIMITS[method])
    ax.set(title=f"{name}: one-day loss limit, last two years", ylabel="loss, %")
axes[0].legend(ncol=2)
fig.tight_layout()

# %% [markdown]
# Grey bars are the losses that followed. A red bar is a day that lost more than the
# scaled limit said it should. The scaled limit moves with the market; the unscaled one
# reacts slowly.
#
# ### Counting the broken limits
#
# A 95% limit should be broken about 5 days in 100. The table counts how often each was
# broken, how often it should have been, and whether the gap is too large to be luck
# (Kupiec's test). Thirty-six limits are tested at once, and by luck alone one or two
# of that many would look off, so a limit is marked unreliable only when its result
# still stands after allowing for that. A second test checks whether broken limits
# arrive in bunches.

# %%
rows = []
for symbol, name in MARKETS.items():
    for horizon, stored in limit_scores[symbol]["horizons"].items():
        for test in stored["backtests"]:
            rows.append(
                {
                    "market": name,
                    "days ahead": int(horizon),
                    "limit": f"{test['level']:.0%}",
                    "method": LIMITS[test["method"]],
                    "periods": test["n"],
                    "broken": test["breaches"],
                    "expected": round(test["expected_breaches"], 1),
                    "count is off (p)": test["kupiec_p_value"],
                    "in bunches (p)": test["clustering_p_value"],
                    "reliable": test["reliable"],
                    "shown in the app": test["method"] == stored["shown"],
                }
            )
limits = pd.DataFrame(rows).set_index(["market", "days ahead", "limit", "method"]).sort_index()
limits

# %%
ratio = (
    limits.assign(ratio=limits["broken"] / limits["expected"])
    .xs(1, level="days ahead")["ratio"]
    .unstack("method")
)
ax = ratio.plot.bar(rot=0, color=[MUTED, ACCENT, INK], figsize=(10, 3.2))
ax.axhline(1.0, color=INK, lw=0.8)
ax.set(title="One-day limits: times broken, divided by times expected (1.0 is right)", xlabel="")
ax.legend(loc="center left", bbox_to_anchor=(1.0, 0.5));

# %%
# The claim in the summary, checked: how many limits passed, by method.
passed = limits.groupby(level="method")["reliable"].agg(["sum", "count"])
passed.columns = ["passed", "tested"]
print(passed.to_string())
chosen = limits[limits["shown in the app"]].reset_index()["method"].value_counts()
print("
shown in the app, by method:", chosen.to_dict())
failed = limits[limits["shown in the app"] & ~limits["reliable"]]
print(f"\nlimits shown in the app that failed their test: {len(failed)}")
if len(failed):
    print(failed[["periods", "broken", "expected"]].to_string())

# %% [markdown]
# Bars near 1.0 are limits that held as stated. Well above 1.0, the limit was too tight
# and was broken too often; well below, it was too loose. The app shows, for each
# market and horizon, the method that did best here, and marks any limit that failed.
#
# ### The deepest falls on record

# %%
falls = pd.concat(
    {MARKETS[s]: pd.DataFrame(limit_scores[s]["drawdowns"]) for s in MARKETS}
).droplevel(1)
falls

# %% [markdown]
# ## What to take from this
#
# - The size of a movement can be forecast to a useful degree, and three numbers do it
#   as well as anything more elaborate tried here.
# - All three ways of setting a loss limit were broken about as often as they said
#   they would be: the count above is the result. For each market and horizon the app
#   shows the one that came closest, and marks any limit that failed.
# - The limit scaled to the forecast is the only one that tightens and loosens with
#   the market, which the two-year chart shows. That is a reason to prefer it when two
#   are equally close, not a result of the test.
# - The seven-day test uses weeks that do not overlap, so it has few of them. A 99%
#   limit judged on that few is rough: read the "periods" column before trusting it.
# - Gold is followed as PAX Gold, whose record starts in 2021, so its tests cover fewer
#   years than the other two.
