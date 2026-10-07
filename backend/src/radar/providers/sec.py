"""Company accounts from the US regulator's public filings (SEC EDGAR), decision 083.

Public, free, no key. Two reads: the list that maps a stock's ticker to the company's
number, and one file per company holding every figure it has reported. Nothing here is
about any account or any market price.

The regulator serves these only to a program that names itself and gives a contact
email in its requests, and answers 403 without one. The contact comes from the setting
`SEC_CONTACT`; it is sent to the regulator's site and nowhere else.
"""

import re
from typing import Any

from radar.providers.public import PublicReader

FILES_HOST = "www.sec.gov"
DATA_HOST = "data.sec.gov"
TICKERS = (FILES_HOST, "/files/company_tickers.json")
ALLOWED = frozenset({TICKERS})
# One file per company, named by its ten-digit number.
FACTS = (DATA_HOST, re.compile(r"/api/xbrl/companyfacts/CIK\d{10}\.json"))
PATTERNS = (FACTS,)
PROGRAM = "RADAR portfolio research"
YEAR_DAYS = (350, 380)


class NoContactError(Exception):
    """No contact email is set, so the regulator would refuse every request."""


def user_agent(contact: str | None) -> str:
    """What the program calls itself to the regulator: its name and the contact."""
    if not contact or "@" not in contact:
        raise NoContactError("Set SEC_CONTACT to an email address to read company accounts.")
    return f"{PROGRAM} {contact.strip()}"


def reader(contact: str | None) -> PublicReader:
    return PublicReader(
        ALLOWED, patterns=PATTERNS, user_agent=user_agent(contact), pause_seconds=0.15
    )


def company_numbers(source: PublicReader) -> dict[str, int]:
    """Every listed ticker and the number the regulator files its company under."""
    rows = source.get(*TICKERS, {})
    return {str(row["ticker"]).upper(): int(row["cik_str"]) for row in rows.values()}


def company_facts(source: PublicReader, number: int) -> dict[str, Any]:
    """Everything one company has reported, as the regulator serves it."""
    facts: dict[str, Any] = source.get(
        DATA_HOST, f"/api/xbrl/companyfacts/CIK{number:010d}.json", {}
    )
    return facts


def _days(start: str, end: str) -> int:
    from datetime import date

    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def yearly(facts: dict[str, Any], tags: tuple[str, ...], unit: str = "USD") -> dict[int, float]:
    """One figure per financial year from annual reports, keyed by the year it ended in.

    The first of `tags` the company has used wins for each year: companies name the same
    thing differently, and change names over time. A figure for a period (profit, cash
    flow) must cover a whole year; a figure at a date (debt, equity) is taken as it is.
    Where a year was reported more than once, the latest filing is used.
    """
    result: dict[int, tuple[str, float]] = {}
    reported = facts.get("facts", {}).get("us-gaap", {})
    for tag in tags:
        found: dict[int, tuple[str, float]] = {}
        for row in reported.get(tag, {}).get("units", {}).get(unit, []):
            if row.get("form") not in ("10-K", "10-K/A", "20-F", "40-F"):
                continue
            start, end = row.get("start"), str(row.get("end", ""))
            if start is not None and not YEAR_DAYS[0] <= _days(str(start), end) <= YEAR_DAYS[1]:
                continue
            year, filed = int(end[:4]), str(row.get("filed", ""))
            if year not in found or filed > found[year][0]:
                found[year] = (filed, float(row["val"]))
        for year, value in found.items():
            result.setdefault(year, value)
    return {year: value for year, (_, value) in sorted(result.items())}
