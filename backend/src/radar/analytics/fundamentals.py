"""The user's rules for a company, checked on its reported accounts (decision 083).

Each rule is a yes, a no, or "cannot tell" when the company has not reported the figure,
with the number behind it. These are filters on the business. They say nothing about
where the share price goes next, and a company that passes can still fall.

Pure functions on yearly figures keyed by the year the financial year ended in.
"""

from pydantic import BaseModel

MODEL_VERSION = "fundamentals-1"
YEARS = 5
MIN_MARGIN = 0.30
MIN_CASH = 0.80
MAX_DEBT_YEARS = 3.0
MIN_RETURN = 0.15
MAX_SPENDING = 0.50
MAX_NEW_SHARES = 0.05

Yearly = dict[int, float]


class Rule(BaseModel):
    key: str
    # None when the accounts do not hold what the rule needs.
    passed: bool | None
    # The figure the rule was judged on, and the mark it had to meet.
    figure: float | None = None
    mark: float | None = None


class Screen(BaseModel):
    ticker: str
    latest_year: int | None
    # The four rules the user set, then the wider checks of quality.
    rules: list[Rule]
    quality: list[Rule]
    passes: bool
    quality_passed: int
    quality_known: int


def _last(series: Yearly, years: int = YEARS) -> list[float]:
    return [series[year] for year in sorted(series)[-years:]]


def profitable(profit: Yearly) -> Rule:
    """A profit in each of the last five reported years."""
    recent = _last(profit)
    if len(recent) < YEARS:
        return Rule(key="profitable", passed=None, figure=float(sum(v > 0 for v in recent)))
    return Rule(
        key="profitable",
        passed=all(v > 0 for v in recent),
        figure=float(sum(v > 0 for v in recent)),
        mark=float(YEARS),
    )


def low_debt(debt: Yearly, profit: Yearly) -> Rule:
    """Long-term debt that the latest year's profit could repay in three years."""
    if not profit:
        return Rule(key="low_debt", passed=None)
    earned = profit[max(profit)]
    owed = debt[max(debt)] if debt else 0.0
    if earned <= 0:
        return Rule(key="low_debt", passed=owed == 0, figure=None, mark=MAX_DEBT_YEARS)
    years = owed / earned
    return Rule(key="low_debt", passed=years <= MAX_DEBT_YEARS, figure=years, mark=MAX_DEBT_YEARS)


def cash_backed(cash: Yearly, profit: Yearly) -> Rule:
    """Cash from the business over five years at least four fifths of the profit."""
    years = sorted(set(cash) & set(profit))[-YEARS:]
    earned = sum(profit[y] for y in years)
    if len(years) < 3 or earned <= 0:
        return Rule(key="cash", passed=None)
    share = sum(cash[y] for y in years) / earned
    return Rule(key="cash", passed=share >= MIN_CASH, figure=share, mark=MIN_CASH)


def margin(gross: Yearly, sales: Yearly) -> Rule:
    """Gross margin above 30% in the latest year."""
    years = sorted(set(gross) & set(sales))
    if not years or sales[years[-1]] <= 0:
        return Rule(key="margin", passed=None)
    share = gross[years[-1]] / sales[years[-1]]
    return Rule(key="margin", passed=share > MIN_MARGIN, figure=share, mark=MIN_MARGIN)


def earning_power(profit: Yearly, equity: Yearly) -> Rule:
    """Profit over five years averaging at least 15% of the owners' money."""
    years = [y for y in sorted(set(profit) & set(equity))[-YEARS:] if equity[y] > 0]
    if len(years) < 3:
        return Rule(key="return", passed=None)
    average = sum(profit[y] / equity[y] for y in years) / len(years)
    return Rule(key="return", passed=average >= MIN_RETURN, figure=average, mark=MIN_RETURN)


def growing(profit: Yearly) -> Rule:
    """More profit in the latest year than five years before."""
    years = sorted(profit)
    if len(years) < YEARS or profit[years[-YEARS]] <= 0:
        return Rule(key="growing", passed=None)
    change = profit[years[-1]] / profit[years[-YEARS]] - 1
    return Rule(key="growing", passed=change > 0, figure=change, mark=0.0)


def light_spending(spending: Yearly, cash: Yearly) -> Rule:
    """Under half the cash from the business spent on buildings and equipment."""
    years = sorted(set(spending) & set(cash))[-YEARS:]
    made = sum(cash[y] for y in years)
    if len(years) < 3 or made <= 0:
        return Rule(key="spending", passed=None)
    share = sum(abs(spending[y]) for y in years) / made
    return Rule(key="spending", passed=share <= MAX_SPENDING, figure=share, mark=MAX_SPENDING)


def not_diluting(shares: Yearly) -> Rule:
    """No more than 5% more shares than five years before."""
    years = sorted(shares)
    if len(years) < YEARS or shares[years[-YEARS]] <= 0:
        return Rule(key="shares", passed=None)
    change = shares[years[-1]] / shares[years[-YEARS]] - 1
    return Rule(key="shares", passed=change <= MAX_NEW_SHARES, figure=change, mark=MAX_NEW_SHARES)


def screen(
    ticker: str,
    *,
    profit: Yearly,
    sales: Yearly,
    gross: Yearly,
    cash: Yearly,
    debt: Yearly,
    equity: Yearly,
    spending: Yearly,
    shares: Yearly,
) -> Screen:
    """Every rule for one company. It passes only when all four of the user's rules are
    a clear yes; "cannot tell" is not a pass."""
    rules = [
        profitable(profit),
        low_debt(debt, profit),
        cash_backed(cash, profit),
        margin(gross, sales),
    ]
    quality = [
        earning_power(profit, equity),
        growing(profit),
        light_spending(spending, cash),
        not_diluting(shares),
    ]
    known = [q for q in quality if q.passed is not None]
    return Screen(
        ticker=ticker,
        latest_year=max(profit) if profit else None,
        rules=rules,
        quality=quality,
        passes=all(r.passed is True for r in rules),
        quality_passed=sum(q.passed is True for q in known),
        quality_known=len(known),
    )
