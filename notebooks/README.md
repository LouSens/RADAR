# Notebooks

A notebook is where an idea is tried. What holds up becomes tested code in
`backend/src/radar/` and a screen in the app; the notebook stays as the explanation.
Every example portfolio and every trader in them is made up.

| Notebook | Question | Code it explains | Used in the app |
|---|---|---|---|
| `01_exploration` | What data is there, and how clean is it? | `features/`, `quality/` | Everywhere |
| `02_state_and_range` | What state is a market in, and what range of prices is plausible? | `models/regime.py`, `simulator.py`, `calibration.py` | Current state, Price range ahead |
| `03_swings_and_loss` | How much will it move, and how bad could a bad day be? | `models/volatility.py`, `tail_risk.py` | Daily movement, Possible loss |
| `04_news` | Can the tone of headlines be scored, and how well? | `models/sentiment.py`, `finetune.py` | News |
| `05_portfolio_and_paying_in` | Where does a mix's risk sit, what range is its value in, and what does paying in regularly lead to? | `models/portfolio.py`, `portfolio_simulation.py`, `regular_buying.py` | Portfolio |
| `06_trading_record` | What do a person's own trades say about how they trade? | `models/ledger.py`, `analytics/trading.py` | Your record |
| `07_what_we_tested` | What was tried and did not work, and why? | (summary) | Not in the app, by decision |

`archive/` holds the seven full research notebooks that `07_what_we_tested` summarises.
`docs/DECISIONS.md` refers to them by their old numbers (08, 10, 11 to 15).

Old numbers, for reading older decisions: 02 and 03 are now `02_state_and_range`; 04 is
`03_swings_and_loss`; 05 and 06 are `04_news`; 07 and 09 are
`05_portfolio_and_paying_in`.

Rebuild one with `uv run python backend/scripts/build_notebooks.py <name>`. Sources are
in `src/`. `04_news` needs `uv sync --extra nlp` and the trained model's files.

## How each one is laid out

The answer comes first, then a table of each step with the code it runs and the screen
it feeds. Charts and tables use plain names. The closing section only repeats what a
count printed in the notebook supports. All of them use `radar.notebooks.use_style`.

The markets shown are the three the app follows. The example portfolio is made up, so
no notebook covers the user's own holdings; experiments on real holdings stay in the
gitignored `data/private/`.
