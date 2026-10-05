# RADAR

RADAR is a market outlook web app for Bitcoin, gold, and US stocks, with a portfolio layer on top. It tells the user what state the market is in, what range of outcomes is plausible, and what the news is doing to price. It is an analytics product. It never places trades.

The full specification is in `docs/PROJECT_SPEC.md`. Read the sections relevant to your task before writing code. Do not import the whole file into every session; open the section you need.

## Current status

Update this block at the end of every work session.

- Phase: 4 (news) is built on branch `phase-4-news`; Phases 0 to 3 are merged to `main`
- Last completed step: Phase 4: tone scoring (F3) with stored aggregates, word-list baseline, 200 evaluation labels, topics for every article, the sentiment-versus-price study overall and by topic (F4), routes, the News panel, the sidebar; a leakage-safe fine-tuning pipeline (run once, not adopted: decision 031); and model notebooks 02 to 06
- Next step: Phase 5 (relationships, macro drivers, portfolio). Still owed from earlier phases: the F9 tree model with sentiment as an input (decision 028)
- The language models need `uv sync --extra nlp` and run on the host, not in the Docker worker (decision 030)
- Carried forward: shading the price chart by regime is not built (decision 028)
- Interface direction is decision 023: follow it for every new screen (liquid glass, Inter, no developer wording, only show what exists). The user will revisit the interface in each phase
- Key decisions (`docs/DECISIONS.md` 010 to 031): primary assets are `BTC/USD`, `GLD` (gold), and `SPY`; `PAXG/USD` is portfolio-only; crypto from location `us-1`; 1Hour and 1Day bars only; live bars are pushed to the app but stored bars always come from REST; version 1 also includes macro drivers (F8), volatility forecast (F9), tail risk (F10), and a read-only Binance holdings source
- The user is in GMT+8: give times in GMT+8 in chat
- Open questions: none

## How to work in this repo

1. Work one phase at a time, in the order given in section 11 of the spec. Stop at the end of each phase and summarise what was built, what was verified, and what is still uncertain.
2. Before starting a phase, restate its "done when" criteria and list the files you plan to create or change.
3. Phase 0 produces `docs/DATA_AUDIT.md`. Several numbers in the spec are marked "verify in Phase 0". Where the audit contradicts the spec, the audit wins: update the spec and tell the user.
4. Ask before adding a dependency that is not in section 5 of the spec.
5. Keep commits small and scoped to one step. Use conventional commit messages (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).

## Hard rules

These apply to every change.

- **No trading.** Do not import, call, or wrap any order, position, or transfer endpoint from Alpaca or any other provider. Market data and news endpoints only. One exception, approved by the user on 2026-10-05: a read-only Binance `HoldingsSource` may call Binance endpoints that **read** account balances and open positions, with an API key that has no trading and no withdrawal permission. It must never call an endpoint that places, changes, or cancels an order, moves funds, or changes account settings, and a test must assert that.
- **Paper keys only.** The Alpaca keys in `.env` must be paper account keys, never live keys. The only Alpaca host this app calls is `data.alpaca.markets` (and its `stream.data.alpaca.markets` WebSocket). Never call `api.alpaca.markets` or `paper-api.alpaca.markets`. A test asserts that the provider clients reject any other base URL.
- **No secrets in the repo.** Keys live in `.env`, which is gitignored. `.env.example` holds names only. Never print keys in logs, tests, or error messages.
- **No lookahead.** A value shown for time `t` may only use data with timestamp `<= t`. This covers features, labels, regime probabilities (use filtered, never smoothed, for anything displayed as "current" or used in a backtest), scalers, and train/test splits. Every model module needs a test that proves it.
- **Time-ordered evaluation only.** Walk-forward or expanding-window splits. Never shuffle time series.
- **UTC everywhere in storage and APIs.** Convert to local time only in the frontend. Store timezone-aware timestamps.
- **Idempotent ingestion.** Re-running any ingestion job for the same window must produce the same rows (upsert on natural keys).
- **Raw data is immutable.** The raw layer is append-only. Cleaning writes to a separate layer.
- **Honest output.** Every conclusion shown in the UI carries its evidence: sample size, time window, and uncertainty. If a signal shows no measurable edge, the UI says so. Never write "buy", "sell", or "you should" in user-facing text; use "signal", "historically", and "probability".
- **Numbers in generated text come from data.** The daily brief may only contain numbers present in its input payload. A test enforces this.

## Commands

Keep this list accurate as targets change. Each target wraps `uv run radar <target>`, which works without Make (for example `uv run radar audit`). `test` and `lint` include the frontend once `npm --prefix frontend ci` has been run.

```
make up              # start db, api, worker, web with docker compose; app on http://localhost:8080
make down            # stop everything
make migrate         # run Alembic migrations
make audit           # run the Phase 0 data probe and rewrite docs/DATA_AUDIT.md (about 70 minutes;
                     # `uv run radar audit --resume` runs only missing sections)
make backfill        # historical backfill for the configured universe (about 17 minutes the first
                     # time, seconds after that; needs `make up` and `make migrate`)
make test            # backend pytest + frontend vitest (database tests need `make up` first)
make lint            # ruff, mypy, eslint, tsc
make demo            # start the app in replay mode from stored data

uv run radar api        # serve the API on http://127.0.0.1:8000 (development)
npm --prefix frontend run dev   # serve the web app on http://localhost:5173 (development)
uv run radar openapi    # rewrite frontend/openapi.json; then `npm --prefix frontend run gen:api`
uv run radar regime     # train the regime model where missing, then score (--retrain to refit)
uv run radar simulate   # store today's outcome simulation (--recalibrate to measure past ranges again)
uv run radar volatility # forecast volatility for new days and score the models
uv run radar risk       # estimate tail risk for new days and backtest (run after volatility)
uv run radar sentiment  # score news tone and topics (needs `uv sync --extra nlp`), refresh summaries,
                        # measure accuracy, rerun the sentiment-versus-price study
uv run radar finetune   # fine-tune the sentiment model and test it on held-out headlines (needs nlp)
uv run radar quality    # check stored data, set flags, write data quality reports
uv run radar worker     # live streams plus hourly sync and quality jobs (one per set of keys)
uv run radar profile    # measure the stored data and rewrite docs/DATA_PROFILE.md
uv run python backend/scripts/build_notebook.py   # rebuild notebooks/01_exploration.ipynb
uv run python backend/scripts/build_notebooks.py  # rebuild notebooks 02 to 06 from notebooks/src/
```

## Code conventions

Backend (Python 3.12+, managed with `uv`):

- Type hints on every function. `mypy --strict` passes on `src/`.
- `ruff` for lint and format.
- Pydantic models at every boundary: API payloads, provider responses, config.
- Provider access goes through the client classes in `radar/providers/`. Nothing else makes HTTP calls to Alpaca.
- Pure functions for all maths (features, models, statistics). I/O stays in `pipelines/` and `api/`.
- Each model lives in its own module with the same interface: `fit`, `predict`, `evaluate`, `save`, `load`, and a `MODEL_VERSION` string.
- Structured JSON logging. No `print`.
- Tests sit next to the behaviour they cover in `tests/`, mirroring `src/`. Provider tests use recorded fixtures, never live calls.

Frontend (React, TypeScript, Vite):

- Strict TypeScript, no `any`.
- Server state through TanStack Query. No ad hoc `fetch` in components.
- API types are generated from the backend OpenAPI schema, not written by hand.
- Every chart has a caption stating what it shows, the time window, and the sample size.

## Repo map

```
backend/
  src/radar/
    providers/     # Alpaca REST and WebSocket clients, rate limiting, retries
    ingest/        # backfill and live ingestion jobs
    quality/       # validation, cleaning, data quality reports
    features/      # returns, volatility, calendars, alignment
    models/        # regime (HMM), simulator (Monte Carlo), sentiment, portfolio
    analytics/     # event study, lead-lag, correlation, signal track records
    signals/       # signal detection and scoring
    brief/         # daily brief generation
    pipelines/     # orchestration of the steps above
    api/           # FastAPI routers and schemas
    db/            # SQLAlchemy models, Alembic migrations
  tests/
frontend/
  src/
docs/
  PROJECT_SPEC.md  # the reference specification
  DATA_AUDIT.md    # generated in Phase 0, measured facts about the data
  DECISIONS.md     # short log of design decisions and why
data/              # gitignored: raw Parquet, model artefacts, MLflow store
```

## When something is unclear

If the spec and the data disagree, or a method in the spec does not work on the real data, do not silently substitute something else. Write the problem and the options into `docs/DECISIONS.md` and ask the user.
