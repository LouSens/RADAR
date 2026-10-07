"""The user's rules for a company, on accounts made up so each answer is plain."""

import httpx
import pytest

from radar.analytics import fundamentals
from radar.providers import sec
from radar.providers.public import DisallowedPublicRequestError, PublicReader

YEARS = range(2021, 2026)


def each(value: float) -> dict[int, float]:
    return dict.fromkeys(YEARS, value)


GOOD = {
    "profit": {2021: 80.0, 2022: 90.0, 2023: 100.0, 2024: 110.0, 2025: 120.0},
    "sales": each(1000.0),
    "gross": each(450.0),
    "cash": each(110.0),
    "debt": each(200.0),
    "equity": each(500.0),
    "spending": each(-30.0),
    "shares": {2021: 100.0, 2022: 99.0, 2023: 98.0, 2024: 97.0, 2025: 96.0},
}


def rules(found: fundamentals.Screen) -> dict[str, bool | None]:
    return {r.key: r.passed for r in [*found.rules, *found.quality]}


def test_a_sound_company_passes_every_rule_with_the_figures_behind_them() -> None:
    found = fundamentals.screen("GOOD", **GOOD)
    assert found.passes
    assert rules(found) == dict.fromkeys(
        ["profitable", "low_debt", "cash", "margin", "return", "growing", "spending", "shares"],
        True,
    )
    by_key = {r.key: r for r in [*found.rules, *found.quality]}
    assert by_key["margin"].figure == pytest.approx(0.45)
    assert by_key["low_debt"].figure == pytest.approx(200 / 120)  # years of profit to repay
    assert by_key["cash"].figure == pytest.approx(550 / 500)
    assert by_key["return"].figure == pytest.approx(sum(GOOD["profit"].values()) / 5 / 500)
    assert by_key["growing"].figure == pytest.approx(0.5)
    assert by_key["shares"].figure == pytest.approx(-0.04)
    assert (found.latest_year, found.quality_passed, found.quality_known) == (2025, 4, 4)


@pytest.mark.parametrize(
    ("change", "failed"),
    [
        ({"profit": {**GOOD["profit"], 2023: -5.0}}, "profitable"),
        ({"debt": each(500.0)}, "low_debt"),
        ({"cash": each(60.0)}, "cash"),
        ({"gross": each(250.0)}, "margin"),
    ],
)
def test_failing_any_one_of_the_four_rules_fails_the_company(
    change: dict[str, dict[int, float]], failed: str
) -> None:
    found = fundamentals.screen("ONE", **{**GOOD, **change})
    assert not found.passes
    assert rules(found)[failed] is False


def test_what_the_accounts_do_not_hold_is_cannot_tell_and_never_a_pass() -> None:
    young = {key: {y: v for y, v in series.items() if y >= 2024} for key, series in GOOD.items()}
    found = fundamentals.screen("NEW", **young)
    assert rules(found)["profitable"] is None  # two years are not five
    assert not found.passes
    assert found.quality_known < 4
    empty = fundamentals.screen("NONE", **{key: {} for key in GOOD})
    assert not empty.passes
    assert empty.latest_year is None


def test_quality_checks_do_not_decide_the_pass_but_are_counted() -> None:
    thin = {**GOOD, "equity": each(5000.0), "shares": {**GOOD["shares"], 2025: 130.0}}
    found = fundamentals.screen("THIN", **thin)
    assert found.passes
    assert rules(found)["return"] is False
    assert rules(found)["shares"] is False
    assert (found.quality_passed, found.quality_known) == (2, 4)


FACTS = {
    "facts": {
        "us-gaap": {
            "NetIncomeLoss": {
                "units": {
                    "USD": [
                        # A whole year, reported twice: the later filing wins.
                        {
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "val": 90,
                            "form": "10-K",
                            "filed": "2025-02-01",
                        },
                        {
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "val": 95,
                            "form": "10-K/A",
                            "filed": "2025-06-01",
                        },
                        # A quarter, and a year from a quarterly report: both left out.
                        {
                            "start": "2024-10-01",
                            "end": "2024-12-31",
                            "val": 30,
                            "form": "10-K",
                            "filed": "2025-02-01",
                        },
                        {
                            "start": "2023-01-01",
                            "end": "2023-12-31",
                            "val": 70,
                            "form": "10-Q",
                            "filed": "2024-05-01",
                        },
                    ]
                }
            },
            "ProfitLoss": {
                "units": {
                    "USD": [
                        {
                            "start": "2023-01-01",
                            "end": "2023-12-31",
                            "val": 71,
                            "form": "10-K",
                            "filed": "2024-02-01",
                        },
                        {
                            "start": "2024-01-01",
                            "end": "2024-12-31",
                            "val": 999,
                            "form": "10-K",
                            "filed": "2025-02-01",
                        },
                    ]
                }
            },
            "StockholdersEquity": {
                "units": {
                    "USD": [
                        {"end": "2024-12-31", "val": 500, "form": "10-K", "filed": "2025-02-01"}
                    ]
                }
            },
        }
    }
}


def test_yearly_figures_come_from_annual_reports_whole_years_and_the_first_name_used() -> None:
    assert sec.yearly(FACTS, ("NetIncomeLoss", "ProfitLoss")) == {2023: 71.0, 2024: 95.0}
    assert sec.yearly(FACTS, ("StockholdersEquity",)) == {2024: 500.0}
    assert sec.yearly(FACTS, ("NothingReported",)) == {}


def test_only_the_two_public_reads_of_filings_are_allowed_and_the_program_names_itself() -> None:
    sent: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if request.url.path == "/files/company_tickers.json":
            return httpx.Response(200, json={"0": {"cik_str": 320193, "ticker": "aapl"}})
        return httpx.Response(200, json=FACTS)

    source = PublicReader(
        sec.ALLOWED,
        patterns=sec.PATTERNS,
        user_agent=sec.user_agent("someone@example.test"),
        transport=httpx.MockTransport(handle),
        sleep=lambda _: None,
    )
    assert sec.company_numbers(source) == {"AAPL": 320193}
    assert sec.company_facts(source, 320193) == FACTS
    assert [r.url.path for r in sent] == [
        "/files/company_tickers.json",
        "/api/xbrl/companyfacts/CIK0000320193.json",
    ]
    agent = "RADAR portfolio research someone@example.test"
    assert all(r.method == "GET" and r.headers["user-agent"] == agent for r in sent)
    # Without a contact nothing is sent at all: the regulator would refuse it.
    for missing in (None, "", "not an address"):
        with pytest.raises(sec.NoContactError):
            sec.reader(missing)
    for host, path in (
        ("data.sec.gov", "/api/xbrl/companyfacts/CIK320193.json"),
        ("data.sec.gov", "/submissions/CIK0000320193.json"),
        ("www.sec.gov", "/cgi-bin/browse-edgar"),
        ("efts.sec.gov", "/files/company_tickers.json"),
    ):
        with pytest.raises(DisallowedPublicRequestError):
            source.get(host, path, {})
    assert len(sent) == 2
