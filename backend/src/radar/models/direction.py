"""Does the price end higher a day from now? Three models on hourly bars (decision 062).

An LSTM reads the last 48 bars; gradient-boosted trees and a logistic regression read
summaries of the same history. All three are trained on the first part of the record,
tuned on the next, and judged once on the last.

No lookahead: every input of a bar uses that bar and earlier bars only; inputs are scaled
with the training part's averages; and a gap is left between the parts so that no answer
in one depends on prices in the next.
"""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd
from pydantic import BaseModel
from scipy.stats import binomtest

from radar.analytics import technical

MODEL_VERSION = "direction-1"
WINDOW = 48
VOLUME_WINDOW = 168
TRAIN_SHARE, VALIDATION_SHARE = 0.6, 0.2
MIN_MARGIN = 0.03
SIGNIFICANCE = 0.05
BAR_INPUTS = ("ret", "range", "volume", "hour_sin", "hour_cos")
SUMMARY_INPUTS = (
    "ret_1",
    "ret_6",
    "ret_24",
    "ret_72",
    "ret_168",
    "swing_24",
    "swing_168",
    "volume",
    "rsi",
    "hour_sin",
    "hour_cos",
)

OUTSIDE_SUMMARY = ("buy_1", "buy_24", "buy_168", "funding", "funding_week", "funding_unusual")
OUTSIDE_BARS = ("buy", "funding")
FUNDING_WEEK = 21
FUNDING_QUARTER = 270

Predict = Callable[[np.ndarray], np.ndarray]


def _clock(index: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    angle = 2 * np.pi * np.asarray(index.hour, dtype=float) / 24
    return np.sin(angle), np.cos(angle)


def _volume(volume: pd.Series) -> pd.Series:
    """Log of a bar's volume against the average of the 168 bars before it."""
    usual = volume.shift(1).rolling(VOLUME_WINDOW).mean()
    return pd.Series(np.log((volume.clip(lower=1e-9)) / usual), index=volume.index)


def bar_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    """What the LSTM sees of each bar. `frame` has high, low, close, volume, by bar."""
    close = frame["close"]
    sin, cos = _clock(pd.DatetimeIndex(frame.index))
    table = pd.DataFrame(
        {
            "ret": np.log(close).diff(),
            "range": (frame["high"] - frame["low"]) / close,
            "volume": _volume(frame["volume"]),
            "hour_sin": sin,
            "hour_cos": cos,
        },
        index=frame.index,
    )
    return table[list(BAR_INPUTS)]


def summary_inputs(frame: pd.DataFrame) -> pd.DataFrame:
    """What the two simpler models see at each bar: summaries of the same history."""
    close = frame["close"]
    logged = np.log(close)
    returns = logged.diff()
    sin, cos = _clock(pd.DatetimeIndex(frame.index))
    table = pd.DataFrame(
        {
            "ret_1": returns,
            "ret_6": logged.diff(6),
            "ret_24": logged.diff(24),
            "ret_72": logged.diff(72),
            "ret_168": logged.diff(168),
            "swing_24": returns.rolling(24).std(),
            "swing_168": returns.rolling(168).std(),
            "volume": _volume(frame["volume"]),
            "rsi": technical.rsi(close),
            "hour_sin": sin,
            "hour_cos": cos,
        },
        index=frame.index,
    )
    return table[list(SUMMARY_INPUTS)]


def _buy_share(frame: pd.DataFrame, bars: int) -> pd.Series:
    """Of the volume of the last `bars` bars, the share bought by the side that crossed
    the spread. Above a half, buyers were the more eager side."""
    volume = frame["volume"].rolling(bars).sum()
    return frame["taker_buy"].rolling(bars).sum() / volume.where(volume > 0)


def funding_by_bar(funding: pd.Series, index: pd.DatetimeIndex) -> pd.DataFrame:
    """For each bar, the funding figures already paid by its opening time: the latest
    rate, its average over the last week of payments, and how unusual the latest is
    against the quarter of payments before it."""
    before = funding.shift(1)
    spread = before.rolling(FUNDING_QUARTER).std()
    table = pd.DataFrame(
        {
            "funding": funding,
            "funding_week": funding.rolling(FUNDING_WEEK).mean(),
            "funding_unusual": (funding - before.rolling(FUNDING_QUARTER).mean())
            / spread.where(spread > 0),
        }
    )
    table.index = pd.DatetimeIndex(table.index).floor("h")
    table = table[~table.index.duplicated(keep="last")]
    return table.reindex(table.index.union(index)).ffill().reindex(index)


def outside_summary(frame: pd.DataFrame, funding: pd.Series) -> pd.DataFrame:
    """Outside inputs for the two simpler models. `frame` also has taker_buy."""
    paid = funding_by_bar(funding, pd.DatetimeIndex(frame.index))
    table = pd.DataFrame(
        {
            "buy_1": _buy_share(frame, 1),
            "buy_24": _buy_share(frame, 24),
            "buy_168": _buy_share(frame, 168),
            "funding": paid["funding"],
            "funding_week": paid["funding_week"],
            "funding_unusual": paid["funding_unusual"],
        },
        index=frame.index,
    )
    return table[list(OUTSIDE_SUMMARY)]


def outside_bars(frame: pd.DataFrame, funding: pd.Series) -> pd.DataFrame:
    """Outside inputs the LSTM sees bar by bar."""
    paid = funding_by_bar(funding, pd.DatetimeIndex(frame.index))
    table = pd.DataFrame(
        {"buy": _buy_share(frame, 1), "funding": paid["funding"]}, index=frame.index
    )
    return table[list(OUTSIDE_BARS)]


@dataclass(frozen=True)
class Split:
    """Rows of each part, in time order, with a gap left out between them."""

    train: np.ndarray
    validation: np.ndarray
    test: np.ndarray


def split(usable: np.ndarray, horizon: int, window: int = WINDOW) -> Split:
    """Cut the record 60 / 20 / 20 by position, dropping `horizon + window` rows at the
    start of the second and third parts, and keep only the `usable` rows of each."""
    n = len(usable)
    first, second = int(n * TRAIN_SHARE), int(n * (TRAIN_SHARE + VALIDATION_SHARE))
    gap = horizon + window
    rows = np.arange(n)
    return Split(
        train=rows[:first][usable[:first]],
        validation=rows[first + gap : second][usable[first + gap : second]],
        test=rows[second + gap :][usable[second + gap :]],
    )


def usable_rows(table: pd.DataFrame, answers: pd.Series, window: int) -> np.ndarray:
    """Rows whose answer is known and whose last `window` bars of inputs are complete."""
    complete = table.notna().all(axis=1)
    whole_window = complete.rolling(window).sum() == window
    usable: np.ndarray = (whole_window & answers.notna()).to_numpy()
    return usable


def scaled(table: pd.DataFrame, train: np.ndarray) -> np.ndarray:
    """Inputs minus the training rows' average, over their spread."""
    values = table.to_numpy(dtype=float)
    centre = np.nanmean(values[train], axis=0)
    spread = np.nanstd(values[train], axis=0)
    result: np.ndarray = (values - centre) / np.where(spread > 0, spread, 1.0)
    return result


def windows(values: np.ndarray, rows: np.ndarray, length: int = WINDOW) -> np.ndarray:
    """For each row, the `length` bars ending at it: shape (rows, length, inputs)."""
    offsets = np.arange(-length + 1, 1)
    result: np.ndarray = values[rows[:, None] + offsets[None, :]]
    return result


def planted_answers(recent_return: pd.Series, seed: int) -> pd.Series:
    """Made-up answers with a known rule: higher 65% of the time when the recent return
    was positive, 40% when it was not. For checking that a model can learn at all."""
    rng = np.random.default_rng(seed)
    chance = np.where(recent_return > 0, 0.65, 0.40)
    made_up = (rng.random(len(recent_return)) < chance).astype(float)
    return pd.Series(made_up, index=recent_return.index).where(recent_return.notna())


def fit_logistic(x: np.ndarray, y: np.ndarray) -> Predict:
    from sklearn.linear_model import LogisticRegression

    model = LogisticRegression(C=0.1, max_iter=1000).fit(x, y)
    return lambda rows: np.asarray(model.predict_proba(rows)[:, 1], dtype=float)


def fit_lstm(
    x: np.ndarray,
    y: np.ndarray,
    x_validation: np.ndarray,
    y_validation: np.ndarray,
    hidden: int = 32,
    rate: float = 1e-3,
    seed: int = 0,
    max_passes: int = 30,
    patience: int = 5,
    batch: int = 256,
) -> Predict:
    """One LSTM layer and a linear read-out, stopped where the validation loss was best.

    The validation part chooses when to stop and nothing else. Needs the `nlp` extra.
    """
    import torch
    from torch import nn

    torch.manual_seed(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    class Net(nn.Module):  # type: ignore[misc]
        def __init__(self) -> None:
            super().__init__()
            self.lstm = nn.LSTM(x.shape[2], hidden, batch_first=True)
            self.drop = nn.Dropout(0.2)
            self.out = nn.Linear(hidden, 1)

        def forward(self, batch_x: "torch.Tensor") -> "torch.Tensor":
            _, (last, _) = self.lstm(batch_x)
            return self.out(self.drop(last[-1])).squeeze(-1)

    def tensor(values: np.ndarray) -> "torch.Tensor":
        return torch.as_tensor(values, dtype=torch.float32, device=device)

    net = Net().to(device)
    optimiser = torch.optim.Adam(net.parameters(), lr=rate)
    loss_of = nn.BCEWithLogitsLoss()
    train_x, train_y = tensor(x), tensor(y)
    val_x, val_y = tensor(x_validation), tensor(y_validation)
    generator = torch.Generator(device="cpu").manual_seed(seed)

    def scores(values: "torch.Tensor") -> "torch.Tensor":
        net.eval()
        with torch.no_grad():
            parts = [net(values[i : i + 4096]) for i in range(0, len(values), 4096)]
        return torch.cat(parts)

    best, best_state, waited = float("inf"), None, 0
    for _ in range(max_passes):
        net.train()
        order = torch.randperm(len(train_x), generator=generator).to(device)
        for start in range(0, len(order), batch):
            rows = order[start : start + batch]
            optimiser.zero_grad()
            loss_of(net(train_x[rows]), train_y[rows]).backward()
            optimiser.step()
        loss = float(loss_of(scores(val_x), val_y))
        if loss < best - 1e-5:
            best, waited = loss, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            waited += 1
            if waited >= patience:
                break
    if best_state is not None:
        net.load_state_dict(best_state)

    def predict(rows: np.ndarray) -> np.ndarray:
        return np.asarray(torch.sigmoid(scores(tensor(rows))).cpu().numpy(), dtype=float)

    return predict


class Score(BaseModel):
    """How a model did on test cases that do not overlap."""

    n: int
    accuracy: float
    baseline: float
    margin: float
    p_value: float
    first_half_margin: float
    second_half_margin: float
    said_higher: float


def score(chance: np.ndarray, answers: np.ndarray, usual_answer: float, horizon: int) -> Score:
    """Accuracy on every `horizon`-th test row against always giving `usual_answer` (the
    answer that was more common in the training part)."""
    chance, answers = chance[::horizon], answers[::horizon]
    right = (chance > 0.5) == (answers == 1)
    usual_right = answers == usual_answer
    n = len(answers)
    half = n // 2
    baseline = float(usual_right.mean())
    return Score(
        n=n,
        accuracy=float(right.mean()),
        baseline=baseline,
        margin=float(right.mean()) - baseline,
        p_value=float(binomtest(int(right.sum()), n, baseline, alternative="greater").pvalue),
        first_half_margin=float(right[:half].mean() - usual_right[:half].mean()),
        second_half_margin=float(right[half:].mean() - usual_right[half:].mean()),
        said_higher=float((chance > 0.5).mean()),
    )


def passes(result: Score, survives: bool) -> bool:
    """The mark of decision 062: 3 points clear of the baseline, a p-value that survives
    the correction, and ahead in both halves of the test part."""
    return (
        result.margin >= MIN_MARGIN
        and survives
        and result.first_half_margin > 0
        and result.second_half_margin > 0
    )


def gain_recovered(result: Score, knowing_the_rule: float) -> float:
    """Of the gain over the baseline that knowing a planted rule would give, the share a
    model got. Under a half and the model "cannot learn here"."""
    possible = knowing_the_rule - result.baseline
    return result.margin / possible if possible > 0 else 0.0
