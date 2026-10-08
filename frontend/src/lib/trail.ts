import { useLocation, useNavigationType } from "react-router-dom";

/**
 * The pages visited inside the app since it was opened, oldest first, so that "Back" can
 * tell where the browser's own back would land. The browser does not say.
 */
const trail: { key: string; path: string }[] = [];

/** Notes a page once, however many times it is drawn. */
function note(key: string, path: string, type: "POP" | "PUSH" | "REPLACE"): void {
  const last = trail.at(-1);
  if (last?.key === key) return;
  const known = trail.findIndex((entry) => entry.key === key);
  if (type === "POP" && known >= 0) {
    // The browser went back (or forward) to a page already on the trail.
    trail.length = known + 1;
  } else if (type === "REPLACE" && last) {
    trail[trail.length - 1] = { key, path };
  } else {
    trail.push({ key, path });
  }
}

/**
 * Notes the page being shown and returns the address of the page before it, if there is
 * one. Safe to call from several components on one page.
 */
export function useTrail(): string | undefined {
  const { key, pathname } = useLocation();
  note(key, pathname, useNavigationType());
  return trail.at(-2)?.path;
}

/** For tests: forget every page. */
export function forgetTrail(): void {
  trail.length = 0;
}
