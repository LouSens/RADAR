import type { ReactNode } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { useTrail } from "../lib/trail";

export interface TabItem {
  /** Path under `base`; empty for the subject's own page. */
  path: string;
  label: string;
  /** What the page answers, in a few plain words. */
  hint?: string;
  /** Pages with the same group are listed together under it. */
  group?: string;
  /** Left out of the menu: reached from inside another page. */
  hidden?: boolean;
}

function Chevron({ back = false }: { back?: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className="shrink-0"
    >
      <path d={back ? "m15 5-7 7 7 7" : "m9 5 7 7-7 7"} />
    </svg>
  );
}

/**
 * The way back from a page inside a subject to the subject itself. On the subject's own
 * page there is nothing to go back to, so it shows nothing. There is no strip of tabs:
 * a subject lists its pages once, in `SectionMenu`.
 */
export function Tabs({
  base,
  items,
  label,
  parent,
  up,
}: {
  base: string;
  items: readonly TabItem[];
  label: string;
  /** The name on the way back; by default the label without " pages". */
  parent?: string;
  /** Where the subject itself sits, when it is reached from another page. */
  up?: { to: string; label: string };
}) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const before = useTrail();
  const inside = items.some((item) => item.path !== "" && pathname === `${base}/${item.path}`);
  if (!inside && !up) return null;
  const to = inside ? base : (up?.to ?? base);
  const name = inside ? (parent ?? label.replace(/ pages$/, "")) : up?.label;
  // Arrived by a link inside the app: go back to exactly that page, wherever it was. A
  // page opened directly (a bookmark, a reload) has nowhere to go back to, so it goes up.
  // So does a page reached by coming up from one of its own inner pages: the browser's
  // back would lead down into that inner page again, which is not "back" from here.
  const cameFromInside = before !== undefined && !before.startsWith(`${pathname}/`);
  return (
    <nav aria-label={label}>
      <Link
        to={to}
        className="back-link"
        onClick={(event) => {
          if (!cameFromInside) return;
          event.preventDefault();
          void navigate(-1);
        }}
      >
        <Chevron back />
        {cameFromInside ? "Back" : `Back to ${name}`}
      </Link>
    </nav>
  );
}

/** A subject's pages as a short list: what each one is called and what it answers. */
const DOOR_ICONS: Record<string, ReactNode> = {
  todo: (
    <>
      <path d="M9 6h11M9 12h11M9 18h11" />
      <path d="m3.5 6 1.3 1.3L7 5M3.5 12l1.3 1.3L7 11M3.5 18l1.3 1.3L7 17" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3" />
    </>
  ),
  try: (
    <>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="8" cy="17" r="2" />
    </>
  ),
  record: (
    <>
      <path d="M4 12a8 8 0 1 0 2.6-5.9" />
      <path d="M4 5v4h4M12 8v4.5l3 1.8" />
    </>
  ),
  holdings: (
    <>
      <rect x="3.5" y="6" width="17" height="13" rx="2.5" />
      <path d="M3.5 10h17M16 14.5h1.5" />
    </>
  ),
  risk: <path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.4 7 9 4.1-1.6 7-4.8 7-9V6l-7-2.5Z" />,
  state: <path d="M3 12h4l2.5-6 4 12 2.5-6h5" />,
  outlook: (
    <>
      <path d="M3.5 12h5" />
      <path d="M8.5 12 20.5 5.5M8.5 12l12 6.5" />
    </>
  ),
  swings: <path d="M3 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0" />,
  news: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M8 9h8M8 12.5h8M8 16h5" />
    </>
  ),
};
const DOOR_FALLBACK = <path d="M5 12h14M13 6l6 6-6 6" />;

/**
 * The pages of a subject as a small grid of tiles: an icon, a name, and what it answers.
 * Pages marked `hidden` are left out; they are reached from inside another page.
 */
export function SectionMenu({
  base,
  items,
  title,
}: {
  base: string;
  items: readonly TabItem[];
  title?: string;
}) {
  const pages = items.filter((item) => item.path !== "" && !item.hidden);
  return (
    <nav aria-label={title ?? "More"}>
      {title && <p className="label mb-2 px-1">{title}</p>}
      <ul className="grid grid-cols-2 gap-2.5 @3xl:grid-cols-3 @xl:gap-4">
        {pages.map((page) => (
          <li key={page.path}>
            <Link to={`${base}/${page.path}`} className="door h-full">
              <span className="door-icon">
                <svg
                  width="19"
                  height="19"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.7"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  {DOOR_ICONS[page.path] ?? DOOR_FALLBACK}
                </svg>
              </span>
              <span className="min-w-0">
                <span className="block font-semibold tracking-tight">{page.label}</span>
                {page.hint && (
                  <span className="mt-0.5 block text-[13px] leading-snug text-muted">
                    {page.hint}
                  </span>
                )}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}
