import { Link, useLocation } from "react-router-dom";

export interface TabItem {
  /** Path under `base`; empty for the subject's own page. */
  path: string;
  label: string;
  /** What the page answers, in a few plain words. */
  hint?: string;
  /** Pages with the same group are listed together under it. */
  group?: string;
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
  const inside = items.some((item) => item.path !== "" && pathname === `${base}/${item.path}`);
  if (!inside && !up) return null;
  const to = inside ? base : (up?.to ?? base);
  const name = inside ? (parent ?? label.replace(/ pages$/, "")) : up?.label;
  return (
    <nav aria-label={label}>
      <Link to={to} className="back-link">
        <Chevron back />
        Back to {name}
      </Link>
    </nav>
  );
}

/** A subject's pages as a short list: what each one is called and what it answers. */
export function SectionMenu({
  base,
  items,
  title,
}: {
  base: string;
  items: readonly TabItem[];
  title?: string;
}) {
  const pages = items.filter((item) => item.path !== "");
  const groups: { name: string | undefined; pages: TabItem[] }[] = [];
  for (const page of pages) {
    const last = groups.at(-1);
    if (last && last.name === page.group) last.pages.push(page);
    else groups.push({ name: page.group, pages: [page] });
  }
  return (
    <nav aria-label={title ?? "More"} className="flex flex-col gap-5">
      {groups.map((group) => (
        <div key={group.name ?? "all"}>
          {(group.name ?? title) && <p className="label mb-2 px-1">{group.name ?? title}</p>}
          <ul className="grid grid-cols-1 gap-2 @3xl:grid-cols-2">
            {group.pages.map((page) => (
              <li key={page.path}>
                <Link to={`${base}/${page.path}`} className="menu-row">
                  <span className="min-w-0">
                    <span className="block font-medium">{page.label}</span>
                    {page.hint && (
                      <span className="mt-0.5 block text-sm text-muted">{page.hint}</span>
                    )}
                  </span>
                  <Chevron />
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
