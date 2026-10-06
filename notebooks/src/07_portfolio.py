# %% [markdown]
# # The portfolio: where the risk sits, steadier mixes, and the range ahead
#
# This notebook walks through every model behind the Portfolio screen, in the order the
# screen uses them:
#
# 1. **The risk model.** How much each holding swings and how they move together.
# 2. **Risk by holding.** A holding's share of the money is not its share of the risk.
# 3. **Other ways to split the same holdings**, each run through the past month by month.
# 4. **The value range ahead**, drawn by gluing together runs of real past days.
# 5. **Is that range any good?** Past ranges checked against what happened next.
# 6. **Core and satellite.** What each group carries and what it added.
#
# It imports the same modules the app runs, so what is shown here cannot drift from what
# the app does.
#
# **The portfolio used here is a made-up example**, not anyone's real holdings: 30% US
# stocks, 15% gold, 15% Bitcoin, and 40% cash, worth $10,000.
#
# Rebuild with `uv run python backend/scripts/build_notebooks.py 07_portfolio`.

# %%
from typing import get_args

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

from radar.db.session import make_engine, session_scope
from radar.models import allocation, simulator, sleeves
from radar.models import portfolio as risk
from radar.models import portfolio_simulation as ahead
from radar.pipelines.datasets import build_mixed_panel
from radar.universe import get_universe

plt.rcParams.update({"figure.figsize": (11, 3.4), "axes.grid": True, "grid.alpha": 0.3})
pd.set_option("display.float_format", lambda v: f"{v:.4f}")
engine, universe = make_engine(), get_universe()

VALUE = 10_000.0
MIX = {"SPY": 0.30, "GLD": 0.15, "BTC/USD": 0.15}  # the rest, 40%, is cash
NAMES = {"SPY": "US stocks", "GLD": "Gold", "BTC/USD": "Bitcoin", "USD": "Cash"}
COLOURS = {"SPY": "tab:blue", "GLD": "goldenrod", "BTC/USD": "tab:orange", "USD": "tab:green"}
symbols = list(MIX)
weights = np.array([MIX[s] for s in symbols])

with session_scope(engine) as session:
    panel = build_mixed_panel(session, universe)

# Daily log returns on days when the US stock market was open. Bitcoin trades every day,
# so its weekend move is folded into Monday: every column describes the same days.
returns = panel.returns[symbols].dropna()
print(f"{len(returns):,} trading days, {returns.index[0].date()} to {returns.index[-1].date()}")

# %% [markdown]
# ## 1. The risk model
#
# Two things decide how much a mix swings: how much each holding swings on its own, and
# whether they swing together. Both are in one table, the **covariance matrix**.
#
# Measuring that table straight from the data is noisy: with a limited number of days,
# some of what looks like a relationship is luck. **Ledoit-Wolf shrinkage** pulls the
# measured table part of the way towards a very plain one (every holding the same size
# of swing, none related). How far to pull is worked out from the data: a lot when
# there are many holdings and few days, hardly at all when there are few holdings and
# many days.

# %%
cov = risk.covariance(returns)
spread = np.sqrt(np.diag(cov))
fitted = LedoitWolf().fit(returns.to_numpy())
print(f"Pulled {fitted.shrinkage_:.1%} of the way towards the plain table")

fig, (left, right) = plt.subplots(1, 2, figsize=(11, 3.4))
left.bar([NAMES[s] for s in symbols], spread * 100, color=[COLOURS[s] for s in symbols])
left.set(title="Typical daily swing of each holding", ylabel="% a day")
correlation = cov / np.outer(spread, spread)
image = right.imshow(correlation, vmin=-1, vmax=1, cmap="RdBu_r")
right.set_xticks(range(3), [NAMES[s] for s in symbols])
right.set_yticks(range(3), [NAMES[s] for s in symbols])
for i in range(3):
    for j in range(3):
        right.text(j, i, f"{correlation[i, j]:.2f}", ha="center", va="center")
right.set(title="How they move together (1 = always together)")
right.grid(False)
fig.colorbar(image, ax=right);

# %% [markdown]
# With three holdings and more than a thousand days, the pull is tiny: the direct
# measurement is already good, and shrinking changes almost nothing here. It earns its
# place when the table is measured on less data, as it is each month in section 3 (250
# days), and when a portfolio holds many more things.
#
# A bigger source of uncertainty is that **the relationships themselves change**. Below
# is how closely Bitcoin moved with US stocks, measured on each year separately, both
# directly and after shrinking.

# %%
rows = []
for start in range(0, len(returns) - 250 + 1, 250):
    year = returns.iloc[start : start + 250]
    raw = np.cov(year.to_numpy(), rowvar=False)
    shrunk = LedoitWolf().fit(year.to_numpy()).covariance_
    rows.append(
        {
            "from": year.index[0].date(),
            "measured directly": raw[0, 2] / np.sqrt(raw[0, 0] * raw[2, 2]),
            "after shrinking": shrunk[0, 2] / np.sqrt(shrunk[0, 0] * shrunk[2, 2]),
        }
    )
by_year = pd.DataFrame(rows).set_index("from")
by_year

# %% [markdown]
# The two columns are close, as expected. The rows are not: in some years Bitcoin moved
# with stocks strongly and in others only loosely. No single number for "how they move
# together" is right for every year, which is why every figure on the Portfolio screen
# states the days it was measured on.

# %% [markdown]
# ## 2. Risk by holding
#
# Each holding's **share of the risk** answers: of all the mix's swings, how much comes
# from this holding? It depends on the holding's size, how wildly it swings, and how
# much it moves with the others. The shares add up to exactly 100%.

# %%
shares = risk.risk_shares(weights, cov)
assert abs(shares.sum() - 1.0) < 1e-9

table = pd.DataFrame(
    {
        "share of money": list(weights) + [1 - weights.sum()],
        "share of risk": list(shares) + [0.0],
    },
    index=[NAMES[s] for s in symbols] + ["Cash"],
)
ax = table.plot.barh(color=["lightgrey", "tab:red"])
ax.set(title="Share of the money against share of the risk", xlabel="share")
ax.invert_yaxis()
table

# %% [markdown]
# Bitcoin is 15% of the money and most of the risk. Cash is 40% of the money and none of
# it. That gap is the single most useful fact about a mixed portfolio.
#
# The mix's own daily swing, and the same holdings if they always moved together (no
# benefit from mixing):

# %%
daily = float(np.sqrt(weights @ cov @ weights))
print(f"Typical day for the mix:        ±{daily:.2%}  (±${daily * VALUE:,.0f})")
print(f"If everything moved together:   ±{float(weights @ spread):.2%}")
print(f"US stocks alone:                ±{spread[0]:.2%}")
print(f"The mix moves {daily / spread[0]:.2f}× as much as US stocks")

# %% [markdown]
# ## 3. Other ways to split the same holdings
#
# Keeping the same three holdings and the same 40% in cash, there are other ways to
# divide the invested part:
#
# | split | the idea |
# |---|---|
# | current | as it is now |
# | equal | the same amount in each |
# | smallest movement | whichever split has swung least |
# | equal risk | each holding carries the same share of the risk |
# | grouped | group holdings that behave alike, then balance the groups |
#
# **How they are tested.** Each split is run through the past as it would really have
# been used. On the first day of each month (every 21 trading days) it looks at the 250
# days *before* that day, decides the split, pays a 0.1% cost on whatever it has to
# trade, and holds until the next month. It never sees a day before it happens.

# %%
simple = np.expm1(returns)
cash = 1 - weights.sum()
LABEL = {
    "current": "current",
    "equal": "equal",
    "min_variance": "smallest movement",
    "equal_risk": "equal risk",
    "hierarchical": "grouped",
}
results = {
    method: allocation.backtest(simple, method, weights, cash=cash)
    for method in get_args(allocation.Method)
}
summary = pd.DataFrame(
    {
        LABEL[m]: {
            "typical day": r.daily_volatility,
            "deepest fall": r.deepest_fall,
            "traded each month": r.turnover,
            "growth over the period": r.total_return,
            **{NAMES[s]: w * (1 - cash) for s, w in r.weights_now.items()},
        }
        for m, r in results.items()
    }
).T
first = next(iter(results.values()))
print(f"{first.n_days:,} trading days, {first.first_day} to {first.last_day}, {first.rebalances} rebalances")
summary

# %%
fig, ax = plt.subplots()
for method, result in results.items():
    ax.plot(result.path, label=LABEL[method], linewidth=1.4)
ax.set(title="Value of 1 unit at each monthly rebalance", xlabel="months")
ax.legend(ncol=5, fontsize=8);

# %% [markdown]
# Read the first two columns, not the last. The steadier splits (smallest movement,
# equal risk) had smaller typical days and shallower falls: that is what they are built
# to do, and it tends to carry over. "Growth over the period" is only what happened in
# these particular years. The split that put most into Bitcoin grew most and the one
# that put least into it grew least, because Bitcoin rose over the period. That says
# nothing about the next few years.
#
# **The no-lookahead check.** The split in force on a day must not change if the future
# changes. Below, everything after one date is replaced with nonsense and the splits
# decided before that date are compared.

# %%
before = allocation.rebalance_weights(simple, "min_variance", weights)
tampered = simple.copy()
tampered.iloc[900:] = 0.5
after = allocation.rebalance_weights(tampered, "min_variance", weights)
decided_before = before.index <= simple.index[900]
assert np.allclose(before[decided_before], after[decided_before])
print(f"{decided_before.sum()} splits decided up to day 900 are identical after rewriting every later day")

# %% [markdown]
# ## 4. The value range ahead
#
# **The question.** Where might this portfolio's value be in 30 or 90 trading days?
#
# **The method: a block bootstrap.** A simulated future is built from real past days.
#
# - Pick a random past day and take the **10 trading days** starting there, for all
#   three holdings at once. Then pick another run of 10, and another, until the future
#   is long enough.
# - Let the holdings grow or shrink through those days. Nothing is rebalanced and cash
#   does not move.
# - Do that 10,000 times and look at where the value ends up.
#
# **Why whole days, for every holding at once?** Because on a day stocks fell hard,
# Bitcoin usually fell too. Taking the same day for all three keeps that.
#
# **Why runs of days and not single days?** Because rough days tend to come in
# clusters. The chart below measures it: how strongly the size of one day's move is
# related to the size of the moves on later days. Drawing single days would shuffle any
# clusters away. Whether that matters for this mix is tested in section 5.

# %%
mix_daily = risk.mix_returns(returns, weights)
size = mix_daily.abs()
lags = range(1, 31)
fig, ax = plt.subplots()
ax.bar(lags, [size.autocorr(lag) for lag in lags], color="tab:blue")
ax.axvline(ahead.BLOCK + 0.5, color="black", linestyle="--", linewidth=1)
ax.text(ahead.BLOCK + 1, ax.get_ylim()[1] * 0.9, "length of a run (10 days)")
ax.set(
    title="How strongly the size of a day's move is related to the size of later days' moves",
    xlabel="trading days later",
    ylabel="correlation",
);

# %%
matrix = returns.to_numpy()
paths = ahead.simulate(matrix, weights, 90, seed=0)
fan = simulator.fan(paths, VALUE)

fig, ax = plt.subplots()
days = range(91)
ax.fill_between(days, fan["0.05"], fan["0.95"], color="tab:blue", alpha=0.15, label="9 in 10")
ax.fill_between(days, fan["0.25"], fan["0.75"], color="tab:blue", alpha=0.3, label="half")
ax.plot(days, fan["0.5"], color="tab:blue", label="middle")
for path in paths[:25]:
    ax.plot(days, [VALUE, *VALUE * np.exp(path)], color="grey", linewidth=0.4, alpha=0.6)
ax.set(title="10,000 simulated futures for the $10,000 example (25 drawn in grey)", xlabel="trading days ahead", ylabel="$")
ax.legend(loc="upper left", ncol=3);

# %%
stored = ahead.run(matrix, weights, VALUE)
rows = {}
for horizon in stored.horizons:
    s = horizon.summary
    eighty = next(i for i in s.intervals if i.level == 0.8)
    down5 = next(c for c in horizon.chances if c.change == -0.05)
    rows[f"{s.steps} trading days"] = {
        "middle outcome $": s.quantiles["0.5"],
        "8 in 10 end above $": eighty.low,
        "8 in 10 end below $": eighty.high,
        "typical deepest dip": s.expected_worst_drawdown,
        "chance of ending 5% down": down5.ends_beyond,
        "chance of being 5% down at some point": down5.touches,
    }
pd.DataFrame(rows).T

# %% [markdown]
# The last two columns answer different questions. Ending 5% down is rarer than being 5%
# down *at some point on the way*, because some dips recover. The app lets you pick any
# size of change and shows both.
#
# ## 5. Is that range any good?
#
# A range is only worth showing if past ranges held about as often as they claimed. The
# check is the same walk-forward idea as before:
#
# - Stand at a past date. Draw a 30-day range **using only the days before it**.
# - Look at what the portfolio actually did over the next 30 days.
# - Move on 30 days (so no two outcomes share a day) and repeat.
#
# If the "80% range" is honest, about 80% of outcomes should land inside it.

# %%
records = ahead.backtest(matrix, weights, 30)
dates = returns.index[[r.origin for r in records]]
low = np.array([r.bounds["0.8"][0] for r in records])
high = np.array([r.bounds["0.8"][1] for r in records])
realised = np.array([r.realised for r in records])
inside = (realised >= low) & (realised <= high)

fig, ax = plt.subplots()
ax.vlines(dates, np.expm1(low) * 100, np.expm1(high) * 100, color="tab:blue", alpha=0.5, linewidth=4, label="80% range drawn that day")
ax.scatter(dates[inside], np.expm1(realised[inside]) * 100, color="black", s=14, zorder=3, label="what happened (inside)")
ax.scatter(dates[~inside], np.expm1(realised[~inside]) * 100, color="tab:red", s=22, zorder=3, label="what happened (outside)")
ax.set(title=f"30-day ranges against what followed: {inside.sum()} of {len(records)} inside", ylabel="% change in value")
ax.legend(ncol=3, fontsize=8);

# %% [markdown]
# ### Against simpler methods
#
# Three ways of drawing the same range, checked on the same dates:
#
# - **Runs of 10 days**: what the app uses.
# - **Single days**: the same, but drawing one day at a time (clusters shuffled away).
# - **Bell curve**: assume every day is an independent draw from a bell curve with the
#   average and spread of the days so far.
#
# The table shows how often each range held. The closer to the stated level, the better.
# The last column is the average width of the 80% range: of two methods that hold equally
# often, the narrower one is more useful.

# %%
def scorecard(records: list[ahead.PastRange]) -> dict[str, float]:
    row = {f"{c.level:.0%} range held": c.inside / c.n for c in ahead.coverage(records)}
    row["cases"] = len(records)
    row["width of the 80% range"] = float(np.mean([np.expm1(r.bounds["0.8"][1]) - np.expm1(r.bounds["0.8"][0]) for r in records]))
    return row


compared = {}
for horizon in ahead.HORIZONS:
    compared[(f"{horizon} days", "runs of 10 days")] = scorecard(ahead.backtest(matrix, weights, horizon))
    compared[(f"{horizon} days", "single days")] = scorecard(ahead.backtest(matrix, weights, horizon, block=1))
    compared[(f"{horizon} days", "bell curve")] = scorecard(ahead.normal_backtest(matrix, weights, horizon))
pd.DataFrame(compared).T

# %% [markdown]
# **The plain result: the three methods cannot be told apart.** Their ranges held about
# equally often and are about equally wide. On this mix and these years, gluing runs of
# real days together is not measurably more accurate than a bell curve.
#
# Read the table with its sample size in mind, too. There are a few dozen 30-day cases
# and only about a dozen 90-day ones, so a difference of one or two cases between
# methods is not evidence of anything.
#
# So why does the app use the simulation?
#
# - It **does not assume a bell curve**. It can only produce days that really happened,
#   including the worst ones, for all holdings together.
# - It gives things a formula for the end point does not: **the dips on the way** and
#   the chance of touching a level before the end.
# - Its range is **in line with its stated level**, which is what the app grades it on:
#   the count of ranges that held must be one an honest range of that level would
#   plausibly produce.
#
# The app states the bell curve's record beside the simulation's and does not claim the
# simulation is more accurate.
#
# ### Does the length of a run matter?

# %%
by_block = {
    f"runs of {block}": scorecard(ahead.backtest(matrix, weights, 30, block=block))
    for block in (1, 5, 10, 20)
}
pd.DataFrame(by_block).T

# %% [markdown]
# The answer barely moves with the length of the run. That is reassuring in one way:
# the result does not hinge on the one number that was picked by judgement. It also
# agrees with the table above: for this mix, keeping clusters of rough days together
# makes little difference at these horizons.
#
# ### The no-lookahead check
#
# A range drawn at a past date must not change if later days change.

# %%
tampered = matrix.copy()
tampered[700:] = 0.5
again = ahead.backtest(tampered, weights, 30)
unchanged = [a.bounds == b.bounds for a, b in zip(records, again) if a.origin <= 700]
assert all(unchanged)
print(f"{len(unchanged)} ranges drawn up to day 700 are identical after rewriting every later day")

# %% [markdown]
# ## 6. Core and satellite
#
# A common way to organise a portfolio: a **core** meant to be held steadily and a
# smaller **satellite** part for more adventurous positions. Here stocks and gold are
# tagged core and Bitcoin satellite.
#
# The report asks two things of each group: how much of the risk does it carry for its
# share of the money, and what did it add over the last 250 trading days?

# %%
xray = risk.xray(returns, weights)
holdings = [*xray.holdings, risk.HoldingRisk(symbol="USD", weight=cash, daily_volatility=0.0, risk_share=0.0)]
tags = {"SPY": "core", "GLD": "core", "BTC/USD": "satellite"}
report = sleeves.report(holdings, tags, returns, "USD")

table = pd.DataFrame(
    {
        s.group: {
            "holds": ", ".join(NAMES[x] for x in s.symbols),
            "share of money": s.weight,
            "share of risk": s.risk_share,
            "added to return": s.contribution,
            "added in $": s.contribution * VALUE,
        }
        for s in report.sleeves
    }
).T
print(f"{report.n_days} trading days, {report.first_day} to {report.last_day}; all together {report.total_return:+.2%}")
table

# %%
fig, (left, right) = plt.subplots(1, 2, figsize=(11, 2.8))
colours = {"core": "tab:blue", "satellite": "tab:orange", "cash": "tab:green"}
for row, column in enumerate(("share of money", "share of risk")):
    start = 0.0
    for sleeve in report.sleeves:
        size = float(table.loc[sleeve.group, column])
        left.barh(column, size, left=start, color=colours[sleeve.group], label=sleeve.group if row == 0 else None)
        start += size
left.set(title="Money against risk", xlim=(0, 1))
left.legend(ncol=3, fontsize=8, loc="lower right")
left.invert_yaxis()
right.bar([s.group for s in report.sleeves], [s.contribution * 100 for s in report.sleeves], color=[colours[s.group] for s in report.sleeves])
right.set(title=f"Added to return over {report.n_days} trading days", ylabel="points");

# %% [markdown]
# The "added to return" figures replay **today's proportions** through the last year.
# They show how this mix would have done, not what anyone earned: the app does not know
# when anything was bought.
#
# ## What these models cannot tell you
#
# - **Everything here is drawn from the past few years.** A future unlike anything in
#   them (a crash deeper than any in the data, or holdings that stop moving together the
#   way they have) is not in the range.
# - **The splits are not recommendations.** They show how different rules behaved. The
#   steadier ones were steadier; none of them is "better" without knowing what the
#   holder wants.
# - **The simulated range has not beaten a bell curve.** It is calibrated, and it is
#   kept for what else it gives, but it is not a more accurate range on this data.
# - **Sample sizes are small for the long horizon.** About a dozen separate 90-day
#   periods fit in the data. The 30-day check rests on a few dozen.
# - **Holdings with a short price record** (a newly listed coin or stock) cannot be drawn
#   from. In the app their risk is estimated from the days they have and every outcome
#   is widened to allow for them; the screen says when that has been done.
