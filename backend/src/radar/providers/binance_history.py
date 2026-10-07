"""Read-only history of the user's Binance account (decision 073).

`binance.py` reads what the account holds now. This module reads what happened before:
what was bought and for how much, money paid in and taken out, rewards received. It is
what lets RADAR know the cost of a holding and tell earnings from top-ups.

Every request is a GET to one of the eight endpoints listed in `ALLOWED`; anything else
is refused before it leaves the process. Each of them only lists past events. There is
no method here that places, changes, or cancels anything, moves funds, or changes a
setting, and there must never be one. Open and past instructions to the exchange are
deliberately not read at all. The API key should have reading permission only.

The key and secret are never logged and never appear in an error message.
"""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, SecretStr

from radar.providers.binance import (
    CLOCK,
    FUTURES_HOST,
    SPOT_HOST,
    TIMEOUT_SECONDS,
    BinanceError,
    DisallowedRequestError,
    sign,
)

# What was bought and sold on the spot market, one row per fill.
FILLS = (SPOT_HOST, "/api/v3/myTrades")
# The account's balances at each day's end, for the last 30 days.
DAILY_BALANCES = (SPOT_HOST, "/sapi/v1/accountSnapshot")
# Coins that arrived from outside.
MONEY_IN = (SPOT_HOST, "/sapi/v1/capital/deposit/hisrec")
# Coins that were sent out. A list of past events only.
MONEY_OUT = (SPOT_HOST, "/sapi/v1/capital/withdraw/history")
# One coin swapped for another through Convert.
CONVERSIONS = (SPOT_HOST, "/sapi/v1/convert/tradeFlow")
# Coins bought with a card or bank balance.
CARD_PURCHASES = (SPOT_HOST, "/sapi/v1/fiat/payments")
# Interest and rewards credited.
REWARDS = (SPOT_HOST, "/sapi/v1/asset/assetDividend")
# Realised gain and loss, fees and funding on futures.
FUTURES_INCOME = (FUTURES_HOST, "/fapi/v1/income")
ALLOWED = frozenset(
    {
        CLOCK,
        FILLS,
        DAILY_BALANCES,
        MONEY_IN,
        MONEY_OUT,
        CONVERSIONS,
        CARD_PURCHASES,
        REWARDS,
        FUTURES_INCOME,
    }
)
PAGE = 1000
DAY_MS = 86_400_000


class Fill(BaseModel):
    """One purchase or sale on the spot market."""

    pair: str
    at: datetime
    bought: bool
    quantity: float
    price: float
    # What was paid or received, in the pair's second currency.
    amount: float
    fee: float
    fee_asset: str


class Movement(BaseModel):
    """Coins that came into or left the account from outside."""

    asset: str
    at: datetime
    quantity: float
    arrived: bool


class Conversion(BaseModel):
    at: datetime
    from_asset: str
    from_quantity: float
    to_asset: str
    to_quantity: float


class CardPurchase(BaseModel):
    at: datetime
    asset: str
    quantity: float
    paid: float
    currency: str
    fee: float


class Reward(BaseModel):
    at: datetime
    asset: str
    quantity: float
    kind: str


class Income(BaseModel):
    at: datetime
    kind: str
    asset: str
    amount: float
    symbol: str


def check(method: str, host: str, path: str) -> None:
    """Refuse anything that is not a GET to one of the listed endpoints."""
    if method != "GET" or (host, path) not in ALLOWED:
        raise DisallowedRequestError(f"Refusing {method} {host}{path}: not a history endpoint")


def _when(milliseconds: Any) -> datetime:
    return datetime.fromtimestamp(int(milliseconds) / 1000, tz=UTC)


def _ms(moment: datetime) -> int:
    if moment.tzinfo is None:
        raise ValueError("A time without a zone was given")
    return int(moment.timestamp() * 1000)


class BinanceHistory:
    """Lists past events on the account. It cannot do anything else."""

    def __init__(
        self,
        api_key: SecretStr,
        api_secret: SecretStr,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._key = api_key
        self._secret = api_secret
        self._client = httpx.Client(
            timeout=TIMEOUT_SECONDS, transport=transport, follow_redirects=False
        )
        self._offset: int | None = None

    def close(self) -> None:
        self._client.close()

    def _get(self, endpoint: tuple[str, str], extra: dict[str, str | int] | None = None) -> Any:
        host, path = endpoint
        check("GET", host, path)
        params: dict[str, str | int] = {}
        headers: dict[str, str] = {}
        if endpoint != CLOCK:
            params = {**(extra or {}), "timestamp": self._now(), "recvWindow": 10_000}
            params["signature"] = sign(self._secret, urlencode(params))
            headers["X-MBX-APIKEY"] = self._key.get_secret_value()
        try:
            response = self._client.send(
                self._client.build_request(
                    "GET", f"https://{host}{path}", params=params, headers=headers
                )
            )
        except httpx.HTTPError as error:
            raise BinanceError(
                f"Could not reach Binance ({type(error).__name__}) for {path}."
            ) from None
        if response.status_code != 200:
            detail = ""
            try:
                detail = str(response.json().get("msg", ""))[:200]
            except (ValueError, AttributeError):
                detail = ""
            raise BinanceError(
                f"Binance answered {response.status_code} for {path}"
                + (f": {detail}" if detail else ".")
            )
        return response.json()

    def _now(self) -> int:
        """Binance's clock, read once and then kept in step with our own."""
        ours = int(datetime.now(UTC).timestamp() * 1000)
        if self._offset is None:
            self._offset = int(self._get(CLOCK)["serverTime"]) - ours
        return ours + self._offset

    def fills(self, pair: str, since: datetime | None = None) -> list[Fill]:
        """Every purchase and sale of one pair, oldest first."""
        rows: list[dict[str, Any]] = []
        extra: dict[str, str | int] = {"symbol": pair, "limit": PAGE}
        if since is not None:
            extra["startTime"] = _ms(since)
        while True:
            page = self._get(FILLS, extra)
            rows.extend(page)
            if len(page) < PAGE:
                break
            extra = {"symbol": pair, "limit": PAGE, "fromId": int(page[-1]["id"]) + 1}
        return [
            Fill(
                pair=str(r["symbol"]),
                at=_when(r["time"]),
                bought=bool(r["isBuyer"]),
                quantity=float(r["qty"]),
                price=float(r["price"]),
                amount=float(r["quoteQty"]),
                fee=float(r["commission"]),
                fee_asset=str(r["commissionAsset"]),
            )
            for r in rows
        ]

    def movements(self, start: datetime, end: datetime) -> list[Movement]:
        """Coins that arrived and coins that left between two times (at most 90 days)."""
        window: dict[str, str | int] = {"startTime": _ms(start), "endTime": _ms(end)}
        arrived = [
            Movement(
                asset=str(r["coin"]),
                at=_when(r["insertTime"]),
                quantity=float(r["amount"]),
                arrived=True,
            )
            for r in self._get(MONEY_IN, {**window, "status": 1})
        ]
        left = [
            Movement(
                asset=str(r["coin"]),
                at=datetime.fromisoformat(str(r["applyTime"])).replace(tzinfo=UTC),
                quantity=float(r["amount"]),
                arrived=False,
            )
            for r in self._get(MONEY_OUT, {**window, "status": 6})
        ]
        return sorted([*arrived, *left], key=lambda m: m.at)

    def conversions(self, start: datetime, end: datetime) -> list[Conversion]:
        """Swaps made through Convert between two times (at most 30 days)."""
        body = self._get(CONVERSIONS, {"startTime": _ms(start), "endTime": _ms(end), "limit": PAGE})
        return [
            Conversion(
                at=_when(r["createTime"]),
                from_asset=str(r["fromAsset"]),
                from_quantity=float(r["fromAmount"]),
                to_asset=str(r["toAsset"]),
                to_quantity=float(r["toAmount"]),
            )
            for r in body.get("list") or []
            if r.get("orderStatus") == "SUCCESS"
        ]

    def card_purchases(self, start: datetime, end: datetime) -> list[CardPurchase]:
        """Coins bought with a card or bank balance between two times."""
        body = self._get(
            CARD_PURCHASES,
            {"transactionType": 0, "beginTime": _ms(start), "endTime": _ms(end), "rows": 500},
        )
        return [
            CardPurchase(
                at=_when(r["createTime"]),
                asset=str(r["cryptoCurrency"]),
                quantity=float(r["obtainAmount"]),
                paid=float(r["sourceAmount"]),
                currency=str(r["fiatCurrency"]),
                fee=float(r["totalFee"]),
            )
            for r in body.get("data") or []
            if r.get("status") == "Completed"
        ]

    def rewards(self, start: datetime, end: datetime) -> list[Reward]:
        """Interest and rewards credited between two times."""
        body = self._get(REWARDS, {"startTime": _ms(start), "endTime": _ms(end), "limit": 500})
        return [
            Reward(
                at=_when(r["divTime"]),
                asset=str(r["asset"]),
                quantity=float(r["amount"]),
                kind=str(r.get("enInfo", "")),
            )
            for r in body.get("rows") or []
        ]

    def futures_income(self, start: datetime, end: datetime) -> list[Income]:
        """Realised gain and loss, fees and funding on futures between two times."""
        rows = self._get(
            FUTURES_INCOME, {"startTime": _ms(start), "endTime": _ms(end), "limit": PAGE}
        )
        return [
            Income(
                at=_when(r["time"]),
                kind=str(r["incomeType"]),
                asset=str(r["asset"]),
                amount=float(r["income"]),
                symbol=str(r.get("symbol", "")),
            )
            for r in rows
        ]

    def daily_balances(self) -> dict[datetime, dict[str, float]]:
        """The spot wallet's balances at each of the last 30 day-ends."""
        body = self._get(DAILY_BALANCES, {"type": "SPOT", "limit": 30})
        return {
            _when(day["updateTime"]): {
                str(b["asset"]): float(b["free"]) + float(b["locked"])
                for b in day["data"]["balances"]
                if float(b["free"]) + float(b["locked"]) > 0
            }
            for day in body.get("snapshotVos") or []
        }
