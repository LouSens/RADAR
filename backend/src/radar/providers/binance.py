"""Read-only Binance holdings source (spec F6; the exception in CLAUDE.md "No trading").

This client can do exactly one thing: read what the account holds. Every request goes to
one of the six endpoints listed below, each of which only returns balances or open
exposure; anything else is refused before it leaves the process. There is no method here
that places, changes, or cancels an order, moves funds, or changes a setting, and there
must never be one. The API key should be created with reading permission only, so that
the exchange would refuse those too.

Five endpoints are read with GET. The sixth, the Funding wallet, is one Binance only
answers by POST even though it changes nothing; it is the single POST this client may
send, it carries no body, and it is named in `READ_BY_POST`.

The key and secret are never logged and never appear in an error message.
"""

import hashlib
import hmac
from collections.abc import Iterable
from typing import Any
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, SecretStr

from radar.logging import get_logger
from radar.models.holdings import Holding, Holdings, SourceName, Unsupported, resolve

log = get_logger(__name__)

SPOT_HOST = "api.binance.com"
FUTURES_HOST = "fapi.binance.com"
CLOCK = (SPOT_HOST, "/api/v3/time")
SPOT_BALANCES = (SPOT_HOST, "/api/v3/account")
MARGIN_BALANCES = (SPOT_HOST, "/sapi/v1/margin/account")
FUTURES_EXPOSURE = (FUTURES_HOST, "/fapi/v2/positionRisk")
# Money placed in fixed-term savings. Flexible savings already show in the spot wallet.
LOCKED_SAVINGS = (SPOT_HOST, "/sapi/v1/simple-earn/locked/position")
# Every (host, path) this client may call. All are read with GET.
ALLOWED = frozenset({CLOCK, SPOT_BALANCES, MARGIN_BALANCES, FUTURES_EXPOSURE, LOCKED_SAVINGS})
# The Funding wallet, where Binance also keeps tokenised US stocks. A read that
# Binance only serves by POST.
FUNDING_BALANCES = (SPOT_HOST, "/sapi/v1/asset/get-funding-asset")
READ_BY_POST = frozenset({FUNDING_BALANCES})

# Balances smaller than this many units are dust and are ignored.
DUST = 1e-8
TIMEOUT_SECONDS = 15.0


class BinanceError(Exception):
    """Reading from Binance failed. The message is safe to show: it holds no credentials."""


class DisallowedRequestError(BinanceError):
    """The request is not one of the reading endpoints this client may call."""


class Leveraged(BaseModel):
    """An open futures exposure, as Binance reports it."""

    symbol: str
    # Positive for long, negative for short, in units of the asset.
    quantity: float
    leverage: float
    entry_price: float
    mark_price: float
    liquidation_price: float | None
    # How far the mark price is from liquidation, as a fraction of the mark price.
    distance_to_liquidation: float | None


class BinanceReading(BaseModel):
    holdings: Holdings
    leveraged: list[Leveraged]


def check(method: str, host: str, path: str) -> None:
    """Refuse anything that is not one of the reading endpoints, by its own method."""
    endpoint = (host, path)
    reading = (method == "GET" and endpoint in ALLOWED) or (
        method == "POST" and endpoint in READ_BY_POST
    )
    if not reading:
        raise DisallowedRequestError(f"Refusing {method} {host}{path}: not a reading endpoint")


def sign(secret: SecretStr, query: str) -> str:
    return hmac.new(secret.get_secret_value().encode(), query.encode(), hashlib.sha256).hexdigest()


def underlying(asset: str) -> str:
    """Binance shows a balance lent out through flexible savings as `LD` plus the asset."""
    return asset[2:] if asset.startswith("LD") and len(asset) > 4 else asset


class BinanceSource:
    """Holdings read from a Binance account. A `HoldingsSource`."""

    name: SourceName = "binance"

    def __init__(
        self,
        api_key: SecretStr,
        api_secret: SecretStr,
        known: Iterable[str],
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._key = api_key
        self._secret = api_secret
        self._known = list(known)
        self._client = httpx.Client(
            timeout=TIMEOUT_SECONDS, transport=transport, follow_redirects=False
        )
        self.leveraged: list[Leveraged] = []

    def close(self) -> None:
        self._client.close()

    def _read(self, endpoint: tuple[str, str], *, signed: bool, clock: int | None = None) -> Any:
        host, path = endpoint
        method = "POST" if endpoint in READ_BY_POST else "GET"
        check(method, host, path)
        params: dict[str, str | int] = {}
        headers: dict[str, str] = {}
        if signed:
            params = {"timestamp": clock or 0, "recvWindow": 10_000}
            params["signature"] = sign(self._secret, urlencode(params))
            headers["X-MBX-APIKEY"] = self._key.get_secret_value()
        try:
            response = self._client.send(
                self._client.build_request(
                    method, f"https://{host}{path}", params=params, headers=headers
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
            except ValueError:
                detail = ""
            raise BinanceError(
                f"Binance answered {response.status_code} for {path}"
                + (f": {detail}" if detail else ".")
            )
        return response.json()

    def read_account(self) -> BinanceReading:
        """Read spot, funding, savings, and margin balances and open futures exposure, netted per
        asset. Dollar stablecoins are counted together as cash."""
        clock = int(self._read(CLOCK, signed=False)["serverTime"])
        totals: dict[str, float] = {}
        unsupported: list[Unsupported] = []

        def add(asset: str, quantity: float) -> None:
            if abs(quantity) < DUST:
                return
            totals[asset] = totals.get(asset, 0.0) + quantity

        spot = self._read(SPOT_BALANCES, signed=True, clock=clock)
        for balance in spot.get("balances", []):
            add(
                underlying(str(balance["asset"])),
                float(balance["free"]) + float(balance["locked"]),
            )

        # The Funding wallet, fixed-term savings, margin, and futures may not be in use;
        # that is not an error.
        try:
            for balance in self._read(FUNDING_BALANCES, signed=True, clock=clock):
                add(
                    str(balance["asset"]),
                    float(balance["free"])
                    + float(balance.get("locked") or 0)
                    + float(balance.get("freeze") or 0),
                )
        except BinanceError as error:
            log.info("binance_funding_skipped", reason=str(error))
        try:
            savings = self._read(LOCKED_SAVINGS, signed=True, clock=clock)
            for row in savings.get("rows", []):
                add(str(row["asset"]), float(row["amount"]))
        except BinanceError as error:
            log.info("binance_savings_skipped", reason=str(error))
        try:
            margin = self._read(MARGIN_BALANCES, signed=True, clock=clock)
            for balance in margin.get("userAssets", []):
                add(str(balance["asset"]), float(balance["netAsset"]))
        except BinanceError as error:
            log.info("binance_margin_skipped", reason=str(error))

        leveraged: list[Leveraged] = []
        try:
            for row in self._read(FUTURES_EXPOSURE, signed=True, clock=clock):
                quantity = float(row["positionAmt"])
                if abs(quantity) < DUST:
                    continue
                contract = str(row["symbol"])
                mark = float(row["markPrice"])
                liquidation = float(row.get("liquidationPrice") or 0.0)
                leveraged.append(
                    Leveraged(
                        symbol=resolve(contract, self._known) or contract,
                        quantity=quantity,
                        leverage=float(row.get("leverage") or 1.0),
                        entry_price=float(row["entryPrice"]),
                        mark_price=mark,
                        liquidation_price=liquidation if liquidation > 0 else None,
                        distance_to_liquidation=abs(mark - liquidation) / mark
                        if liquidation > 0 and mark > 0
                        else None,
                    )
                )
                add(contract, quantity)
        except BinanceError as error:
            log.info("binance_futures_skipped", reason=str(error))

        # Different names for one asset (a coin and its futures contract) net together.
        net: dict[str, float] = {}
        for asset, quantity in totals.items():
            symbol = resolve(asset, self._known)
            if symbol is None:
                unsupported.append(
                    Unsupported(symbol=asset, reason="RADAR has no price history for this.")
                )
                continue
            net[symbol] = net.get(symbol, 0.0) + quantity
        holdings = []
        for symbol, quantity in sorted(net.items()):
            if quantity > DUST:
                holdings.append(Holding(symbol=symbol, quantity=quantity))
            else:
                unsupported.append(
                    Unsupported(
                        symbol=symbol,
                        reason="Net short or flat after futures. Only long exposure is analysed.",
                    )
                )
        log.info(
            "binance_read",
            holdings=len(holdings),
            unsupported=len(unsupported),
            leveraged=len(leveraged),
        )
        self.leveraged = leveraged
        return BinanceReading(
            holdings=Holdings(source=self.name, holdings=holdings, unsupported=unsupported),
            leveraged=leveraged,
        )

    def read(self) -> Holdings:
        return self.read_account().holdings
