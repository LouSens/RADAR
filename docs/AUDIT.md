# RADAR: audit of the product and the repository

Written 2026-10-07 by Claude, acting as product QA and repository QA. It covers the
whole directory as it stands on branch `pay-in-timing` (everything up to pull request 21
is merged to `main`). The companion file `WHAT_RADAR_IS.md` explains the app itself.
This file is the criticism, including of my own work.

## Verdict

**The engineering is sound and the product is unfocused.** RADAR is about 21,000 lines
of backend, 13,500 of frontend, 581 passing backend tests, 15 notebooks and 70 recorded
decisions. Roughly half of that effort went into questions whose answer was predictable
from theory ("can public daily prices tell which way the market goes next?") and into a
news pipeline that feeds nothing. The parts that do work (risk, swings, portfolio X-ray,
paying-in simulation) are under-used, and the thing you actually asked for, an assistant
built around your own portfolio, does not exist yet as a screen.

| Area | Grade | One-line reason |
|---|---|---|
| Data handling (ingest, cleaning, time order) | Good | Idempotent, raw kept, no lookahead, tested |
| Risk and swings (volatility, loss limits, stress) | Good | The one forecast that holds up on unseen data |
| Portfolio maths (X-ray, mixes, paying in) | Fair | Correct, but knows quantities only, not what you paid |
| Direction and timing research (notebooks 11 to 15) | Honest, poor value | Five notebooks, one answer: no |
| News (tone, topics, fine-tuning) | Poor value | Drives no forecast and no signal |
| Signals | Weak | True statements, little to act on |
| Product focus | Poor | Goal changed three times; home screen still market-first |
| Documentation | Poor | Spec describes an older product; README is one line |

## The theory that should have steered the work

1. **Prices are close to a fair game.** In a market many people trade, today's price
   already holds what is publicly known, so the next move is close to a coin toss with a
   small upward tilt. An edge, where one exists, is a point or two above 50% and needs
   private data, speed, or thousands of independent cases to show. We have about 2,500
   days per market. *Consequence: notebooks 11 to 14 were always likely to say no.*
2. **No stopping rule beats a fair game** (the optional stopping theorem). If the price
   is a fair game with upward drift, any rule for choosing *when* to buy within a fixed
   window pays the same on average, minus the drift lost while waiting. *Consequence:
   notebook 15 found every one of eight readings paid 0.2% to 0.8% more than the
   scheduled day. That is the theorem showing up in the data.*
3. **Swings cluster; direction does not.** Rough days follow rough days. This is the
   best-established fact in the field, and it is why the volatility forecast works.
   *Consequence: risk warnings are the honest core of the product.*
4. **Holding less always falls less.** Any rule that holds cash part of the time looks
   safer than holding everything. It only counts if it beats a fixed share of the same
   average size. *I missed this in decision 064 and fixed it in 065.*
5. **Test many things and some pass by luck.** Each notebook corrects for this inside
   itself. Nothing corrects for it *across* notebooks, and the same 27 markets were
   reused in 13, 14 and 15, so they are no longer fresh evidence.
6. **With a rising market, putting money in sooner wins on average.** Regular paying-in
   is about cash flow and nerves, not about return. The app should say this plainly.
7. **Estimated "best mixes" are fragile.** With short records, clever splits rarely beat
   equal weights out of sample. Notebook 07 partly shows this; the app still offers five.

## What went wrong, in order of cost

1. **The product was built before the question was asked.** Six phases followed a spec
   for a "market outlook dashboard". Only on 2026-10-07 did you say what you want: a
   portfolio assistant. Markets, news and signals were built as destinations when they
   should have been inputs. I followed the spec phase by phase and did not challenge it.
2. **Sunk cost on direction.** After notebook 11 said no, each of your next questions
   (LSTM, cash timing, outside data, timing within the month) became another full
   notebook. I should have said after the first: theory gives this a few per cent chance,
   here is what it costs, here is what else that time buys. I recorded guesses, and most
   were right, which means the runs taught us little.
3. **News was built before it was tested.** A tone model, a fine-tuned version, topics,
   an event study and a lexicon rival were built in Phases 4 and 5. Only afterwards did
   decision 045 test whether news improves anything. It did not, in 12 of 12 comparisons.
4. **Honesty turned into an app that mostly reports what it cannot do.** The rule
   "every claim carries its evidence" is right. Applied to features with no edge, it
   fills screens with "no measurable pattern". Those features should have been removed,
   not labelled.
5. **The assistant cannot see what you paid.** A holding is a symbol and a quantity.
   There is no purchase price and no transaction history, so RADAR cannot show your real
   gain or loss, cannot tell when you are near break-even, and cannot replay your actual
   paying-in. For a portfolio assistant this is the largest functional gap.
6. **My own errors.** A test that was too easy (064). First model settings that could
   not learn even a planted pattern (061). A false RSI "finding" from counting clustered
   days (061). Two visual regressions you caught (sidebar, charts). One merge with a red
   type check. And in notebook 15, a dip forecast designed without each market's own dip
   rate as an input, so it lost to a baseline that had it.

## Decisions I now think were irrational

- Adding screens faster than removing them. Decision 069 "folds away" six sections;
  none has been removed.
- Three stacked pull requests of 60+ commits, reviewed by nobody but CI.
- A decisions log of 2,700 lines and a status paragraph of about 1,500 words in
  `CLAUDE.md`. Both are write-only: too long for either of us to use.
- Testing crypto on Alpaca's history (from 2021) when Binance's public history (from
  2017) was approved and used for only three coins.
- Fixed thresholds chosen for convenience and never questioned: a 5% dip for bonds and
  coins alike, 21 trading days as "a month", 0.1% cost for every market.
- Spending on a soft-voting ensemble where theory said there was nothing to find, and
  not on the one place machine learning has a real target (risk).

## Repository findings

| Finding | Evidence | Severity |
|---|---|---|
| About 1,900 lines of research-only code live in the app package and are imported by nothing the app runs | `analytics/technical.py`, `positioning.py`, `buying.py`, `models/direction.py`, `payin.py`, `providers/cftc.py`, `binance_public.py`, `public.py`, `pipelines/research.py` | Medium |
| Spec is out of date | `docs/PROJECT_SPEC.md` section 1 still describes a market outlook app | Medium |
| No orientation for a newcomer | `README.md` is one line | Medium |
| No login on the API | Fine on your own machine; a blocker before anyone else uses it | High if shared |
| Analysis is a chain of about 14 hand-run commands in a required order | `radar regime`, `simulate`, `volatility`, `risk`, ... `brief` | Medium |
| Notebooks are not checked by CI and need a filled database to rebuild | They can drift from the code without anyone noticing | Medium |
| Notebooks 11 to 14 overlap | Same question, same answer, four files, 1.7 MB | Low |
| Very large files | `PortfolioPage.tsx` 923 lines, `api/routes.py` 869, `pipelines/portfolio.py` 754 | Low |
| Frontend tested less than backend | 20 test files for 69 source files; no end-to-end test of a whole screen flow | Medium |
| Language models run only on the host, not in the worker | Tone scoring silently stops on any other machine (decision 030) | Low, since news drives nothing |
| Notebook 15 is 2.1 MB, uncommitted, with placeholder text | Work in progress | Note |

## What is not considered anywhere, and must be

1. **Your currency.** You are in GMT+8 and hold US-dollar assets. Exchange-rate moves
   change your real result and are not modelled.
2. **What you paid, fees and tax.** See point 5 above.
3. **Your goal.** There is no target amount, horizon, monthly budget or loss you can
   live with. Without one, "how much to hold" has no reference point.
4. **One bull market.** Stocks from 2016, crypto from 2021. No 2008, no long flat
   decade. Every "worst case" in the app is milder than history.
5. **Advice.** Suggestions about buying and selling shown to other people may count as
   regulated financial advice. Settle this before sharing the app.
6. **Privacy.** Connecting a language model to the daily brief would send your portfolio
   figures to an outside service.

## What I recommend, in order

1. **Stop direction and timing research.** Record notebook 15 as the last of its kind.
2. **Cut before building.** Remove from the main path: news tone studies, markets
   together, outside forces, per-signal track-record pages, compare mixes, core and
   satellite. Move research-only code out of the app package.
3. **Give the portfolio a memory.** Purchases with date, amount and price, so the app
   can show real gain and loss, break-even, and your actual paying-in history.
4. **Ask for a goal.** Monthly amount, horizon, and the fall you can tolerate.
5. **Build one home screen** from what holds up: value and real gain, risk now, the
   range ahead if you keep paying in, how much to hold for the fall you can tolerate,
   and warnings (rougher week, drift, turbulent market, event day).
6. **Show technical readings as context only**, each with its record, never as a signal.
7. **Rewrite the spec and README** for the product in point 5, and cut the status block
   in `CLAUDE.md` to a few lines.

## My assumptions, so you can correct them

- You want the truth about what works more than output that sounds actionable.
- The app is for you alone, on your own machine.
- "RSI (5,3,3)" means the stochastic oscillator (you confirmed this today).
- A month is 21 trading days, a trade costs 0.1%, and a "dip" is 5%.
- Alpaca's data is good enough for stocks; I never checked it against a second source.
- You pay in monthly, in US dollars. I do not know the amount or how long you plan to.
