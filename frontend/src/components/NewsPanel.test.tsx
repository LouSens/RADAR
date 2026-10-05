import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, EventStudy, Sentiment } from "../api/client";
import { NewsPanel, toneWord } from "./NewsPanel";

const state = vi.hoisted(() => ({ sentiment: null as unknown, study: null as unknown }));
vi.mock("../api/queries", () => ({
  useSentiment: () => ({ data: state.sentiment }),
  useEventStudy: () => ({ data: state.study }),
}));

const BITCOIN: Asset = {
  symbol: "BTC/USD",
  slug: "btc-usd",
  name: "Bitcoin",
  asset_class: "crypto",
  is_primary: true,
  history_start: "2021-01-01",
  news_start: "2022-01-01",
  trades_continuously: true,
};

const SENTIMENT: Sentiment = {
  symbol: "BTC/USD",
  model_version: "finbert-prosus-1",
  news_start: "2022-01-01",
  as_of: "2026-10-05T16:00:00Z",
  current: -0.31,
  articles_24h: 12,
  articles_7d: 88,
  articles_in_window: 1040,
  days_with_news: 89,
  daily: [
    { ts: "2026-10-03T00:00:00Z", article_count: 9, score_mean: 0.2, score_decayed: 0.1 },
    { ts: "2026-10-04T00:00:00Z", article_count: 0, score_mean: null, score_decayed: 0.1 },
    { ts: "2026-10-05T00:00:00Z", article_count: 14, score_mean: -0.4, score_decayed: -0.2 },
  ],
  most_positive: [
    {
      id: 1,
      created_at: "2026-10-03T10:00:00Z",
      headline: "Invented positive headline",
      url: "https://example.test/1",
      source: "test",
      score: 0.93,
      topic: "funds_flows",
    },
  ],
  most_negative: [],
  topics: [
    { topic: "price", article_count: 700, score_mean: 0.05 },
    { topic: "security", article_count: 40, score_mean: -0.6 },
  ],
  accuracy: {
    labelled_by: ["claude"],
    model: { n: 200, accuracy: 0.71, macro_f1: 0.7 },
    baseline: { n: 200, accuracy: 0.52, macro_f1: 0.48 },
    topics: { n: 200, accuracy: 0.58, macro_f1: 0.5 },
  },
};

const path = (n: number, mean: number[]) => ({
  n,
  offsets: [-1, 0, 1, 2, 3],
  mean,
  low: mean.map((v) => v - 0.01),
  high: mean.map((v) => v + 0.01),
});

const STUDY: EventStudy = {
  symbol: "BTC/USD",
  computed_at: "2026-10-05T16:20:00Z",
  verdict: "price leads sentiment",
  n_events: 96,
  n_positive: 41,
  n_negative: 55,
  min_events: 30,
  days_with_news: 1730,
  first_day: "2022-01-01",
  last_day: "2026-10-04",
  positive: path(41, [0.01, 0.03, 0.03, 0.02, 0.02]),
  negative: path(55, [-0.01, -0.04, -0.04, -0.03, -0.03]),
  baseline: path(96, [0, 0, 0.001, 0, 0]),
  lags: [-2, -1, 0, 1, 2].map((lag) => ({
    lag,
    correlation: lag === -1 ? 0.14 : 0.01,
    n: 1700,
    significant: lag === -1,
  })),
};

describe("NewsPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    state.sentiment = SENTIMENT;
    state.study = STUDY;
  });

  it("shows nothing until news tone is stored", () => {
    state.sentiment = null;
    expect(render(<NewsPanel asset={BITCOIN} />).container).toBeEmptyDOMElement();
  });

  it("shows the current tone in words, with how much news there is", () => {
    render(<NewsPanel asset={BITCOIN} />);
    expect(screen.getByText("Mostly negative")).toBeVisible();
    expect(screen.getByText("−0.31")).toBeVisible();
    expect(screen.getByText("88")).toBeVisible();
    expect(screen.getByText(/1,040 articles on 89 of the last 3 days/)).toBeVisible();
  });

  it("links the strongest articles to their source and names topics plainly", () => {
    render(<NewsPanel asset={BITCOIN} />);
    const link = screen.getByRole("link", { name: "Invented positive headline" });
    expect(link).toHaveAttribute("href", "https://example.test/1");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByText(/Funds and large investors/)).toBeVisible();
    expect(screen.getByText("Hacks, fraud, and failures")).toBeVisible();
    expect(screen.getByText("None in this period.")).toBeVisible();
  });

  it("states the verdict with its event count", () => {
    render(<NewsPanel asset={BITCOIN} />);
    expect(
      screen.getByText("Price has tended to move first, with news tone following it."),
    ).toBeVisible();
    expect(screen.getByText("96")).toBeVisible();
    expect(screen.getByText(/41 days of unusually positive news/)).toBeVisible();
  });

  it("says so when there is too little news to judge, and draws no charts for it", () => {
    state.study = { ...STUDY, verdict: "not enough events", n_events: 12 };
    render(<NewsPanel asset={BITCOIN} />);
    expect(
      screen.getByText("There is too little news coverage of this asset to measure an effect."),
    ).toBeVisible();
    expect(screen.queryByText(/unusually positive news \(green\)/)).toBeNull();
  });

  it("reports the model's accuracy and who labelled the sample", () => {
    render(<NewsPanel asset={BITCOIN} />);
    expect(screen.getByText(/labelled by an AI model \(Claude\), not a person/)).toBeVisible();
    expect(screen.getByText(/agreed with the label 71% of the time/)).toBeVisible();
    expect(screen.getByText(/counting positive and negative words agreed 52%/)).toBeVisible();
    expect(screen.getByText(/subject it assigned matched 58%/)).toBeVisible();
  });

  it("puts tone into plain words", () => {
    expect(toneWord(0.4)).toBe("Mostly positive");
    expect(toneWord(0.05)).toBe("Mixed");
    expect(toneWord(null)).toBe("No recent news");
  });

  it("never tells the reader what to do", () => {
    const { container } = render(<NewsPanel asset={BITCOIN} />);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });
});
