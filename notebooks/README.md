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
in `src/`.

## Still owed

Notebooks 01 to 05 were merged and cut down without being run again, so their charts
and wording are as first built. Each still needs: the shared style
(`radar.notebooks.use_style`), the answer stated first, plainer chart titles and column
names, any logic written inside the notebook moved into tested code, and every holding
covered instead of three markets. `06_trading_record` is the pattern to follow.
