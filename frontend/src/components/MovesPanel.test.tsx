import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Asset, Moves } from "../api/client";
import { MovesPanel, headline, rankWords } from "./MovesPanel";

const query = vi.hoisted(() => ({ value: {} as unknown }));
vi.mock("../api/queries", () => ({ useMoves: () => query.value }));

const ASSET: Asset = {
  symbol: "ETH/USD",
  slug: "eth-usd",
  name: "Ethereum",
  asset_class: "crypto",
  is_primary: false,
  history_start: "2021-01-01",
  news_start: null,
  trades_continuously: true,
};

const DAY: Moves["days"][number] = {
  day: "2026-10-07",
  move: -0.0461,
  market: -0.032,
  own: -0.0141,
  sensitivity: 1.2,
  times_usual: 2.2,
  rank: 0.97,
  events: ["Fed decision"],
  state_from: null,
  state_to: null,
  headlines: [
    {
      headline: "Ether slides with the market",
      source: "example",
      url: null,
      created_at: "2026-10-07T09:00:00Z",
    },
  ],
};

const SPLIT: Moves = {
  symbol: "ETH/USD",
  reference: "BTC/USD",
  reference_name: "Bitcoin",
  evidence: null,
  split_shown: true,
  days: [DAY],
  trust: { grade: "solid", reason: "On 1,985 unseen days the wider market accounted for 70%." },
};

describe("why it moved", () => {
  afterEach(cleanup);

  it("shows the two parts of a day when the link to the wider market holds up", () => {
    query.value = { data: SPLIT, isPending: false };
    render(<MovesPanel asset={ASSET} />);
    // Once on the day's row and once in the note saying what it means.
    expect(screen.getAllByText("With Bitcoin")).toHaveLength(2);
    expect(screen.getAllByText("Its own")).toHaveLength(2);
    // The two parts are the ones that sum to the move.
    expect(screen.getByText("−3.20%")).toBeInTheDocument();
    expect(screen.getByText("−1.41%")).toBeInTheDocument();
    expect(screen.getByText("2.2× a usual day")).toBeInTheDocument();
    expect(screen.getByText("Larger than 97 of 100 days before it")).toBeInTheDocument();
    // An event is something that fell on the day, never given as the cause.
    expect(screen.getByText("Fed decision that day")).toBeInTheDocument();
    expect(screen.getByText("1 headline that day")).toBeInTheDocument();
    expect(screen.getByText("Solid")).toBeInTheDocument();
  });

  it("shows no parts when the link did not clear its bar", () => {
    query.value = {
      data: {
        ...SPLIT,
        split_shown: false,
        days: [{ ...DAY, market: null, own: null, sensitivity: null }],
        trust: { grade: "fair", reason: "No split is shown: only 121 days to judge it on." },
      } satisfies Moves,
      isPending: false,
    };
    render(<MovesPanel asset={ASSET} />);
    expect(screen.queryByText("With Bitcoin")).not.toBeInTheDocument();
    expect(screen.queryByText("Its own")).not.toBeInTheDocument();
    expect(screen.getByText("Fair")).toBeInTheDocument();
    expect(screen.getByText("2.2× a usual day")).toBeInTheDocument();
  });

  it("says so when there are no days yet", () => {
    query.value = { data: null, isPending: false };
    render(<MovesPanel asset={ASSET} />);
    expect(screen.getByText(/not enough days of prices/)).toBeInTheDocument();
  });

  it("words the newest day in one line", () => {
    expect(headline(DAY, "Bitcoin")).toMatch(
      /^Down 4\.61% on .*: −3\.20% with Bitcoin, −1\.41% its own$/,
    );
    expect(headline({ ...DAY, market: null, own: null }, null)).toMatch(
      /^Down 4\.61% on .*: larger than 97 of 100 days before it$/,
    );
    expect(rankWords(0.5)).toBe("Larger than 50 of 100 days before it");
  });
});
