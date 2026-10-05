"""API response models. The OpenAPI schema built from these generates the frontend types.

Every timestamp is timezone-aware UTC. The frontend converts to the viewer's zone.
"""

from datetime import date
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from radar.models import evidence


class AssetOut(BaseModel):
    symbol: str
    # URL-safe form of the symbol, for example "btc-usd". Routes accept either.
    slug: str
    name: str
    asset_class: Literal["crypto", "stock"]
    is_primary: bool
    history_start: date
    news_start: date | None
    # False for assets that only trade during US market hours.
    trades_continuously: bool


class BarOut(BaseModel):
    ts: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    is_quote_only: bool
    # Flagged by the quality job: an unusual jump, or a high or low that looks like a bad print.
    is_outlier: bool


class BarsOut(BaseModel):
    symbol: str
    timeframe: str
    # Where the bars come from: the crypto location, or the stock feed.
    source: str | None
    count: int
    bars: list[BarOut]


class SeriesStatus(BaseModel):
    symbol: str
    timeframe: str
    is_primary: bool
    bars: int
    first_ts: AwareDatetime
    last_ts: AwareDatetime
    # Seconds since the end of the latest stored bar.
    lag_seconds: float
    stale: bool
    # Share of expected bars that are missing, from the latest quality report.
    missing_share: float | None


class QualitySummary(BaseModel):
    last_run: AwareDatetime | None
    findings: int
    warnings: int
    failures: int


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "down"]
    generated_at: AwareDatetime
    database: bool
    last_sync: AwareDatetime | None
    stream_clients: int
    quality: QualitySummary
    series: list[SeriesStatus]


class LiveBar(BaseModel):
    """A live one-minute bar pushed over `WS /stream`. Not stored."""

    type: Literal["bar"]
    symbol: str
    ts: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class LiveNews(BaseModel):
    """A new article pushed over `WS /stream`."""

    type: Literal["news"]
    id: int
    symbols: list[str]


class RegimeStateOut(BaseModel):
    label: str
    # Average size of a day's price swing in this state, as a fraction (0.02 is 2%).
    typical_daily_volatility: float
    typical_duration_days: float
    # Probability of each other state being next, once this one ends.
    next_states: dict[str, float]


class RegimePoint(BaseModel):
    ts: AwareDatetime
    label: str
    probability: float


class RegimeEvaluationOut(BaseModel):
    """Walk-forward results: every figure is from days the model had not seen."""

    n_days: int
    first_test_day: date
    last_test_day: date
    next_day_volatility: dict[str, float]
    volatility_is_ordered: bool
    model_log_density: float
    baseline_log_density: float
    average_run_length: float


class RegimeModelOut(BaseModel):
    version: str
    trained_at: AwareDatetime
    train_start: date
    train_end: date
    n_train: int
    bic_by_states: dict[str, float]


class RegimeOut(BaseModel):
    symbol: str
    # When the latest reading became known: the end of the day it describes.
    as_of: AwareDatetime
    label: str
    probability: float
    probabilities: dict[str, float]
    # Consecutive days, counting back from the latest, with this label.
    days_in_state: int
    states: list[RegimeStateOut]
    history: list[RegimePoint]
    model: RegimeModelOut
    evaluation: RegimeEvaluationOut | None


class OutlookRange(BaseModel):
    """A central range of simulated prices, raw and after the conformal adjustment."""

    level: float
    low: float
    high: float
    # Widened or narrowed using how earlier ranges held. Null until that has been measured.
    adjusted_low: float | None
    adjusted_high: float | None
    # True when the adjustment is as wide as it can go, so the range is nearly every outcome.
    adjusted_is_widest: bool


class OutlookHorizon(BaseModel):
    horizon_days: int
    # Trading steps simulated: days for crypto, market sessions for stocks.
    steps: int
    quantiles: dict[str, float]
    intervals: list[OutlookRange]
    histogram_edges: list[float]
    histogram_counts: list[int]
    # Average of each path's largest peak-to-trough fall, as a negative fraction.
    expected_worst_drawdown: float
    mean_return: float


class SimulationOut(BaseModel):
    symbol: str
    # When the inputs became known: the end of the last day the run used.
    as_of: AwareDatetime
    start_price: float
    n_paths: int
    seed: int
    model_version: str
    horizons: list[OutlookHorizon]
    # Price quantiles at the end of each step, starting from the start price.
    fan: dict[str, list[float]]


class LevelIn(BaseModel):
    level: float = Field(gt=0)
    horizon_days: int


class LevelOut(BaseModel):
    """Two different questions about one price level, kept apart."""

    symbol: str
    as_of: AwareDatetime
    start_price: float
    level: float
    horizon_days: int
    steps: int
    n_paths: int
    # Share of simulated paths at or beyond the level at the end of the horizon.
    ends_above: float
    ends_below: float
    # Share of paths whose daily close reaches the level at any point in the horizon.
    touches: float


class CalibrationRowOut(BaseModel):
    horizon_days: int
    steps: int
    nominal: float
    # Share of past ranges that contained the outcome, raw and after adjustment.
    empirical: float
    empirical_conformal: float
    n: int
    # 95% range for each share. Forecasts several steps ahead overlap, so the range is
    # worked out from the number of periods that do not overlap (n divided by steps).
    empirical_low: float | None = None
    empirical_high: float | None = None
    conformal_low: float | None = None
    conformal_high: float | None = None
    # Average pinball loss; lower is better. The baseline is a constant-volatility random walk.
    pinball_model: float
    pinball_baseline: float
    first_origin: date
    last_origin: date

    @model_validator(mode="after")
    def _ranges(self) -> "CalibrationRowOut":
        independent = max(self.n // max(self.steps, 1), 1)
        self.empirical_low, self.empirical_high = evidence.share_interval(
            self.empirical, independent
        )
        self.conformal_low, self.conformal_high = evidence.share_interval(
            self.empirical_conformal, independent
        )
        return self


class CalibrationOut(BaseModel):
    symbol: str
    model_version: str
    computed_at: AwareDatetime
    rows: list[CalibrationRowOut]


class VolatilityScoreOut(BaseModel):
    # "har" (regression on recent volatility), "gbt" (tree model), "carry" (yesterday
    # carried forward), or "regime" (average for the current market state).
    model: str
    # Average loss on days the model had not seen; lower is better.
    qlike: float
    mse: float
    # Diebold-Mariano p-value for the difference from "har". Null for "har" itself.
    dm_p_value_vs_har: float | None = None


class VolatilityPoint(BaseModel):
    ts: AwareDatetime
    forecast: float
    # What happened over the days the forecast covered. Null until they have ended.
    realised: float | None


class VolatilityHorizonOut(BaseModel):
    horizon_days: int
    steps: int
    # The model whose forecast is shown, and why it was chosen.
    shown: str
    reason: str
    # Per-day volatility expected over the next `steps` days, as a fraction.
    forecast: float
    # The latest completed outcome: per-day volatility over the last `steps` days.
    last_realised: float | None
    history: list[VolatilityPoint]
    n: int
    first_day: date
    last_day: date
    scores: list[VolatilityScoreOut]


class VolatilityOut(BaseModel):
    symbol: str
    as_of: AwareDatetime
    model_version: str
    horizons: list[VolatilityHorizonOut]


class RiskMethodOut(BaseModel):
    """One method's current limit at one level, and how its past limits held."""

    # "historical", "filtered" (scaled to the volatility forecast), or "simulator".
    method: str
    # The loss, as a fraction, that should be exceeded only (1 - level) of the time.
    var: float
    # The average loss in the periods that do exceed it.
    expected_shortfall: float
    # Periods tested; for horizons longer than a day they do not overlap.
    n: int
    breaches: int
    expected_breaches: float
    breach_rate: float
    # 95% range for the breach rate.
    breach_rate_low: float | None = None
    breach_rate_high: float | None = None
    kupiec_p_value: float | None
    # The same p-value adjusted for the number of limits tested together.
    kupiec_p_adjusted: float | None = None
    clustering_p_value: float | None
    # False when the limit was broken measurably more or less often than stated, after
    # allowing for the number of limits tested.
    reliable: bool

    @model_validator(mode="after")
    def _ranges(self) -> "RiskMethodOut":
        self.breach_rate_low, self.breach_rate_high = evidence.wilson(self.breaches, self.n)
        return self


class RiskLevelOut(BaseModel):
    level: float
    methods: list[RiskMethodOut]


class RiskHorizonOut(BaseModel):
    horizon_days: int
    steps: int
    # The method with the best backtest, whose figures are displayed.
    shown: str
    first_day: date
    last_day: date
    levels: list[RiskLevelOut]


class DrawdownOut(BaseModel):
    peak_day: date
    trough_day: date
    depth: float
    recovered_day: date | None


class RiskOut(BaseModel):
    symbol: str
    as_of: AwareDatetime
    model_version: str
    horizons: list[RiskHorizonOut]
    # The deepest falls in daily closing prices over the stored history.
    drawdowns: list[DrawdownOut]


class SentimentPoint(BaseModel):
    # When the day ended: midnight UTC for crypto, the market close for stocks.
    ts: AwareDatetime
    article_count: int
    # Average tone of that day's articles, from -1 to +1. Null on a day with none.
    score_mean: float | None
    # Average tone of all earlier articles, each one's weight halving every 24 hours.
    score_decayed: float | None


class ArticleOut(BaseModel):
    id: int
    created_at: AwareDatetime
    headline: str
    url: str | None
    source: str
    score: float
    topic: str | None


class ClassifierScoreOut(BaseModel):
    n: int
    accuracy: float
    macro_f1: float
    # 95% range for the accuracy, given the number of headlines.
    accuracy_low: float | None = None
    accuracy_high: float | None = None

    @model_validator(mode="after")
    def _ranges(self) -> "ClassifierScoreOut":
        self.accuracy_low, self.accuracy_high = evidence.share_interval(self.accuracy, self.n)
        return self


class DirectionOut(BaseModel):
    n: int
    # Share of headlines given the opposite tone to their label (positive for negative).
    opposite_rate: float
    # Where label and model both took a side, how often it was the same side.
    both_polar: int
    same_direction: float | None


class SentimentAccuracyOut(BaseModel):
    """How the tone model did on headlines labelled by hand."""

    labelled_by: list[str]
    model: ClassifierScoreOut
    # A word-count method on the same headlines. Null if the word list is not installed.
    baseline: ClassifierScoreOut | None = None
    # The same for assigning a topic. Null until topics have been measured.
    topics: ClassifierScoreOut | None = None
    # The original model on the same headlines, when a fine-tuned one is in use.
    original: ClassifierScoreOut | None = None
    direction: DirectionOut | None = None
    # True when the figures come from headlines later than everything the model was
    # trained on. False when they come from the earlier reference sample.
    held_out: bool = False
    fine_tuned: bool = False


class TopicSummary(BaseModel):
    topic: str
    article_count: int
    score_mean: float


class SentimentOut(BaseModel):
    symbol: str
    model_version: str
    # Tone is measured from this date; before it there is too little news.
    news_start: date
    as_of: AwareDatetime
    # Tone now: the decayed average at the latest completed hour.
    current: float | None
    articles_24h: int
    articles_7d: int
    # Articles in the window, and how many of those days had any.
    articles_in_window: int
    days_with_news: int
    daily: list[SentimentPoint]
    most_positive: list[ArticleOut]
    most_negative: list[ArticleOut]
    topics: list[TopicSummary]
    accuracy: SentimentAccuracyOut | None


class EventPathOut(BaseModel):
    n: int
    # Days relative to the event day: -1 is the day before.
    offsets: list[int]
    mean: list[float]
    low: list[float]
    high: list[float]


class LagOut(BaseModel):
    # Positive: tone came first. Negative: price came first.
    lag: int
    correlation: float
    n: int
    significant: bool


class TopicVerdict(BaseModel):
    topic: str
    verdict: str
    n_events: int
    days_with_news: int


class EventStudyOut(BaseModel):
    symbol: str
    computed_at: AwareDatetime
    # One of: sentiment leads price, price leads sentiment, no measurable relationship,
    # not enough events.
    verdict: str
    n_events: int
    n_positive: int
    n_negative: int
    min_events: int
    days_with_news: int
    first_day: date | None
    last_day: date | None
    positive: EventPathOut
    negative: EventPathOut
    baseline: EventPathOut
    lags: list[LagOut]
    # How many tests were judged together when deciding significance.
    tests_in_family: int | None = None
    # The same verdict for each news topic on its own. Empty until articles have topics.
    by_topic: list[TopicVerdict] = []


class TrackRecordRow(BaseModel):
    # "outlook_range", "volatility", or "loss_limit".
    kind: str
    horizon_days: int
    key: str
    # Forecasts written down, and how many of those have an outcome so far.
    recorded: int
    resolved: int
    held: int | None
    held_share: float | None
    held_low: float | None
    held_high: float | None
    expected_share: float | None
    forecast_to_outcome: float | None
    first_as_of: AwareDatetime
    last_as_of: AwareDatetime


class TrackRecordOut(BaseModel):
    """Forecasts logged on the day they were made and scored afterwards. Not a backtest."""

    symbol: str
    recording_since: AwareDatetime | None
    recorded: int
    resolved: int
    rows: list[TrackRecordRow]
