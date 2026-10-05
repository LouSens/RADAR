# %% [markdown]
# # Outlook: a range of outcomes, and how often past ranges held
#
# **The question.** What range of prices is plausible over the next day, week, or month?
#
# **The method.** A Monte Carlo simulation: play out 10,000 possible futures and look at
# where they end. Each future starts from today's regime probabilities. For every day
# ahead it first draws the next regime (using how regimes have followed each other),
# then draws that day's return from the **real past returns seen in that regime**.
# Drawing real returns keeps the occasional very large move that a textbook bell curve
# would miss.
#
# **Why you can check it.** For every past day, the same simulation is run using only
# what was known then, and its ranges are compared with what happened next. If the "80%
# range" really is one, it should have contained the outcome about 80% of the time.
#
# Rebuild with `uv run python backend/scripts/build_notebooks.py 03_outlook`.

# %%
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sqlalchemy import select

from radar.db.models import CalibrationReport
from radar.db.session import make_engine, session_scope
from radar.models import calibration, regime, simulator
from radar.pipelines import simulation as job
from radar.pipelines.datasets import build_regime_observations
from radar.pipelines.regime import current_model
from radar.universe import get_universe

plt.rcParams.update({"figure.figsize": (11, 3.4), "axes.grid": True, "grid.alpha": 0.3})
pd.set_option("display.float_format", lambda v: f"{v:.4f}")
engine, universe = make_engine(), get_universe()
asset = universe.get("BTC/USD")

with session_scope(engine) as session:
    observations = build_regime_observations(session, asset)
    model = regime.RegimeModel.model_validate(current_model(session, asset.symbol).params)
    run = job.latest(session, asset.symbol)
    stored_paths = job.decode_paths(run)
    stored = {"seed": run.seed, "as_of": run.as_of, "start_price": run.start_price, "n_paths": run.n_paths,
              "horizons": run.horizons}
    reports = pd.read_sql(select(CalibrationReport), session.connection())

# %% [markdown]
# ## 1. One simulation, step by step (Bitcoin)
#
# First, sort every past return by the regime of its day. These are the "pools" the
# simulation draws from. Notice how much wider the turbulent pool is.

# %%
clean = observations.dropna(subset=list(regime.FEATURES))
probabilities = regime.filtered_probabilities(model, clean).to_numpy()
returns = clean["ret"].to_numpy()
pools, thin = simulator.build_pools(returns, probabilities.argmax(axis=1), model.n_states)

fig, ax = plt.subplots()
bins = np.linspace(-0.15, 0.15, 61)
for label, pool, colour in zip(model.labels, pools, ("#3ddc97", "#9a9daa", "#ff6b5e")):
    ax.hist(pool, bins=bins, density=True, alpha=0.55, color=colour, label=f"{label}: n = {len(pool):,}, std = {pool.std():.3f}")
ax.set(title=f"{asset.symbol}: past daily returns by regime (the pools the simulation draws from)", xlabel="daily log return")
ax.legend();

# %%
print("Today's regime probabilities:", dict(zip(model.labels, probabilities[-1].round(3))))
pd.DataFrame(model.transition, index=model.labels, columns=model.labels).rename_axis("from / to").round(3)

# %% [markdown]
# The table above is the chance of moving from one regime (row) to another (column) in
# a day. The large numbers on the diagonal are why regimes persist.
#
# ### Reproducible from a seed
#
# The app stores each run's random seed. Re-running with that seed and the same data
# must give exactly the stored paths; otherwise a displayed number could not be traced.

# %%
inputs = simulator.SimulationInputs(probabilities[-1], np.array(model.transition), pools, returns)
again = simulator.cumulative_returns(simulator.simulate(inputs, 30, n_paths=stored["n_paths"], seed=stored["seed"]))
print(f"stored run: as of {stored['as_of']:%Y-%m-%d}, seed {stored['seed']}, {stored['n_paths']:,} paths")
print("largest difference between the stored paths and a rerun:", float(np.abs(again - stored_paths).max()))

# %%
prices = stored["start_price"] * np.exp(stored_paths)
days = np.arange(0, 31)
with_start = np.column_stack([np.full(len(prices), stored["start_price"]), prices])
fig, axes = plt.subplots(1, 2, figsize=(13, 3.6))
axes[0].plot(days, with_start[:60].T, color="tab:blue", alpha=0.25, linewidth=0.7)
for q, style in ((0.05, ":"), (0.5, "-"), (0.95, ":")):
    axes[0].plot(days, np.quantile(with_start, q, axis=0), color="black", linestyle=style)
axes[0].set(title="60 of the simulated paths, with the 5%, 50%, 95% lines", xlabel="days ahead")
axes[1].hist(prices[:, -1], bins=60, color="tab:blue", alpha=0.8)
axes[1].axvline(stored["start_price"], color="black", linestyle="--", label="price today")
axes[1].set(title=f"Where the {stored['n_paths']:,} paths end after 30 days")
axes[1].legend();

# %% [markdown]
# ### Two different questions about a price level
#
# "Will it **end** above X?" and "Will it **touch** X at some point?" have different
# answers. Touching is always at least as likely.

# %%
level = round(stored["start_price"] * 1.10, -2)
pd.DataFrame(
    [simulator.level_probabilities(stored_paths, steps, stored["start_price"], level).model_dump() for steps in (1, 7, 30)]
).set_index("steps")[["level", "ends_above", "touches"]]

# %% [markdown]
# ## 2. Checking it against history
#
# For every day after the first 500, with the regime model refitted on earlier days
# only, the simulation was run and its 50%, 80%, and 95% ranges compared with what
# happened. "Raw" is the simulation as it is. "Adjusted" applies a correction that
# widens the range after misses and narrows it after hits, using earlier results only
# (adaptive conformal inference).

# %%
table = reports.assign(
    raw=reports["empirical"], adjusted=reports["empirical_conformal"]
).pivot_table(index=["symbol", "horizon_days"], columns="nominal", values=["raw", "adjusted"])
table.round(3)

# %%
fig, axes = plt.subplots(1, 3, figsize=(13, 3.6), sharey=True)
for ax, (symbol, group) in zip(axes, reports.groupby("symbol")):
    for horizon, part in group.groupby("horizon_days"):
        part = part.sort_values("nominal")
        ax.plot(part["nominal"], part["empirical"], marker="o", label=f"{horizon}d raw")
        ax.plot(part["nominal"], part["empirical_conformal"], marker="x", linestyle="--", label=f"{horizon}d adjusted")
    ax.plot([0.45, 1], [0.45, 1], color="black", linewidth=0.8)
    ax.set(title=f"{symbol}: n = {int(group['n'].max()):,} past cases", xlabel="stated coverage")
axes[0].set(ylabel="how often the range held")
axes[0].legend(fontsize=7);

# %% [markdown]
# Points on the black line are perfectly calibrated. Above the line the ranges were too
# wide (held more often than stated); below, too narrow.
#
# ## 3. Against a simple forecast
#
# The rival is a random walk with constant volatility from the trailing year. Both are
# scored by pinball loss, a standard score for forecast ranges; lower is better.

# %%
loss = reports.drop_duplicates(["symbol", "horizon_days"])[["symbol", "horizon_days", "n", "pinball_model", "pinball_baseline"]].copy()
loss["simulator against simple forecast"] = loss["pinball_model"] / loss["pinball_baseline"] - 1
loss.set_index(["symbol", "horizon_days"]).style.format({"simulator against simple forecast": "{:+.1%}", "pinball_model": "{:.5f}", "pinball_baseline": "{:.5f}"})

# %% [markdown]
# A negative percentage means the simulator's error was smaller. It is not better
# everywhere, and the app says so where it is not.
#
# ## What to take from this
#
# - The ranges are honest in the measurable sense: they have held about as often as
#   they state, and the adjustment brings them closer still.
# - The simulation assumes the future resembles the sampled past. A kind of move that
#   has never happened in the data cannot appear in it.
# - For the 95% range at long horizons the adjustment is sometimes at its widest
#   setting, so that range covers nearly every simulated outcome.
