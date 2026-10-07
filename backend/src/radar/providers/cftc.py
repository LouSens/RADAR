"""The US regulator's weekly positioning report (Commitments of Traders), decision 066.

Public, free, no key. Each row describes the positions held on a Tuesday and is
published the Friday after.
"""

from dataclasses import dataclass

import pandas as pd

from radar.providers.public import PublicReader

HOST = "publicreporting.cftc.gov"
DISAGGREGATED = "/resource/72hh-3qpy.json"
FINANCIAL = "/resource/gpe5-46if.json"
ALLOWED = frozenset({(HOST, DISAGGREGATED), (HOST, FINANCIAL)})
DATE = "report_date_as_yyyy_mm_dd"


@dataclass(frozen=True)
class Contract:
    """One futures market in the report, and which group of traders is counted."""

    name: str
    path: str
    code: str
    long_field: str
    short_field: str
    traders: str


GOLD = Contract(
    "gold",
    DISAGGREGATED,
    "088691",
    "m_money_positions_long_all",
    "m_money_positions_short_all",
    "managed money",
)
SP500 = Contract(
    "S&P 500",
    FINANCIAL,
    "13874A",
    "lev_money_positions_long",
    "lev_money_positions_short",
    "leveraged funds",
)
BITCOIN = Contract(
    "Bitcoin",
    FINANCIAL,
    "133741",
    "lev_money_positions_long",
    "lev_money_positions_short",
    "leveraged funds",
)


def reader() -> PublicReader:
    return PublicReader(ALLOWED)


def to_frame(rows: list[dict[str, str]], contract: Contract) -> pd.DataFrame:
    """Long, short and open interest by report date, oldest first."""
    frame = pd.DataFrame(
        {
            "long": [float(row[contract.long_field]) for row in rows],
            "short": [float(row[contract.short_field]) for row in rows],
            "open_interest": [float(row["open_interest_all"]) for row in rows],
        },
        index=pd.DatetimeIndex([pd.Timestamp(row[DATE]) for row in rows]),
    )
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def positions(source: PublicReader, contract: Contract) -> pd.DataFrame:
    """Every weekly report for one contract."""
    rows = source.get(
        HOST,
        contract.path,
        {
            "cftc_contract_market_code": contract.code,
            "$select": f"{DATE},{contract.long_field},{contract.short_field},open_interest_all",
            "$order": DATE,
            "$limit": 5000,
        },
    )
    return to_frame(rows, contract)
