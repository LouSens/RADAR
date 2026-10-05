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

