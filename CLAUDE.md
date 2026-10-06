# RADAR

RADAR is a market outlook web app for Bitcoin, gold, and US stocks, with a portfolio layer on top. It tells the user what state the market is in, what range of outcomes is plausible, and what the news is doing to price. It is an analytics product. It never places trades.

The full specification is in `docs/PROJECT_SPEC.md`. Read the sections relevant to your task before writing code. Do not import the whole file into every session; open the section you need.

## Current status

Update this block at the end of every work session.

- Phase: Phase 5 and Phase 6 part 1 are merged to `main`. The portfolio tools (regular buying, ticker lookup) are on branch `portfolio-tools` (pull request open or merged: check `git log main`)
- Last completed step: portfolio tools (decision 053): a regular-buying simulator the user sets up themselves, compared with putting the same total in at once and checked walk-forward (tab `/portfolio/buying`, `POST /portfolio/regular-buying`, notebook 09), and a ticker box on Try a mix and Regular buying that looks up any US stock or Alpaca crypto and fetches its history (`POST /portfolio/lookup`). Before that, the two signal questions were decided (decision 052). Before that, Phase 6 part 1 (decision 051): the three signal rules replayed walk-forward, a track record per kind of signal with verdicts on direction and on the size of the move (both corrected for multiple comparisons), tables `signals` and `signal_track_records`, `GET /signals` and `GET /signals/track-records/{type}`, and notebook 08. Result: no signal has an edge in direction; abnormal moves in US stocks were followed by larger moves. Before that, Phase 5D part 2 (decision 050): the value range ahead by block bootstrap, checked walk-forward and stated beside a bell-curve baseline it did not beat; the core and satellite report, with tags kept by symbol; and notebook 07 on the whole portfolio layer. Before that, "Try a mix" (decision 049): the user sets each asset's share and sees the resulting risk beside the portfolio as it is; levels and splits are only starting points; a tried mix can be the target. It replaced the three fixed level cards. Before that, Phase 5D part 1 (decision 048): five ways to split the holdings with a walk-forward backtest, low / moderate / high risk levels applied to the user's holdings, a chosen target, and signals against it (movement outside the band, drift, turbulent market). Before that, Phase 5C (decisions 044, 045): a pre-registered walk-forward test of whether news volume and tone improve the swings forecast. Result: no measurable gain in any of twelve comparisons, so news is not in the forecast and no variants are to be tried on this data. Before that, Phase 5B (decision 039): correlations, risk transmission, weekend gaps, macro drivers, the "Markets together" screen and the "Outside forces" tabs; and the read-only Binance source with cash as a holding and the portfolio tied to market states, drivers, and the weekend (decision 038). Before that, Phase 5A (decision 037): holdings by manual entry and CSV, the portfolio X-ray, loss limits, stress episodes, and the Portfolio screen; and the market page as tabs with real addresses (decision 036). Before that, fluid layout and chart fixes (decision 034) and the product pass (decision 033): an "In brief" card and `GET /assets/{symbol}/summary`; a Solid, Fair, or Rough trust mark on every claim from fixed rules in `analytics/summary.py`; sections folded behind their claims; news articles listed unranked and topics folded away
- Next step: Phase 6 part 2, the daily brief (payload, template writer, the grounding test that every number in the text is in the payload, optional LLM writer behind a flag), then part 3, the Signals and Overview screens (each signal links to its track record). The feed shows changes of state and abnormal moves only; news-tone shocks are scored as evidence and never shown in the feed or the brief (decision 052). News drives no forecast and no signal (decision 045). After Phase 6 the user wants a macro event layer (Fed decisions, jobs reports, CPI): a calendar, how much each market moves on those days, and pre-registered tests of direction after the release; the dates come once from the official Fed and BLS pages into a config file, which the user approved on 2026-10-06; write the rules for the direction tests down before running them. The user deferred a news-tone accuracy experiment (target 85 to 90%; ensemble plus abstaining); decision 045 lowers its value, so ask before starting it. The detail tabs still need the visual pass. Still owed: stability and sensitivity checks; labels from a person
- Before merging, run exactly what CI runs: `uv run radar lint` covers the tests directory too; a pull request was once merged with a red type check in a test file
- Held assets are discovered, never added by hand (decision 041); an asset the user wants to try can be looked up by ticker (decision 053): `EQ_` names are stocks only, every other name is a crypto pair only. A holding with 30 to 249 sessions is estimated on its own record and the loss limits are scaled for it; under 30 it is counted in the money only (decision 043). The screen says which
- The abnormal-move bar is 5 times the usual hourly size, chosen on how often it fires (decision 052). Never tune a signal's rule to its track record
- Section names are plain and fixed in decision 042; tab label and section title must match
- Document model work in a notebook (`notebooks/src/NN_name.py`, built by `build_notebooks.py`), as the user asked on 2026-10-06. Notebooks are committed with their outputs, so they use a made-up example portfolio, never the user's holdings. Check the built outputs against the commentary before committing: a notebook has already shown that a method did not beat its baseline
- Let the user choose and show the consequence (decision 049): do not present a choice the app has already made for them when they could set the inputs themselves
- The Binance client may only call the endpoints listed in `providers/binance.py`; adding one needs the user's agreement and a test
- Visual first (decision 040): a first view is tiles and charts built from `components/viz.tsx`, not sentences; long explanations go in `Caption`, which is collapsed. Detail tabs still need this pass
- Sections are pages behind tabs (`components/Tabs.tsx`), never folding panels; a new section gets its own address (decision 036)
- Layout rules (decision 034): inside the page use container variants (`@xl:`, `@4xl:`), not `sm:` or `lg:`; phones have bottom tabs only, no top bar; charts must not pan or zoom into empty time
- Every new section must use the shared `Panel` and take a trust grade from `analytics/summary.py`
- The fine-tuned model's files live in the gitignored `data/models/finbert-radar-1`; scoring new articles needs them on the machine that runs `radar sentiment`
- The language models need `uv sync --extra nlp` and run on the host, not in the Docker worker (decision 030)
- Carried forward: shading the price chart by regime is not built (decision 028)
- Interface direction is decision 023: follow it for every new screen (liquid glass, Inter, no developer wording, only show what exists). The user will revisit the interface in each phase
- Key decisions (`docs/DECISIONS.md` 010 to 053): primary assets are `BTC/USD`, `GLD` (gold), and `SPY`; `PAXG/USD` is portfolio-only; crypto from location `us-1`; 1Hour and 1Day bars only; live bars are pushed to the app but stored bars always come from REST; version 1 also includes macro drivers (F8), volatility forecast (F9), tail risk (F10), and a read-only Binance holdings source
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

- **No trading.** Do not import, call, or wrap any order, position, or transfer endpoint from Alpaca or any other provider. Market data and news endpoints only. One exception, approved by the user on 2026-10-05: a read-only Binance `HoldingsSource` may call Binance endpoints that **read** account balances and open positions, with an API key that has no trading and no withdrawal permission. It must never call an endpoint that places, changes, or cancels an order, moves funds, or changes account settings, and a test must assert that. The endpoints it may call are listed in `providers/binance.py`; one of them, the Funding wallet read, is a POST because Binance serves it no other way (`docs/DECISIONS.md` 038); three more reads were approved on 2026-10-07 (046, 047).
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
uv run radar track      # log today's forecasts and score those whose days have ended
uv run radar portfolio  # recompute the stored portfolio analysis with the latest prices (reads
                        # Binance again first when that is the source and a key is set)
uv run radar relationships  # recompute correlations, risk transmission, weekend gaps, drivers
uv run radar news-swings    # test whether news improves the swings forecast (decision 044)
uv run radar signals        # replay the signal rules and recompute their track records (about a minute)
uv run radar quality    # check stored data, set flags, write data quality reports
uv run radar worker     # live streams plus hourly sync and quality jobs (one per set of keys)
uv run radar profile    # measure the stored data and rewrite docs/DATA_PROFILE.md
uv run python backend/scripts/build_notebook.py   # rebuild notebooks/01_exploration.ipynb
uv run python backend/scripts/build_notebooks.py  # rebuild notebooks 02 to 09 from notebooks/src/
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
