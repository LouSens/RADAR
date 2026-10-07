/** The pages of one market. The first, with no path, is the market's own page. */
export const SECTIONS = [
  { path: "", label: "Summary" },
  { path: "state", label: "Current state", hint: "Calm, normal or turbulent right now" },
  {
    path: "outlook",
    label: "Price range ahead",
    hint: "Where the price might be in days or weeks",
  },
  { path: "swings", label: "Daily movement", hint: "How much it is expected to move each day" },
  { path: "risk", label: "Possible loss", hint: "How bad a bad day or week could be" },
  { path: "news", label: "News", hint: "Recent headlines and their tone" },
] as const;

export type SectionPath = (typeof SECTIONS)[number]["path"];

export function isSection(value: string | undefined): value is SectionPath {
  return SECTIONS.some((section) => section.path === (value ?? ""));
}
