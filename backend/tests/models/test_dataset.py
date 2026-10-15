"""The headline cleaning the tone model is trained and scored on."""

from radar.models import dataset


def test_headline_key_ignores_numbers_case_and_punctuation() -> None:
    a = dataset.headline_key("Bitcoin Whale Moves 2,901 BTC Off Coinbase")
    b = dataset.headline_key("bitcoin whale moves 1,112 btc off coinbase!")
    assert a == b == "bitcoin whale moves # btc off coinbase"
    assert dataset.headline_key("Gold rises") != dataset.headline_key("Gold falls")
    assert dataset.headline_key("USA CPI (MoM) for May 1.000% vs 0.700% Est") == (
        "usa cpi mom for may # vs # est"
    )
    assert dataset.headline_key("123") == "#"


def test_cleaning_removes_only_what_carries_no_tone() -> None:
    assert dataset.clean_headline("  Gold &amp; Silver   Rise ") == "Gold & Silver Rise"
    assert dataset.clean_headline("Commodities Poised For Comeback (UPDATED)") == (
        "Commodities Poised For Comeback"
    )
    assert dataset.clean_headline("Brown praised Oracle Corporation (NYSE:ORCL) today") == (
        "Brown praised Oracle Corporation today"
    )
    assert dataset.clean_headline("'UK suspends some sharing'- CNN") == "'UK suspends some sharing'"
    # A dash inside an ordinary headline is part of it.
    assert dataset.clean_headline("Asia Mixed - Markets Today") == "Asia Mixed - Markets Today"
    assert dataset.clean_headline("Bitcoin FALLS 5%!") == "Bitcoin FALLS 5%!"
