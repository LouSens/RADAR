# What RADAR is

A full description of this directory for someone who has never seen it. Written
2026-10-07. For the criticism of all this, read `AUDIT.md` beside it.

## 1. In one paragraph

RADAR is a private web app for one person. It collects prices and news for Bitcoin,
gold and US stocks, reads what you hold (typed in, from a CSV file, or from Binance with
a read-only key), and shows you the state of those markets, how risky your mix is, what
range of outcomes is plausible, and what happens if you keep paying in each month. It
never buys or sells. As of 2026-10-07 its stated purpose is to be a **personal portfolio
assistant**; before that it was a market outlook dashboard, and most of what is built
still reflects the older purpose.

## 2. Words used in this project

| Word | Meaning here |
|---|---|
| Bar | One period of prices: open, high, low, close, volume. RADAR stores hourly and daily bars |
| Return | The percentage change from one close to the next |
| Swing / volatility | How large the daily moves have been. High means rough |
| Regime / state | A label for the market's mood: calm, normal, turbulent |
| Walk-forward | Testing a model only on days after the ones it learned from, moving forward in time |
| Lookahead | Accidentally using information from the future. Forbidden everywhere |
| Baseline | The simple rival a method must beat, such as "always say up" |
| Planted pattern | Made-up answers with a known rule, to check a model is able to learn at all |
| Paying in / DCA | Putting in the same amount at regular intervals |
| Track record | What actually followed each past case of a signal |

## 3. How the pieces fit

```
 WHERE DATA COMES FROM              BACKEND (Python, folder backend/src/radar)             WHAT YOU SEE
┌───────────────────────┐   ┌─────────────────────────────────────────────────────┐   ┌─────────────────┐
│ Alpaca (paper keys)   │   │ providers/  talk to outside services, read-only     │   │ Home            │
│  prices, news         │──▶│ ingest/     download and store, raw copy kept       │   │ Markets         │
│ Binance (read key)    │   │ quality/    find gaps and bad bars, flag them       │   │  └ one market   │
│  your balances        │──▶│ features/   returns, swings, calendars, aligning    │   │ Portfolio       │
│ events.toml           │   │ models/     the maths: state, range, risk, mixes    │──▶│ Signals         │
│  Fed, jobs, inflation │──▶│ analytics/  studies: correlations, events, levels   │   │ Calendar        │
│ CFTC, Binance public  │   │ signals/    "something changed" rules + records     │   │ (System, hidden)│
│  research only        │──▶│ brief/      daily summary, every number checked     │   └─────────────────┘
└───────────────────────┘   │ pipelines/  run the steps above in the right order  │     React app in
                            │ api/        hand results to the web app             │     frontend/src
                            │ db/         23 tables in Postgres                   │
                            └─────────────────────────────────────────────────────┘
  Runs as four containers: database, api, worker (hourly sync + live prices), web.
```

**The path of one number.** Alpaca sends a daily bar → `ingest` stores it untouched and
writes a cleaned copy → `features` turns closes into returns and swings → a model in
`models` produces, say, tomorrow's expected swing → a `pipeline` saves that to a table
→ `api` serves it → a card on the screen shows it with its sample size and trust grade.

## 4. The folders

| Folder | What is in it |
|---|---|
| `backend/src/radar/` | All application code, about 21,000 lines |
| `backend/tests/` | 581 tests mirroring the code; no test calls a live service |
| `backend/scripts/` | Builds the notebooks from their sources |
| `frontend/src/` | The web app: 6 pages, 38 shared components, about 13,500 lines |
| `docs/PROJECT_SPEC.md` | The original 700-line specification (now out of date) |
| `docs/DATA_AUDIT.md` | Measured facts about what Alpaca really provides |
| `docs/DATA_PROFILE.md` | Measured facts about the stored data |
| `docs/DECISIONS.md` | 70 numbered decisions, each with its reason. The project's memory |
| `notebooks/` | 15 research reports, committed with their charts and tables |
| `notebooks/src/` | The plain Python each notebook is built from |
| `data/` | Not in git: raw bars, trained models, research downloads |
| `CLAUDE.md` | Working rules and current status for the AI assistant |
| `docker-compose.yml`, `Makefile` | How to start everything |

## 5. What each method is and whether it holds up

### Market state (`models/regime.py`, notebook 02)
A **hidden Markov model**: it assumes the market is always in one of a few unseen moods
and learns them from two numbers a day, the return and the size of recent swings. The
app shows the mood using only data up to that day. *Holds up as a description of now.
It does not predict the next mood change.*

### Outlook range (`models/simulator.py`, `calibration.py`, notebook 03)
A **Monte Carlo simulation**: thousands of made-up futures, each built by drawing a
mood for every day ahead and then a real past return from that mood. The spread of the
futures is the range shown. Past ranges are checked against what happened, and widened
or narrowed accordingly (conformal adjustment). *Holds up as a range. It says nothing
about direction.*

### Swings ahead (`models/volatility.py`, notebook 04)
**HAR regression**: the next days' swing predicted from the swing of the last day, week
and month. Compared with boosted trees and two simple rivals, walk-forward. *This is the
strongest result in the project. How rough the coming days will be is forecastable.*

### Loss limits (`models/tail_risk.py`, notebook 04)
**Value at Risk** (the loss exceeded only 5% of the time) and **expected shortfall**
(the average loss when it is exceeded), estimated three ways and back-tested by counting
how often the limit broke. *Holds up.*

### News tone (`models/sentiment.py`, `finetune.py`, `topics.py`, `lexicon.py`, notebooks 05 and 06)
**FinBERT**, a language model for financial text, scores each article from −1 to +1. A
version fine-tuned on our own labelled headlines exists. Topics are assigned by a second
model without training. An **event study** asks whether tone leads price. *The models
run; the result is that news tone improves no forecast (decision 045). Low usefulness.*

### What a market moves with (`models/drivers.py`)
**Ridge regression** of a market's daily return on stocks, the dollar, bonds and
expected volatility. *Descriptive only.*

### Markets together (`analytics/correlation.py`, `transmission.py`)
Rolling **correlations**, what happened to one market after another turned turbulent,
and weekend gaps in crypto. *Descriptive; little use for one person's portfolio.*

### Portfolio risk (`models/portfolio.py`, notebook 07)
The **X-ray**: how much the whole mix swings and which holding each part of that comes
from. Loss limits for the mix. Replays of past bad episodes. *Holds up. Works from
quantities and current prices; it does not know what you paid.*

### Ways to split a portfolio (`models/allocation.py`, notebook 07)
Five rules: as it is, equal weights, smallest swings, equal risk from each holding, and
hierarchical risk parity. Back-tested walk-forward. *Correct; differences between the
clever rules are small and unreliable on this much data.*

### Value range for the portfolio (`models/portfolio_simulation.py`, notebook 07)
A **block bootstrap**: futures made by gluing together short runs of real past days,
all holdings at once, so they keep moving together as they really did. *Works, but did
not beat a plain bell-curve range, and the app says so.*

### Regular buying (`models/regular_buying.py`, notebook 09)
The same bootstrap, with a fixed amount bought at a fixed interval, compared with
putting the same total in at once. *Works as a simulator.*

### Signals (`signals/detect.py`, `track.py`, notebook 08)
Three rules: the market's state changed; an hour's move was 5 times its usual size; news
tone jumped (scored, never shown). Each is replayed through history to build a track
record. *No signal predicts direction. Abnormal moves in US stocks were followed by
larger moves.*

### Scheduled events (`analytics/events.py`, notebook 10)
Dates of Fed decisions, jobs and inflation reports, with five questions fixed in
advance. *Gold moves more on Fed days, stocks on jobs days. No pattern in direction.*

### Daily brief (`brief/`)
A written summary built from stored results by a template. A check refuses any number
in the text that is not in the data it was given. A slot for a language model exists
and is not connected.

### Research that came back negative (notebooks 11 to 15)

| Notebook | Question | Method | Answer |
|---|---|---|---|
| 11 | Do indicators and levels tell direction? | RSI, moving averages, order blocks, fair value gaps, support, resistance; boosted trees; sizing rules | No. Some tell the *size* of the next move |
| 12 | Can a neural network on hourly bars? | LSTM, small trees, logistic regression; train, validate, test in time order | No. 0 of 9 passed |
| 13 | Is there a right time to hold cash? | Swings and 200-day rules on 24 fresh markets | Falls less than holding everything, but no better than a fixed smaller share |
| 14 | Does outside data help? What about selling at break-even or waiting for dips? | Trader positioning, funding rates, buy-side volume; three ways of paying in | No direction call. Paying in on schedule mostly won; cutting at break-even is insurance with a price |
| 15 | When in the month to pay in? Can a dip be forecast? | Eight readings; a four-model voting ensemble on 27 markets pooled | First run: every reading paid more than the scheduled day. Not yet written up |

## 6. The screens

| Place | Address | Contents |
|---|---|---|
| Home | `/` | Daily brief, newest signals, coming events |
| Markets | `/markets`, `/asset/...` | Per market: in brief, state, outlook, swings, loss limits, news, outside forces |
| Markets together | `/together` | Correlations, risk spreading, weekend gaps |
| Portfolio | `/portfolio/...` | Holdings, X-ray, loss limits, stress, try a mix, compare mixes, range ahead, regular buying, core and satellite |
| Signals | `/signals` | Feed and a track record per kind of signal |
| Calendar | `/calendar` | Coming events and how markets behaved around past ones |
| System | `/system` | Data health; hidden unless something is wrong |

Every claim on screen carries a trust mark (Solid, Fair, Rough) from fixed rules, and
its sample size and period.

## 7. Rules the project never breaks

- No trading, order, or transfer call, to any service. A test enforces it.
- Alpaca paper keys only, and only the market-data host.
- Keys live in `.env`, are never printed, and are never read by the AI assistant.
- No lookahead; every model has a test proving it.
- Tests in time order only; nothing is shuffled.
- A test's rules and pass mark are written into `DECISIONS.md` before it is run.
- A rule that failed its test is never turned into a suggestion.

## 8. How to run it

```bash
make up        # start database, api, worker, web; app on http://localhost:8080
```

```bash
make migrate   # create the tables
```

```bash
make backfill  # download history, about 17 minutes the first time
```

After that the analysis commands are run by hand, in order: `uv run radar regime`,
`simulate`, `volatility`, `risk`, `sentiment`, `track`, `portfolio`, `relationships`,
`signals`, `events`, `brief`. `make test` and `make lint` check everything.

## 9. How the purpose changed

| When | What RADAR was meant to be |
|---|---|
| Phases 0 to 4 | A market outlook dashboard: state, range, news |
| Phase 5 | Plus a portfolio layer on top |
| Phase 6 | Plus signals and a daily brief |
| Notebooks 11 to 15 | A search for something that times buying and selling |
| 2026-10-07 | A personal portfolio assistant; markets, news and signals become inputs |

## 10. Where things stand today

- Everything through pull request 21 is merged to `main`.
- Branch `pay-in-timing` holds the written-down test (decision 070) and its code.
  Notebook 15 has been run once and is not committed or written up.
- The portfolio-first home screen, the "how much to hold" tool, and purchase history do
  not exist yet.

## 11. What RADAR can honestly tell you, and what it cannot

| It can | It cannot |
|---|---|
| How risky your mix is and where the risk comes from | Which way a price goes next |
| How rough the coming days are likely to be | The best day or price level to buy |
| A range for your portfolio's value ahead | When to sell before a fall |
| What paying in monthly could lead to | Whether news will move the price |
| How far a given cash share would have fallen | Your real gain or loss (it does not know what you paid) |
| When a scheduled event is coming and how big moves tend to be | Anything about your currency, fees or tax |
