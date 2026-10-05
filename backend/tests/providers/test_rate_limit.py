import pytest

from radar.providers.rate_limit import DEFAULT_CAPACITY, DEFAULT_RATE_PER_MINUTE, TokenBucket

PLAN_LIMIT_PER_MINUTE = 200


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_defaults_stay_under_the_plan_limit() -> None:
    assert DEFAULT_CAPACITY + DEFAULT_RATE_PER_MINUTE < PLAN_LIMIT_PER_MINUTE


def test_burst_up_to_capacity_does_not_wait() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=60, capacity=5, clock=clock, sleep=clock.sleep)
    assert [bucket.acquire() for _ in range(5)] == [0.0] * 5


def test_waits_for_refill_once_empty() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=60, capacity=2, clock=clock, sleep=clock.sleep)
    bucket.acquire()
    bucket.acquire()
    assert bucket.acquire() == pytest.approx(1.0)
    assert clock.now == pytest.approx(1.0)


def test_never_exceeds_the_plan_limit_in_any_minute() -> None:
    clock = FakeClock()
    bucket = TokenBucket(clock=clock, sleep=clock.sleep)
    stamps: list[float] = []
    for _ in range(1000):
        bucket.acquire()
        stamps.append(clock.now)
    worst = max(sum(1 for t in stamps if start <= t < start + 60.0) for start in stamps)
    assert worst <= DEFAULT_CAPACITY + DEFAULT_RATE_PER_MINUTE + 1
    assert worst < PLAN_LIMIT_PER_MINUTE


def test_tokens_do_not_accumulate_past_capacity() -> None:
    clock = FakeClock()
    bucket = TokenBucket(rate_per_minute=60, capacity=3, clock=clock, sleep=clock.sleep)
    clock.now = 3600.0
    assert [bucket.acquire() for _ in range(3)] == [0.0] * 3
    assert bucket.acquire() > 0


@pytest.mark.parametrize(("rate", "capacity"), [(0, 1), (-1, 1), (10, 0)])
def test_invalid_configuration_is_rejected(rate: float, capacity: int) -> None:
    with pytest.raises(ValueError, match="rate_per_minute"):
        TokenBucket(rate_per_minute=rate, capacity=capacity)
