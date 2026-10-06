import type { Position, StressResult, Xray } from "../api/client";

export const PORTFOLIO_SECTIONS = [
  { path: "", label: "Summary" },
  { path: "holdings", label: "Holdings" },
  { path: "try", label: "Try a mix" },
  { path: "mixes", label: "Compare mixes" },
  { path: "sources", label: "Risk by holding" },
  { path: "limits", label: "Possible loss" },
  { path: "forces", label: "What it moves with" },
  { path: "episodes", label: "Past crashes" },
] as const;

export type PortfolioSection = (typeof PORTFOLIO_SECTIONS)[number]["path"];

export function isPortfolioSection(value: string | undefined): value is PortfolioSection {
  return PORTFOLIO_SECTIONS.some((section) => section.path === (value ?? ""));
}

export interface Imbalance {
  symbol: string;
  name: string;
  weight: number;
  riskShare: number;
}

/** The holding whose share of the risk most exceeds its share of the money. */
export function largestImbalance(positions: Position[], xray: Xray): Imbalance | undefined {
  let found: Imbalance | undefined;
  for (const holding of xray.holdings) {
    const position = positions.find((p) => p.symbol === holding.symbol);
    if (!position) continue;
    const gap = holding.risk_share - holding.weight;
    if (!found || gap > found.riskShare - found.weight) {
      found = {
        symbol: holding.symbol,
        name: position.name,
        weight: holding.weight,
        riskShare: holding.risk_share,
      };
    }
  }
  return found;
}

/**
 * The episode to quote in the summary: the largest loss among episodes replayed with
 * every holding, or, when there is none, among those replayed with some.
 */
export function worstEpisode(episodes: StressResult[]): StressResult | undefined {
  const replayed = episodes.filter((e) => e.available && e.change != null);
  const complete = replayed.filter((e) => e.missing.length === 0);
  const pool = complete.length > 0 ? complete : replayed;
  return pool.reduce<StressResult | undefined>(
    (worst, e) => (!worst || (e.change ?? 0) < (worst.change ?? 0) ? e : worst),
    undefined,
  );
}

/** Parse a typed quantity. Returns undefined unless it is a number above zero. */
export function parseQuantity(text: string): number | undefined {
  const value = Number(text.replace(/,/g, "").trim());
  return text.trim() !== "" && Number.isFinite(value) && value > 0 ? value : undefined;
}
