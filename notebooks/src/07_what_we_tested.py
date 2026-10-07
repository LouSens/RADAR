# %% [markdown]
# # What we tested, and why it is not in the app
#
# Seven pieces of research asked whether something could tell the user when to buy or
# sell, or which way a price would go. Each had its rules and pass mark written into
# `docs/DECISIONS.md` before it was run. None passed. This page is the summary; the full
# notebooks, with every table and chart, are in `notebooks/archive/`.
#
# ## The answer in one table
#
# | Question | What was tried | Result | Decision | Full notebook |
# |---|---|---|---|---|
# | Do signals tell direction? | Changes of market state, abnormal hourly moves, jumps in news tone, replayed through history | No edge in direction. After an abnormal move US stocks moved more, in either direction | 051, 052 | `08_signals` |
# | Do markets lean one way around Fed, jobs and inflation days? | Five questions per event and market, fixed in advance | No pattern in direction. Gold moves more on Fed days, US stocks on jobs days | 055, 056 | `10_events` |
# | Does news tone lead price, or improve the swings forecast? | An event study of tone against price; the swings forecast with and without news | Tone mostly follows the move. News improved nothing in 12 of 12 comparisons | 044, 045 | parts of `04_news` as first built |
# | Do indicators and levels tell direction? | RSI, moving averages, order blocks, fair value gaps, support, resistance, volume; boosted trees; sizing rules | None tells direction. Several tell the size of the next move. No sizing rule beat holding | 060, 061 | `11_direction_and_levels` |
# | Can a neural network on hourly bars? | An LSTM, small trees and a logistic regression, trained, validated and tested in time order | 0 of 9 comparisons passed, though all three found a planted pattern | 062, 063 | `12_direction_lstm` |
# | Is there a right time to hold cash? | Swings and 200-day rules on 24 markets not used before; events, stochastic (5,3,3), fair value gaps, order blocks as triggers to buy back | The deepest fall was shallower in 23 of 24, but no better than a fixed smaller share, and it earned less | 064, 065 | `13_cash_share` |
# | Does data from outside the price help? Is cutting at break-even or waiting for dips better than paying in on schedule? | Trader positioning, funding rates, buy-side volume; three ways of paying in on 27 markets | 0 of 9 models passed. Paying in on schedule ended with more in about three markets of four. Cutting at break-even had the better worst point in 21 of 27: insurance, with a price | 066 to 068 | `14_outside_data_and_buying` |
# | When in the month to pay in? | Eight readings (stochastic, RSI, EMA 9 and 13, EMA 50, fair value gap, order block, Fibonacci 61.8%) and a four-model voting ensemble | All eight paid 0.2% to 0.8% more than the scheduled day. The ensemble did not pass | 070, 073 | `15_when_to_pay_in` |
#
# ## Why the answer keeps being no
#
# Prices that many people trade already hold what is publicly known, so the next move is
# close to a coin toss with a small upward lean. Two consequences showed up every time:
#
# - **Direction.** A model can only find what is there. Each one was first shown made-up
#   answers with a known rule and found it, then found nothing in real prices.
# - **Timing a purchase.** If the next move cannot be told, no rule for choosing the day
#   beats the first day, and waiting gives up the upward lean. Every waiting rule paid
#   more on average, while often getting a lower price: many small wins, a few large
#   losses.
#
# ## What did hold up, and where it went
#
# | Finding | Where it is used |
# |---|---|
# | How rough the coming days will be can be forecast | `03_swings_and_loss`; the swings and possible-loss figures |
# | How much is held decides most of the outcome | The portfolio's risk and "try a mix" |
# | A stop at break-even lowers the average a little and cuts the worst case a lot | To be offered as a rule the user can switch on, with both figures shown |
# | Several readings tell the *size* of the next move | Context on a chart, never a call |
#
# ## Three checks that came out of this work and are now standing rules
#
# 1. **A planted pattern first.** Before trusting a model's "no", give it made-up answers
#    with a known rule and check it finds them.
# 2. **Compare with a fixed share.** A rule that holds less always falls less. It counts
#    only if it beats a fixed share of the same average size.
# 3. **Count runs once.** A pattern that comes in runs of days is one case, not many.
#
# ## One thing left open
#
# The forecast of "a close 5% lower within a month" in `15_when_to_pay_in` failed because
# of how it was designed, not because of the market: the models were not given each
# market's own rate of such falls. It is to be redone once, as part of
# `03_swings_and_loss`.
