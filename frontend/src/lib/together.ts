import type { Pair, Spillover, WeekendGap } from "../api/client";

export const TOGETHER_SECTIONS = [
  { path: "", label: "Summary" },
  { path: "pairs", label: "Two markets compared", hint: "Any two markets side by side" },
  { path: "grid", label: "All markets compared", hint: "Every market against every other" },
  { path: "spillovers", label: "Knock-on effects", hint: "Does trouble in one spread to another" },
  { path: "weekends", label: "Weekend effect", hint: "What Bitcoin's weekend means for Monday" },
] as const;

export type TogetherSection = (typeof TOGETHER_SECTIONS)[number]["path"];

export function isTogetherSection(value: string | undefined): value is TogetherSection {
  return TOGETHER_SECTIONS.some((section) => section.path === (value ?? ""));
}

/** How closely two markets have moved together, in words. */
export function linkWords(correlation: number): string {
  const size = Math.abs(correlation);
  if (size < 0.15) return "have moved almost independently";
  const strength = size < 0.4 ? "loosely" : size < 0.7 ? "fairly closely" : "closely";
  return correlation > 0
    ? `have moved ${strength} together`
    : `have moved ${strength} in opposite directions`;
}

export const pairKey = (pair: Pick<Pair, "a" | "b">) => `${pair.a}|${pair.b}`;

/** The one row per pair to quote: five sessions after, the middle horizon. */
export function headlineSpillovers(rows: Spillover[], steps = 5): Spillover[] {
  return rows.filter((row) => row.steps === steps);
}

const possessive = (name: string) => (name.endsWith("s") ? `${name}'` : `${name}'s`);

export function spillSentence(row: Spillover, name: (symbol: string) => string): string {
  const source = name(row.source);
  const target = name(row.target);
  if (row.verdict === "not enough episodes" || row.ratio == null) {
    return `${source} has turned turbulent only ${row.episodes} times, too few to say what follows for ${target}.`;
  }
  if (row.verdict === "spills over") {
    return `After ${source} turned turbulent, ${possessive(target)} daily swings were ${row.ratio.toFixed(1)} times their usual size over the next ${row.steps} sessions.`;
  }
  return `After ${source} turned turbulent, ${possessive(target)} swings were not measurably different from usual.`;
}

export function weekendSentence(row: WeekendGap, name: (symbol: string) => string): string {
  const market = name(row.symbol);
  if (row.verdict === "not enough weekends" || row.slope == null) {
    return `There are too few weekends to say how ${market} opens after Bitcoin moves.`;
  }
  if (row.verdict === "no measurable link") {
    return `${possessive(market)} Monday open has had no measurable link to Bitcoin's weekend move.`;
  }
  const share = Math.abs(row.slope * 100).toFixed(0);
  return row.verdict === "moves with"
    ? `${market} has tended to open in the same direction as Bitcoin's weekend move, by about ${share}% of its size.`
    : `${market} has tended to open against Bitcoin's weekend move, by about ${share}% of its size.`;
}

/** A line path through values in [-1, 1] across a box; gaps where a value is missing. */
export function correlationPath(
  values: (number | null | undefined)[],
  width: number,
  height: number,
): string {
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  let path = "";
  let drawing = false;
  values.forEach((value, i) => {
    if (value == null) {
      drawing = false;
      return;
    }
    const y = ((1 - value) / 2) * height;
    path += `${drawing ? "L" : "M"}${(i * step).toFixed(1)},${y.toFixed(1)} `;
    drawing = true;
  });
  return path.trim();
}
