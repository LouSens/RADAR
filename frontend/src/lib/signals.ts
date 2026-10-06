import type { Signal } from "../api/client";

export const SIGNAL_PAGES = [
  { path: "", label: "Latest" },
  {
    path: "regime_change",
    label: "Change of state",
    hint: "What followed a change of market state",
  },
  {
    path: "abnormal_move",
    label: "Abnormal move",
    hint: "What followed an unusually large hourly move",
  },
  { path: "sentiment_shock", label: "Unusual news tone", hint: "Tested, and why it is not shown" },
] as const;

export type SignalType = Exclude<(typeof SIGNAL_PAGES)[number]["path"], "">;

export function isSignalType(value: string | undefined): value is SignalType {
  return SIGNAL_PAGES.some((page) => page.path !== "" && page.path === value);
}

export const TYPE_NAME: Record<SignalType, string> = {
  regime_change: "Change of state",
  abnormal_move: "Abnormal move",
  sentiment_shock: "Unusual news tone",
};

const VARIANT_NAME: Record<string, string> = {
  "to calm": "to calm",
  "to normal": "to normal",
  "to turbulent": "to turbulent",
  up: "up",
  down: "down",
  positive: "positive",
  negative: "negative",
};

/** "Change of state, to calm" or "Abnormal move, down". */
export function kindName(type: SignalType, variant: string): string {
  return `${TYPE_NAME[type]}, ${VARIANT_NAME[variant] ?? variant}`;
}

/** The one figure that says how large the signal was. */
export function signalDetail(signal: Pick<Signal, "type" | "detail">): string | undefined {
  const detail = signal.detail as Record<string, unknown>;
  if (signal.type === "abnormal_move" && typeof detail.multiple === "number") {
    const move = typeof detail.move === "number" ? Math.expm1(detail.move) * 100 : undefined;
    const size =
      move === undefined ? "" : `${move > 0 ? "+" : "−"}${Math.abs(move).toFixed(1)}% in an hour, `;
    return `${size}${detail.multiple.toFixed(1)}× the usual size`;
  }
  if (signal.type === "regime_change" && typeof detail.probability === "number") {
    const from = typeof detail.from === "string" ? `from ${detail.from}, ` : "";
    return `${from}${Math.round(detail.probability * 100)}% probable`;
  }
  return undefined;
}

export const DIRECTION_WORDS: Record<string, string> = {
  "followed by rises more often": "Rises followed more often",
  "followed by falls more often": "Falls followed more often",
  "no measurable edge": "No edge in direction",
  "not enough occurrences": "Too few cases to judge",
};

export const SIZE_WORDS: Record<string, string> = {
  "followed by larger moves": "Larger moves followed",
  "followed by smaller moves": "Smaller moves followed",
  "no measurable difference": "Moves of the usual size followed",
  "not enough occurrences": "Too few cases to judge",
};

/** True for a verdict that says the signal has carried information. */
export const isFinding = (verdict: string) =>
  verdict.startsWith("followed by") && verdict !== "not enough occurrences";
