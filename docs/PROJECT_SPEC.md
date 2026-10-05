# RADAR: Project Specification

Reference document for building RADAR. `CLAUDE.md` holds the working rules; this file holds the detail.

Contents:

1. Product
2. Scope
3. Data sources and their limits
4. Architecture
5. Technology stack
6. Data model
7. ML and data pipeline
8. Feature specifications
9. API
10. Frontend
11. Build plan
12. Demo mode and demo script
13. Product copy
14. Risks and known limitations

---

## 1. Product

**Name:** RADAR, which stands for Regimes, Analytics, Distributions, Alerts, Risk. A radar shows what is around you now; it does not claim to know the future. The app takes the same stance towards markets.

| Letter | Stands for | Feature |
|---|---|---|
| R | Regimes | F1, the regime detector |
| A | Analytics | F3 to F5 and F8: news sentiment, cross-asset analysis, macro drivers |
| D | Distributions | F2 and F9: the outcome simulator and the volatility forecast |
| A | Alerts | F7, signals and the daily brief |
| R | Risk | F6 and F10: the portfolio lab and tail risk |

Write the name in capitals. Where a longer form is needed to tell it apart from other products with the same name, use "RADAR Markets". The Python package and repo name are lowercase `radar`.

**One-line description:** A market outlook app for Bitcoin and gold that reports the current market regime, the plausible range of outcomes, and the measured effect of news, with the evidence shown beside every conclusion.

**Who it is for:** A self-directed investor who holds Bitcoin, gold, and a few other assets, makes their own decisions, and wants a disciplined read of conditions instead of opinions and price targets.

**What makes it useful:**

- It answers three questions a person has before acting: What kind of market is this? What could happen next, and how likely is each outcome? Is the news moving price or only following it?
- Every answer comes with a track record. The simulator shows how often its past ranges held. Each signal shows what followed similar conditions historically.
- It says "no measurable effect" when that is what the data shows.

**What it is not:** a price predictor, a trading bot, or financial advice.

---

## 2. Scope

### In scope for version 1 (Alpaca data only)

| # | Feature | Question it answers |
|---|---|---|
| F1 | Regime detector | What state is this market in right now? |
| F2 | Outcome simulator | What range of prices is plausible over 1, 7, and 30 days? |
| F3 | News sentiment pulse | What is the tone of the news on this asset, and how much news is there? |
| F4 | Sentiment versus price | Does news sentiment lead price, follow it, or neither? |
| F5 | Bitcoin versus gold | Is Bitcoin currently moving with gold or against it? |
| F6 | Portfolio lab | Where does my portfolio's risk come from, and what would a risk-based allocation look like? |
| F7 | Signals and daily brief | What changed today, and how reliable has this kind of change been? |
| F8 | Macro drivers | Which outside forces (the dollar, interest rates, stocks, market fear) are Bitcoin and gold moving with right now? |
| F9 | Volatility forecast | How large are the price swings likely to be over the next day and week? |
| F10 | Tail risk | How much could be lost on a bad day, and how often has that limit been broken? |

### Asset universe

- **Primary assets (full analysis, F1 to F5):** `BTC/USD` and gold, represented by `GLD` (section 3.7).
- **Portfolio assets (F6 only):** `SPY`, `PAXG/USD`, and other crypto pairs Alpaca lists, such as `ETH/USD` and `SOL/USD`. The list is configuration, not code. `PAXG/USD` is here because the user holds it; its daily bars are complete on `us-1`, which is all the portfolio lab uses. It is not the gold instrument for F1 to F5 (section 3.7).

- **Macro driver assets (F8 only):** exchange-traded funds that stand for outside forces: `UUP` (US dollar), `TLT` (long-term US government bonds), `TIP` (inflation-linked bonds), `VIXY` (expected stock market volatility), plus `SPY` (US stocks). They are stored like any other stock. The list is configuration.

### Out of scope for version 1

- Order placement of any kind.
- Price direction prediction.
- Reinforcement learning.
- Order book and market microstructure analytics.
- The Binance connector. Version 1 defines the `HoldingsSource` interface with manual entry and CSV upload; a read-only Binance implementation is added later without changing anything else.
- User accounts. Version 1 is single-user.

---

## 3. Data sources and their limits

Everything here was taken from Alpaca's documentation in October 2026 or from the user's screenshots of it, then checked by the Phase 0 data audit. Statements marked **Measured** come from `docs/DATA_AUDIT.md` (run on 2026-10-05 on the free Basic plan); that file holds the full tables. Re-run `make audit` to refresh them.

### 3.1 Endpoints

Authentication headers on every authenticated call: `APCA-API-KEY-ID` and `APCA-API-SECRET-KEY`.

| Data | Endpoint |
|---|---|
| Crypto historical bars | `GET https://data.alpaca.markets/v1beta3/crypto/{loc}/bars` |
| Crypto latest bars, quotes, trades, orderbook, snapshots | under `https://data.alpaca.markets/v1beta3/crypto/{loc}/` |
| Crypto live stream | `wss://stream.data.alpaca.markets/v1beta3/crypto/{loc}` |
| Stock historical bars | `GET https://data.alpaca.markets/v2/stocks/bars` |
| News, historical | `GET https://data.alpaca.markets/v1beta1/news` |
| News, live stream | `wss://stream.data.alpaca.markets/v1beta1/news` |

Crypto `loc` values listed in the docs: `us` (Alpaca), `us-1` (Kraken US), `eu-1` (Kraken EU). The docs page also lists `us-2` and `bs-1` as allowed values without describing them.

**RADAR uses `us-1` for all crypto data, historical and live** (section 3.3 gives the reason; `docs/DECISIONS.md` 010a). The location is configuration, not code. **Measured:** `eu-1` returns data identical to `us-1`, so only one is stored. `us-2` rejects historical requests and `bs-1` returns no bars; neither is usable.

Crypto bar timeframes: 1 to 59 minutes, 1 to 23 hours, 1 day, 1 week, and 1, 2, 3, 4, 6, or 12 months.

Symbol formats differ by endpoint: crypto market data uses `BTC/USD`; the news endpoint uses `BTCUSD`. Keep one canonical symbol in the database and map at the provider boundary.

### 3.2 Plan limits (free Basic plan)

- 200 historical API calls per minute.
- Real-time stock data from the IEX exchange only. Consolidated (SIP) stock data is available with a 15-minute delay.
- Stock WebSocket subscriptions are limited to 30 symbols.
- Historical crypto data is the one market data category that does not require authentication.
- The paid plan (Algo Trader Plus, 99 USD per month) raises these limits. RADAR must work fully on the free plan.

**Measured:**

- The API reports a limit of 200 calls per minute.
- The historical news endpoint and the news stream both work on the Basic plan.
- Each stream endpoint accepts one connection per account. A second connection to the same endpoint is refused with `406 connection limit exceeded`. The crypto stream and the news stream can be open at the same time.
- Historical stock bars from the SIP feed are served when the requested window ends more than 15 minutes ago. The latest SIP bar returns `403`; the latest IEX bar is served.
- Not measured: the largest number of symbols one crypto or news connection may subscribe to. RADAR needs fewer than ten.

### 3.3 Crypto data caveats

- **Crypto history starts on 2021-01-01** for `BTC/USD`, `PAXG/USD`, and `ETH/USD` on every location (`SOL/USD` on Kraken starts 2021-06-17). **Measured.** That is 2,104 daily bars at the time of the audit.
- **Alpaca's own venue (`us`) is too thin for gold. Measured, 2021 to the audit date:** `PAXG/USD` on `us` has a daily bar on 53.8% of days and an hourly bar in 48.3% of hours. On `us-1` it has a daily bar on 100% of days and an hourly bar in 96.0% of hours. `BTC/USD` is complete on both (99.9% of hours or better). Volume over the last 30 days on `us-1` was 722 times that of `us` for Bitcoin and 255 times for PAXG. Daily closes on the two venues differ by a median of 0.02% for Bitcoin and 0.12% for PAXG. This is why RADAR uses `us-1`.
- **Volume is still one exchange's volume.** Kraken's volume is far larger than Alpaca's but it is not the global market. Do not build volume-based signals on it.
- **A quiet period can appear as a missing bar or as a quote-only bar.** Alpaca's docs say that when no trade occurs in a bar, volume is 0 and the prices come from quote mid-prices. **Measured:** that happens on `us` only from 2023, and on `us-1` only for PAXG from 2026; otherwise the bar is simply absent. Gap detection must therefore treat missing crypto bars as normal for thin symbols and record them, and every bar on every location stores a derived `is_quote_only` flag (`volume == 0`).
- **PAXG minute bars are too sparse to use. Measured:** in sampled weeks, `PAXG/USD` 1Min bars on `us-1` cover 8% to 31% of minutes in 2021 to 2025 and 80% in 2026. `BTC/USD` covers 99% or more. RADAR stores 1Hour and 1Day bars and computes realised volatility from hourly bars for every asset (`docs/DECISIONS.md` 010b).
- **Crypto `1Day` bars are stamped at 00:00 UTC and cover the following 24 hours. Measured:** on every location, and recent daily bars equal the 24 hourly bars that start at the stamp.
- **PAXG is not used for gold.** Its history is half as long as `GLD`'s, 4% of its hours have no bar, and it has almost no news. Section 3.7 gives the comparison.
- **Historical requests page by underlying minute data. Measured:** a `BTC/USD` 1Hour request returns about one week (167 or 168 bars) per page whatever `limit` is sent, so a full hourly history is about 300 calls per symbol. A full 1Day history fits in one page.

### 3.4 News caveats

- All news comes from one provider, Benzinga. Alpaca states an average of 130+ articles per day across all symbols.
- Article fields: headline, summary, content, author, created and updated timestamps, URL, symbols, source, images.
- Coverage is weighted towards US stocks, and its depth differs by symbol. **Measured**, articles per day:

| Symbol | First article | Before 2022 | 2022 to 2026 |
|---|---|---|---|
| `SPY` | 2015-01-02 | 3.9 to 36.3 | 21.8 to 25.5 |
| `BTCUSD` | 2022-01-04 (8 articles in 2021) | none | 10.5 to 14.2 |
| `GLD` | 2015-01-06 | 0.19 to 0.90 | 0.30 in 2022, then 1.36 to 1.75 |
| `PAXGUSD` | 2022-05-11 | none | 41 articles in total |
| any of `GLD`, `IAU`, `GDX`, `PAXGUSD` | 2015-01-06 | 0.20 to 0.99 | 0.38 in 2022, then 1.48 to 1.93 |

- **Bitcoin news starts in 2022.** F3 and F4 for Bitcoin cover 2022 onward, about 4.75 years at the audit date.
- **Gold news is thin.** Gold news is the set of articles tagged `GLD`, the same instrument used for the gold price (section 3.7). It averaged 1.36 to 1.75 articles per day from 2023, under the 2 per day this spec first set as a floor. The decision (`docs/DECISIONS.md` 010c and 011): gold F3 is shown from 2023-01-01 only, always with its article count, and gold F4 reports whatever its own rules give, including `not enough events`. Before 2023 gold news is shown as "insufficient news coverage". Do not pad the data.

### 3.5 Stock data caveats

- `SPY` and `GLD` trade only during US market hours; crypto trades continuously. Section 7.4 defines the alignment rule.
- Request split- and dividend-adjusted bars for stocks.
- **Measured:** `SPY` and `GLD` bars start on 2016-01-04.
- **Measured:** stock `1Day` bars are stamped at midnight America/New_York (04:00 or 05:00 UTC, depending on daylight saving). The stamp is the session date, not the time of the close. Code must map it to the 16:00 New York close before aligning with crypto.

### 3.6 Forex

The docs sidebar lists a Forex section. **Measured:** every forex request on the Basic plan, including a control pair, returns `403 forbidden: insufficient grants`. There is no `XAU/USD` reference series for RADAR; `GLD` is the only gold cross-check.

### 3.7 Gold instrument

Gold is represented by one instrument, `GLD` (`docs/DECISIONS.md` 011). It replaces `PAXG/USD`, which earlier drafts of this spec used; the PAXG measurements in section 3.3 are kept as the reason for the change.

**Measured on 2026-10-05:**

| | `GLD` | `PAXG/USD` on `us-1` | `XAU/USD` |
|---|---|---|---|
| Available on the Basic plan | yes | yes | no (`403`) |
| History starts | 2016-01-04 | 2021-01-01 | n/a |
| Daily bars | 2,703, none with zero volume | 2,104 | n/a |
| Hourly bars | every sampled session complete, none with zero volume | 96.0% of hours | n/a |
| Typical daily volume | about 8.1 million shares | about 520 PAXG | n/a |
| News articles per day, 2023 on | 1.36 to 1.75 | 41 articles in total | n/a |
| Trades | US market hours | all hours | n/a |

What this changes:

- Gold has ten years of history against five for Bitcoin. Each asset's models use its own full history.
- Gold has no weekend or overnight bars. Anything that compares Bitcoin with gold uses the mixed panel (section 7.4).
- Horizons for gold count trading days. A 7-day outlook for gold is the next 5 sessions; the UI states the session count.
- Live gold prices on the free plan come from the IEX feed during market hours. Hourly and daily history comes from the consolidated (SIP) feed, which is available once it is 15 minutes old.
- Stock bars are stored at 1Hour and 1Day.

---

## 4. Architecture

### 4.1 Layers

```
Alpaca REST + WebSocket
        |
   [providers]        rate-limited, retried, typed clients
        |
   [ingest]           backfill jobs and live stream consumers
        |
   raw layer          append-only Parquet, exactly as received
        |
   [quality]          validation, deduplication, calendar alignment, flags
        |
   clean layer        Postgres/TimescaleDB tables
        |
   [features]         returns, realised volatility, aligned return panels
        |
   [models] [analytics]   regime, simulator, sentiment, event study, portfolio
        |
   results tables     regime states, simulations, sentiment, signals, briefs
        |
   [api]              FastAPI: REST for results, WebSocket for live updates
        |
   [frontend]         React dashboard
```

### 4.2 Processes

Four containers, run with Docker Compose:

- `db`: PostgreSQL with the TimescaleDB extension.
- `api`: FastAPI application. Reads results, serves the frontend's requests, pushes live updates.
- `worker`: scheduled and streaming jobs. Runs ingestion, quality checks, model refits, scoring, signal detection, and the daily brief.
- `web`: the React app.

No message broker in version 1. The worker writes to the database and issues a Postgres `NOTIFY`; the API listens and forwards to WebSocket clients. This is enough for a single-user app and removes a moving part. Record this in `docs/DECISIONS.md`.

Only the `worker` opens Alpaca stream connections. Alpaca allows one connection per stream endpoint per account (section 3.2), so two workers, or a developer machine and a deployed worker, cannot stream with the same keys at the same time.

### 4.3 Schedules

| Job | Frequency |
|---|---|
| Live crypto bars and news | continuous stream, with REST gap-fill on reconnect |
| Stock daily bars | once after US market close |
| Data quality report | hourly |
| Sentiment scoring | on article arrival |
| Regime scoring (apply current model) | hourly |
| Simulation refresh | hourly |
| Signal detection | hourly, plus on regime change |
| Model refit (HMM, covariance) | weekly |
| Calibration and track record recompute | weekly |
| Daily brief | once per day at a configured UTC time |

---

## 5. Technology stack

Check current stable versions when installing; do not pin from memory.

**Backend:** Python 3.12+, `uv`, FastAPI, Pydantic, `pydantic-settings`, SQLAlchemy 2, Alembic, `psycopg` (PostgreSQL driver), `httpx`, `websockets`, APScheduler, `structlog`.

**Data and maths:** pandas, NumPy, SciPy, PyArrow, statsmodels, scikit-learn, `hmmlearn`, `pandera` for schema validation, `exchange_calendars` for market calendars.

**NLP:** Hugging Face `transformers` with the `ProsusAI/finbert` model, CPU inference.

**Experiment tracking:** MLflow with a local file store under `data/mlflow`.

**Database:** PostgreSQL with TimescaleDB.

**Frontend:** React, TypeScript, Vite, Tailwind CSS, TanStack Query, `lightweight-charts` for price charts, a general chart library for histograms and bar charts.

**Quality:** pytest, `respx`, `ruff`, `mypy`, Vitest, ESLint, GitHub Actions.

**Daily brief text:** a deterministic template renderer is the default and has no external dependency. An LLM rewrite sits behind a `BriefWriter` interface and a feature flag, with the provider and model name set in environment variables.

---

## 6. Data model

Timestamps are `timestamptz` in UTC. Tables marked (H) are TimescaleDB hypertables.

| Table | Key columns | Notes |
|---|---|---|
| `assets` | `symbol`, `asset_class`, `provider_symbols`, `is_primary` | canonical symbol plus per-endpoint mappings |
| `bars` (H) | `symbol`, `timeframe`, `ts`, `loc`, OHLC, `volume`, `trade_count`, `vwap`, `is_quote_only` | unique on (`symbol`, `timeframe`, `ts`, `loc`) |
| `news_articles` | `id`, `created_at`, `updated_at`, `headline`, `summary`, `author`, `url`, `source` | provider article id is the key |
| `news_symbols` | `article_id`, `symbol` | many-to-many |
| `news_sentiment` | `article_id`, `model_version`, `p_pos`, `p_neg`, `p_neu`, `score` | `score = p_pos - p_neg` |
| `sentiment_agg` (H) | `symbol`, `bucket`, `ts`, `score_mean`, `score_decayed`, `article_count` | hourly and daily buckets |
| `regime_states` (H) | `symbol`, `ts`, `model_version`, `probs` (JSON), `label` | filtered probabilities only |
| `simulations` | `symbol` or `portfolio_id`, `as_of`, `horizon_days`, `quantiles`, `histogram`, `model_version` | one row per run and horizon |
| `calibration_reports` | `symbol`, `model_version`, `horizon_days`, `nominal`, `empirical`, `n` | coverage of past intervals |
| `signals` | `id`, `symbol`, `ts`, `type`, `payload`, `track_record_id` | |
| `signal_track_records` | `type`, `symbol`, `computed_at`, `n`, forward-return statistics, `baseline`, `verdict` | |
| `portfolios`, `holdings` | `portfolio_id`, `symbol`, `quantity`, `source` | source is `manual` or `csv` in version 1 |
| `briefs` | `date`, `symbol`, `payload` (JSON), `text` | payload is the grounded input |
| `model_registry` | `name`, `version`, `trained_at`, `train_window`, `metrics`, `artefact_path` | |
| `factor_exposures` (H) | `symbol`, `ts`, `window_days`, `model_version`, `betas` (JSON), `r_squared`, `n` | F8, one row per asset, day, and window |
| `volatility_forecasts` (H) | `symbol`, `ts`, `horizon_days`, `model_version`, `forecast`, `realised` | F9; `realised` is filled in once known |
| `risk_metrics` (H) | `symbol` or `portfolio_id`, `ts`, `horizon_days`, `level`, `method`, `var`, `expected_shortfall` | F10 |
| `ingestion_runs` | `job`, `window`, `status`, `rows`, `started_at`, `finished_at` | |
| `data_quality_reports` | `ts`, `symbol`, `check`, `status`, `detail` | |

---

## 7. ML and data pipeline

The pipeline has ten stages. Each maps to a package in the repo and to steps in the build plan.

### 7.1 Ingestion (`providers/`, `ingest/`)

- A token-bucket rate limiter holds REST calls under the plan limit with headroom (target 150 per minute).
- Retries with exponential backoff and jitter on 429 and 5xx responses. Follow `next_page_token` pagination to the end.
- Backfill requests data in date chunks and records each chunk in `ingestion_runs`, so an interrupted backfill resumes where it stopped. Hourly crypto history costs about 300 calls per symbol (section 3.3).
- Stream consumers reconnect automatically. After a reconnect, a REST call fills the gap between the last stored bar and now.
- Every response is written unchanged to the raw layer as Parquet, partitioned by source, symbol, and date.

### 7.2 Validation and cleaning (`quality/`)

- Schema validation with `pandera`: types, non-null keys, `high >= max(open, close)`, `low <= min(open, close)`, prices above zero, volume not negative.
- Deduplicate on the natural key, keeping the latest received version.
- Gap detection: compare stored timestamps against the expected calendar (continuous for crypto, exchange calendar for stocks). Missing hourly bars are normal for thinly traded crypto symbols (section 3.3). Record gaps; never fill prices by interpolation. Forward-fill is allowed only when building aligned panels and is flagged.
- Outlier flagging: a bar whose return exceeds a robust threshold (for example 10 median absolute deviations for its timeframe) is flagged for review, not deleted.
- Set `is_quote_only`.
- News: strip HTML from `content`, normalise whitespace, drop exact duplicate headlines within a short window for the same symbol, keep `updated_at` revisions as the latest version.

### 7.3 Exploratory analysis (notebooks, then `docs/DATA_AUDIT.md`)

Phase 0 and Phase 1 produce measured facts: history depth, missing-data rates, quote-only share, return distributions, volatility clustering, autocorrelation of returns and of squared returns, and news counts per symbol per year. These numbers decide parameters later in the spec.

### 7.4 Feature engineering (`features/`)

- Log returns at 1 hour and 1 day.
- Realised volatility, from hourly bars for every asset. Crypto: square root of the sum of squared hourly log returns per UTC day; a day with fewer than a configured number of hourly bars (start at 18) has no value and is flagged. Stocks: per trading session, the square root of the squared overnight log return (previous close to open) plus the sum of squared hourly log returns inside regular hours, so the figure covers the full day as the crypto figure does.
- Daily range: `log(high / low)`.
- Rolling statistics (means, standard deviations, z-scores) use trailing windows only.
- **Alignment rule for mixed calendars.** Two panels are built:
  - *Crypto panel:* daily returns on UTC day boundaries, seven days a week. Used for crypto assets on their own and against each other.
  - *Mixed panel:* returns sampled at 16:00 America/New_York on NYSE trading days, with crypto prices taken from the hourly bar at that time. Stock daily bars carry a midnight New York stamp (section 3.5); their close belongs to 16:00 that day. A weekend's crypto move lands in Monday's return. Used whenever `SPY` or `GLD` is involved.
- Scalers and any fitted transforms are fitted on training windows only and stored with the model version.

### 7.5 Splitting

Walk-forward evaluation with an expanding training window. A model evaluated at date `t` is fitted on data strictly before `t`. No random splits anywhere.

### 7.6 Training

Each model's method is in section 8. All training runs log parameters, the data window, metrics, and the artefact path to MLflow, and write a row to `model_registry`.

### 7.7 Evaluation

Each model has a stated baseline and a stated metric in section 8. A model that does not beat its baseline is still shipped if the feature needs it, but the app shows the comparison.

### 7.8 Deployment

Models are loaded by the worker from `model_registry`. Scoring jobs write results tables. The API never runs a model inside a request; it reads stored results. This keeps response times flat and makes every displayed number reproducible from a stored row.

### 7.9 Monitoring

- Data: ingestion lag, gap counts, quote-only share, news arrival rate.
- Models: distribution of regime probabilities over time, simulator coverage on new data, sentiment score distribution drift (population stability index against the training period).
- System: job success and duration, API latency, WebSocket client count.
- A `/health` endpoint and a status page in the app expose these.

### 7.10 Retraining

Scheduled weekly refits. A refit replaces the live model only if it passes the same evaluation as the current one; otherwise the old model stays and the failure is logged.

---

## 8. Feature specifications

Each feature lists its method, baseline, evaluation, output, and what counts as done.

### F1. Regime detector

- **Method:** Gaussian hidden Markov model on daily observations of [log return, log realised volatility]. Fit candidates with 2, 3, and 4 states and choose by BIC; expect 3. Fit with several random initialisations and keep the best likelihood.
- **State labels:** order states by their volatility mean after every fit and name them `calm`, `normal`, `turbulent` (for 3 states). This prevents labels swapping between refits.
- **Live output:** filtered state probabilities, computed with the forward algorithm only. Smoothed probabilities may be used for a clearly labelled "hindsight" view of history, never for the current state or for any backtest.
- **Baseline:** a rule that assigns regimes by rolling 30-day volatility terciles.
- **Evaluation:** walk-forward. Report out-of-sample log-likelihood against the baseline, the average realised volatility in the days after each predicted state (states must be separated and ordered), and state persistence (average run length).
- **UI output:** current state and probability, price chart shaded by regime, transition matrix shown as "typical duration" and "what usually comes next".
- **Done when:** the no-lookahead test passes, labels are stable across refits on overlapping data, and next-day realised volatility is ordered by predicted state out of sample.

### F2. Outcome simulator

- **Method:** regime-switching Monte Carlo. Start from the current filtered state probabilities. For each path and each day, draw the next state from the transition matrix, then draw that day's return by bootstrapping from historical returns observed in that state. Bootstrapping keeps fat tails that a normal distribution would miss. 10,000 paths; horizons of 1, 7, and 30 days.
- **Outputs:** histogram of terminal prices; 5, 25, 50, 75, and 95 percent quantiles; probability of finishing above or below a user-entered level; probability of touching that level at any point in the horizon (these are different numbers and are labelled separately); expected worst drawdown.
- **Baseline:** geometric Brownian motion with constant volatility estimated over the trailing year.
- **Evaluation:** walk-forward calibration. For each historical date, generate the 50, 80, and 95 percent intervals and check whether the realised price fell inside. Report empirical against nominal coverage per horizon, plus pinball loss against the baseline.
- **UI output:** histogram, fan chart, level-probability input, and a calibration panel ("the 80% range has contained the outcome in X% of N past cases").
- **Done when:** the simulation is reproducible from a stored seed, the calibration report exists for every horizon, and the calibration panel renders from stored data.

### F3. News sentiment pulse

- **Method:** score each article's headline and summary with FinBERT. `score = P(positive) - P(negative)`. Aggregate per symbol into hourly and daily buckets: mean score, article count, and an exponentially decayed score (half-life starts at 24 hours). Bitcoin uses articles tagged `BTCUSD`, from 2022. Gold uses the gold news set from 2023 (section 3.4).
- **Baseline:** a finance sentiment word list (Loughran-McDonald).
- **Evaluation:** hand-label a random sample of 200 stored headlines (stratified by symbol) and report accuracy and macro F1 for FinBERT and the baseline. This is an evaluation set only. Fine-tuning is a stretch goal and needs its own, larger labelled set.
- **UI output:** sentiment line under the price chart, article count bars, and a list of the articles with the strongest scores linking to the source.
- **Done when:** every stored article has a score for the current model version, aggregates update on arrival, and the evaluation numbers are in the model registry and visible in the methodology page.

### F4. Sentiment versus price

- **Method, part 1 (event study):** define an event as a day where the daily sentiment z-score exceeds 2 in absolute value (trailing one-year window). For each event compute cumulative returns from 24 hours before to 72 hours after, minus the asset's mean return over the trailing 90 days. Average across events separately for positive and negative shocks. Confidence bands by bootstrap. Events closer than 72 hours apart are merged.
- **Method, part 2 (lead-lag):** cross-correlation between daily sentiment and daily returns at lags from -5 to +5 days, with significance bands. Report whether the larger correlations sit where sentiment leads or where price leads.
- **Baseline:** the same statistics on randomly chosen dates, matched on regime.
- **Verdict labels:** `sentiment leads price`, `price leads sentiment`, `no measurable relationship`, or `not enough events` (fewer than 30).
- **UI output:** average path chart around positive and negative events with bands, the lead-lag bar chart, the verdict, and the event count.
- **Done when:** the verdict is derived by a tested rule from the statistics, and the feature displays `not enough events` correctly on a symbol with thin news.

### F5. Bitcoin versus gold

- **Method:** rolling 30-day and 90-day correlation of daily returns between `BTC/USD` and `GLD` on the mixed panel (windows count trading days). Report the correlation conditional on Bitcoin's regime from F1.
- **Weekend note:** gold does not trade at weekends, so a weekend Bitcoin move is compared with gold's Friday-to-Monday move. The UI says so.
- **UI output:** correlation time series, a small table of correlation by regime with sample sizes, and one sentence stating the current reading.
- **Done when:** the correlation series and the by-regime table render from stored data, sample sizes are displayed, and the weekend treatment is stated in the UI.

### F6. Portfolio lab

- **Input:** holdings as (symbol, quantity) by manual entry or CSV upload through the `HoldingsSource` interface. Only symbols with stored price history are accepted; others are listed as unsupported.
- **Risk model:** covariance of daily returns on the mixed panel with Ledoit-Wolf shrinkage. Minimum history per asset set from the audit; start at 250 trading days.
- **X-ray:** weights, volatility per asset, each asset's percentage contribution to portfolio variance, correlation matrix, and historical maximum drawdown of the current mix.
- **Allocations compared:** current, equal weight, minimum variance, equal risk contribution, and hierarchical risk parity. Long-only, with a configurable maximum weight per asset.
- **Evaluation:** walk-forward backtest with monthly rebalancing and a configurable cost per trade (start at 10 basis points). Report volatility, maximum drawdown, and turnover for each allocation. Returns are shown but labelled as history, not expectation.
- **Portfolio simulation:** block bootstrap of joint daily returns to preserve cross-asset dependence; same outputs as F2 at 30 and 90 days.
- **Core and satellite report:** the user tags holdings as core or satellite. Show the satellite sleeve's share of weight against its share of risk, and its historical contribution to return.
- **Rebalancing signal:** when any weight drifts more than a configurable threshold (start at 5 percentage points) from the user's chosen target, list the trades that would restore it.
- **Done when:** risk contributions sum to 100 percent in a test, optimised weights satisfy their constraints in tests, and the backtest has no lookahead (weights at `t` use covariance estimated before `t`).

### F7. Signals and daily brief

- **Signal types:**
  - `regime_change`: the most probable state changes and its probability exceeds 0.7.
  - `abnormal_move`: an hourly return more than 3 standard deviations from zero, using the current regime's volatility. Based on price only, because venue volume is unreliable (section 3.3).
  - `sentiment_shock`: daily sentiment z-score beyond 2.
  - `rebalance_drift`: from F6.
- **Track record:** for each signal type and symbol, find every historical occurrence using only information available at the time. Report the count, the distribution of forward returns at 1 and 7 days, the share of positive outcomes with a confidence interval, and the same statistics for all days as a baseline. The verdict is `no measurable edge` when the interval overlaps the baseline.
- **Daily brief:** a JSON payload assembled from F1 to F6 results, rendered to a short paragraph per asset by a template. If the LLM writer is enabled, it receives only the payload and its output is rejected and replaced by the template version if it contains any number not in the payload.
- **Done when:** each signal shown in the UI links to its track record, the grounding test passes, and the template writer works with no API key set.

### F8. Macro drivers

- **Method:** rolling regression of each primary asset's daily return on the daily returns of the macro driver assets, on the mixed panel, over trailing 90-day and 250-day windows. Ridge regularisation, because the drivers are correlated with each other. Report each driver's coefficient with a bootstrap confidence interval, the share of variance explained (R squared), and how both have moved over time.
- **Baseline:** a model with `SPY` as the only driver.
- **Evaluation:** walk-forward. Fit on a window, then measure out-of-sample R squared on the following 20 trading days, against the baseline.
- **Verdict per driver:** `moves with`, `moves against`, or `no measurable link` when the interval includes zero.
- **UI output:** a bar per driver with its interval, a line of R squared over time, and one sentence naming the strongest current driver or saying that none is measurable.
- **Done when:** the no-lookahead test passes, intervals are shown beside every coefficient, and `no measurable link` displays correctly for a driver whose interval includes zero.

### F9. Volatility forecast

- **Method:** a HAR model (heterogeneous autoregressive): next-period realised volatility regressed on the average realised volatility of the last day, week, and month, fitted on log volatility. Horizons of 1 and 7 days (5 sessions for gold).
- **Second model:** gradient-boosted trees (scikit-learn) on the same inputs plus the current regime probabilities and the daily sentiment aggregate. It is shown only if it beats HAR out of sample.
- **Baselines:** yesterday's volatility carried forward, and the average volatility of the current regime from F1.
- **Evaluation:** walk-forward with an expanding window. QLIKE loss and mean squared error against both baselines, with a Diebold-Mariano test for whether the difference is real.
- **UI output:** forecast beside the last realised value, a chart of past forecasts against what happened, and the evaluation table.
- **Use elsewhere:** the forecast scales the F10 risk figures. It does not change the F2 simulator in version 1.
- **Done when:** the no-lookahead test passes, the evaluation table is stored for every horizon, and the UI states which model is shown and why.

### F10. Tail risk

- **Measures:** Value at Risk and expected shortfall at 95% and 99%, over 1 day and 7 days, for each primary asset and for the portfolio. Value at Risk is the loss that should be exceeded only 5% (or 1%) of the time; expected shortfall is the average loss when it is exceeded.
- **Methods compared:** historical simulation; filtered historical simulation (past returns rescaled to the F9 volatility forecast); and the F2 regime-switching simulator's own distribution.
- **Evaluation:** walk-forward backtest. Count how often the realised loss exceeded each limit and compare with the nominal rate, using Kupiec's coverage test and Christoffersen's test for whether breaches cluster.
- **UI output:** the figures as a percentage and in money for the user's holdings, the breach count against the expected count, and the worst historical drawdowns with their dates.
- **Done when:** breach rates are stored and shown for every method and level, the method displayed is the one with the best backtest, and a limit that fails its coverage test is marked as unreliable in the UI.

---

## 9. API

All routes are under `/api/v1`. Responses are Pydantic models; the OpenAPI schema generates frontend types.

| Route | Returns |
|---|---|
| `GET /assets` | configured universe |
| `GET /assets/{symbol}/bars` | bars for a timeframe and window |
| `GET /assets/{symbol}/regime` | current state, probabilities, history, transition summary |
| `GET /assets/{symbol}/simulation` | latest simulation per horizon |
| `POST /assets/{symbol}/simulation/level` | probabilities for a user-entered price level, from stored paths |
| `GET /assets/{symbol}/calibration` | coverage table |
| `GET /assets/{symbol}/sentiment` | aggregates and top articles |
| `GET /assets/{symbol}/event-study` | event paths, lead-lag, verdict |
| `GET /relationships/btc-gold` | correlation series, by-regime table, tracking gap |
| `GET/PUT /portfolio` | holdings and tags |
| `POST /portfolio/import` | CSV upload |
| `GET /portfolio/xray` | risk breakdown |
| `GET /portfolio/allocations` | allocation comparison and backtest summary |
| `GET /portfolio/simulation` | portfolio outcome distribution |
| `GET /signals` | recent signals with track record summaries |
| `GET /signals/track-records/{type}` | full track record |
| `GET /briefs/latest` | today's brief |
| `GET /methodology` | model versions, evaluation metrics, data coverage |
| `GET /assets/{symbol}/drivers` | macro driver coefficients, intervals, R squared history |
| `GET /assets/{symbol}/volatility` | forecasts, past forecasts against realised, evaluation |
| `GET /assets/{symbol}/risk` | Value at Risk and expected shortfall with breach history |
| `GET /portfolio/risk` | the same tail-risk figures for the portfolio |
| `GET /health` | pipeline and data status |
| `WS /stream` | live bars, new signals, new articles |

---

## 10. Frontend

Six screens:

1. **Overview:** today's brief, current regime for Bitcoin and gold, latest signals, live prices.
2. **Asset page (Bitcoin, Gold):** tabs for Regime, Outlook (simulator, calibration, volatility forecast, and tail risk), News (sentiment and the sentiment-versus-price study), and Drivers (F8).
3. **Bitcoin versus gold:** F5.
4. **Portfolio:** holdings entry, X-ray, allocation comparison, portfolio outlook, rebalancing.
5. **Signals:** feed with filters; each signal opens its track record.
6. **Methodology and status:** how each number is produced, model versions, evaluation results, data coverage, pipeline health, and the limitations in section 14.

Rules: every chart has a caption with window and sample size; probability and uncertainty are always shown with the number; a persistent footer states that RADAR is analytics, not financial advice. Times are stored in UTC and shown in the viewer's local time zone, taken from the browser, with the zone named beside the time (for example "04:00 GMT+8"). The US market close is also labelled as such, since gold only updates while that market is open.

---

## 11. Build plan

Eight phases. Each ends in something that runs and can be shown.

### Phase 0: Bootstrap and data audit

1. Create the repo layout from `CLAUDE.md`, `pyproject.toml`, Docker Compose, Makefile, `.env.example`, `.gitignore`, linters, and a CI workflow that runs lint and tests.
2. Write the Alpaca REST client with rate limiting, retries, pagination, and typed responses. Record fixtures for tests.
3. Write `make audit`: a probe script that answers every "verify in Phase 0" item in section 3 and writes `docs/DATA_AUDIT.md` with the measured numbers.
4. Review the audit against the spec and update the spec where they differ.

*Done when:* `make audit` runs from a clean checkout with only `.env` filled in, CI is green, and the audit file answers every open item.

### Phase 1: Data platform

1. Database models and migrations for `assets`, `bars`, `news_*`, `ingestion_runs`, `data_quality_reports`.
2. Raw Parquet writer and resumable backfill for bars (all configured symbols, 1Hour and 1Day, crypto from location `us-1`) and news.
3. Validation, cleaning, flags, and gap detection.
4. Live stream consumers with reconnect and gap-fill.
5. Feature builders: returns, realised volatility, both aligned panels.
6. An exploratory notebook whose key figures are copied into the audit file.

*Done when:* a re-run of the backfill changes zero rows, killing and restarting the worker leaves no gaps, and alignment tests pass on a hand-built example including a weekend.

### Phase 2: API and dashboard shell

1. FastAPI app, health route, assets and bars routes, WebSocket stream.
2. React app with routing, layout, generated API types, live price chart for Bitcoin and gold, and the status page.

*Done when:* `make up` shows a live Bitcoin chart updating in the browser, and a gold (`GLD`) chart that updates during US market hours and shows the last close, clearly labelled, when the market is shut.

### Phase 3: Regime and outlook

1. F1: HMM module, walk-forward evaluation, baseline, registry entry, scoring job.
2. F2: simulator, calibration job, baseline comparison.
3. F9: HAR and gradient-boosted volatility forecasts, baselines, evaluation.
4. F10: tail-risk measures for single assets, with the breach backtest.
5. Asset page tabs for Regime and Outlook.

*Done when:* the done-when items for F1, F2, F9, and F10 hold and the calibration panel shows real coverage numbers.

### Phase 4: News

1. F3: sentiment scoring job, aggregates, hand-labelling tool (a simple script that shows a headline and records a label), evaluation.
2. F4: event study, lead-lag, verdict rule.
3. News tab on the asset page.

*Done when:* the done-when items for F3 and F4 hold for Bitcoin, and gold shows either results or the insufficient-coverage state decided by the audit.

### Phase 5: Relationship and portfolio

1. F5 and its screen, and F8 with the Drivers tab.
2. F6: holdings sources, risk model, allocations, backtest, portfolio simulation, core and satellite report, and the Portfolio screen.

*Done when:* the done-when items for F5, F6, and F8 hold on a sample portfolio fixture, and portfolio tail risk (F10) is shown.

### Phase 6: Signals and brief

1. Signal detectors and track record computation.
2. Brief payload, template writer, optional LLM writer with the grounding check.
3. Overview and Signals screens.

*Done when:* the done-when items for F7 hold and the Overview screen renders entirely from stored results.

### Phase 7: Hardening and demo

1. Monitoring metrics, drift checks, weekly refit with promotion gate.
2. Demo mode (section 12).
3. Methodology screen completed with real numbers.
4. Production Compose file, README with setup steps, and a deployment note for a single small server.

*Done when:* a new machine can go from clone to running demo with the README alone.

### Later, not in version 1

- Read-only Binance `HoldingsSource` and automatic trade journal.
- Fine-tuned sentiment model.
- Additional news or macro data sources for gold.

---

## 12. Demo mode and demo script

### Demo mode

`make demo` starts the app against stored data and replays a chosen historical window at accelerated speed through the same WebSocket the live stream uses. Models and results are those that were valid at each replayed moment. The demo therefore works with no network and shows an eventful day on demand. The UI displays a visible "Replay" badge whenever demo mode is on.

### Five-minute demo script

1. **Overview (30 seconds):** read today's brief aloud. Point out that each sentence links to its source panel.
2. **Bitcoin regime (60 seconds):** show the shaded chart; the audience can see past turbulent periods match what they remember.
3. **Outlook (90 seconds):** type a price level and read the two probabilities. Then open the calibration panel and show how often past ranges held. This is the moment that earns trust.
4. **News (60 seconds):** show a sentiment shock and the average price path around such events, then the verdict, including the case where it says there is no relationship.
5. **Portfolio (60 seconds):** load the sample portfolio and show a small holding that carries a large share of the risk.

---

## 13. Product copy

Tone: plain, specific, no hype. The copy must stay true to section 14.

### Hero

**Know what kind of market you are in.**

RADAR: Regimes, Analytics, Distributions, Alerts, Risk.

RADAR reads Bitcoin and gold the way a risk desk would: the current regime, the realistic range of outcomes, and what the news has measurably done to price. Every number comes with its track record.

Button: **Open the dashboard**

### Feature blurbs

**Market regime.** Calm, normal, or turbulent. RADAR classifies the market each hour from price behaviour and shows how long each state has tended to last.

**Outlook.** A distribution, not a price target. See the plausible range for the next day, week, or month, and the probability of reaching a level you choose.

**Checked against history.** When RADAR says 80% of outcomes fall in a range, it also shows how often that has been true so far.

**News, measured.** Each headline is scored for tone. RADAR then tests whether tone has moved price for this asset, and tells you when it has not.

**Bitcoin and gold.** Track whether Bitcoin is moving with gold or apart from it, and how that changes when markets turn rough.

**Your portfolio's risk.** Enter your holdings to see which ones drive the swings, and how risk-based allocations would have compared.

**Signals with receipts.** Each alert shows what followed similar conditions in the past, including when the answer is "nothing reliable".

### What RADAR does not do

- It does not predict prices.
- It does not place trades or hold your funds.
- It does not give financial advice. It gives you measurements; decisions are yours.

### Footer disclaimer

RADAR is an analytics tool for information and education. It is not financial advice. Historical patterns do not guarantee future results. Gold is represented by GLD, an exchange-traded fund backed by physical gold. It trades only during US market hours and can differ slightly from the spot gold price.

### Empty and limited states

- Not enough news: "There is too little news coverage of this asset to measure an effect."
- No edge: "Historically this signal has not been followed by a reliable move."
- Short history: "This asset has less than a year of data here. Treat these figures as rough."

---

## 14. Risks and known limitations

State these on the Methodology screen.

1. **Single venue.** Crypto prices and volume come from one exchange's feed (Kraken, through Alpaca). Prices track the wider market closely for Bitcoin; volume does not represent it.
2. **Gold proxy.** Gold is represented by the GLD fund. It trades only in US market hours, so gold figures do not move at weekends or overnight, and it carries a small management fee that makes it drift slowly below spot gold.
3. **Single news source.** One provider, weighted towards US stocks. Sentiment reflects that provider's coverage, not all news. Bitcoin coverage starts in 2022. Gold coverage is under 2 articles per day and is used from 2023 only.
4. **Short crypto history.** Crypto data starts in 2021. Regimes and tail events are estimated from a limited number of years. Rare events are under-sampled.
5. **Regime models describe, they do not forecast turning points.** A regime change is detected after it starts.
6. **Simulations assume the future resembles the sampled past.** Calibration is reported so the user can see how well that has held.
7. **Sentiment models misread sarcasm, negation, and headlines about price itself.** Evaluation accuracy is published in the app.
8. **Portfolio statistics are sensitive to the window.** Covariances change, most of all in stress.
9. **Free plan limits.** Stock data is from one exchange in real time, or consolidated with a delay.
10. **No private information.** Moves driven by information that is not public will appear as unexplained.
