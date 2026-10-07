# Decisions

Short log of design decisions and why. Newest at the bottom. Open questions that need
the user's answer are marked **OPEN**.

## 001. No message broker in version 1 (2026-10-05)

The worker writes to Postgres and issues `NOTIFY`; the API listens and forwards to
WebSocket clients. Enough for a single-user app and one fewer moving part (spec 4.2).

## 002. Dependencies managed with uv, not conda (2026-10-05)

`uv.lock` gives a hashed, cross-platform lock that CI and Docker install with
`uv sync --locked`. Nothing in spec section 5 needs conda-only binaries.

## 003. One `pyproject.toml` at the repo root (2026-10-05)

The package lives in `backend/src/radar` as the repo map says, but the project file is
at the root so `uv run` works from a clean checkout without changing directory.

## 004. Makefile targets are wrappers around `uv run radar <command>` (2026-10-05)

GNU Make is not installed by default on Windows. Every target calls a subcommand of the
`radar` entry point (`radar/cli.py`), so `uv run radar audit` and `make audit` are the
same thing. CI calls the `uv run` form.

## 005. Frontend and the `web` container are deferred to Phase 2 (2026-10-05)

Phase 0 lists linters and CI, but the React app is built in Phase 2. Until then
`frontend/` is a placeholder, `make lint` and `make test` cover the backend only, and
ESLint, `tsc`, and Vitest are wired in with the app.

## 006. Compose scope in Phase 0 (2026-10-05)

`db` runs. `api` and `worker` are defined and build, but sit behind the `app` profile
because they have nothing to run until Phases 1 and 2. `make up` therefore starts the
database only for now.

## 007. Dependencies added beyond spec section 5 (2026-10-05)

`pydantic-settings` (typed config from `.env`) and `respx` (mocking `httpx` in tests).
Approved by the user; listed in section 5.

## 008. Test fixtures (2026-10-05)

News fixtures are synthetic: the real response schema and field types, with invented
headlines, summaries, authors, and URLs. No Benzinga text is committed. Bar, quote, and
trade fixtures keep the real response structure with a few trimmed rows. The recording
script never writes auth headers to disk.

## 009. Database host port is configurable (2026-10-05)

`POSTGRES_PORT` sets the port on the host (default 5432). The developer machine already
runs a local PostgreSQL on 5432, so RADAR's container uses 5433 there.

## 010. Audit findings and the decisions taken (2026-10-05)

All numbers are from `docs/DATA_AUDIT.md`, run 2026-10-05. The user decided 010a to
010d on 2026-10-05 and approved the factual corrections; the spec was updated to match.

### 010a. Which crypto location is the source of record

Problem: the spec assumes location `us` (Alpaca's own venue). On `us`, `PAXG/USD` has a
1Day bar on only 53.8% of days since 2021 and a 1Hour bar in 48.3% of hours; sampled
weeks in 2024 and 2025 have no 1Min bars at all. The spec also assumes quiet periods
appear as quote-only bars. Before 2023 on `us`, and on Kraken until 2026, they are
simply missing.

Measured on `us-1` (Kraken US): 100% of days and 96.0% of hours for PAXG, 99.9% of hours
for BTC, 30-day volume 722x (BTC) and 255x (PAXG) that of `us`. Daily closes differ from
`us` by a median of 0.02% (BTC) and 0.12% (PAXG). A live stream exists for `us-1` and
accepted a subscription. `eu-1` returned numbers identical to `us-1`.

Options:
1. `us-1` for all crypto, history and live. Recommended.
2. `us-1` for PAXG only, `us` for the rest. Two venues to reason about, for no gain.
3. Stay on `us`. Gold features would run on half the days.

**Decided: option 1.** `us-1` for all crypto, history and live.

### 010b. Bar resolution to store and to use for realised volatility

Problem: spec 7.4 leaves "5-minute or hourly" to the audit, and Phase 1 says "1-minute
or coarser as the audit supports". PAXG 1Min bars on `us-1` cover 8% to 31% of minutes
in the sampled weeks of 2021 to 2025 (80% in 2026). BTC 1Min bars cover 99% or more.

Options:
1. Store 1Hour and 1Day only; realised volatility from hourly bars for every asset.
   Recommended: one method for both primary assets, and PAXG cannot support finer.
2. Also store BTC 1Min and use 5-minute realised volatility for BTC only. Better BTC
   estimate, but BTC and gold volatility are then not comparable.

**Decided: option 1.** Store 1Hour and 1Day; hourly realised volatility for every asset.

### 010c. Gold news coverage is below the spec threshold

Problem: spec 3.4 sets "about 2 articles per day" as the floor for F3 and F4. `GLD`
averaged 1.36 to 1.75 per day in 2023 to 2026 and 0.19 to 0.90 before. The union of
`GLD`, `IAU`, `GDX`, `PAXGUSD` reaches 1.48 to 1.93 in 2023 to 2026, with an article on
62% to 71% of days. `PAXGUSD` alone has 41 articles in total.

Options:
1. Apply the rule as written: gold shows "insufficient news coverage" for F3 and F4.
2. Show gold F3 from 2023 onward using the union set, labelled with its article count,
   and let F4's own rule (`not enough events` below 30) decide the verdict.
3. Add another news source for gold. Out of scope for version 1.

**Decided: option 2.** Before 2023, gold news shows "insufficient news coverage".

### 010d. Bitcoin news starts in 2022, not 2015

`BTCUSD` has 8 articles before 2022 and 10 to 14 per day from 2022 on. F3 and F4 for
Bitcoin therefore cover about 4.75 years. Proposed: state this in spec 3.4 and section
14; no method change. **Decided: as proposed.**

### 010e. One stream connection per endpoint

A second connection to the same stream endpoint is refused with `406 connection limit
exceeded`. Crypto and news can be open together. Consequence: only the worker may hold
stream connections, and a developer machine and a deployed worker cannot both stream
with the same keys. Proposed: add to spec 4.2.

### 010f. Forex is not available on the Basic plan

Every forex call returned `403 insufficient grants`. `XAU/USD` cannot be a reference
series. `GLD` stays the only gold cross-check.

### 010g. Backfill cost

For `BTC/USD`, a 1Hour request returns about one week (167 or 168 bars) per page
whatever `limit` is sent, so a full hourly history is about 300 calls. `PAXG/USD` pages
hold more (975 to 1,847 bars), which fits a page being capped by underlying minute bars.
1Day history fits in one page. See audit section 2.7.

## 011. Gold is represented by `GLD` alone (2026-10-05)

The user asked for one gold instrument, chosen for data quality, in place of the mix of
`PAXG/USD` for price, `GLD` as a cross-check, and four tickers for news. They also
offered switching the product to Bitcoin and `SPY`. The user left the choice to Claude.

Measured on 2026-10-05:

- `XAU/USD`: not available on the Basic plan (`403`).
- `PAXG/USD` on `us-1`: starts 2021, 96.0% of hours present, minute bars too sparse to
  use, 41 news articles in total.
- `GLD`: starts 2016-01-04, 2,703 daily bars with none at zero volume, every sampled
  session has all its hourly bars, about 8.1 million shares a day, 1.36 to 1.75 news
  articles per day from 2023.

**Decided: `GLD`.** It has the best data of the three and twice the history. The
product stays "Bitcoin and gold"; `SPY` stays a portfolio asset.

Costs accepted:

- Gold has no weekend or overnight prices. Bitcoin against gold uses the mixed panel
  only, and the tracking-gap panel is dropped.
- Live gold on the free plan is the IEX feed in market hours; history is the
  consolidated feed, 15 minutes delayed.
- Gold news is `GLD` articles only, slightly fewer than the four-ticker set of 010c.
- Realised volatility for a stock session adds the squared overnight return to the
  hourly returns of regular hours. This rule was written by Claude and has not been
  reviewed by the user.

`PAXG/USD` is removed from the universe. This supersedes the gold parts of 010a and
010c; `us-1` remains the location for the remaining crypto assets.

## 012. Times are shown in the viewer's time zone (2026-10-05)

The user is in GMT+8 and finds UTC hard to read. Storage and APIs stay in UTC (hard
rule). The frontend shows the browser's local time with the zone named. Reports written
for the user give times in GMT+8.

## 013. Phase 1 choices (2026-10-05)

Approved by the user:

- `psycopg` added as the PostgreSQL driver. `jupyter` and `matplotlib` will be added as
  dev-only dependencies when the exploration notebook is written.
- News is backfilled only for symbols the universe uses. `SPY` news (about 82,500
  articles, 80% of the volume) is not stored; no feature analyses it.
- The mixed panel takes the crypto price at 16:00 New York from the close of the hourly
  bar that ends at that time, the last price known at the stock close.

Made by Claude while building, open to change:

- `news_symbols.symbol` holds the canonical asset symbol (`BTC/USD`), not the provider
  tag (`BTCUSD`). Tags for symbols outside the universe are not stored in the clean
  layer; the raw layer keeps every tag.
- `news_articles` has no `content` column, as in spec section 6. Sentiment uses headline
  and summary. Article bodies are not requested from the API.
- `bars` has two columns beyond section 6: `is_outlier` (the review flag of section 7.2)
  and `received_at`.
- `bars.loc` holds the crypto location, or the feed name for stocks.
- Database tests run against a throwaway `radar_test` database on the dev server. They
  are skipped when no database is reachable, and required in CI.

## 014. `PAXG/USD` stays as a portfolio asset (2026-10-05)

The user holds PAXG, BTC, and SPY on Binance and asked whether PAXG can still be used
for allocation. It can: the portfolio lab works on daily returns, and `PAXG/USD` has a
daily bar on 100% of days since 2021-01-01 on `us-1`. What ruled PAXG out as the gold
instrument was its short history, sparse minute bars, missing hours, and lack of news,
none of which the portfolio lab depends on.

`PAXG/USD` is in the universe as a non-primary asset. Decision 011 is unchanged: gold
analysis (F1 to F5) uses `GLD`.

Known gap: prices are Kraken's USD pairs, while the user's holdings are on Binance,
mostly against USDT. The difference is small for valuation but is not measured.

## 015. The user's SPY holding is the tokenised `SPYB` on Binance (2026-10-05)

The user reports it tracks SPY almost exactly. The portfolio lab will value and model it
with `SPY` prices, one unit to one share. Not measured: the tracking difference, and
whether one `SPYB` equals one SPY share or a fraction. Confirm the ratio in Phase 5
before showing portfolio values.

## 016. Raw layer and backfill design (2026-10-05)

Made by Claude while building step 2, open to change:

- Raw Parquet files are partitioned by source, symbol, and the date the response was
  **received**, one file per response page. Spec 7.1 says "by source, symbol, and date"
  without saying which date. The received date keeps the layer strictly append-only and
  avoids about 11,000 one-day files per backfill.
- Fields the provider adds later are kept in an `extra` JSON column, so a raw file never
  silently loses data.
- Backfill windows are calendar months (hourly bars, news) and calendar years (daily
  bars). A window in the past is marked `done` and never refetched; the window holding
  "now" is `partial` and refetched every run.
- A bar is stored only once its period has ended. The hour or day still forming is
  skipped, so stored values do not change later and a re-run changes zero rows.
- Stock bars come from the consolidated (`sip`) feed, requested up to 16 minutes ago.
  Hourly stock bars include extended-hours bars.
- News is fetched from 2015-01-01 for every news symbol in the universe.

## 017. Three features added to version 1 (2026-10-05)

The user judged the plan too thin and approved three additions from a list of five:
F8 macro drivers, F9 volatility forecast, F10 tail risk. Not adopted: liquidity
measures from quotes and order books, and widening the asset list.

The user's stated purpose for the app: to show what can be built on Alpaca's free tier.
RADAR uses Alpaca's market data and news only; it never calls the trading API.

Consequences:

- Four macro driver funds join the universe: `UUP`, `TLT`, `TIP`, `VIXY`.
- F9 and F10 are built in Phase 3, F8 in Phase 5. Phase 1 is unchanged apart from
  backfilling the four funds.
- Three results tables are added to section 6.

Not decided: the read-only Binance connector stays in "later", and the hard rule
against position endpoints in `CLAUDE.md` is unchanged, because the user has not
answered either question.

## 018. Five more additions to version 1 (2026-10-05)

Approved by the user from a list of nine: the cross-asset correlation grid, a
fast-adapting (exponentially weighted) correlation, stress scenarios, news topics, and
conformal adjustment of the outlook ranges. They extend F5, F6, F3 and F4, and F2; no
new feature numbers.

Not adopted: PCA, change-point detection, price-direction prediction, reinforcement
learning, Black-Litterman, Kelly sizing.

None of these changes Phase 1.

## 019. Phase 1 steps 3 to 6: choices made while building (2026-10-05)

Made by Claude, open to change:

- **Live bars are not stored.** The streams push live prices to the app and trigger a
  REST gap-fill; every stored bar comes from the REST API through the same code as the
  backfill. A dropped stream or a restarted worker therefore cannot leave a hole, and
  live and historical data cannot disagree.
- **A third stream for stocks.** Live `GLD` needs the IEX stock stream
  (`wss://stream.data.alpaca.markets/v2/iex`), in addition to crypto and news. All three
  connected on the Basic plan when tested on 2026-10-05.
- **Duplicate news is marked, not deleted.** `news_articles.duplicate_of` points at the
  earlier article with the same headline and asset within 24 hours.
- **Outlier flags skip returns across a break.** On hourly series a return is judged
  only when the previous bar is exactly one hour earlier, so overnight and weekend gaps
  in stock data are not flagged as outliers.
- **Rejected bars.** A bar that fails schema validation is not stored; the rejection is
  written to `data_quality_reports`. None of the 433,338 bars stored on 2026-10-05 failed.
- **Stock realised volatility** uses the daily open, the hourly closes inside regular
  hours, and the overnight move from the previous close. Extended-hours bars are stored
  but not used.
- **Mixed panel fill.** If the crypto bar ending at a session close is missing, the
  latest bar from the previous 6 hours is used and the cell is flagged. Older than
  that, the price is left empty.
- **The Phase 1 measurements live in `docs/DATA_PROFILE.md`,** not in the audit file,
  because `make audit` regenerates the audit file from the provider.
- **`pandas-stubs`** added as a dev dependency so `mypy --strict` can check pandas code.

Measured, worth knowing (see `docs/DATA_PROFILE.md`):

- `GLD` and `PAXG/USD` daily returns correlate at 0.96 on the mixed panel.
- `PAXG/USD` has no realised-volatility value on 8.3% of days (too few hourly bars).
- Volatility clusters in every asset: squared-return autocorrelation at lag 1 is 0.15
  for Bitcoin and 0.17 for `GLD`.

## 020. Read-only Binance holdings in version 1 (2026-10-05)

The user confirmed the Binance connector is read-only and wants their Binance portfolio
analysed. It moves from "later" into F6 (Phase 5). The hard rule in `CLAUDE.md` gains
one narrow exception: reading balances and open positions with a key that cannot trade
or withdraw. Everything else in the rule stands, and a test must prove the connector
has no order, transfer, or settings calls.

Still to confirm with the user in Phase 5: which Binance products to read (spot,
futures, margin, earn), and the `SPYB` to `SPY` unit ratio (decision 015).

## 021. `SPY` is a primary asset (2026-10-05)

The user holds SPY (as `SPYB`, decision 015) and asked whether giving it the same
analysis as Bitcoin and gold would be worthwhile. It is: `SPY` has the best data in the
universe (ten years, no missing daily bars, 22 to 25 news articles a day), so every
model has more to work with than it does for Bitcoin or gold.

`SPY` gets its own regime, outlook, news, drivers, volatility, and tail-risk pages. Its
news is now stored: this reverses the part of decision 013 that left `SPY` news out.

Costs: about 82,500 more articles to store and, in Phase 4, to score for sentiment
(a one-off CPU job); and one more asset page to build. When `SPY` is the asset being
explained in F8, it is removed from its own drivers.

## 022. Phase 2 choices (2026-10-05)

Approved by the user: `uvicorn`, `react-router`, `openapi-typescript`, and Testing
Library with `jsdom`, added to section 5.

Made by Claude while building, open to change:

- **The API listens for live events on a plain thread.** The worker publishes with
  Postgres `NOTIFY`; the API holds one blocking `LISTEN` connection in a thread and
  passes each event to every WebSocket client. This behaves the same on Windows and
  Linux.
- **Routes accept a symbol or a slug.** `BTC/USD` contains a slash, so every asset also
  has a URL-safe slug (`btc-usd`), which the frontend uses.
- **"Live" is a claim the app only makes with evidence.** A price is labelled live only
  if it arrived from the stream in the last 3 minutes. Otherwise the app shows the last
  stored price with its time and says it is not live.
- **The bar still forming is drawn, not stored.** The newest candle comes from the live
  feed and the caption says so.
- **Charts show local time by shifting timestamps.** The chart library has no time zone
  support; hourly timestamps are shifted by the viewer's offset before drawing. Daily
  bars are placed on their trading day (New York for stocks, UTC for crypto).
- **Stale rules for the status page.** A crypto series is behind when its latest bar
  ended more than one bar length plus 3 hours ago; a stock series after 5 days, to
  allow for weekends and holidays.
- **Screens for later phases are honest placeholders** that say what they will show and
  which phase builds them.
- **TypeScript is held at version 5** because the API type generator does not yet
  support version 6.
- **`starlette`'s test client warns that `httpx` is deprecated in favour of `httpx2`.**
  Tests pass; not acted on, because `httpx` is also the Alpaca client's library.

## 023. Interface direction (2026-10-05)

The user rejected the first two interfaces as generic, and asked for a responsive site
in the visual language of their portfolio site (`C:\Users\David\portfolio-website`),
designed as a real product. They then asked to leave the interface as it stands and
revisit it in each phase.

What that settled:

- **Look.** One dark theme, the Inter typeface, liquid-glass surfaces, and an ambient
  glow tinted by the market in view. Numbers use Inter with fixed-width digits; the
  monospace face was dropped at the user's request. The accent is a cool blue instead of
  the portfolio's orange, so it does not clash with rising and falling colours.
- **Navigation.** A floating glass bar on top; on phones, a floating tab bar at the
  bottom. One system-status dot replaces the status pills.
- **Screens show only what exists.** The placeholder pages for the comparison,
  portfolio, and signals screens, and every "not built yet" note, were removed. Those
  screens enter the navigation when they are built.
- **Overview.** A market picker, one large surface with the chosen market's price and
  chart, and a side-by-side table (change over a day, week, month, and year, and the
  52-week range). These use only stored bars and the live feed.
- **Wording.** No developer language on screen. Chart captions stay, as the project
  rules require, in a quiet line under each chart.

## 024. Bars with a suspect high or low (2026-10-05)

Found while building the 52-week range: `SPY`'s daily bar for 2026-02-02 has a low of
68.47 against a close of 689.99, which passes schema validation but is almost certainly
a bad print. A few crypto bars have similar wicks.

The quality job now also flags a bar when its high or low sits far outside its open and
close (30 robust deviations and at least 10%). It shares the existing `is_outlier`
flag, which the API now returns. Flagged bars are kept. The interface draws them
without wicks and uses their close, not their high or low, for ranges.

Open for later phases: the daily-range feature (spec 7.4) and any model input that uses
highs and lows must skip flagged bars. Some flagged wicks are real, such as Ethereum's
fall to 700 on Kraken on 2021-02-22.

## 025. The regime model as specified does not give usable regimes (2026-10-05)

Spec F1 says: a hidden Markov model on each day's [log return, log realised volatility],
2 to 4 states chosen by BIC, "expect 3". Fitted on the real data on 2026-10-05:

- BIC chooses 4 states for Bitcoin, gold, and SPY, not 3.
- The states last 1.5 to 7 days. The product promises "what kind of market this is" and
  "how long each state has tended to last"; a state that flips every two days is a
  volatility reading, not a regime.
- For gold the model splits days by the sign of the return (one state averages +0.45% a
  day, the next -0.52%), and next-day volatility is **not** ordered by state out of
  sample (calm 0.74%, normal 0.73%). That fails F1's done-when.
- It does beat the rule-based baseline on one-step-ahead log density for all three.

The cause: one day's realised volatility is noisy, so the model chases daily noise.

Measured alternatives, 3 states, filtered states over full history (average length of an
unbroken run of one state; all have next-day volatility ordered):

| Variant | Bitcoin | Gold | SPY |
|---|---|---|---|
| As specified, 3 states | 2 to 4 days | 2.0 days | 4.4 days |
| Volatility only (no return) | 9.3 days | 25.0 days | 7.0 days |
| Return plus volatility smoothed over about 5 days | 23.1 days | 24.3 days | 24.1 days |

"Smoothed" is an exponentially weighted average of log realised volatility with a
5-day half-life, using that day and earlier days only, so it adds no lookahead.

Options:
1. Return plus smoothed volatility, fixed at 3 states. Recommended: regimes last about a
   month for all three assets, the two inputs of the spec are kept, and the three names
   (calm, normal, turbulent) keep one meaning across assets. BIC by state count is still
   reported on the methodology page.
2. Volatility only, 3 states. Simpler, but regime length differs a lot by asset.
3. As specified. Honest to the original text, but gold fails its own acceptance test.

**Decided by the user on 2026-10-05: option 1.** Return plus volatility smoothed with a
5-day half-life, 3 states. Spec F1 updated.

## 026. Regime pipeline choices (2026-10-05)

Made by Claude while building, open to change:

- **MLflow uses a local SQLite store,** `data/mlflow/mlflow.db`, with artefacts beside
  it. Spec section 5 said "a local file store", but the current MLflow refuses the plain
  file store. A failure to log to MLflow is a warning, not an error: the registry row in
  Postgres is what the app depends on.
- **Model parameters live in `model_registry.params`.** Scoring and the API read the
  model from the database, so the worker container and the host do not need to share a
  model file. A JSON copy is still written under `data/models` and logged to MLflow.
- **A regime reading is stamped when its day ended:** midnight UTC of the next day for
  crypto, the session close for stocks. A value stamped `t` therefore uses data up to
  `t` only.
- **Walk-forward settings.** Expanding window, first 500 days for training only, refit
  every 63 days (the evaluation refits about 30 times per asset; a 21-day step took
  several minutes per asset for no visible gain).
- **Schedule.** Regimes are scored at five past each hour and refitted on Sundays at
  02:30 UTC. The promotion gate of spec 7.10 is Phase 7: until then a refit always
  replaces the current model.

Measured on 2026-10-05 (walk-forward, out of sample):

| Asset | Days tested | Next-day volatility: calm, normal, turbulent | Ordered | Log density, model vs rule | Average run |
|---|---|---|---|---|---|
| BTC/USD | 1,602 | 1.96%, 2.71%, 3.63% | yes | 2.017 vs 1.972 | 34.1 days |
| GLD | 2,202 | 0.61%, 0.75%, 1.14% | yes | 3.440 vs 3.054 | 16.8 days |
| SPY | 2,202 | 0.54%, 0.67%, 1.24% | yes | 3.183 vs 2.558 | 21.8 days |

BIC still prefers 4 states for all three; 3 is used by decision 025.

## 027. Simulator calibration: measured results and choices (2026-10-05)

Walk-forward, out of sample, on 2026-10-05. For every day after the first 500 the
simulator ran with a regime model fitted on earlier days only and returns up to that day
only (2,000 paths per day; the regime model refitted every 63 days). Share of ranges that
contained the outcome, raw and after the conformal adjustment:

| Asset | Horizon | Cases | 50% raw / adjusted | 80% raw / adjusted | 95% raw / adjusted |
|---|---|---|---|---|---|
| BTC/USD | 1 day | 1,601 | 52.5% / 50.4% | 81.8% / 80.1% | 95.3% / 94.9% |
| BTC/USD | 7 days | 1,595 | 58.2% / 50.3% | 83.3% / 80.3% | 93.5% / 94.7% |
| BTC/USD | 30 days | 1,572 | 57.9% / 49.8% | 79.5% / 80.3% | 93.2% / 94.8% |
| GLD | 1 session | 2,201 | 47.7% / 50.1% | 78.1% / 80.1% | 93.5% / 95.0% |
| GLD | 5 sessions | 2,197 | 50.4% / 50.1% | 79.0% / 80.1% | 92.1% / 95.0% |
| GLD | 21 sessions | 2,181 | 48.3% / 49.7% | 77.0% / 80.1% | 93.3% / 94.5% |
| SPY | 1 session | 2,201 | 48.5% / 49.9% | 79.0% / 80.0% | 94.3% / 95.0% |
| SPY | 5 sessions | 2,197 | 51.3% / 50.2% | 81.7% / 80.1% | 95.4% / 95.0% |
| SPY | 21 sessions | 2,181 | 53.3% / 50.4% | 85.0% / 80.5% | 94.6% / 95.2% |

Against the constant-volatility baseline (pinball loss, lower is better): the simulator
is clearly better for `SPY` at every horizon, slightly better for Bitcoin at 1 and 30
days and level at 7, and slightly **worse** for gold at 5 and 21 sessions (0.00489 vs
0.00486, and 0.00970 vs 0.00940). The app must show this comparison as it is.

Choices made by Claude, open to change:

- **Horizons in trading steps.** 1, 7, and 30 days are 1, 7, and 30 days for crypto
  and 1, 5, and 21 sessions for stocks (spec 3.7).
- **Touching a level** is judged at daily closes, and the current price counts.
- **The conformal adjustment is left unbounded,** as the method needs for its long-run
  guarantee. Bounding it to within a factor of three of the stated miss rate was tried
  and rejected: 30-day coverage fell to 74% to 88%.
- **The live range uses the median adjustment of the last 250 forecasts,** not the
  latest value, which swings after every hit or miss.

Known limit: for the 95% range at the longest horizon, the adjustment for Bitcoin and
gold currently sits at its widest setting, so the adjusted 95% range is close to the
full spread of the simulated outcomes. The interface should say so where it applies.

## 028. Phase 3 steps 2 to 4: storage, volatility forecast, tail risk (2026-10-05)

Choices made by Claude while building, open to change. Results are walk-forward, out of
sample, measured on 2026-10-05.

**Outlook (F2) storage**

- `simulations` holds one row per run, not one per run and horizon as the spec's table
  listed: the horizons share one set of paths, so they are stored together. A run is
  keyed by asset, day, and regime model; its seed is derived from those three, so a
  rerun gives the same paths.
- The simulated paths (10,000 by 30, about 1 MB) are kept for the latest run of each
  asset only. Older runs keep their summaries. The level check reads the latest run.
- Displayed ranges use the conformal adjustment from the latest calibration report.
  Calibration is measured weekly; a run is stored once per completed day.
- Known limit, updated: the 95% range sits at its widest setting for Bitcoin at 7 and
  30 days and for gold at 21 sessions. Slowing the adjustment for high levels was tried
  (rates of 0.1 and 0.2 times the miss rate, in place of a fixed 0.02) and did not
  change this. The panel says so where it applies.

**Volatility forecast (F9)**

- The quantity forecast is per-day volatility over the next 1 or 7 days (5 sessions for
  stocks): the square root of the average daily realised variance over those days.
- **Departure from the spec, forced by the build order:** the second model is specified
  with the daily sentiment aggregate as an input. Sentiment is built in Phase 4, so the
  trees currently use the three HAR inputs and the regime probabilities only. The
  comparison is repeated when sentiment exists.
- The trees are shown only if their QLIKE is lower than HAR's and the Diebold-Mariano
  test gives p below 0.05. They are not shown for any asset.

| Asset | Horizon | Days | HAR | Trees | Yesterday repeated | Regime average |
|---|---|---|---|---|---|---|
| BTC/USD | 1 day | 1,601 | 0.467 | 0.566 | 0.924 | 0.535 |
| BTC/USD | 7 days | 1,595 | 0.194 | 0.208 | 1.329 | 0.251 |
| GLD | 1 session | 2,201 | 0.667 | 0.872 | 1.822 | 0.659 |
| GLD | 5 sessions | 2,197 | 0.257 | 0.298 | 1.522 | 0.296 |
| SPY | 1 session | 2,201 | 0.491 | 0.674 | 0.871 | 0.759 |
| SPY | 5 sessions | 2,197 | 0.335 | 0.492 | 0.903 | 0.580 |

QLIKE loss, lower is better. HAR beats both baselines with p below 0.05 in every row
except gold at 1 session, where the regime average is level with it (p = 0.65).

**Tail risk (F10)**

- Loss limits are simple-return losses over the horizon. The historical and filtered
  methods use a trailing window of 500 completed periods (at least 250).
- The filtered method scales past outcomes by the stored HAR forecasts, not the trees.
- For the 7-day horizon the backtest uses periods that do not overlap, so that the
  clustering test is not triggered by overlap alone. This leaves 192 periods for
  Bitcoin and 389 for the stocks, which is few for a 99% limit.
- All methods are scored on the same periods. The method shown is the one with the
  fewest limits failing Kupiec's test, then the smallest distance from the stated rates.
- Money figures for the user's holdings arrive with the portfolio in Phase 5; until
  then the panel shows percentages.

| Asset | Horizon | Shown | 95% breaches (expected) | 99% breaches (expected) | Unreliable limits |
|---|---|---|---|---|---|
| BTC/USD | 1 day | filtered | 73 (67.6) | 12 (13.5) | none |
| BTC/USD | 7 days | simulator | 6 (9.6) | 2 (1.9) | none |
| GLD | 1 session | filtered | 106 (97.6) | 21 (19.5) | historical at both levels; simulator at 99% |
| GLD | 5 sessions | filtered | 26 (19.5) | 7 (3.9) | historical at both levels; simulator at 99% |
| SPY | 1 session | filtered | 91 (97.6) | 22 (19.5) | simulator at 99% |
| SPY | 5 sessions | filtered | 16 (19.5) | 5 (3.9) | none |

**Tables.** `volatility_forecasts` has a `model` column and `risk_metrics` a `method`
column and `realised_loss`, so every method's history is stored, not only the one shown.
Evaluation tables live in `model_registry.metrics`.

**Not built in Phase 3:** shading the price chart itself by regime. The Market state
panel shows the regime of each day as a band beside the chart instead.

## 029. Navigation moves to a sidebar (2026-10-05)

Asked for by the user. On screens 768 px and wider, navigation is a left sidebar
(Overview, the primary markets, System with its status dot) that collapses to an icon
rail; the choice is remembered in the browser. Under the market being viewed it lists
that page's sections (Market state, Outlook, Expected swings, Downside risk) as jump
links. Phones keep the slim top bar and the bottom tab bar. This replaces the floating
top capsule of decision 023 on larger screens; the rest of 023 stands.

## 030. Phase 4: news sentiment, topics, and the sentiment-versus-price study (2026-10-06)

**Decided by the user**

- `torch` is added, in its CUDA build, so the language models run on the user's
  graphics card (RTX 4050). The spec said CPU inference; the code uses the graphics
  card when there is one and the CPU otherwise.
- The Loughran-McDonald word list is downloaded for the baseline. It is free for
  research use and needs a licence for commercial use, so it lives in the gitignored
  `data/lexicons/` and is never committed.
- The 200-headline evaluation sample is labelled by Claude, not by a person. The app
  says so wherever the accuracy figure is shown. The labels were written before any
  model output for those headlines existed. They are stored by article id only
  (`backend/src/radar/sentiment_labels.csv`), with no article text.

**Choices made by Claude, open to change**

- `torch` and `transformers` are an optional install (`uv sync --extra nlp`), so CI and
  the containers do not download them. **Consequence:** the Docker worker cannot score
  articles. Scoring runs on the host with `uv run radar sentiment` (or a worker started
  on the host). The Docker worker still refreshes the summaries from stored scores.
- A day's sentiment bucket ends at midnight UTC for crypto and at the market close for
  stocks, so weekend and overnight news lands in the next session, beside the price
  move that could reflect it.
- The event study uses daily steps: the day before the event to three days after.
  For crypto that is the spec's 24 hours before to 72 hours after; for stocks the steps
  are sessions.
- **Verdict rule.** With fewer than 30 events: `not enough events`. Otherwise compare
  the strongest significant correlation where tone came first (lags 1 to 5) with the
  strongest where price came first (lags -5 to -1); significance allows for five lags
  a side (Bonferroni). Neither significant: `no measurable relationship`. The same-day
  correlation is ignored because it cannot say which came first. The event-study paths
  are shown as supporting evidence and do not enter the rule.
- Topics: seven fixed topics (regulation, funds and flows, security, macro, adoption,
  price commentary, other), the same for every asset. Two zero-shot models were tried
  on the labelled sample: `MoritzLaurer/deberta-v3-base-zeroshot-v2.0` (60.0% accuracy)
  and `cross-encoder/nli-deberta-v3-small` (39.0%). The first is used.
- Study results are stored in `model_registry` rows (`event_study`, `sentiment`), not
  in tables of their own.

**Measured on 2026-10-06**

| | Accuracy | Macro F1 | n |
|---|---|---|---|
| FinBERT | 65.5% | 0.654 | 200 |
| Word-list baseline | 51.5% | 0.502 | 200 |
| Topic model | 60.0% | 0.489 | 200 |

| Asset | Events | Verdict | Strongest link |
|---|---|---|---|
| BTC/USD | 89 (2022 on) | price leads sentiment | tone tracks the previous day's return, correlation 0.34 |
| SPY | 98 (2016 on) | price leads sentiment | correlation 0.06 with the previous day's return |
| GLD | 22 (2023 on) | not enough events | none; all 22 events are positive ones |

No asset shows news tone leading price. The app states this.

**By topic (added once every article had a topic).** The study was repeated for each
topic. Price commentary shows `price leads sentiment` for Bitcoin (65 events) and US
stocks (110). Every other topic with 30 or more events shows `no measurable
relationship`. No gold topic has enough events.

**Not done in Phase 4**

- Re-running the F9 tree model with sentiment as an input (decision 028).

## 031. Fine-tuning the sentiment model, and model notebooks (2026-10-06)

Asked for by the user: fine-tune if it helps, with labels written by Claude, no leakage,
a proper pipeline, and notebooks that document the models.

**Data.** 1,800 stored headlines (720 Bitcoin, 720 US stocks, 360 gold), drawn at random
with seed 20261006 and labelled by Claude from the headline alone, in random order and
without knowing which part each would land in. Stored by article id only in
`backend/src/radar/sentiment_training_labels.csv`.

**Leakage guards** (`models/dataset.py`, enforced by `pipelines/finetune.check_dataset`
before any training):

- Headlines are reduced to a key with numbers, case, and punctuation removed; a key
  appears once in the whole dataset, so templated headlines cannot sit in two parts.
- No article or headline key is shared with the earlier 200-headline sample.
- The split is by time: train to 2025-05-09 (1,261), validation to 2026-01-26 (270),
  test from 2026-01-26 (269).
- The training function is never given the test part. The epoch is chosen on
  validation; the test part is scored once, afterwards.

**Settings**, fixed before any result was seen: 4 epochs, learning rate 2e-5, batch 16,
weight decay 0.01, 10% warm-up, seed 13.

**Rule for adoption**, fixed in advance: the fine-tuned model replaces the original only
if it is more accurate on the test part and McNemar's test gives p below 0.05.

**Result: not adopted.**

| On the 269 test headlines | Accuracy | Macro F1 |
|---|---|---|
| Original FinBERT | 58.7% | 0.593 |
| Fine-tuned | 63.6% | 0.638 |
| Word-list baseline | 48.3% | |

The fine-tuned model was right where the original was wrong on 33 headlines and the
reverse on 20: McNemar p = 0.098. That is not below 0.05, so the app keeps the original
FinBERT. On the earlier 200-headline sample the fine-tuned model scored 72.5% against
65.5%, but that sample overlaps the training period in time and does not decide.

**Not done, on purpose.** The settings were not changed and the run was not repeated
after seeing the test result. Doing so would turn the test part into a tuning set. A
fair retry needs either a new, later test set, or more labelled headlines so that a
5-point gain becomes measurable (about 700 test headlines would be needed).

**Caveat stated in the app and the notebook.** The labels are Claude's. Fine-tuning on
them teaches FinBERT to agree with that labeller, and every accuracy figure here is
agreement with that labeller, not with human judgement.

**Notebooks.** `notebooks/02` to `06` cover the regime model, the outlook simulation,
volatility and tail risk, news, and the fine-tuning run. Their sources are plain Python
files in `notebooks/src/` (percent format), built and executed by
`backend/scripts/build_notebooks.py`. They import the app's own modules and print no
article text.

## 032. Evidence step: a larger test of the fine-tuned model, intervals, corrections, live record (2026-10-06)

Asked for by the user before Phase 5. This entry was written and committed **before**
the larger test below was labelled or scored, so the rule cannot bend to the result.

**Replication of the fine-tuning test, fixed in advance**

- The first test had 269 headlines, too few to tell a 5-point gain from chance.
- A fresh test set of 700 headlines is drawn (seed 20261007; 280 Bitcoin, 280 US
  stocks, 140 gold): all later than every training and validation headline
  (after 2026-01-26 15:04 UTC), sharing no article and no headline key with the 1,800
  training labels or the 200 reference labels.
- The fine-tuned model is **not retrained and no setting is changed**. The model saved
  by the first run is scored as it is.
- Labels are written by Claude from the headline alone, before either model has scored
  these headlines.
- Rule: the fine-tuned model is adopted if, on these 700 headlines, it is more accurate
  than the original and McNemar's test gives p below 0.05. Otherwise the original
  stays, and the question is closed until there are labels from a person.
- The first 269 test headlines are reported beside the new ones but do not decide.

**Result of the replication (run after the rule above was committed)**

| On the 700 fresh headlines | Accuracy (95% range) | Macro F1 |
|---|---|---|
| Original FinBERT | 51.6% (47.9% to 55.3%) | 0.516 |
| Fine-tuned, unchanged from the first run | 61.1% (57.5% to 64.7%) | 0.611 |
| Word-list baseline | 43.6% | |

The fine-tuned model was right where the original was wrong on 112 headlines and the
reverse on 45: McNemar p = 0.00000009. By the rule, **the fine-tuned model is adopted**
(`finbert-radar-1`). All 103,094 articles were re-scored with it, the aggregates rebuilt,
and the sentiment-versus-price study rerun. By market the gain was 10 points for
Bitcoin and US stocks and 7 for gold.

What the accuracy does and does not mean:

- 61% on single headlines is modest, and the app grades it "Rough" beside the tone
  reading. It is agreement with one labeller (Claude), on headline text alone.
- Most disagreements are between neutral and a mild tone. The fine-tuned model gave the
  **opposite** tone to the label on 7% of headlines (11% for the original). Where label
  and model both took a side, they took the same side 84% of the time (75% before).
- The app's tone figures are daily averages over many articles, which is steadier than
  any single score, and the verdict on news and price did not change with the model.

**Intervals (item 2).** `models/evidence.py` adds the Wilson interval. The API now
returns a 95% range with every accuracy, every calibration coverage figure, and every
breach rate. For forecasts several steps ahead, which overlap, the range is computed
from the number of non-overlapping periods (n divided by steps). The screens show the
range beside the figure, and the News panel leads with a trust grade taken from the low
end of the accuracy range (Reliable from 80%, Fair from 65%, otherwise Rough).

**Many tests at once (item 4).** Benjamini-Hochberg correction at a 5% false discovery
rate, applied per market to two families:

- the news study: the overall study and one per topic, eleven lags each (77 to 88
  tests). Verdicts are worked out from the corrected significance.
- loss limits: every method, level, and horizon (12 tests). Reliability is taken from
  the corrected Kupiec p-value.

After correction: Bitcoin and US stocks still show `price leads sentiment` overall and
for price commentary only; every other topic with enough events shows `no measurable
relationship`. Gold now has 41 events with the new scores and shows `no measurable
relationship`. The set of loss limits marked unreliable did not change.

**Live record (item 7).** Table `forecast_log` (migration 0009) and `radar track`. Each
hour the worker copies the forecasts the app is showing (outlook ranges, the volatility
forecast, the loss limits) into the log, once per day and market, and never edits them;
outcomes are filled in when the days they cover have ended. Days the worker did not run
have no row and are not filled in later. Recording began on 2026-10-05 with 45
forecasts. The asset page shows the log with ranges, and says "No results yet" until
there are some.

**Not done here.** Items 1 (labels from a person), 5 (stability across sub-periods and
seeds), and 6 (sensitivity to settings) from the list offered to the user.

## 033. Product pass: answers first, one trust mark per claim, weak parts demoted (2026-10-06)

Asked for by the user after the evidence step, before Phase 5.

**Answers first.** Each market page now opens with an "In brief" card: one sentence each
for the market state, the one-week outlook range, expected swings, the one-day loss
limit, and news, then "What changed this week". The sections below it are folded; each
shows its claim in one line and opens to the evidence. A link to a section opens it.
New route `GET /assets/{symbol}/summary`.

**One trust mark per claim.** Every claim carries Solid, Fair, or Rough, with the reason
in one sentence. The rules are fixed and tested in `analytics/summary.py`:

| Claim | Solid when |
|---|---|
| Market state | on 1,000 or more unseen days, rougher states were followed by larger swings and the model beat the 30-day rule |
| Outlook | the stated 80% lies inside the 95% range of how often the adjusted one-week range held, and the simulator was within 1% of the constant-volatility forecast or better |
| Expected swings | the shown model beat "yesterday repeated" beyond chance and was not measurably worse than the regime average |
| Downside risk | both one-day limits of the shown method held at their stated rates after correction |
| News | the low end of the tone model's accuracy range is 80% or more (65% for Fair) |

On 2026-10-06 the first four are Solid for all three markets and News is Rough.

**What changed** lists only: a change of state in the last 7 days; expected swings 15%
or more different from a week ago; decayed news tone 0.15 or more different from a week
ago. Otherwise it says nothing notable changed.

**Demoted.** This departs from the F3 "UI output" line in the spec, with the user's
agreement:

- The lists of most positive and most negative articles are replaced by recent
  headlines, newest first, with no tone score shown. A single article's tone agrees with
  its label about 61% of the time, which is too weak to rank on.
- The topic breakdown is folded away inside the News section and labelled rough.

## 034. Fluid layout on every screen size; chart never shows empty time (2026-10-06)

Reported by the user: the layout broke at some window sizes and display scales, the price
chart could be moved to show empty space, long periods were cut off on a phone, and the
phone had a top bar as well as the bottom tabs.

**What was wrong, and the fix.**

| Problem | Cause | Fix |
|---|---|---|
| Chart squeezed to one side after the window changed size | the chart kept its old bar width | it fits the whole period again whenever its width changes |
| "1M" and "All" cut off on a phone | bars could not be drawn thinner than half a pixel, so 719 or 2,103 bars did not fit | bars may be as thin as needed; every period shows from its first bar to its last |
| Empty time when dragging or zooming | the view could move past the first and last bar | the view stops at both ends |
| Scrolling the page stopped over the chart | the wheel and an up-or-down swipe zoomed the chart | they belong to the page; drag sideways to move, pinch or drag the time axis to zoom, double-click the axis to reset |
| Two-column sections cramped beside the sidebar | columns switched on by window width, not by the room left for the page | sections respond to the width of the page area (container queries) |
| Sidebar too wide on a tablet or small window | one width from 768 pixels up | icon rail from 768 to 1023 pixels, full sidebar from 1024 |
| Top bar on a phone | duplicated the bottom tabs | removed; the status dot moved to the System tab |

Also: prices of 1,000 or more on the chart scale show no decimals, so the scale is
narrower; daily charts no longer show "00:00"; page gutters grow with the screen and
respect a notch.

**Checked** in the browser at 320, 375, 390, 768, 900, 1024, and 1440 pixels wide, and
at 844 by 390 (a phone on its side): no sideways page scroll at any of them. Wide tables
still scroll sideways inside their own box on a phone.

## 035. Phase 5 reshaped around portfolio and cross-market risk (2026-10-06)

Proposed after the user asked what would make RADAR less generic; the user agreed to the
reshaping on 2026-10-06. Nothing in the spec's Phase 5 is dropped. The order changes and
three things are added. Each part is its own pull request.

**The product idea.** RADAR answers three questions for someone holding Bitcoin, gold,
and stocks together: how risky is my mix now, what changed, and what would a steadier mix
have looked like.

| Part | Contents | New to the spec? |
|---|---|---|
| 5A. Your portfolio's risk | holdings by manual entry, CSV, and read-only Binance; risk model; X-ray with each holding's share of risk; portfolio loss limits (F10); stress scenarios; Portfolio screen opening with "In brief" | no (F6, F10) |
| 5B. How the markets move together | F5 as specified; **risk transmission**; **weekend gap risk**; F8 macro drivers | two additions |
| 5C. Does news predict swings? | **news volume and tone as inputs to the F9 forecast**, kept only if it beats the current model out of sample | addition; settles the item owed since decision 028 |
| 5D. Steadier mixes | the five allocations, walk-forward backtest, portfolio simulation, core and satellite, rebalancing drift | no (F6) |

**The three additions.**

- *Risk transmission.* For each pair of markets: in the 1, 5, and 10 days after market A
  entered its turbulent state (filtered, so known at the time), what market B's swings
  and return were, against all other days, with the number of episodes and an interval.
  Verdict by a tested rule: `spills over`, `no measurable spillover`, or `not enough
  episodes`.
- *Weekend gap risk.* Bitcoin trades while gold and stocks are shut. Measure how the
  Monday open of `GLD` and `SPY` has related to Bitcoin's Friday-close-to-Monday-open
  move, and show the current weekend's move when there is one. Same verdict rule.
- *News into the swings forecast.* Add yesterday's article count, its surprise against
  the trailing average, and the daily tone to the F9 models. Shown only if QLIKE is lower
  with a Diebold-Mariano p-value below 0.05; otherwise the screen says news added nothing
  measurable. No further work on single-article tone accuracy.

**Rules that carry over.** Every new section uses the shared `Panel` and a trust grade
from `analytics/summary.py`. Walk-forward only, filtered regime probabilities only. The
Binance source reads balances and positions only, with a test asserting it cannot reach
an order, transfer, or settings endpoint.

**No new dependencies expected:** Ledoit-Wolf is in scikit-learn; clustering and the
optimisers are in SciPy; Binance is called with the HTTP client already in use.

**Open for the user:** confirm the order 5A, 5B, 5C, 5D; and say whether a read-only
Binance key will be in `.env` for 5A (manual entry and CSV work without one).


## 036. Market page as tabs with real addresses; sections no longer fold (2026-10-06)

Reported by the user: the folded sections looked inconsistent (the claim and the arrow
wrapped differently on each), and navigation and routing were poor.

- Each market now has seven pages with their own addresses: `/asset/{slug}` (Summary) and
  `/asset/{slug}/state`, `/outlook`, `/swings`, `/risk`, `/news`, `/record`. The back
  button and shared links work. An unknown page goes to Summary.
- One row of tabs under the market's name is the only way between them, on every screen
  size; on a phone the row scrolls sideways and keeps the chosen tab in view. The
  sidebar's list of sections is removed, because it duplicated the tabs.
- Sections no longer fold. Every one has the same header: its name and trust mark, the
  claim in one line, why it earned the mark, then the evidence. This replaces the folding
  in decision 033; "answers first" is kept by the Summary page, whose "Evidence" links go
  to the matching tab.

## 037. Phase 5A: portfolio risk, with manual and CSV holdings (2026-10-06)

Built as the first part of decision 035. The user asked for manual entry and CSV now,
with the Binance connection to follow when a read-only key exists.

**What is built.** Holdings by manual entry or CSV through one `HoldingsSource`
interface; each holding's share of the money beside its share of the risk (Ledoit-Wolf
covariance on the mixed panel, at least 250 shared sessions); loss limits for the mix at
95% and 99% over 1 day and 1 week, backtested walk-forward; today's mix replayed through
five named episodes; a Portfolio screen that opens with the answers and a trust mark on
each.

**Where this departs from the spec, and why.**

| Spec | Built | Why |
|---|---|---|
| `GET /portfolio/xray` and `GET /portfolio/risk` | one `GET /portfolio/analysis` | the screen shows them together and they are computed together |
| `POST /portfolio/import` as a file upload | the browser reads the file and sends its text as JSON | a file upload needs a dependency that is not in section 5 |
| "No model runs inside a request" | saving holdings recomputes the analysis in that request (about 1.5 seconds) | the analysis depends on the holdings just saved; every read is still only a read. The worker also refreshes it hourly |
| `risk_metrics` rows per day for the portfolio | one stored row holding the latest analysis | the holdings can change at any time, which would make stored daily rows stale |
| Filtered limits scaled to the F9 forecast | scaled to an exponentially weighted average of the mix's own past swings (decay 0.94) | there is no F9 forecast for a mix of assets |
| Three methods compared | two: historical and filtered | the third needs the portfolio simulation, which is in 5D |

**Not built yet.**

- The Binance source. The interface is ready for it. It will come with its own client,
  the environment variable names, and the test that it can only reach reading endpoints.
  Leverage and distance to liquidation come with it.
- The `core` and `satellite` tags are read from a CSV and stored, but not shown: the
  report that uses them is in 5D.

**Stress episodes** are configuration in `universe.toml`. Dates chosen: Covid crash
(19 Feb to 23 Mar 2020), crypto sell-off of May 2021 (7 to 24 May), rising interest
rates (3 Jan to 14 Oct 2022), Terra collapse (4 May to 17 Jun 2022), FTX collapse (4 to
21 Nov 2022). Crypto history starts in 2021, so the Covid episode is partial for any
portfolio holding crypto, and the screen says so.

**Trust rules** (in `analytics/summary.py`): the X-ray is Solid at 750 or more shared
sessions, otherwise Fair; loss limits use the same rule as a single market; episodes are
Solid only when every one was replayed with every holding.

**Checked on real data** with a sample of 0.05 Bitcoin, 1.2 PAX Gold, and 6 SPY
(about $13,800): Bitcoin was 31% of the money and 72% of the risk; the one-day 95% limit
was 1.9% and had been broken 55 times in 1,172 past days against 59 expected. That
sample is saved in the local database as the current portfolio; saving real holdings
replaces it.

**Navigation.** Portfolio is in the sidebar and in the phone tabs. To make room, System
left the phone tabs; a status link sits at the foot of every page on a phone.

## 038. Read-only Binance holdings, cash as a holding, and the portfolio tied to the markets (2026-10-06)

The user added a Binance key and asked for the portfolio to connect to it, and for the
other features to relate to their own holdings.

**The Binance source** (`providers/binance.py`) is a `HoldingsSource`. It reads and does
nothing else:

| Read | Endpoint | Method |
|---|---|---|
| Server clock, for signing | `api.binance.com/api/v3/time` | GET |
| Spot wallet (flexible savings show here) | `/api/v3/account` | GET |
| Funding wallet (tokenised US stocks are kept here) | `/sapi/v1/asset/get-funding-asset` | POST |
| Fixed-term savings | `/sapi/v1/simple-earn/locked/position` | GET |
| Margin balances | `/sapi/v1/margin/account` | GET |
| Open futures exposure | `fapi.binance.com/fapi/v2/positionRisk` | GET |

- Every request passes one check against that list before it is sent; any other host,
  path, or method is refused in the process. Tests assert the list, that requests have no
  body, that no trading or transfer path appears in the module, and that neither the key
  nor the secret appears in errors or logs.
- **One POST.** Binance serves the Funding wallet read only by POST. It changes nothing
  and needs reading permission only, so it is within the exception in `CLAUDE.md` ("may
  call Binance endpoints that read account balances and open positions"). It is the single
  POST the client can send, and it is named in `READ_BY_POST`.
- Balances from all wallets are netted per asset with futures exposure. A net short or
  flat asset is listed as left out: the risk figures cover long exposure only.
- Open futures exposure is stored with its leverage and distance to liquidation and
  shown on the Holdings tab.
- While Binance is the source, the hourly job reads the account again before analysing.
  If Binance cannot be reached, the last holdings are kept.
- `SPYB` is valued as one share of `SPY` each, as the spec states. The user should say if
  the token's ratio is different.

**Cash is a holding.** First built as "left out"; the user pointed out that cash is part
of the portfolio. Dollars and dollar stablecoins (USDT, USDC, FDUSD, BUSD, TUSD, DAI)
are counted one for one as `USD`, "Cash (US dollars)". Cash is part of the money and
none of the risk: it lowers the mix's swings and loss limits in proportion, has a risk
share of zero, and is unchanged through every past episode. Interest earned on savings
is not counted. It can also be typed in or put in a CSV. Stored as `portfolios.cash`,
because cash has no price history to hang a holding row on.

**The portfolio tied to the rest of the app.**

- *Market states:* each holding's market state right now, and the share of the money in
  a turbulent market. `PAXG/USD` takes gold's state from `GLD` (decision 011).
- *Outside forces:* the F8 regression with the whole mix as the target (250 sessions),
  with its own trust grade.
- *Weekend:* while stock markets are shut, Bitcoin's move since the close and what a move
  like it has historically meant for a held market's open, in money on that holding.
  Shown only for a market whose weekend link passed its test.

**Checked on the real account:** five wallets read without error; Bitcoin, PAX Gold, SPY
(from `SPYB`), and cash were found; one token with no price history was listed as left
out. Cash is about three quarters of the money, and Bitcoin about 9% of the money and
74% of the risk.

## 039. Phase 5B: how the markets move together (2026-10-06)

Built as the second part of decision 035. One job (`radar relationships`, hourly in the
worker) stores two results as `model_registry` rows; requests only read them.

**F5, correlation.** Rolling 30 and 90 sessions and an exponentially weighted estimate
(half-life 30) for every pair of primary markets, not only Bitcoin and gold; split by
the first market's regime, with a 95% range and the number of days, and withheld below
30 days; a grid across the whole universe in clustered order for the last 90 sessions and
for the full shared history.

**Risk transmission (new).** An episode starts on the first session a market's filtered
label reads turbulent after it did not, at least 10 sessions after the last. Measured:
the other market's average absolute daily return over the next 1, 5, and 10 sessions, as
a multiple of the same on all other days. Range from resampling episodes; p-value from
2,000 draws of the same number of ordinary days; Benjamini-Hochberg across all pairs and
horizons. Fewer than 15 episodes gives `not enough episodes`.

**Weekend gaps (new).** For each break of three or more days between sessions: Bitcoin's
move from the last close to the next open (its price at the open is the last hourly
close known before it) against each stock market's opening gap. Correlation with a 95%
range, a slope, and the average gap after Bitcoin's worst tenth of weekends. Fewer than
30 weekends gives `not enough weekends`.

**F8, macro drivers.** Ridge regression (penalty 5 on drivers standardised within the
window) of each primary market on SPY, UUP, TLT, TIP, and VIXY over 90 and 250 sessions;
500 bootstrap resamples for the ranges; walk-forward out-of-sample R squared on the next
20 sessions against the single-driver baseline. The driver list is a constant in the
pipeline rather than configuration, which is a small departure from the spec.

**Trust rules** (in `analytics/summary.py`): a pair is Solid at 750 shared sessions;
spillovers are graded on the pair with the fewest episodes (30 Solid, 15 Fair);
weekends on their count (100 Solid, 30 Fair); drivers are Solid when on 500 or more
unseen days they explained some of the moves and more than the baseline did.

**What the real data shows (2026-10-06).**

| Finding | Evidence |
|---|---|
| US stocks open in line with Bitcoin's weekend move, by about 8% of its size | correlation 0.47 (0.38 to 0.56) over 299 weekends |
| Gold's Monday open has no measurable link to Bitcoin's weekend | correlation 0.10 (-0.02 to 0.21) |
| After gold turned turbulent, stocks swung 1.5 to 2 times their usual size | 16 episodes; adjusted p 0.03 to 0.04 |
| After stocks turned turbulent, Bitcoin swung about 1.4 times its usual size over 5 sessions | 17 episodes; adjusted p 0.03 |
| Bitcoin turning turbulent was not followed by measurably larger swings in gold or stocks | 16 episodes |
| Gold to Bitcoin cannot be judged | 9 episodes |
| Bitcoin and gold: 0.53 over the last 90 sessions against 0.11 over the whole record | 1,443 sessions |
| Drivers explain about 60% of stock moves, 20% of gold's, 18% of Bitcoin's on unseen days | for Bitcoin, no better than stocks alone |

Spillovers are graded Rough overall because one pair has only 9 episodes, and every
figure there rests on 16 to 26 episodes. They are shown with that caveat.

**Screens.** "Markets together" (`/together`) with tabs Summary, Pair by pair, All
markets, When one turns rough, Weekend gaps; an "Outside forces" tab on each market page
and on the Portfolio. The phone tab bar now has six entries.

**Not built.** The by-regime split uses only the first market's regime. The driver
history over time is stored but not charted yet.


## 040. Visual first: dashboards of tiles, explanations one tap away (2026-10-06)

Reported by the user: every tab opened on too much text and too few pictures. "It's an
app, not a book."

- **Summary pages are dashboards.** The market, Portfolio, and Markets together
  summaries replace their sentences with tiles: a label, one large figure, and a small
  picture of it (a range track, comparison bars, a tone meter, twenty dots for "1 day in
  20", money against risk as two stacked bars, past episodes as bars, a grid for
  spillovers). Each tile carries its trust mark and is a link to the evidence.
- **Explanations are one tap away.** Every caption is now behind "About this", and a
  section's trust reason behind "Why solid" (or fair, or rough). Nothing was removed:
  sample sizes, windows, and caveats are all still on the page, as the honest-output rule
  requires. They are no longer the first thing read.
- Shared pieces are in `components/viz.tsx`. New first views should be built from them.

**Not done yet.** The detail tabs still state several results as sentences inside cards
(for example the loss limits and the spillover list). Turning those into charts is the
next visual pass.

## 041. Held assets are discovered automatically; short histories; a risk scale (2026-10-06)

The user holds a US stock on Binance (`PURR`) that RADAR did not know, and asked that
assets never have to be added one by one: holdings change, and the app should follow.

**Automatic discovery** (`pipelines/discover.py`). When a holdings source reports a name
with no price history, RADAR looks for it in Alpaca's market data, records it in the
`assets` table with `discovered = true`, fetches its bars, and reads the source again.
It happens on "Read from Binance" (which can take up to a minute the first time a new
holding is seen) and in the hourly job. The worker's hourly sync keeps discovered
assets up to date. The configured universe in `universe.toml` still decides which
markets are analysed; discovered assets are portfolio assets only.

Two rules stop a name being matched to the wrong instrument:

- A name Binance marks as a tokenised US stock (`EQ_` plus the ticker) is looked up as
  a stock only.
- Every other name is looked up as a crypto pair against the dollar only. Many crypto
  names are also stock tickers (LINK, for one), and a wrong match would silently
  misprice a holding.

A consequence: a stock typed by hand or in a CSV must be written `EQ_TICKER` to be
discovered. Names already known resolve as before.

**A holding with too little history.** `PURR` has 210 sessions of prices (since
3 December 2025); the risk maths needs 250 (spec F6). The spec and the data disagree
here, so the options were:

| Option | Effect |
|---|---|
| Refuse to analyse the portfolio | one new holding would blank the whole screen |
| Lower the minimum for everything | weaker estimates for every portfolio |
| **Count it in the money, leave it out of the risk figures, and say so** (chosen) | the figures describe the rest and state the share they cover |

The screen names the holding, its share of the money, and how many days it has. Loss
figures in money are shares of the covered part. Nothing stands in for the missing
holding, so the risk shown is understated by whatever it carries. **The user should say
if another treatment is wanted.**

**A risk scale.** The user asked what low, moderate, and high risk look like, as the
basis for rebalancing. The mix's daily movement is divided by that of US stocks (`SPY`)
over the same sessions: below 0.5 is `low`, below 1 `moderate`, below 2 `high`, above
that `very high`. Government bonds, gold, stocks, and Bitcoin are drawn on the same
scale as reference points, and cash is zero. The bands are a convention of this app,
not a standard; they are stated on the screen. This describes the mix. Suggesting
another mix belongs to Phase 5D.

**On cash and risk.** Cash is inside the risk figures: it is why the mix reads `low`.
Its own share of the risk is 0% because it does not move, which is the correct reading
and is what the donut shows (a wide inner arc, no outer arc).

## 042. Chart choices and section names (2026-10-06)

Asked for by the user: the best chart for each card, and section names that cannot be
misread by someone who invests but is not a specialist.

| What is shown | Chart | Why |
|---|---|---|
| How the money and the risk are split | two-ring donut with a table beside it | parts of one whole; the two rings make a mismatch visible at a glance |
| Risk level | a scale cut into four bands with reference ticks | a position on a range |
| Likely price range | a track with a band and a marker | a range and where the price is in it |
| A chance such as "1 day in 20" | twenty dots, one lit | a frequency reads better counted than as a percentage |
| Forecast against last outcome; past crashes | bars on one scale | comparing a few amounts |
| News tone; correlations | a meter from one extreme to the other | a value between two poles |
| Correlation over time | a line | change over time |
| Knock-on effects between markets | a grid, lit where measured | every pair at once |

Section names, old to new: Market state to Current state; Outlook to Price range ahead;
Expected swings to Daily movement; Downside risk and Loss limits to Possible loss;
Outside forces to What it moves with; Live record to Forecast accuracy; Where risk
comes from to Risk by holding; Past episodes to Past crashes; Markets together to
Market connections, with tabs Two markets compared, All markets compared, Knock-on
effects, and Weekend effect.

## 043. Newer holdings join the risk figures on the history they have (2026-10-06)

The user chose this over leaving a newer holding out (decision 041), with new listings
in mind: "what if I go with ICO and IPO".

| Sessions of prices | Treatment |
|---|---|
| 250 or more | established, as before |
| 30 to 249 | **newer**: in the risk figures, estimated on its own record |
| under 30 | counted in the money only; the screen names it and the share covered |

**How a newer holding is estimated.** The established holdings keep their shrunk
covariance on the long shared history, so one newcomer does not shorten everyone's
record. The newcomer's own swings, and its correlation with each other holding, are
measured on the sessions it has; two holdings with under 30 sessions in common are
taken as unrelated. The pieces are made into one valid correlation matrix (negative
eigenvalues clipped, diagonal restored).

**Loss limits** cannot be backtested on a holding with a short record. They are measured
and backtested on the established holdings, then multiplied by how much the newer ones
raise the mix's swings (whole-mix volatility over established-part volatility). The
risk level is scaled the same way. The backtest counts shown are those of the
established part.

**What this cannot do.** A newly listed asset has no record of a crash, so its risk is
likely understated, and a holding in its first 30 sessions is not in the risk figures at
all. The X-ray's trust mark drops to Fair whenever a newer holding is present, and the
screen says which holding and how many days it has. Past crashes still mark a newer
holding as missing for any episode before it existed.

**On the real account:** `PURR` (208 sessions) is 1.1% of the money and about 11% of the
risk; the one-day 95% limit rose from 0.50% to 0.55%.


## 044. Phase 5C: does news predict swings? The rule, written before the test (2026-10-07)

Third part of decision 035, and the item owed since decision 028. The earlier study
(decision 030) found news tone does not lead price direction. The open question is
whether the amount and tone of news says anything about the size of the swings that
follow, beyond what recent swings already say.

**What is compared.** For each primary market and each forecast horizon, walk-forward
from the first day news is used for that market:

| Model | Inputs |
|---|---|
| HAR (the one shown today) | swings of the last day, week, and month |
| HAR with news | the same, plus the four news inputs below |
| Trees | the HAR inputs |
| Trees with news | the HAR inputs plus the four news inputs |

News inputs for day `t`, all from articles published by the end of day `t`: the log of
one plus the article count; that figure minus its own average over the previous 22
days (a surprise in volume); the day's average tone; and the size of that tone
regardless of sign. A day with no articles has a count of zero and a neutral tone.

**Rule, fixed now.** News is said to improve the forecast for a market and horizon only
if a model with news has a lower QLIKE than the same model without news, and the
Diebold-Mariano p-value for that difference is below 0.05 after Benjamini-Hochberg
correction across every market, horizon, and model pair tested. This is stricter than
the spec's F9 line, which has no correction, because twelve comparisons are made at
once. If the rule is met anywhere, wiring news into the forecast that is shown is a
separate step for the user to approve. If it is met nowhere, the screen says news added
nothing measurable, and no further variants are tried on this data.

**Not tuned.** The inputs, the 22-day window, the refit interval, and the tree settings
are set before the run and are not changed after seeing results.

## 045. Phase 5C result: news adds nothing measurable to the swings forecast (2026-10-07)

The test of decision 044 was run once, on 2026-10-07, with the rule and settings fixed
beforehand. Code: `models/news_volatility.py`, `pipelines/news_volatility.py`, run with
`radar news-swings`.

**Result.** None of the twelve comparisons met the rule. News is not wired into the
forecast, and no further variants are tried on this data.

| Market | Horizon | Model | Days | Error without news | With news | Change | p | p, corrected |
|---|---|---|---|---|---|---|---|---|
| Bitcoin | 1 day | HAR | 1,466 | 0.473 | 0.478 | 1.1% worse | 0.27 | 0.65 |
| Bitcoin | 1 day | Trees | 1,466 | 0.585 | 0.591 | 0.9% worse | 0.75 | 0.82 |
| Bitcoin | 1 week | HAR | 1,460 | 0.190 | 0.198 | 4.1% worse | 0.09 | 0.36 |
| Bitcoin | 1 week | Trees | 1,460 | 0.226 | 0.223 | 1.2% better | 0.46 | 0.77 |
| Gold | 1 day | HAR | 668 | 0.728 | 0.731 | 0.5% worse | 0.70 | 0.82 |
| Gold | 1 day | Trees | 668 | 1.002 | 1.021 | 2.0% worse | 0.58 | 0.77 |
| Gold | 1 week | HAR | 664 | 0.314 | 0.315 | 0.3% worse | 0.86 | 0.86 |
| Gold | 1 week | Trees | 664 | 0.438 | 0.430 | 1.9% better | 0.47 | 0.77 |
| US stocks | 1 day | HAR | 2,429 | 0.482 | 0.478 | 0.8% better | 0.048 | 0.29 |
| US stocks | 1 day | Trees | 2,429 | 0.624 | 0.619 | 0.7% better | 0.56 | 0.77 |
| US stocks | 1 week | HAR | 2,425 | 0.319 | 0.314 | 1.7% better | 0.12 | 0.36 |
| US stocks | 1 week | Trees | 2,425 | 0.478 | 0.453 | 5.2% better | 0.039 | 0.29 |

Error is QLIKE; lower is better. Periods: Bitcoin from 30 September 2022, gold from
2 February 2024, US stocks from 2 February 2017, each to early October 2026.

**Reading it honestly.**

- For Bitcoin and gold, news made the forecast slightly worse more often than better.
- For US stocks all four comparisons lean the right way, and two have an uncorrected
  p-value just under 0.05. Under the spec's original F9 line, which had no correction,
  one of those would have counted. Under the rule fixed in decision 044 it does not:
  with twelve comparisons, one or two results at that level are what chance alone gives.
- The largest lean, 5.2%, is for the tree model, which is not the one shown, because HAR
  beats it with or without news.
- So the fair statement is "no measurable gain", with a hint for US stocks that is too
  weak to act on. It would need new data to test again, not another pass over this data.

**What this settles.**

- The item owed since decision 028 (the F9 tree model with sentiment as an input) is
  done: it does not beat HAR.
- Together with decision 030 (news tone does not lead price direction), the evidence in
  this app is that news is not a usable trigger, for direction or for the size of
  swings. This shapes Phase 5D: rebalancing signals will be driven by the swings
  forecast, the market state, and drift, and not by headlines.
- It lowers the value of pushing single-headline tone accuracy higher, since the daily
  tone figure adds nothing to either forecast. The accuracy experiment the user asked
  to defer is still theirs to call.

**On the screen.** The Daily movement tab now ends with "Does news improve this
forecast?", showing the error with and without news as paired bars for the horizon in
view, and the verdict in words. New route `GET /assets/{symbol}/news-and-swings`.

## 046. Binance: two more reads, and a check against Binance's own totals (2026-10-07)

The user saw about $400.87 on Binance and $363 in RADAR, with the gap in cash. They
agreed on 2026-10-07 to two more reading endpoints, both GET:

| Read | Endpoint |
|---|---|
| Cash sitting in the futures wallet | `fapi.binance.com/fapi/v2/balance` |
| Binance's own dollar total per wallet | `api.binance.com/sapi/v1/asset/wallet/balance` |

The client's list is now seven GET endpoints and the one POST of decision 038. Both new
ones are covered by the same tests: on the list, no body, refused under any other method.

**The check.** Binance's total per wallet is stored at each read and shown on the
Holdings tab beside what RADAR found. A shortfall above 3% is stated in red with the
amount; under that it is put down to prices moving since the last close, which RADAR
values at.

**What it found on the real account (2026-10-07).**

| Wallet | Binance says | RADAR found |
|---|---|---|
| Spot | $90.42 | about $89.7 (Bitcoin, PAX Gold, SPYB) |
| Funding | $4.19 | about $3.9 (PURR) |
| Earn | $306.24 | $269.04 |
| Total | $400.85 | $363.24 |

The futures wallet is empty, so that was not it. The whole gap, about $37, is in the
Earn wallet. RADAR reads Earn two ways: flexible savings as the `LD`-prefixed balances
Binance shows in the spot wallet, and fixed-term savings from
`/sapi/v1/simple-earn/locked/position`. Together those give $269, so some Earn product
is reported through neither.

**Open, for the user.** The direct read of flexible savings is
`GET /sapi/v1/simple-earn/flexible/position`. It is a third new endpoint, so it needs the
user's agreement like the others. If it is added, flexible savings would be taken from
it and the `LD` balances ignored, so that nothing is counted twice. Until then the
Holdings tab shows the $37 as not found, and it is in none of the risk figures.

## 047. Binance: flexible savings read directly; the gap is closed (2026-10-07)

The user agreed on 2026-10-07 to one more reading endpoint,
`GET api.binance.com/sapi/v1/simple-earn/flexible/position`. The client's list is now
eight GET endpoints and the one POST of decision 038.

**Counted once.** Flexible savings are taken from this read. The copies Binance shows in
the spot wallet under `LD` names are then skipped. If the direct read is refused, the
`LD` copies are used instead, as before. A test covers both paths and checks that the
same holding is never counted twice.

**Result on the real account.** Cash went from $269.04 to $306.24, which is Binance's
Earn wallet total to the cent. The earlier shortfall of about $37 was flexible savings
that Binance does not mirror into the spot wallet. RADAR's total now matches Binance's
within the small difference that comes from valuing at the last market close.

## 048. Phase 5D, part 1: risk levels, other mixes, a target, and signals (2026-10-07)

Fourth part of decision 035. Split in two; this is the part the user asked about (what
low, moderate, and high risk look like, and how rebalancing reacts). Part 2 is the
portfolio simulation and the core and satellite report.

**Two questions kept apart.**

- *How the holdings are split among themselves.* Five rules (spec F6): as it is now,
  equal shares, smallest movement (minimum variance), equal risk each, and grouped by
  behaviour (hierarchical risk parity). Long-only, no holding above 60% of the invested
  part, or above an equal share when there are too few holdings for that.
- *How much is kept in cash.* Cash does not move, so it scales the mix's movement down
  in proportion. A level fixes the movement aimed for against US stocks, which fixes the
  cash share: one minus the aim over the movement of the holdings with no cash at all.

| Level | Band (multiple of US stocks' daily movement) | Aim |
|---|---|---|
| Low | under 0.5 | 0.25 |
| Moderate | 0.5 to 1 | 0.75 |
| High | 1 to 2 | 1.5 |

The bands are those of the risk scale (decision 041); the aims are their midpoints. A
level the holdings cannot reach without borrowing is shown as out of reach with no cash,
not forced.

**Backtest of the mixes.** Walk-forward: rebalanced every 21 sessions, each split worked
out from the 250 sessions before it and nothing later (a test changes later returns and
checks earlier splits do not move). Trading costs 0.1% of what is traded. Today's cash
share is kept in every mix. Holdings with a short record are left out of the backtest
and keep their share when a split is applied. Reported: daily movement, deepest fall,
share traded per month, and growth over the period, which is labelled as what happened.

**The target and the signals.** The user chooses a level and, optionally, a split.
It is stored with the portfolio and kept when holdings are read again. Against it:

| Signal | Rule |
|---|---|
| Movement above or below target | the mix's movement in current conditions is outside the level's band |
| Drift | any holding, or cash, is more than 5 percentage points of the whole from its target share |
| Turbulent market | a holding's market reads turbulent now (information, not counted as a move) |

"Current conditions" is the long-run figure scaled by how much the mix has been moving
lately (the same exponentially weighted measure the loss limits use) against its own
long-run movement. This is how the app reacts to volatility: when markets get rougher
the same holdings read higher on the scale, and the screen shows the gap. It does not
react to headlines, because the tests in decisions 030 and 045 found news leads neither
direction nor the size of moves.

**Wording.** Each holding's gap to target is given as shares and as an amount of money,
with a sign. Nothing says buy, sell, or what to do; setting a target changes nothing at
Binance. Route `PUT /portfolio/target`; the plan is part of `GET /portfolio/analysis`.

**On the real account (2026-10-07).** With no cash these holdings move 1.59 times as
much as US stocks; with 76% in cash the mix reads low, 0.37 over the long run and 0.27
in current conditions. Low would mean 84% in cash, moderate 53%, high 6%. Over 1,194
trading days from 31 December 2021, the split as it is moved 0.34% a day with a deepest
fall of 9.4%; the smallest-movement split moved 0.19% with a deepest fall of 4.5%.

**Not built yet (part 2).** Portfolio simulation by block bootstrap; the core and
satellite report. The detail tabs elsewhere still need the visual pass.

## 049. Try a mix: the user sets the shares, the app shows the risk (2026-10-07)

The first version of decision 048 opened with three cards, low, moderate, and high,
each with its cash share already worked out. The user asked for the opposite: let them
pick the share of each asset themselves and then show the typical day, the possible
loss, and the movement against US stocks. That is the better design, because the levels
were the app's choice and the mix is the user's.

**What replaced the cards.** The tab is now "Try a mix" (`/portfolio/try`):

- One row per holding with a slider and a number box for its share of the whole; cash
  is whatever is left. Any asset RADAR stores prices for can be added, held or not.
- "Work out the risk" runs the mix through the same analysis as the saved holdings, at
  the portfolio's current value, and shows it beside the portfolio as it is: movement
  against US stocks with its level, a typical day in money, the loss on about 1 day in
  20 and 1 day in 100, the deepest fall on record, and each holding's share of the risk.
- The levels and the other splits are kept only as starting points: one click fills the
  rows, and every number can then be changed.
- A tried mix can be set as the target. A target is now either a level with a split, or
  a mix of the user's own with a share for every holding. A mix has no band, so only
  drift and turbulent markets are flagged against it.

**How it is computed.** `POST /portfolio/what-if` turns the shares into quantities at
the latest stored prices and calls the same `analyse` function, without the driver
regression. Nothing is saved. It is the second place a calculation runs inside a
request (the first is saving holdings, decision 037); it takes about a second. Shares
must be between 0 and 100%, add up to at most 100%, and name assets with stored prices.

**Kept from decision 048.** The Compare mixes tab, the backtest, the signals, and the
distance from the target are unchanged.

## 050. Phase 5D part 2: the value range ahead, and core and satellite (2026-10-06)

**The value range ahead** (`models/portfolio_simulation.py`, tab `/portfolio/ahead`).

- A block bootstrap of the holdings' joint daily returns, as the spec asks: each of
  10,000 paths joins runs of 10 consecutive real sessions, taken for every holding at
  once. The run length is a judgement; the notebook shows the result barely moves from
  1 to 20.
- Holdings are left alone along a path (nothing is rebalanced) and cash does not move.
  The range is for the covered value, 30 and 90 sessions ahead, with the same outputs
  as a single market's range: quantiles, intervals, a fan, and the average deepest dip.
- Instead of one fixed question, the chance of ending past, and of touching, every
  change from -50% to +50% is stored, so the user picks the size on a slider
  (decision 049).
- Newer holdings (30 to 249 sessions) are not in the joint record. As with the loss
  limits (decision 043), the paths are drawn from the established holdings and widened
  by the same factor. The screen says so.
- **Checked walk-forward.** A range is drawn at past dates from earlier sessions only
  and compared with what followed; dates are a full horizon apart so no two outcomes
  share a day. A test proves that rewriting later days changes no earlier range.
- **Grade** (`grade_simulation`): on the 80% range at 30 sessions. Solid when the count
  that held lies in the middle 95% of what a true 80% range would give, on at least 30
  cases; fair when in line on fewer; rough when off.

**What the check found, and what was done about it.** On the example mix in the
notebook the 80% range held in 35 of 39 past 30-session cases. A constant-volatility
bell curve checked on the same dates held equally often with the same width, and so did
drawing single days. So the bootstrap is calibrated but **not measurably more accurate
than the baseline**. It is kept because the spec asks for it, it does not assume a bell
curve, and it gives path figures a formula for the end point does not. The baseline's
record is stored (`baseline_coverage`) and stated on the screen beside the
simulation's, with the words "not because its range has proved more accurate".

**Core and satellite** (`models/sleeves.py`, tab `/portfolio/sleeves`).

- Tags are now kept by symbol on the portfolio (`portfolios.tags`, migration 0016), so
  a new read from an exchange keeps them. `PUT /portfolio/tags` sets or clears tags
  and recomputes the analysis. Tags from a CSV are merged in.
- The report shows, for core, satellite, untagged, and cash: share of the money, share
  of the risk (from the X-ray, so they sum to 100%), and what the group added to return
  over the last 250 sessions.
- "Added to return" is each holding's weight today times the sum of its daily simple
  returns, so the parts add up to the mix's return at fixed weights. It describes
  today's mix in past markets, not what the user earned: RADAR does not know purchase
  dates, and the screen says that. A holding with fewer sessions is added up over what
  it has and is named.
- There is no report until something is tagged; the tab then shows only the tag
  controls. It takes the X-ray's grade.

**Notebook.** `notebooks/07_portfolio.ipynb` documents the whole portfolio layer (risk
model, risk by holding, the splits and their backtest, the range and its check, core
and satellite) on a made-up example portfolio, so that no real holdings are committed.
New model work is documented in a notebook from here on, at the user's request.

**Not done.** The simulation is not run for a mix being tried (`what-if`), to keep that
request quick.

## 051. Phase 6 part 1: signal rules and their track records (2026-10-06)

Phase 6 is split in three, each its own pull request: (1) the signal rules and track
records, (2) the daily brief, (3) the Signals and Overview screens. This is part 1.

**The rules** (`signals/detect.py`), as the spec gives them, per primary market:

| Signal | Rule | Split by |
|---|---|---|
| `regime_change` | the most probable state changes and the new one is above 0.7; the state it changed from is the last one that itself passed 0.7, so a day of doubt is not two changes | the state changed to |
| `abnormal_move` | an hourly return beyond 3 times the usual hourly size for the state the market was in going into the day; one per day | up, down |
| `sentiment_shock` | the day's tone beyond 2 standard deviations of the year before; days within three of a shock belong to it (the event study's rule) | positive, negative |

**Only what was known that day.** Past states come from a walk-forward replay
(`walk_forward_states`): the regime model is refitted every 63 sessions on earlier days
only, after 500 sessions of history. For days after the app's current model was fitted,
that model's stored readings are used, so new signals agree with the Current state
page. The usual hourly size is an expanding figure over earlier days in the same state
(at least 200 hours). Tests rewrite later days and check that earlier states, sizes,
shocks, and outcomes do not change.

**The track record** (`signals/track.py`). For each type, market, and split: the return
over the next day and the next week (7 days for crypto, 5 sessions for stocks) from the
close of the signal's day, against the same for all days. Stored: the count, quantiles,
the share that ended higher with a 95% Wilson range, and the typical size of the move.

**Verdicts, stricter than the spec.** The spec says "no measurable edge when the
interval overlaps the baseline". With about twenty records and two horizons each, luck
alone would pass one or two at that bar, so a verdict must also survive a
Benjamini-Hochberg correction across every record and horizon with at least 30
occurrences (the rule already used for the event study, decision 030). Under 30 the
verdict is "not enough occurrences".

**Added: a verdict on the size of the move.** The spec's verdict is about direction
only. A second one asks whether the move that followed was larger or smaller than on
other days, whichever way it went (Mann-Whitney test, the same correction).
This was added **after** the direction results were seen and the size table showed a
gap, so it was not planned in advance; the notebook and this entry say so, and it is to
be treated as provisional until it holds on new data.

**What the real data showed** (1,664 signals; 21 records; 24 comparisons with enough
cases):

- Direction: no signal on any market has an edge. One comparison passed 5% before
  correction, none after.
- Size: abnormal moves in US stocks were followed by larger moves over the next day and
  week (about 1.1 to 1.3% against 0.7% on all days). Nothing else separated.
- Changes of state are rare: most splits have under 30 cases and are not judged.
- News tone shocks have no edge in direction or size, in line with decisions 030 and
  045.

**Two questions for the user, recorded and not decided here.**

1. *The abnormal-move rule fires on about one day in five* (Bitcoin 22%, gold 21%, US
   stocks 17%), because there are many hours in a day and hourly moves have fat tails.
   Options: (a) keep the spec's 3 times; (b) raise the multiple (5 times would fire far
   less often); (c) keep 3 times but require it of the day's move, not one hour's.
   Kept as (a) until the user chooses. Changing it changes the track record, so it must
   be chosen once and not tuned to a result.
2. *`sentiment_shock` against "signals are never driven by news"* (CLAUDE.md, from
   decision 045). Decision 045 was about not using news to drive forecasts or
   rebalancing. The spec lists this signal, so it is built, and its record says "no
   measurable edge". Options: (a) keep it in the feed as a description of the news with
   that record beside it; (b) leave it out of the feed and the brief and keep only its
   record as evidence. Kept as (a) until the user chooses.

**Portfolio signals.** The signals of decision 048 (movement outside the band, drift,
turbulent market) describe where the portfolio stands against the user's target. They
are returned beside the market signals by `GET /signals` and have no track record:
there is no history of past holdings to replay, and they are not forecasts.

**Storage and running.** Tables `signal_track_records` (one row per type, market, and
split) and `signals` (one row per market, day, and type), migration 0017. `uv run radar
signals` replays everything and upserts; the worker runs it hourly at :55. It takes
about a minute. Running it twice stores the same rows.

**Routes.** `GET /signals` (newest first, filters for market and type, each with a
summary of its record) and `GET /signals/track-records/{type}`.

**Notebook.** `notebooks/08_signals.ipynb`.

**Not tested end to end.** The job's loading step (`pipelines/signals.build`) is covered
by the pure tests of what it calls and by the run on real data, not by a database test
of its own; `store` and the routes are tested against the database.

## 052. The two signal questions, decided (2026-10-06)

The user asked for both questions of decision 051 to be decided on product and
research grounds.

**1. An abnormal move is 5 times the usual hourly size, not 3.**

- At the spec's 3 the rule fired on about one day in five. Counted at each bar:

  | Bar | Bitcoin | Gold | US stocks |
  |---|---|---|---|
  | 3 times | 21.5% | 21.4% | 17.3% |
  | 4 times | 9.9% | 11.0% | 7.5% |
  | 5 times | 5.4% | 6.0% | 4.0% |
  | 6 times | 2.5% | 3.1% | 2.3% |

- The criterion, fixed before choosing: fire on about one day in twenty (roughly once a
  month per market), and leave at least 30 past cases in each direction on each market
  so the record can be judged. 5 is the only whole number that meets both; at 6, US
  stocks would have under 30 upward cases.
- **It was chosen on how often it fires, not on what followed.** The outcomes at 4, 6,
  and 7 were never computed. The constant carries a comment saying not to tune it to a
  track record.
- Applying the rule to the day's move was the other option. It was not taken because a
  signal of that kind already exists in effect (the state model reacts to the day's
  swings), while a single violent hour is something nothing else in the app flags.
- Result at 5: 536 signals in the feed. Direction: still no edge anywhere. Size:
  followed by larger moves in US stocks (both directions) and after falls in gold;
  no difference for Bitcoin. This is still the provisional finding of decision 051.

**2. News-tone shocks are scored but not shown.**

- Three tests now agree that news tone carries no usable information here: it does not
  lead price (030), it does not improve the swings forecast (045), and tone shocks are
  followed by nothing distinguishable in direction or size (051).
- An alert with a record of meaning nothing is noise, and it lowers trust in the alerts
  beside it. So `sentiment_shock` is left out of the feed (`detect.FEED_TYPES`) and will
  be left out of the daily brief. Its track record is still computed, stored, and served
  by `GET /signals/track-records/sentiment_shock`, as the evidence for leaving it out,
  and it would show if that ever changed.
- This settles the wording in CLAUDE.md: news drives no forecast, no rebalancing signal,
  and no item in the feed or brief.

**Housekeeping.** Storing the replay now removes signal rows it no longer produces, so
changing a rule cannot leave old rows in the feed.

## 053. Portfolio tools: regular buying, and trying any ticker (2026-10-06)

Two things the user asked for, built between Phase 6 parts 1 and 2. Neither is in the
spec; both extend F6.

**Regular buying** (`models/regular_buying.py`, tab `/portfolio/buying`).

- The user chooses what each purchase buys (any assets with stored prices, with their
  shares), the amount, how often (weekly, every two weeks, monthly), and for how long
  (6 months, 1 year, 2 years). Nothing is pre-decided; the plan starts from the
  proportions held (decision 049).
- The futures come from the same block bootstrap as the range ahead (decision 050):
  runs of 10 real sessions, every asset at once. Along each the plan buys the amount at
  the interval and never sells. 5,000 futures.
- **The comparison.** The same total put in on the first day is run through the very
  same futures. The screen shows both spreads, how often each ended below the money
  paid in, and how often buying bit by bit ended ahead. It does not call either better:
  the notebook shows it is a trade of less risk for less growth.
- **Checked walk-forward**, like every range: the plan is simulated at past starts from
  earlier sessions only and compared with how the real plan then went; starts are a
  full plan apart. A test rewrites later days and checks earlier ranges do not move.
- **The evidence is thin for long plans, and the screen says so.** Only about five
  separate one-year stretches fit in the stored prices (four can be checked), two for
  two years. The result states how many, the grade is "fair" at best under 30 cases, a
  note appears under 10, and a plan is capped at 504 sessions.
- Assets must share 250 sessions of prices. Trading costs and taxes are left out and
  the caption says so.
- It runs inside the request (about a second) and saves nothing, like `what-if`.
- Named "Regular buying" on the screen, not "DCA" (decision 042).

**Trying any ticker** (`POST /portfolio/lookup`, `TickerBox`).

- On Try a mix and on Regular buying the user can type a ticker and say whether it is a
  stock or a crypto coin (the same letters can be both, so RADAR does not guess). A
  known asset is returned at once. An unknown one is looked up through the existing
  discovery path (decision 041): Alpaca market data only, its history is fetched, and
  it joins the stored assets, kept up to date by the worker afterwards.
- This widens decision 041, which said assets are discovered from holdings and never
  added by hand. The rule that mattered there stands: the user never has to add what
  they hold. Looking one up to try it is a choice, not a chore.
- Limits, stated on the screen: US stocks and funds, and the crypto Alpaca carries. A
  newly listed asset still needs 30 sessions to be measured and 250 to be simulated.

**Notebook.** `notebooks/09_regular_buying.ipynb`, on a made-up plan.

## 054. Phase 6 parts 2 and 3: the daily brief, and the Signals and Overview screens (2026-10-06)

**The brief** (`brief/`, `pipelines/brief.py`, table `briefs`, migration 0018).

- **Payload first.** `brief/payload.py` defines every fact the brief may state, for each
  primary market and for the portfolio. Numbers are stored already rounded to what the
  text shows. It is built only from stored results: a market's facts come from the same
  summary the market page uses, so the two cannot disagree; nothing is computed for it.
- **The grounding check** (`brief/grounding.py`). Every number in the text is read back
  and must be in the payload. Tests cover the template on a full payload and prove the
  check catches an invented figure.
- **The template writer** is the default and needs no key and no outside service. Each
  sentence carries the page that holds its evidence, and the Overview links it there.
  It describes what is and what has happened; a test asserts it never says "buy",
  "sell", or "you should".
- **Signals in the brief** are those of the feed in the last 7 days (decision 052), each
  with its record in words, including "too few to say what tends to follow". News tone
  is not mentioned.
- **A probability is never written as 100%.** It is capped at 99 and worded "more than
  99%", since a model is never certain.
- **The language-model writer is an interface, not a connection.** `LlmWriter` takes any
  function from prompt to text. Its output is used only if it has the right number of
  sentences, no number outside the payload, and no banned word; otherwise the
  template's text stands. `write` applies the same check to any writer. **No provider
  is wired in and nothing is sent anywhere**: connecting one would send the user's
  portfolio figures to an outside service and may need a dependency, so it waits for
  the user to ask.
- **Stored** one row per day and subject (each market, and `PORTFOLIO`), with the
  payload, the sentences, and which writer's text was used. Run again on the same day,
  it replaces that day's rows. `uv run radar brief`; the worker rewrites it hourly at
  :58, after the signals, so the day's brief follows the day. `GET /briefs/latest`.

**The Signals screen** (`/signals`, `/signals/{type}`).

- "Latest": the feed, newest first, filtered by market and kind. Each row shows the
  signal's size in one figure, what has followed its kind (direction, size, and the
  count of past cases), and links to the track record. The portfolio's standing against
  the user's target sits above it, apart, with no record (decision 051).
- One tab per signal type with its track record: for each market and direction, how
  often the market ended higher after the signal with its plausible range, against any
  day, and the typical size of the move against any day, over a day and a week.
- "Unusual news tone" has a tab although it is not in the feed: the tab says why it is
  not shown and keeps the evidence in view.
- **Grade** (`grade_signals`): on the fewest past cases behind any kind of the signal:
  100 for solid, 30 for fair.
- The caption states the walk-forward rule, the correction for the number of
  comparisons with its count, and that the size findings are provisional.

**The Overview** now shows "Today in brief" and the five newest signals under the
market chart. It still renders entirely from stored results.

**Navigation.** Signals is in the sidebar. On a phone the bottom bar already holds six
tabs, so Signals is reached from the Overview ("See all") and from the brief's
sentences; a seventh tab would not fit.

**Phase 6 done-when.** Each signal shown links to its track record; the grounding test
passes; the template writer works with no key set; the Overview renders from stored
results.

## 055. Scheduled economic events: the data, and the tests written down before running (2026-10-06)

The user asked for forecasts around the regular US announcements (Fed decisions, the
jobs report, inflation). This entry fixes the data and the rules **before any result
has been computed**; it is committed on its own first so the order can be checked.

**The data.** `backend/src/radar/events.toml`, taken once from the official pages (the
user approved this source on 2026-10-06):

- Fed: the last day of each scheduled FOMC meeting, 2016 to 2027 (95 dates). Unscheduled
  meetings and votes between meetings are left out: they could not be known in advance,
  and the product is about events the user can see coming.
- Jobs report (Employment Situation) and inflation report (CPI): the day each came out,
  2016 to 2026 (131 dates each), from the Bureau of Labor Statistics' yearly schedule
  pages. Two late-2025 reports were delayed and one month was not published separately;
  the file holds what happened.
- The BLS site refuses scripted downloads, so its pages were read in a browser and the
  dates were checked against a fingerprint computed there. Nothing was done to get
  around the refusal.
- Alpaca has no economic calendar and expected ("consensus") figures are sold, not
  free. So RADAR cannot know the surprise in a number. Everything below uses dates and
  prices only.

**What is measured**, for each event type and each primary market. An event's day is
the trading day of its date (the session for gold and stocks, the UTC day for Bitcoin,
which contains both announcement times).

| # | Question | Statistic | Against |
|---|---|---|---|
| 1 | Does the market move more on the day? | size of the event day's return | all other days (Mann-Whitney) |
| 2 | Does it lean one way the day before? | share of days-before that ended higher | the share for all days (binomial) |
| 3 | Does it lean one way on the day? | share of event days that ended higher | the share for all days |
| 4 | Does the day's move carry on next day? | share of events where the next day went the same way as the event day | the same share for any two consecutive days |
| 5 | Does it carry on over the next week? | the same, for the following 5 sessions (7 days for Bitcoin) | the same share for any day |

**Departure from what was first described to the user.** The reaction is the event
day's close-to-close return, not the first hour after the release. Two of the three
events come out at 08:30 Eastern, before the US stock market opens, and the stored
hourly bars do not cover that hour reliably for stocks. One rule for all three markets
was preferred to a different one each.

**Verdicts.**

- Under 30 past events: "not enough events", no judgement.
- Tests 2 to 5 (direction) form one family of 36 comparisons; test 1 (size) another of
  9. Within each, a result counts only if it survives a Benjamini-Hochberg correction
  at 5%, as for signals (decision 051), and for direction the 95% Wilson range of the
  share must also exclude the baseline.
- Words: for size, "moves more on these days", "moves less", or "no measurable
  difference"; for direction, "leans up", "leans down", "tends to carry on", "tends to
  reverse", or "no measurable pattern".

**What will not be done whatever the result.** No rule, window, or threshold above will
be changed after seeing the results. If nothing passes, the screen says so and the
calendar is shown as dates with the measured size of moves only. No sentence will say
what to do before an event.

**Expected, for the record.** Before running: test 1 will probably pass for stocks on
Fed days and possibly on inflation days; tests 2 to 5 will probably find nothing. This
is written down so the result can be compared with the guess.

## 056. Scheduled economic events: the result, and what the app shows (2026-10-06)

The tests of decision 055, run once, with nothing changed afterwards.

**Result.**

- **Direction: no pattern.** Of 36 comparisons, one passed 5% on its own (Bitcoin the
  day before a jobs report, 33% up against 50%); about two would be expected by luck,
  and none survives the correction. Not before the event, not on the day, not after it.
- **Size: two findings out of nine.** Gold moves more on Fed decision days (a typical
  0.92% against 0.73%), and US stocks move more on jobs report days (0.87% against
  0.72%). Bitcoin on inflation days looked larger (2.69% against 2.02%) but did not
  survive the correction.
- **Against the guess written in 055.** The guess was that stocks would move more on
  Fed days and perhaps on inflation days. Neither held: close to close, US stocks moved
  no more than usual on Fed days. The guess that direction would show nothing was right.

**What this means for the user's request.** The request was a forecast of direction
around these announcements. On dates and prices alone there is none to give, and the
app says so and does not offer one. What it does offer is the calendar and the measured
size of the day's move. A direction forecast conditional on the surprise would need the
expected figures, which RADAR does not have.

**What was built.**

- `analytics/events.py` (pure), `pipelines/events.py`, stored as one `model_registry`
  row named `events`; `uv run radar events`; the worker runs it once a day.
- `GET /events`: the stored findings, plus the next events read from the dates file at
  the time of the request.
- Calendar screen (`/calendar`, `/calendar/{fed|jobs|inflation}`): "Coming up" in the
  viewer's local time, and a tab per event with, for each market, the typical move on
  the day against any other day and the four direction shares against any day.
- "Coming up" on the Overview; Calendar in the sidebar.
- **Grade** (`grade_events`): on the market with the fewest past events of the kind:
  100 for solid, 30 for fair.
- Days until an event are counted in the viewer's own calendar, so "tomorrow" is right
  in GMT+8.
- A report that came out on a market holiday (Good Friday 2023, for example) has no
  trading day of its own for gold and stocks and is left out for them.
- Notebook `10_events.ipynb`.

**Not done.** Events are not yet in the daily brief. The dates file needs a refresh
when the 2027 BLS schedule is published (it holds BLS dates to December 2026).

## 057. Navigation and look, reworked after the user's review (2026-10-06)

The user's review, in their words: sideways-scrolling tab strips on a phone feel
machine-made; too many choices with no sign of where to start or what each page is for;
no back button; phone cards cropped or oversized; on a desk the background and the
cards feel disconnected, with the background stopping short like a border; and, after a
first flat attempt, "minimalist and clean, not bland and tasteless". This replaces the
navigation of decision 036 and the surfaces of decision 023.

**Navigation.**

- **Five places, the same on a phone and on a desk:** Home, Markets, Portfolio, Signals,
  Calendar. System stays at the foot of the sidebar and as a status line on a phone.
  The three markets are no longer in the main navigation: they are on Markets, with the
  side-by-side comparison and Market connections.
- **No tab strips anywhere.** A subject (a market, the portfolio, signals, market
  connections) has its own page, and that page ends with a short list of its other
  pages: each one's name and, in a few words, what it answers (`SectionMenu`; hints are
  kept under 48 characters by a test). The portfolio's list is grouped: Understand your
  risk, Try things.
- **A way back on every inner page:** "Back to Portfolio", "Back to Gold". A market and
  Market connections also lead back to Markets. Addresses are unchanged, so old links
  and the brief's sentence links still work.
- Every page starts at its top and eases in when the address changes; anything tapped
  gives slightly under the finger. Both are off for people who ask for reduced motion.

**Home, rebuilt around the portfolio** (after two references the user supplied: an
exchange app's home and a banking app's). In order: the portfolio's value as the one
large figure, with its risk level and typical day; four shortcuts as round icons (Your
risk, Range ahead, Try a mix, Regular buying), so there is an obvious first thing to do;
the three markets as small cards side by side, at every width; then what is coming up
and the newest signals as short lists, and the brief, one sentence per subject until
"Read all". With nothing held, the figure is replaced by "Start with what you hold" and
one button. The large chart, the market picker, and the side-by-side table left Home:
the chart is on each market's page and the table is on Markets.

**The phone's bar** is a pill: the place you are in shows its name, the other four are
icons with their names for screen readers.

**Phone density.** Market cards are single compact rows on a phone and cards when there
is room. Card padding, headline and figure sizes, the donut, and the gaps are smaller
on a phone; the page has more room at the top; the bottom bar is solid, so page text no
longer shows through it. The long note about a newer holding is one line, and its
detail (limits scaled for newer holdings) moved to the Possible loss page.

**The look: one light, one material.**

- The glow behind a page used to be drawn inside the content column, which clipped it
  and made the frame the user saw. It now belongs to the window (`body::before`), fills
  it edge to edge, and takes the colour of the market being looked at, changing
  smoothly between pages.
- Cards, menu rows, and the navigation are the same thin translucent pane, lit from
  above with a hairline edge: the light shows through, so a card sits in the page and
  not on a different one. No blur and no drop shadows, except under the phone's bar.
- Character without clutter: a market's card carries its own colour in the corner and
  under its week line; small labels are set in spaced capitals; the page title is
  larger; the place you are in is lit in the page's colour.
- The first attempt of this pass (flat solid cards on a flat ground, no light) was
  rejected by the user as bland and is not to be returned to.

**Not changed.** Section names (decision 042), what each page contains, and every
figure. The detail pages still have the density they had; only their frame changed.

## 058. First use, loading, and motion, by how people actually decide (2026-10-06)

The user asked for careful wording, natural motion, skeleton loading in place of
waiting, nothing on screen that is not meant for the person using it, and five
principles applied: smart defaults, the goal-gradient effect, reciprocity, the
endowment effect, and attention to conversion and retention. Each is used only where it
is true to the product; none is used to push.

| Principle | What it became |
|---|---|
| Smart defaults, no blank forms | A newcomer is offered "Try an example" (four made-up holdings, saved in one tap) beside "Add my own". Regular buying opens on a result for a starting plan, not on an empty form. Try a mix already starts from the holdings |
| Fewer choices at once | One next step is offered at a time (below); Home has four shortcuts and five places (decision 057) |
| Goal gradient | "Make RADAR yours": five steps as a segmented bar with the count done and one "Continue" button to the next. It disappears when all are done and has a "Not now" |
| Endowed progress | The first step, "3 markets tracked for you", is true for everyone, so nobody starts at zero |
| Reciprocity | Markets, the brief, the calendar, signals, and a full example portfolio are given before anything is asked for. There is no sign-up and no gate |
| Endowment | It is "your portfolio", "your risk", "your target"; an example is labelled "Example portfolio" with "Use my own" beside it, so what is theirs is never confused with what is not |
| Retention | Reasons to come back are real ones: what is coming up, the day's brief, new signals |

**Honesty kept.** A step counts as done only when it is: holdings saved, the risk page
opened while something is held, a target stored. The example is offered only when
nothing is held, so it can never replace real holdings, and it is marked as made up.
No urgency, no countdowns, no advice.

**Loading.** Tapping always goes somewhere at once. While figures load, the page shows
its own shape in soft moving grey (`components/Skeleton.tsx`) where it used to say
"Loading…" or show a dash; assistive technology is told it is loading.

**Motion.** A page's parts arrive one after another over about a third of a second;
buttons and cards give under a tap. All of it is off under reduced motion.

**Removed from view.** The System link and "All systems normal" are shown only when
something needs attention; the page stays reachable at its address.

**Wording.** Buttons say what the person gets: "See where it could end up", "Show the
risk", "Continue", "Try an example", "Add my own". Home's shortcuts are "Your risk",
"What's ahead", "Try a mix", "Buy regularly".

**Not measured.** Conversion and retention are named as aims, but RADAR records nothing
about what people do, so none of this has been tested on real use.


## 059. One stylesheet, one colour family, and evidence as facts (2026-10-06)

The user's review: the words are tiring because almost every explanation is a paragraph
inside a collapsible section; an opened "About this" uses only the left half of a wide
card and wraps the text into a narrow ribbon; switching market in Signals looks glitchy;
and the animations should feel of a piece.

**Evidence is facts, not prose.** `Caption` now takes `facts`: a list of short named
values laid out as tiles across the card's full width, in as many columns as fit
(`.facts`, `auto-fit minmax(11rem, 1fr)`). Every one of the 39 captions was rewritten
this way. What a chart shows, its window, and its sample size are still all there, as
required, but as "Shows", "Window", "Sample" rather than buried mid-sentence. Sentences
remain only where they carry a caveat that a label cannot, and those sit under the facts
at one reading measure (`--measure`, 64ch, via `.prose`). The narrow ribbon was never a
layout bug: it was a `max-w-[80ch]` on 12px text inside a 1,100px card.

**One stylesheet.** `index.css` had been added to in layers until `:root`, `body::before`,
`.tile`, `.label`, `.title`, `.well` and `.page-in` were each written two or three times,
with the earlier copies dead. It is now one ordered sheet: tokens, page, type, material,
pressable things, the working, motion, the phone's bar, phone, reduced motion. `.aurora`,
`.radar`, `.market` and `.text-fluid-*` were dead and are gone, with the seven empty
`.aurora` nodes removed from the pages.

**One colour family.** The six hues were picked afresh at an even lightness and similar
chroma in OKLCH so they read as a set, then written as hex. They must stay hex: the price
charts read these variables and hand them to a parser that does not understand `oklch()`,
and shipping them as `oklch()` made every chart throw. `--faint` was lightened to #7c8095,
which is where the small "About this" text gets to about 4.8:1 on the ground.

**One set of motions.** Three durations and two curves as tokens, used everywhere.
Pressable surfaces compose one `transform` from `--lift` and `--squash`; written as
separate `transform` rules they overrode each other, so a tap on a hovered card did
nothing. Every `:hover` now sits behind `(hover: hover) and (pointer: fine)`, because on a
phone a hover state sticks after a tap. `<details>` opens and closes on a height
transition where the browser supports `interpolate-size`.

**Signals stopped flickering.** Changing the market or the kind changed the query key, so
the list unmounted, three skeletons took its place and the headline vanished: the card
collapsed and sprang back on every tap. The signals queries now keep the previous data;
the list stays mounted and dims (`[data-busy]`), and skeletons appear only on a first
load, when there is genuinely nothing to show.

**Not changed.** The name RADAR and the mark stay as they are. Inter stays, now with
`font-optical-sizing: auto`.

**Careful.** Plain CSS in `index.css` is outside Tailwind's layers, so it beats every
utility class. The shared material rule sets no `position` and no `border-radius` for
that reason: a first version did, and took `fixed` and `rounded-3xl` off the desktop
sidebar.

## 060. Technical indicators, levels, sizing rules and machine learning: the tests, written before running (2026-10-06)

The user's view: the app is weak where it matters to them. They want it to help with
when to resize, and around which prices to add or reduce, using what traders use:
volatility, volume, moving averages, RSI, support and resistance, order blocks, fair
value gaps, upcoming news, and machine learning. They asked for one notebook that tests
whether these work on our data before anything is built, with the research behind them.

Nothing below has been run. The rules, parameters and pass marks are fixed here first so
they cannot be tuned to the result. Parameters are the textbook ones, not chosen by us.

**What the research says (read before testing).**
- Sizing down when swings are high: Moreira and Muir (2017) found it raised return per
  unit of risk; Cederburg and others (2020) found that versions usable in real time
  generally did not beat leaving the portfolio alone.
- Trend: Moskowitz, Ooi and Pedersen (2012) found the past 12 months' direction tends to
  continue across many futures markets; Huang and others (2020) found little evidence
  market by market. Brock, Lakonishok and LeBaron (1992) found moving-average and
  range-break rules worked on 90 years of the Dow; Sullivan, Timmermann and White (1999)
  found the best rules did not hold up out of sample once the number of rules tried was
  allowed for. Park and Irwin (2007): 56 of 95 studies positive, most open to that same
  problem.
- Support and resistance: Osler (2000) found published levels did mark where intraday
  currency trends paused more often than chance.
- Events: Lucca and Moench (2015) found US stocks rose in the day before Fed decisions;
  Kurov and others found this had gone after 2015.
- Machine learning: Gu, Kelly and Xiu (2020), with 900 inputs and 30,000 stocks, found a
  predictable part of about 0.3% to 0.4% of monthly movement. Real, and very small.
- Order blocks and fair value gaps: no peer-reviewed test found.
- Bailey and Lopez de Prado (2014): try enough rules and one looks good by luck; allow
  for how many were tried.

**Data.** Daily bars for Bitcoin (from 2021), gold (GLD) and US stocks (SPY) (from 2016).
A position decided from data up to a day's close is held over the next day. Changing a
position costs 0.1% of the amount traded. Cash earns nothing. The first 252 days are
warm-up. A week is 7 days for Bitcoin and 5 for the others.

**Family S: rules that set how much to hold (between nothing and everything).**
1. Swings: hold min(1, usual swing / current swing), current = last 20 days, usual = the
   median of that up to the day.
2. 200-day average: hold when the close is above it.
3. 50 over 200: hold when the 50-day average is above the 200-day.
4. 12-month direction: hold when the close is above the close 252 days earlier.
5. Event caution: hold half on the day before and the day of a Fed decision, jobs
   report, or inflation report.
6. Gradient-boosted trees and 7. a small neural network: hold when the model's chance of
   a rise over the next week is above half. Inputs known at the close: returns over 1,
   5, 20, 60, 252 days; RSI; distance from the 50 and 200-day averages; swing over 20
   days and against 60; volume against its 20-day average; distance from the 252-day
   high and low; days to the next scheduled event. Refit every 63 days on all earlier
   days whose outcome was already known; first forecast after 750 days. Both come from
   scikit-learn, already a dependency.
8. Rules 1 and 2 together.

Judged against holding throughout, on return per unit of risk (Sharpe ratio) after
costs. A rule "does better" only if the difference is above zero with a two-sided
p-value, from 5,000 resamples of 20-day blocks of both return series together, that
survives Benjamini-Hochberg at 5% across all 24 comparisons (8 rules, 3 markets). The
deepest fall, return, and share of time held are reported beside it but not judged. For
6 and 7, accuracy against always saying "up" is reported on weeks that do not overlap.

**Family P: patterns and levels, judged on what followed.**
1. RSI(14) under 30. 2. RSI(14) over 70.
3. Fair value gap, up: a day's low above the high two days before. The gap is between
   them. The case is the first day in the next 20 whose low reaches into the gap.
4. Fair value gap, down: the mirror.
5. Order block, up: a close above the highest high of the 20 days before. The block is
   the last falling day among the 5 days before it, low to high. The case is the first
   day in the next 60 whose low reaches the block. 6. Order block, down: the mirror.
7. Support: the low comes within 0.5% of the lowest low of the 60 days before, or under.
8. Resistance: the high comes within 0.5% of the highest high of the 60 days before, or
   over.
9. A close at a new 252-day high.
10. Volume over twice its 20-day average on a rising day. 11. The same on a falling day.

For each, the share of cases followed by a rise over the next week is set against the
same share for all days, by the method of decision 051 (`signals/track.py`): at least 30
cases, a range for the share that excludes the all-days share, and a p-value that
survives Benjamini-Hochberg at 5% across all 33 comparisons. Whether the move that
followed was larger than usual is reported the same way, as a second question.

**Known weakness, stated now.** Six to eleven years of one market is little data. A rule
that fails here is "not detectable on this data", not "proved useless". A rule that
passes has passed once and is provisional.

**My guess, to be checked against the result.** Sizing by swings and the trend rules
will cut the deepest fall without a Sharpe gain that survives. No pattern in family P
will survive on direction; high volume may be followed by larger moves. Both models
will be right about as often as "always up".

**After the result.** What is built is decided with the user. Whatever it is, the app
never says "buy" or "sell"; a level or a size is shown with its record.

## 061. Indicators, levels, sizing rules and models: the result (2026-10-07)

The tests of decision 060, run once. Notebook 11 shows every table.

**Sizing rules (24 comparisons, return per unit of risk after costs).** None did better
than holding. One did worse: holding half around scheduled events, in gold. On the
deepest fall, which was reported but not judged: the 200-day rule took Bitcoin's from
about 77% to 36%, and sizing by swings took US stocks' from about 34% to 14% at a cost of
about 4 points of return a year; in gold the trend rules made the fall deeper and every
rule earned less.

**Models.** The gradient-boosted trees did not beat always saying "up" in any market
(Bitcoin 54% against 53%, US stocks 60% against 61%, gold 53% against 59%).

**Patterns and levels (33 comparisons).** On direction, one stood out by the written
rule: US stocks after RSI under 30 (85% of 41 days against 62%). Those 41 days were 15
separate sell-offs; counted once each it is 11 of 15, with a range that covers 62%. It
is treated as not shown. Fair value gaps, order blocks, support, resistance, new highs
and volume showed nothing on direction. On the size of the move, 12 stood out, mostly in
US stocks: larger moves after falls (support, down-gaps, RSI under 30, heavy volume on a
falling day), smaller near highs. That is the known link between falls and rougher
markets, which the swings forecast already carries.

**Two departures from 060, both made in the open.**
1. *The model settings.* 060 did not fix them. The first ones (200 rounds, depth 3)
   recovered about an eighth of a pattern planted in made-up answers; they were fitting
   noise. Smaller ones (60 rounds, depth 2, leaves of 50, some shrinkage) recovered
   nearly all of it. They were chosen on the planted pattern only, never on real
   outcomes, and the real test was then run with them. The small neural network could
   not recover the planted pattern in any setting tried, so its result on real data is
   reported and given no weight.
2. *Counting runs once.* The check on RSI under 30 was added after the result. 060
   should have said "the first day of each run" for every pattern that comes in runs.
   Future tests of this kind must.

**What the planted pattern settles.** The user asked whether "no measurable difference"
everywhere means the method is wrong or the models badly trained. In part it did: the
first model settings could not learn. The tests themselves find a planted pattern. What
they cannot see is a small one: with 100 cases, under about 10 points; with 400, under
about 5. "No measurable difference" means "smaller than this data can show", not "none".

**My guess in 060, checked.** Right that sizing and trend rules cut the deepest fall
without a gain that survives, for Bitcoin and US stocks; wrong for gold. Right in
substance that no pattern holds on direction, though the rule as written let one
through. Right about volume and larger moves. Right about the trees; I did not expect
the first settings to be unable to learn at all.

**Not to be done.** Do not rerun these tests with other parameters until something
passes. Do not show a level as a place to add or reduce: that was tested and did not
hold.

**Open, for the user.** What could be built from this: a sizing guide shown as a
trade-off (shallower falls for less return, and not in gold), and levels shown as places
where moves get larger rather than where price turns.

## 062. Suggestions are allowed with their basis; and the LSTM test, written before running (2026-10-07)

**The wording rule, changed by the user.** Until now the app could never write "buy",
"sell" or "you should". The user's decision on 2026-10-07: RADAR still never places a
trade, but it may give alerts, forecasts and suggestions about adding and reducing,
provided each one states the rule or theory it rests on and its justification. So:

- A suggestion names its rule ("the close is below its 200-day average"), what following
  that rule did in the past, over what period and how many cases, and where it failed.
- A suggestion is only made from a rule that has passed a test written down beforehand.
  A rule that was tested and did not hold (decision 061: levels as places to add or
  reduce, direction from RSI, gaps, blocks) is not turned into a suggestion.
- Nothing is executed, and nothing is worded as a certainty or a promise.

If RADAR is later opened to other people, suggestions about buying and selling may count
as financial advice where they live. That is a question to settle before opening it, not
now.

**The LSTM test.** The user asked for an LSTM, or anything that might work, trained,
validated and tested properly. Nothing below has been run.

*Why hourly bars.* Decision 061 showed a neural network cannot learn even a planted
pattern from a few thousand days. Hourly bars give about 50,000 examples for Bitcoin and
about 42,000 each for gold and US stocks.

*Question.* At each hour: will the close one day later (24 bars for Bitcoin, 16 for the
others, which trade 16 hourly bars a day with extended hours) be higher than now?

*Inputs.* For the LSTM, the last 48 bars, each as: its return, its high-to-low range,
its volume against the average of the 168 bars before, and the hour of day. For the two
simpler models, summaries known at the bar: returns over 1, 6, 24, 72 and 168 bars, the
spread of the last 24 and 168 returns, the volume figure, RSI over 14 bars, and the hour.
Everything is scaled with the averages of the training part only.

*Split, in time order.* First 60% to train, next 20% to validate (choose when to stop),
last 20% to test, looked at once. A gap of one horizon plus 48 bars is left out between
parts so no answer in one part depends on prices in the next.

*Models.* (1) LSTM: one layer of 32 units, dropout 0.2, Adam at 0.001, batches of 256,
at most 30 passes, stopping when the validation loss has not improved for 5; three
seeds, averaged. (2) Gradient-boosted trees with the small settings of decision 061.
(3) Logistic regression. Against: always giving the answer that was more common in the
training part.

*First, the planted pattern.* Before any real answer is used, each model is run on
made-up answers (higher 65% of the time when the last 24 bars rose, 40% when they fell).
A model that recovers less than half of the possible gain on the test part "cannot learn
here" and its real result carries no weight. If the LSTM fails, its size (16, 32 or 64
units) and learning rate (0.0003, 0.001, 0.003) may be chosen on the planted validation
part, never on real answers.

*Pass mark, for "accurate enough to build alerts on".* On test cases one horizon apart
(so they do not overlap), a model passes in a market only if all of these hold:
1. it is right at least 3 points more often than the always-one-answer baseline;
2. the binomial p-value against that baseline survives Benjamini-Hochberg at 5% across
   the 9 comparisons (3 models, 3 markets);
3. it is ahead of the baseline in both halves of the test part.
Reported beside it, not judged: holding only when the model says "higher", decided once
a day, after 0.1% costs, against holding throughout.

*Known limit.* The test part holds roughly 400 separate days per market, where an edge
under about 5 points cannot be seen. A model can fail here and still have a small edge;
an edge that small is not one to send alerts on.

*My guess.* The LSTM will pass the planted check on hourly data. No model will pass the
mark on real answers; accuracy will sit within 2 points of the baseline.

*After.* If a model passes, alerts are built on it with its record shown. If none does,
the alerts that remain possible are the damage-side rules of decision 061, which rest on
how far the portfolio fell, not on calling direction.
