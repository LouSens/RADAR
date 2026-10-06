import type { PortfolioAnalysis, PortfolioPlan } from "../api/client";

export type LevelName = "low" | "moderate" | "high";
export type MixName = "current" | "equal" | "min_variance" | "equal_risk" | "hierarchical";
type LevelPlan = PortfolioPlan["levels"][number];
type Signal = PortfolioPlan["signals"][number];

export const LEVEL_WORDS: Record<LevelName, string> = {
  low: "low",
  moderate: "moderate",
  high: "high",
};

export const MIX_NAMES: Record<MixName, string> = {
  current: "As it is now",
  equal: "Equal shares",
  min_variance: "Smallest movement",
  equal_risk: "Equal risk each",
  hierarchical: "Grouped by behaviour",
};

/** The level the mix's movement falls in right now, using current conditions when known. */
export function levelNow(plan: PortfolioPlan): string {
  const ratio = plan.now_ratio ?? plan.ratio;
  return ratio < 0.5 ? "low" : ratio < 1 ? "moderate" : ratio < 2 ? "high" : "very high";
}

/**
 * Each holding's share of the whole at one level: today's proportions among the holdings
 * (or the target split's, when that level is the target), with the level's cash share.
 */
export function levelMix(
  analysis: PortfolioAnalysis,
  plan: PortfolioPlan,
  level: LevelPlan,
): Record<string, number> {
  const mix: Record<string, number> = { USD: level.cash_share };
  if (plan.target && plan.moves.length > 0) {
    // The split in use is the target's: read its proportions from the gaps to target.
    const invested = plan.moves
      .filter((m) => m.symbol !== "USD")
      .reduce((sum, m) => sum + m.target_weight, 0);
    for (const move of plan.moves) {
      if (move.symbol !== "USD" && invested > 0) {
        mix[move.symbol] = (move.target_weight / invested) * (1 - level.cash_share);
      }
    }
    return mix;
  }
  const risky = analysis.xray.holdings.filter((h) => h.symbol !== "USD");
  const total = risky.reduce((sum, h) => sum + h.weight, 0);
  for (const holding of risky) {
    mix[holding.symbol] = total > 0 ? (holding.weight / total) * (1 - level.cash_share) : 0;
  }
  return mix;
}

/** Today's one-day loss limit, as a share of the covered value. */
export function dayLimit(analysis: PortfolioAnalysis): number | undefined {
  const day = analysis.limits.find((h) => h.horizon_days === 1);
  return day?.levels.find((l) => l.level === 0.95)?.methods.find((m) => m.method === day.shown)
    ?.var;
}

/** One signal in a plain sentence. It states the gap; it does not say what to do. */
export function signalText(signal: Signal, name: (symbol: string) => string): string {
  const names = signal.symbols.map(name).join(", ");
  switch (signal.kind) {
    case "risk_above_target":
      return `The mix is moving ${signal.value.toFixed(2)}× as much as US stocks, above your target's upper edge of ${signal.against.toFixed(2)}×.`;
    case "risk_below_target":
      return `The mix is moving ${signal.value.toFixed(2)}× as much as US stocks, below your target's lower edge of ${signal.against.toFixed(2)}×.`;
    case "drift":
      return `${names} ${signal.symbols.length === 1 ? "is" : "are"} more than ${(signal.against * 100).toFixed(0)} points from target; the widest gap is ${(signal.value * 100).toFixed(0)} points.`;
    default:
      return `${(signal.value * 100).toFixed(0)}% of your money is in a market that is turbulent right now (${names}).`;
  }
}
