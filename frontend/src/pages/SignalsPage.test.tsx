import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Asset, Brief } from "../api/client";
import { BriefCard, sentenceLink } from "../components/BriefCard";
import { signalDetail } from "../lib/signals";
import { SignalsPage } from "./SignalsPage";

const state = vi.hoisted(() => ({
  filter: undefined as unknown,
  signals: undefined as unknown,
  records: undefined as unknown,
  brief: undefined as unknown,
}));

const ASSETS = [
  { symbol: "BTC/USD", slug: "btc-usd", name: "Bitcoin", asset_class: "crypto", is_primary: true },
  {
    symbol: "SPY",
    slug: "spy",
    name: "US stocks (S&P 500)",
    asset_class: "stock",
    is_primary: true,
  },
] as unknown as Asset[];

vi.mock("../api/queries", () => ({
  useAssets: () => ({ data: ASSETS }),
  useSignals: (filter: unknown) => {
    state.filter = filter;
    return { data: state.signals, isPending: false, isError: false };
  },
  useSignalRecords: () => ({ data: state.records, isPending: false }),
  useBrief: () => ({ data: state.brief }),
}));

const outcome = (n: number, share: number, size: number) => ({
  n,
  share_positive: share,
  share_low: share - 0.12,
  share_high: share + 0.12,
  mean: 0,
  mean_size: size,
  quantiles: {},
});
const horizon = (label: string, steps: number, size: string) => ({
  steps,
  label,
  signal: outcome(58, 0.54, 0.0168),
  baseline: outcome(2203, 0.55, 0.0072),
  p_value: 0.8,
  verdict: "no measurable edge",
  size_p_value: 0.0001,
  size_verdict: size,
});

const SIGNALS = {
  signals: [
    {
      id: 2,
      symbol: "SPY",
      name: "US stocks (S&P 500)",
      ts: "2026-09-28T20:00:00Z",
      type: "abnormal_move",
      variant: "down",
      detail: { move: -0.021, usual: 0.0034, multiple: 6.2 },
      record: {
        n: 58,
        verdict: "no measurable edge",
        size_verdict: "followed by larger moves",
        share_positive: 0.54,
        baseline_share_positive: 0.55,
        mean_size: 0.0168,
        baseline_mean_size: 0.0072,
      },
    },
    {
      id: 1,
      symbol: "BTC/USD",
      name: "Bitcoin",
      ts: "2026-09-14T00:00:00Z",
      type: "regime_change",
      variant: "to calm",
      detail: { from: "normal", to: "calm", probability: 0.91 },
      record: {
        n: 17,
        verdict: "not enough occurrences",
        size_verdict: "not enough occurrences",
        share_positive: 0.53,
        baseline_share_positive: 0.5,
        mean_size: 0.02,
        baseline_mean_size: 0.02,
      },
    },
  ],
  portfolio: [{ kind: "drift", value: 0.22, against: 0.05, symbols: ["USD"] }],
};

const RECORDS = {
  type: "abnormal_move",
  tested: 24,
  in_feed: true,
  trust: { grade: "fair", reason: "Each kind of this signal rests on 30 to 58 past cases." },
  records: [
    {
      type: "abnormal_move",
      symbol: "SPY",
      name: "US stocks (S&P 500)",
      variant: "down",
      n: 58,
      first_day: "2018-01-24",
      last_day: "2026-09-28",
      computed_at: "2026-10-06T06:00:00Z",
      verdict: "no measurable edge",
      size_verdict: "followed by larger moves",
      horizons: [
        horizon("1 day", 1, "followed by larger moves"),
        horizon("1 week", 5, "followed by larger moves"),
      ],
    },
  ],
};

function page(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="signals/:type?" element={<SignalsPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SignalsPage", () => {
  beforeEach(() => {
    state.signals = SIGNALS;
    state.records = RECORDS;
  });
  afterEach(cleanup);

  it("lists what changed with what has followed each kind, and links to the record", () => {
    const { container } = page("/signals");
    const row = screen.getByRole("link", {
      name: /^US stocks \(S&P 500\): Abnormal move, down.*See its track record$/,
    });
    expect(row).toHaveAttribute("href", "/signals/abnormal_move");
    expect(within(row).getByText("US stocks · Abnormal move, down")).toBeVisible();
    expect(within(row).getByText(/−2\.1% in an hour, 6\.2× the usual size/)).toBeVisible();
    expect(within(row).getByText("No edge in direction")).toBeVisible();
    expect(within(row).getByText("Larger moves followed")).toBeVisible();
    expect(within(row).getByText("58 past cases")).toBeVisible();
    // A kind with too few cases says so once, and is not given a second verdict.
    const thin = screen.getByRole("link", { name: /^Bitcoin: Change of state, to calm/ });
    expect(within(thin).getAllByText("Too few cases to judge")).toHaveLength(1);
    expect(within(thin).getByText(/from normal, 91% probable/)).toBeVisible();
    // Where the portfolio stands against the target is shown apart, with no record.
    expect(
      screen.getByText("A holding has drifted more than 5 points from its target share."),
    ).toBeVisible();
    expect(container.textContent).toMatch(/it is not a forecast of direction/);
    expect(container.textContent).not.toMatch(/\b(buy|sell|you should)\b/i);
  });

  it("narrows the feed by market and by kind", () => {
    page("/signals");
    fireEvent.click(screen.getByRole("button", { name: "Bitcoin" }));
    expect(state.filter).toEqual({ symbol: "btc-usd", type: undefined });
    fireEvent.click(screen.getByRole("button", { name: "Abnormal move" }));
    expect(state.filter).toEqual({ symbol: "btc-usd", type: "abnormal_move" });
  });

  it("shows a track record against any day, with how far to trust it", () => {
    const { container } = page("/signals/abnormal_move");
    expect(screen.getByText("1 of 1 kinds were followed by something measurable")).toBeVisible();
    expect(screen.getByText("US stocks · down")).toBeVisible();
    expect(screen.getByText(/58 past cases, 24 Jan 2018 to 28 Sept? 2026/)).toBeVisible();
    expect(
      screen.getAllByRole("img", {
        name: /^Ended higher 54% of the time after the signal, plausibly between 42% and 66%; 55% on any day$/,
      }),
    ).toHaveLength(2);
    expect(screen.getAllByText("±1.68%")).toHaveLength(2);
    expect(screen.getAllByText("±0.72%")).toHaveLength(2);
    expect(container.textContent).toMatch(/Because 24 comparisons were looked at together/);
    expect(container.textContent).toMatch(/treat them as provisional/);
  });

  it("says why a signal that is scored is not shown in the feed", () => {
    state.records = { ...RECORDS, type: "sentiment_shock", in_feed: false, records: [] };
    page("/signals/sentiment_shock");
    expect(screen.getByText(/This one is not shown as a signal/)).toBeVisible();
    expect(screen.getByText("This signal has not fired in the stored history")).toBeVisible();
  });

  it("sends an unknown address back to the feed", () => {
    page("/signals/hot_tip");
    expect(screen.getByText("Latest signals")).toBeVisible();
  });
});

describe("signalDetail", () => {
  it("gives the one figure that says how large the signal was", () => {
    expect(signalDetail({ type: "abnormal_move", detail: { multiple: 5.04 } })).toBe(
      "5.0× the usual size",
    );
    expect(signalDetail({ type: "regime_change", detail: {} })).toBeUndefined();
  });
});

const BRIEF = {
  day: "2026-10-06",
  generated_at: "2026-10-06T10:00:00Z",
  items: [
    {
      symbol: "BTC/USD",
      name: "Bitcoin",
      sentences: [
        { text: "Bitcoin: the market is in a calm state.", section: "state" },
        { text: "No signals in the past 7 days.", section: "signals" },
      ],
    },
    {
      symbol: "PORTFOLIO",
      name: "Your portfolio",
      sentences: [{ text: "In 30 trading days it ends between two figures.", section: "outlook" }],
    },
  ],
} as unknown as Brief;

describe("BriefCard", () => {
  afterEach(cleanup);

  it("shows the brief with each sentence leading to the page behind it", () => {
    state.brief = BRIEF;
    render(
      <MemoryRouter>
        <BriefCard assets={ASSETS} />
      </MemoryRouter>,
    );
    expect(screen.getByText("Today in brief")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Bitcoin: the market is in a calm state." }),
    ).toHaveAttribute("href", "/asset/btc-usd/state");
    expect(screen.getByRole("link", { name: "No signals in the past 7 days." })).toHaveAttribute(
      "href",
      "/signals",
    );
    expect(
      screen.getByRole("link", { name: "In 30 trading days it ends between two figures." }),
    ).toHaveAttribute("href", "/portfolio/ahead");
    const [first] = BRIEF.items;
    expect(first && sentenceLink(first, "risk", ASSETS)).toBe("/asset/btc-usd/risk");
  });

  it("shows nothing before a brief has been written", () => {
    state.brief = null;
    const { container } = render(
      <MemoryRouter>
        <BriefCard assets={ASSETS} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
