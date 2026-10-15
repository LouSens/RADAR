# Notebooks

A notebook is where an idea is tried and explained. What holds up becomes tested code in
`backend/src/radar/` and a screen in the app. Every example portfolio and trader in them
is made up.

| Notebook | Question | Code it explains | Used in the app |
|---|---|---|---|
| `01_exploration` | What data is there, and how clean is it? | `features/`, `quality/` | Everywhere |
| `02_state_and_range` | What state is a market in, and what range of prices is plausible? | `models/regime.py`, `simulator.py`, `calibration.py` | Current state, Price range ahead |
| `03_swings_and_loss` | How much will it move, and how bad could a bad day be? | `models/volatility.py`, `tail_risk.py` | Daily movement, Possible loss |
| `04_news` | Can headline tone be scored accurately on a laptop GPU? | Self-contained: trains the tone model the app loads | News |
| `05_portfolio_and_paying_in` | Where does a mix's risk sit, and what does paying in regularly lead to? | `models/portfolio.py`, `portfolio_simulation.py`, `regular_buying.py` | Portfolio |
| `06_trading_record` | What do a person's own trades say about how they trade? | `models/ledger.py`, `analytics/trading.py` | Your record |

Sources are in `src/`; rebuild one with
`uv run python backend/scripts/build_notebooks.py <name>`.

## `04_news`

Self-contained: it imports nothing from the app and needs no database. It reads the raw
Alpaca news under `data/raw/alpaca_news/` and the files in `labels/`:

| File | What it is |
|---|---|
| `labels/RUBRIC.md` | The labelling rubric: three classes (0 positive, 1 negative, 2 neutral), whose price, facts against opinion, the contrast rule, market impact |
| `labels/sample.csv` | Which articles were drawn for labelling, their split and how many passes each gets |
| `labels/tone_labels.csv` | Every pass's label, by article id (no headline text: it is the provider's) |

Pipeline: audit → cleaning → exploratory analysis → token-length audit → time-ordered
split with an embargo → stage A, task-adaptive pre-training on the unlabelled
train-period archive (LoRA, merged) → stage B, LoRA fine-tuning with a ticker × tone
balanced sampler and a pre-declared settings search → a single test → the saved model
and its card in `data/models/finbert-tone/`. It needs `uv sync --extra nlp`; a full run
takes about an hour on an RTX 4050 Laptop GPU (6 GB). `TONE_FAST=1` runs a quick check.

The other notebooks still import `radar` and read the database (`make up`); making them
self-contained is open work.
