/** The pages of one market, in the order they are shown. The first has no path of its own. */
export const SECTIONS = [
  { path: "", label: "Summary" },
  { path: "state", label: "Current state" },
  { path: "outlook", label: "Price range ahead" },
  { path: "swings", label: "Daily movement" },
  { path: "risk", label: "Possible loss" },
  { path: "drivers", label: "What it moves with" },
  { path: "news", label: "News" },
  { path: "record", label: "Forecast accuracy" },
] as const;

export type SectionPath = (typeof SECTIONS)[number]["path"];

export function isSection(value: string | undefined): value is SectionPath {
  return SECTIONS.some((section) => section.path === (value ?? ""));
}
