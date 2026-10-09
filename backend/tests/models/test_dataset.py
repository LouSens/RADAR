"""The leakage guards for a labelled text dataset."""

import pandas as pd
import pytest

from radar.models import dataset


def frame(headlines: list[str], start: str = "2024-01-01") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "article_id": range(1, len(headlines) + 1),
            "headline": headlines,
            "created_at": pd.date_range(start, periods=len(headlines), freq="D", tz="UTC"),
        }
    )


def test_headline_key_ignores_numbers_case_and_punctuation() -> None:
    a = dataset.headline_key("Bitcoin Whale Moves 2,901 BTC Off Coinbase")
    b = dataset.headline_key("bitcoin whale moves 1,112 btc off coinbase!")
    assert a == b == "bitcoin whale moves # btc off coinbase"
    assert dataset.headline_key("Gold rises") != dataset.headline_key("Gold falls")
    assert dataset.headline_key("USA CPI (MoM) for May 1.000% vs 0.700% Est") == (
        "usa cpi mom for may # vs # est"
    )
    assert dataset.headline_key("123") == "#"


def test_repeats_are_kept_once_and_excluded_keys_dropped() -> None:
    data = frame(["Whale moves 5 BTC", "Gold rises", "Whale moves 9 BTC", "Stocks fall", "!!!"])
    kept = dataset.drop_repeats(data, exclude_keys=[dataset.headline_key("STOCKS FALL")])
    assert kept["article_id"].tolist() == [1, 2]  # the earliest whale headline, and gold


def test_split_is_by_time_with_no_overlap() -> None:
    data = frame([f"headline {chr(97 + i % 26)}{chr(97 + i // 26)}" for i in range(100)])
    split = dataset.time_split(data.sample(frac=1, random_state=0))
    counts = split["split"].value_counts()
    assert counts.to_dict() == {"train": 71, "validation": 15, "test": 14}
    newest_train = split.loc[split["split"] == "train", "created_at"].max()
    oldest_validation = split.loc[split["split"] == "validation", "created_at"].min()
    newest_validation = split.loc[split["split"] == "validation", "created_at"].max()
    oldest_test = split.loc[split["split"] == "test", "created_at"].min()
    assert newest_train < oldest_validation
    assert newest_validation < oldest_test
    dataset.check_no_leakage(split)


def test_rows_at_the_same_instant_stay_in_one_part() -> None:
    data = frame([f"h {chr(97 + i)}" for i in range(20)])
    data["created_at"] = pd.Timestamp("2024-01-01", tz="UTC")
    assert set(dataset.time_split(data)["split"]) == {"train"}


def test_leakage_check_catches_each_kind() -> None:
    good = dataset.time_split(frame([f"h {chr(97 + i)}" for i in range(20)]))
    dataset.check_no_leakage(good)

    repeated = good.copy()
    repeated.loc[19, "headline"] = str(repeated.loc[0, "headline"]).upper() + "!"
    with pytest.raises(ValueError, match="headline key"):
        dataset.check_no_leakage(repeated)

    same_article = good.copy()
    same_article.loc[19, "article_id"] = same_article.loc[0, "article_id"]
    with pytest.raises(ValueError, match="article_id"):
        dataset.check_no_leakage(same_article)

    out_of_order = good.copy()
    out_of_order.loc[0, "created_at"] = pd.Timestamp("2030-01-01", tz="UTC")
    with pytest.raises(ValueError, match="not older"):
        dataset.check_no_leakage(out_of_order)


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


def test_a_summary_is_used_only_up_to_its_last_whole_sentence() -> None:
    cut = "Commodities are back. This could benefit investors. And then the"
    assert dataset.whole_sentences(cut) == "Commodities are back. This could benefit investors."
    assert dataset.whole_sentences("no sentence ends here") == ""
    assert dataset.whole_sentences("") == ""


def test_model_text_is_built_from_the_parts_chosen() -> None:
    assert dataset.model_text("Gold rises", "It was up 2%. More", "Gold") == "Gold rises"
    assert dataset.model_text("Gold rises", "", "Gold", with_asset=True) == "Gold: Gold rises"
    assert dataset.model_text("Gold rises", "It was up 2%. More", "Gold", with_summary=True) == (
        "Gold rises. It was up 2%."
    )
    # A summary that only repeats the headline adds nothing.
    assert dataset.model_text("Gold rises", "Gold rises.", with_summary=True) == "Gold rises"


def test_walk_forward_blocks_never_train_on_later_rows() -> None:
    parts = dataset.walk_forward_blocks(100, block=10, blocks=3)
    assert [(len(train), validate.start) for train, validate in parts] == [
        (70, 70),
        (80, 80),
        (90, 90),
    ]
    for train, validate in parts:
        assert max(train) < min(validate)
        assert len(validate) == 10
    assert max(parts[-1][1]) == 99
    with pytest.raises(ValueError, match="Not enough rows"):
        dataset.walk_forward_blocks(30, block=10, blocks=3)
