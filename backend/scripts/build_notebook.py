"""Write and execute notebooks/01_exploration.ipynb from the stored data.

Run with `uv run python backend/scripts/build_notebook.py`. Needs the database running
and backfilled. The notebook draws its numbers from `radar.pipelines.profile`, the same
code that writes docs/DATA_PROFILE.md.
"""

import sys
from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

NOTEBOOK = Path("notebooks/01_exploration.ipynb")

CELLS: list[tuple[str, str]] = [
    (
        "markdown",
        "# RADAR data exploration\n\n"
        "Phase 1 look at the stored data: how much there is, how returns are distributed,\n"
        "whether volatility clusters, and how the assets move together. Every table comes\n"
        "from `radar.pipelines.profile`, which also writes `docs/DATA_PROFILE.md`.\n\n"
        "Rebuild with `uv run python backend/scripts/build_notebook.py`. Times are UTC.",
    ),
    (
        "code",
        "import matplotlib.pyplot as plt\n"
        "import numpy as np\n"
        "import pandas as pd\n\n"
        "from radar.db.session import make_engine, session_scope\n"
        "from radar.pipelines import profile as P\n"
        "from radar.pipelines.datasets import (\n"
        "    build_mixed_panel, build_realised_volatility, load_field, stock_daily,\n"
        ")\n"
        "from radar.universe import get_universe\n\n"
        "plt.rcParams.update({'figure.figsize': (10, 3.6), 'axes.grid': True, 'grid.alpha': 0.3})\n"
        "pd.set_option('display.float_format', lambda v: f'{v:.4f}')\n"
        "universe = get_universe()\n"
        "engine = make_engine()\n"
        "profile = P.build_profile(engine, universe)\n"
        "btc, gld = universe.get('BTC/USD'), universe.get('GLD')",
    ),
    ("markdown", "## History depth and missing data"),
    ("code", "profile.coverage"),
    (
        "markdown",
        "## Prices\n\nBitcoin from the Kraken feed (2021 on) and gold as GLD (2016 on), log scale.",
    ),
    (
        "code",
        "with session_scope(engine) as s:\n"
        "    btc_close = load_field(s, ['BTC/USD'], '1Day')['BTC/USD'].dropna()\n"
        "    gld_close = stock_daily(s, ['GLD'])['GLD'].dropna()\n"
        "fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))\n"
        "axes[0].plot(btc_close.index, btc_close.values, color='tab:blue')\n"
        "axes[0].set(title=f'BTC/USD daily close, n = {len(btc_close):,}', yscale='log')\n"
        "axes[1].plot(gld_close.index, gld_close.values, color='goldenrod')\n"
        "axes[1].set(title=f'GLD daily close, n = {len(gld_close):,}', yscale='log')\n"
        "plt.tight_layout()",
    ),
    (
        "markdown",
        "## Daily return distributions\n\n"
        "Bars are the observed returns; the line is a normal distribution with the same\n"
        "mean and standard deviation. The observed tails are fatter.",
    ),
    ("code", "profile.returns.set_index('symbol')"),
    (
        "code",
        "fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))\n"
        "with session_scope(engine) as s:\n"
        "    for ax, asset, colour in ((axes[0], btc, 'tab:blue'), (axes[1], gld, 'goldenrod')):\n"
        "        r = P.daily_returns(s, asset)\n"
        "        ax.hist(r, bins=80, density=True, color=colour, alpha=0.6)\n"
        "        x = np.linspace(r.min(), r.max(), 300)\n"
        "        ax.plot(x, np.exp(-0.5 * ((x - r.mean()) / r.std()) ** 2) / (r.std() * np.sqrt(2 * np.pi)), 'k', lw=1)\n"
        "        ax.set(title=f'{asset.symbol} daily log returns, n = {len(r):,}', yscale='log')\n"
        "plt.tight_layout()",
    ),
    (
        "markdown",
        "## Volatility clustering\n\n"
        "Autocorrelation of squared daily returns. Values that stay above zero mean large\n"
        "moves follow large moves, which is what the regime model relies on.",
    ),
    (
        "code",
        "fig, ax = plt.subplots()\n"
        "lags = range(1, 21)\n"
        "with session_scope(engine) as s:\n"
        "    for asset, colour, shift in ((btc, 'tab:blue', -0.2), (gld, 'goldenrod', 0.2)):\n"
        "        squared = P.daily_returns(s, asset) ** 2\n"
        "        ax.bar([lag + shift for lag in lags], [squared.autocorr(lag) for lag in lags],\n"
        "               width=0.4, color=colour, label=asset.symbol)\n"
        "ax.set(title='Autocorrelation of squared daily returns', xlabel='lag (days)')\n"
        "ax.legend();",
    ),
    (
        "markdown",
        "## Realised volatility\n\nDaily realised volatility from hourly bars, with a 30-day median.",
    ),
    ("code", "profile.volatility.set_index('symbol')"),
    (
        "code",
        "fig, axes = plt.subplots(1, 2, figsize=(12, 3.6))\n"
        "with session_scope(engine) as s:\n"
        "    for ax, asset, colour in ((axes[0], btc, 'tab:blue'), (axes[1], gld, 'goldenrod')):\n"
        "        rv = build_realised_volatility(s, asset)['rv'].dropna()\n"
        "        ax.plot(rv.index, rv.values, color=colour, lw=0.5, alpha=0.5)\n"
        "        ax.plot(rv.index, rv.rolling(30).median().values, color='k', lw=1)\n"
        "        ax.set(title=f'{asset.symbol} realised volatility, n = {len(rv):,} days')\n"
        "plt.tight_layout()",
    ),
    (
        "markdown",
        "## Bitcoin against gold\n\n"
        "Rolling 90-session correlation of daily returns on the mixed panel, where a\n"
        "weekend Bitcoin move is compared with gold's Friday-to-Monday move.",
    ),
    (
        "code",
        "with session_scope(engine) as s:\n"
        "    mixed = build_mixed_panel(s, universe)\n"
        "pair = mixed.returns[['BTC/USD', 'GLD']].dropna()\n"
        "rolling = pair['BTC/USD'].rolling(90).corr(pair['GLD']).dropna()\n"
        "fig, ax = plt.subplots()\n"
        "ax.plot(rolling.index, rolling.values, color='tab:purple')\n"
        "ax.axhline(0, color='k', lw=0.8)\n"
        "ax.set(title=f'BTC/USD and GLD, rolling 90-session correlation, n = {len(pair):,} sessions', ylim=(-1, 1));",
    ),
    ("code", "profile.correlation.round(2)"),
    ("markdown", "## News articles per month"),
    (
        "code",
        "from sqlalchemy import select\n"
        "from radar.db.models import NewsArticle, NewsSymbol\n"
        "with session_scope(engine) as s:\n"
        "    rows = s.execute(select(NewsSymbol.symbol, NewsArticle.created_at)\n"
        "                     .join(NewsArticle, NewsArticle.id == NewsSymbol.article_id)).all()\n"
        "news = pd.DataFrame(rows, columns=['symbol', 'created_at'])\n"
        "news['month'] = pd.to_datetime(news['created_at'], utc=True).dt.tz_localize(None).dt.to_period('M').dt.to_timestamp()\n"
        "monthly = news.groupby(['month', 'symbol']).size().unstack(fill_value=0)\n"
        "fig, ax = plt.subplots()\n"
        "for symbol, colour in (('BTC/USD', 'tab:blue'), ('GLD', 'goldenrod')):\n"
        "    ax.plot(monthly.index, monthly[symbol].values, color=colour, label=symbol)\n"
        "ax.set(title=f'News articles per month, n = {len(news):,} article links')\n"
        "ax.legend();",
    ),
]


def main() -> int:
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [
        nbformat.v4.new_markdown_cell(source)
        if kind == "markdown"
        else nbformat.v4.new_code_cell(source)
        for kind, source in CELLS
    ]
    ExecutePreprocessor(timeout=600, kernel_name="python3").preprocess(
        notebook, {"metadata": {"path": "."}}
    )
    NOTEBOOK.parent.mkdir(parents=True, exist_ok=True)
    with NOTEBOOK.open("w", encoding="utf-8", newline="\n") as handle:
        nbformat.write(notebook, handle)
    return 0


if __name__ == "__main__":
    sys.exit(main())
