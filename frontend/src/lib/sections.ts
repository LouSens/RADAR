/** The pages of one market, in the order they are shown. The first has no path of its own. */
export const SECTIONS = [
  { path: "", label: "Summary" },
  { path: "state", label: "Market state" },
  { path: "outlook", label: "Outlook" },
  { path: "swings", label: "Expected swings" },
  { path: "risk", label: "Downside risk" },
  { path: "news", label: "News" },
  { path: "record", label: "Live record" },
] as const;

export type SectionPath = (typeof SECTIONS)[number]["path"];

export function isSection(value: string | undefined): value is SectionPath {
  return SECTIONS.some((section) => section.path === (value ?? ""));
}
