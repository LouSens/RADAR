import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, Sentiment } from "../api/client";
import { NewsPanel, toneWord } from "./NewsPanel";

const state = vi.hoisted(() => ({ sentiment: null as unknown }));
vi.mock("../api/queries", () => ({
  useSentiment: () => ({ data: state.sentiment }),
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
  recent: [
    {
      id: 1,
      created_at: "2026-10-03T10:00:00Z",
      headline: "Invented headline",
      url: "https://example.test/1",
      source: "test",
      score: 0.93,
      topic: "funds_flows",
    },
  ],
  topics: [
    { topic: "price", article_count: 700, score_mean: 0.05 },
    { topic: "security", article_count: 40, score_mean: -0.6 },
  ],
  accuracy: {
    labelled_by: ["claude"],
    model: { n: 200, accuracy: 0.71, macro_f1: 0.7, accuracy_low: 0.64, accuracy_high: 0.77 },
    baseline: { n: 200, accuracy: 0.52, macro_f1: 0.48 },
    topics: { n: 200, accuracy: 0.58, macro_f1: 0.5, accuracy_low: 0.51, accuracy_high: 0.65 },
    direction: { n: 200, opposite_rate: 0.06, both_polar: 110, same_direction: 0.89 },
    held_out: false,
    fine_tuned: false,
  },
};

describe("NewsPanel", () => {
  afterEach(cleanup);
  beforeEach(() => {
    state.sentiment = SENTIMENT;
  });

  it("shows nothing until news tone is stored", () => {
    state.sentiment = null;
    expect(render(<NewsPanel asset={BITCOIN} />).container).toBeEmptyDOMElement();
  });

  it("shows the current tone in words, with how much news there is", () => {
    render(<NewsPanel asset={BITCOIN} />);
    expect(screen.getAllByText("Mostly negative")).toHaveLength(2);
    expect(screen.getByText("−0.31")).toBeInTheDocument();
    expect(screen.getByText("88")).toBeInTheDocument();
    expect(screen.getByText(/1,040 articles on 89 of the last 3 days/)).toBeInTheDocument();
  });

  it("lists recent headlines with links, without ranking or showing a tone score", () => {
    render(<NewsPanel asset={BITCOIN} />);
    const link = screen.getByRole("link", { name: "Invented headline" });
    expect(link).toHaveAttribute("href", "https://example.test/1");
    expect(link).toHaveAttribute("rel", "noreferrer noopener");
    expect(screen.getByText("Recent headlines")).toBeInTheDocument();
    expect(screen.queryByText(/0\.93/)).toBeNull(); // the single-article score is not shown
    expect(screen.getByText(/not coloured by tone/)).toBeInTheDocument();
  });

  it("opens with the claim, its trust grade, and the reason for the grade", () => {
    render(
      <NewsPanel
        asset={BITCOIN}
        trust={{ grade: "rough", reason: "It agreed with labels on 61% of 700 headlines." }}
      />,
    );
    expect(screen.getByRole("heading", { name: "News" })).toBeInTheDocument();
    expect(screen.getByText("Rough")).toBeInTheDocument();
    expect(screen.getAllByText("Mostly negative")).toHaveLength(2);
    expect(screen.getByText("Why rough")).toBeInTheDocument();
    expect(screen.getByText("Tone of recent news")).toBeInTheDocument();
  });

  it("shows how the tone model was checked, with ranges and who labelled the sample", () => {
    render(<NewsPanel asset={BITCOIN} />);
    expect(screen.getByText("How the tone reading was checked")).toBeInTheDocument();
    expect(screen.getByText("Agreed with the label, on 200 headlines")).toBeInTheDocument();
    expect(screen.getByText("(64% to 77%)")).toBeInTheDocument();
    expect(screen.getByText("Counting positive and negative words")).toBeInTheDocument();
    expect(screen.getByText("52%")).toBeInTheDocument();
    expect(screen.getByText(/An AI model \(Claude\), not a person/)).toBeInTheDocument();
    expect(screen.getByText(/Calling a mild article neutral/)).toBeInTheDocument();
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
