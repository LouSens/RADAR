# RADAR: audit of the product, the code and the notebooks

Written 2026-10-07 by Claude, acting as product QA and repository QA. Second version,
after a full pass over the code and after the user restated what the product is for.
The companion `WHAT_RADAR_IS.md` describes the app; `PROJECT_SPEC.md` section 0 holds
the new direction. This file is the criticism, including of my own work.

> **A record of that day.** Counts here (tests, notebooks, the one-line README) were
> true on 2026-10-07 and several no longer are. An outside review of 2026-10-08 and
> what was done about it is in `DECISIONS.md` 094.

**Corrections to the first version of this audit.** (1) I wrote that analysis is a chain
of hand-run commands. Wrong: the worker schedules all 16 jobs. (2) I called the news
pipeline "poor value" and proposed a minimal planner. That rested on a wrong picture of
the user. News failed as a *forecast*; it is still what explains a move after the fact.

## 1. What the user wants (stated 2026-10-07)

1. **Awareness.** What is going on (news, macro) and *why* each asset I own went up or
   down (technical and fundamental reasons).
2. **Protection.** When to cut a loss and take profit, as ranges with conditions; moving
   a stop to break-even before a profit becomes a loss; when to add or reduce without
   going all in or all out. The user has no rules of their own: the app should propose
   rules, and let the parameters be edited to see different results.
3. **Analytics for each asset owned**, from the data we have.
4. **A showcase.** It must demo well and show skill in finance data, a full machine
   learning pipeline, and full-stack work (database, deployment).
5. **Focus.** The app today "babbles about so many things".

## 2. Verdict

**Sound engineering pointed at the wrong centre.** The app is organised around three
markets and a list of studies. The user needs it organised around *their holdings* and
three verbs: explain, protect, size. Of 30 API routes, 13 serve per-market study pages
and only the three primary markets get state, outlook, swings and risk at all
(`universe.primary` in every model pipeline). A holding outside those three gets a price
and a place in the portfolio maths and nothing else.

| Area | Grade | Reason |
|---|---|---|
| Data handling | Good | Idempotent, raw kept, time order enforced and tested |
| Risk and swings | Good | The forecast that holds up on unseen data |
| Portfolio maths | Fair | Correct, but knows quantity only, not what was paid |
| Explaining a move | Missing | The parts exist (drivers, abnormal moves, events, news); nothing joins them |
| Protection rules | Missing | Three behaviours tested in notebook 14; no tool the user can use |
| Per-holding analytics | Poor | Three markets only; indicators exist only in research code, drawn nowhere |
| Machine learning as a showcase | Fair | Real models, real tests, but no place in the app shows the pipeline |
| Notebooks | Poor to read | See section 6 |
| Focus | Poor | See section 5 |
| Documentation | Poor | Spec described an older product; README is one line |

## 3. The theory that should steer the work

1. **Prices are close to a fair game.** Public daily data gives at best a point or two
   over a coin toss on direction. Notebooks 11 to 14 confirmed it.
2. **No rule for *when* to buy inside a fixed window beats the first day on average**
   (optional stopping). Notebook 15: all eight readings paid 0.2% to 0.8% more.
3. **Swings cluster.** Rough days follow rough days. This is why risk can be forecast,
   and why stop and take-profit *ranges* can be sized honestly from expected swings.
4. **A stop is insurance, not profit.** It lowers the average a little and cuts the
   worst case a lot (notebook 14: ended lower in 20 of 27 markets, worst point better
   in 21). The app must show both numbers for every rule.
5. **Holding less always falls less.** A sizing rule is judged against a fixed share of
   the same average size (decision 065).
6. **Try enough settings and one will look good by luck.** This matters now, because
   "edit the parameters and see" is trial and error. A rule tool must search on one part
   of history, judge on a later part and on other markets, and show how many settings
   were tried.
7. **Explaining is easier than predicting.** Splitting today's move into "the whole
   market", "this asset alone", "an event day", "unusually large" is arithmetic on known
   data. It needs no forecast and is always available.

## 4. What went wrong, in order of cost

1. **Built around markets, not holdings.** Six phases followed a spec for a market
   outlook dashboard. I did not challenge it.
2. **I guessed the user twice and was wrong twice.** First "wants statistical honesty
   above all", then "passive monthly investor". I should have asked in Phase 0.
3. **Sunk cost on direction.** Five notebooks on variations of one question after the
   first said no. The time would have built the explain and protect tools.
4. **Negative results were shipped as features.** News-and-swings, tone-versus-price,
   signal track records and event studies are research findings ("no effect") shown as
   app pages. That is the babbling: the app reports its own homework.
5. **Every card explains itself at length.** Each has a caption of four to six facts
   (Shows, Assumes, Window, Measured on...). Right for an audit, tiring for a user.
6. **No purchase history.** A holding is a symbol and a quantity (`models/holdings.py`).
   Break-even, real gain and loss, and every stop the user asked for depend on it.
7. **My technical errors.** A test that was too easy (064); model settings that could
   not learn (061); a false RSI finding from clustered days (061); two visual
   regressions; a merge with a red type check; a dip forecast in notebook 15 that was
   denied the one input its baseline had; a wrong claim in the first version of this
   audit.

## 5. What should not be in the app

Kept as research in notebooks where it has a result; removed from screens and routes.

| Remove | Why | What replaces it |
|---|---|---|
| **Markets together** page (pair correlations, risk spreading, weekend gaps) | About markets, not your holdings | The "how your holdings move together" grid already in the X-ray |
| **News and swings** section (`/news-and-swings`) | A negative research result | Nothing |
| **Tone versus price** section (`/event-study`) | A negative research result | Nothing |
| **Forecast accuracy** as a page per market | Belongs to the models, not to a market | One Models page |
| **What it moves with** as a page | A regression table nobody acts on | One line inside "why it moved" |
| **Signals** as a place, and a track-record page per signal type | True, nothing to act on | Alerts on your holdings and your rules |
| **Compare mixes** (five allocation rules) | Differences are within noise on this data | One sizing tool: how much to hold |
| **Core and satellite** | A tagging exercise with a report | Nothing |
| **Event study per event** on Calendar | Five-question study as a page | The date, and one line: "moves are usually N times normal" |
| **News topics**, the word-list rival | Machinery with no reader | Headlines tied to a move |
| **Markets** as a top-level place for three fixed markets | The user's assets are the subject | A page per holding |
| Long captions on every card | Fatigue | One line; the detail moves to Models |
| About 1,900 lines of research-only code in the app package | Imported by nothing the app runs | A `research` package beside the app |

Navigation after the cut, five places: **Home** (your portfolio), **Holdings** (one page
each), **Rules**, **Calendar**, **Models**.

## 6. The notebooks

All 15 run and their numbers are right. As documents they are hard to read, and the
user said so. Measured:

| Problem | Evidence |
|---|---|
| Lines too wide to read | Widest code line per notebook: 117 to 303 characters |
| Cells too long | Up to 73 lines in one cell (notebook 15), 56 (notebook 11) |
| Logic written inside notebooks, untested | 22 functions defined in notebooks 11 to 15 |
| No shared look | Every notebook sets its own chart style; colours and sizes differ |
| Jargon column names | "p across markets", "share of resamples not ahead", "ranking score" |
| Walls of text | 3,017 words of commentary in notebook 11 |
| No common shape | Each is organised differently; none opens with the answer |
| Overlap | 11 to 15 are one question five ways |
| Heavy files | Notebook 15 is 2.1 MB |

**What a notebook should be:** the answer in three lines at the top; then Question,
Data, Method, Result, What it means, Limits, in that order every time; one shared style
module; every chart with a plain title that states the finding, labelled axes with
units, and no table wider than the page; all logic imported from tested code.
**Proposed set:** one notebook per model that lives in the app (state, range, swings and
loss, news, portfolio, rules), and one "what we tested and why it failed" notebook that
replaces 11 to 15.

## 7. Code findings

| Finding | Evidence | Severity |
|---|---|---|
| Models cover three markets only | `universe.primary` in 18 places across pipelines | High for the new product |
| No cost or purchase date on a holding | `Holding(symbol, quantity, tag)` | High |
| No login, no access control on the API | No auth dependency in `api/` | High before sharing; fine locally (ports bound to 127.0.0.1) |
| Research code inside the app package | `technical`, `direction`, `payin`, `positioning`, `buying`, `cftc`, `binance_public`, `public`, `pipelines/research` | Medium |
| Model tracking is partial | MLflow is used by the regime model only; a `model_registry` table exists | Medium for a showcase |
| No end-to-end test | 581 backend tests and 20 frontend test files, none drives a whole screen against a running API | Medium |
| Modules with no test of their own | `analytics/correlation.py`, `transmission.py`, `models/drivers.py`, `models/topics.py`, `pipelines/worker.py` (some are covered through API tests) | Medium |
| Notebooks outside CI | They need a filled database; nothing detects drift | Medium |
| Very large files | `PortfolioPage.tsx` 923 lines, `api/routes.py` 869, `pipelines/portfolio.py` 754, `NewsPanel.tsx` 526 | Low |
| Database image not pinned | `timescale/timescaledb:latest-pg17` | Low |
| Language models run on the host only | Decision 030; tone scoring stops on any other machine | Medium for deployment |
| Not deployed anywhere | Docker Compose on one machine; no hosted demo | High for a showcase |
| Docs out of date | README one line; status block in `CLAUDE.md` about 1,500 words | Medium |
| Uncommitted work | Notebook 15 and one setting in `models/payin.py` | Note |

Clean: no TODO or FIXME markers; no unused components; lint and type checks pass; no
secret in the repository; the trading and host restrictions are enforced by tests.

## 8. What is still not considered anywhere

1. **Currency.** The user is in GMT+8 holding US-dollar assets.
2. **Fees and tax** on the user's actual venues.
3. **One bull market.** Stocks from 2016, crypto from 2021 (Binance's public history
   goes back to 2017 and is approved, but used for three coins only).
4. **Advice.** Stop and take-profit suggestions shown to other people may be regulated.
5. **Privacy.** A language model on the brief would send portfolio figures outside.
6. **Fundamentals.** The user asked for "fundamental news". We have headlines only: no
   earnings, no on-chain data, no economic series beyond event dates.

## 9. Recommended order

1. Record notebook 15 and stop direction research.
2. Cut section 5 from the app; move research code out.
3. Purchases: date, amount, price. Real gain, loss and break-even per holding.
4. Run every model for every holding, not three markets.
5. Holding page: chart with indicators, "why it moved", state, risk, your position.
6. Rules: a small set with editable parameters, each with its cost and its saving,
   searched and judged as section 3 point 6 requires; alerts when a condition is met.
7. Risk forecast with the pooled ensemble, done properly; a Models page showing data,
   training, testing and live scoring for every model.
8. Rebuild the notebooks to the shape in section 6.
9. Deploy a demo with example data.

## 10. My assumptions, to be corrected

- The app is used by one person for now, and shown to others as a demo with example data.
- "RSI (5,3,3)" is the stochastic oscillator; EMAs are 9 and 13, with 50 and 200 added by me.
- The user holds mostly crypto and some US-listed assets, and adds money from time to time.
- A rule the app proposes is a starting point the user may change, never an instruction.
- Showing a failed research result honestly is worth more in a demo than hiding it.
