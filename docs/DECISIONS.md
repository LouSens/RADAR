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
