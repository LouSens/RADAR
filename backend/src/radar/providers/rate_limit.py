"""Token-bucket rate limiter for REST calls."""

import threading
import time
from collections.abc import Callable

# The free plan allows 200 historical calls per minute. In any 60-second window this
# bucket admits at most `capacity + rate_per_minute` calls, so the defaults (20 + 150)
# stay under the limit with headroom.
DEFAULT_RATE_PER_MINUTE = 150.0
DEFAULT_CAPACITY = 20


class TokenBucket:
    def __init__(
        self,
        rate_per_minute: float = DEFAULT_RATE_PER_MINUTE,
        capacity: int = DEFAULT_CAPACITY,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if rate_per_minute <= 0 or capacity < 1:
            raise ValueError("rate_per_minute must be positive and capacity at least 1")
        self._rate_per_second = rate_per_minute / 60.0
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._clock = clock
        self._sleep = sleep
        self._updated = clock()
        self._lock = threading.Lock()

    def acquire(self) -> float:
        """Block until a token is available. Returns the seconds spent waiting."""
        with self._lock:
            now = self._clock()
            elapsed = now - self._updated
            self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_second)
            self._updated = now
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                return 0.0
            # Sleep off the deficit while holding the lock, then spend the token it bought.
            delay = (1.0 - self._tokens) / self._rate_per_second
            self._sleep(delay)
            self._tokens = 0.0
            self._updated = self._clock()
            return delay
