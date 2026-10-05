"""Provider errors. Messages never include request headers or credentials."""


class AlpacaError(Exception):
    """Base class for every error raised by the Alpaca clients."""


class DisallowedURLError(AlpacaError):
    """The URL is not on the market data host this app is allowed to call."""


class AlpacaHTTPError(AlpacaError):
    """The API answered with a non-200 status."""

    def __init__(self, status_code: int, path: str, message: str) -> None:
        super().__init__(f"Alpaca returned {status_code} for {path}: {message}")
        self.status_code = status_code
        self.path = path
        self.message = message


class AlpacaTransportError(AlpacaError):
    """The request never produced a response (timeout, connection reset, DNS)."""

    def __init__(self, path: str, kind: str) -> None:
        super().__init__(f"Transport error calling {path}: {kind}")
        self.path = path
        self.kind = kind
