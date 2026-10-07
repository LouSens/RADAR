"""The worker's scheduler."""

from radar.pipelines import worker


def test_a_job_that_starts_late_still_runs() -> None:
    # The library drops a job more than one second late unless told otherwise, which
    # once left every hourly job unrun for two days.
    defaults = worker.make_scheduler()._job_defaults
    assert defaults["misfire_grace_time"] == worker.MISFIRE_GRACE_SECONDS
    assert defaults["misfire_grace_time"] >= 300
    assert defaults["coalesce"] is True
