import type { Position, StressResult, Xray } from "../api/client";

const RISK = "Understand your risk";
const TRY = "Try things";

export const PORTFOLIO_SECTIONS = [
  { path: "", label: "Summary" },
  { path: "todo", label: "What to do now", hint: "Where spare cash goes, and at what prices" },
  { path: "holdings", label: "Holdings", hint: "See, change or re-read what you hold" },
  { path: "record", label: "Your trades so far", hint: "What you made or lost, coin by coin" },
  {
    path: "sources",
    label: "Risk by holding",
    hint: "Which holding carries the risk",
    group: RISK,
  },
  { path: "limits", label: "Possible loss", hint: "How much a bad day could cost", group: RISK },
  {
    path: "ahead",
    label: "Value range ahead",
    hint: "Where its value might be in 1 to 3 months",
    group: RISK,
  },
  {
    path: "episodes",
    label: "Past crashes",
    hint: "How it would have fared in past crashes",
    group: RISK,
  },
  { path: "try", label: "Try a mix", hint: "Change the shares and see the risk", group: TRY },
  {
    path: "buying",
    label: "Regular buying",
    hint: "Simulate buying a fixed amount on a schedule",
    group: TRY,
  },
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
