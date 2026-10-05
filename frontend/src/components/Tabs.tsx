import { useEffect, useRef } from "react";
import { NavLink, useLocation } from "react-router-dom";

export interface TabItem {
  /** Path under `base`; empty for the first page. */
  path: string;
  label: string;
}

/**
 * The pages of one subject as a row of tabs. Each tab is a real address. On a narrow
 * screen the row scrolls sideways and keeps the chosen tab in view.
 */
export function Tabs({
  base,
  items,
  label,
}: {
  base: string;
  items: readonly TabItem[];
  label: string;
}) {
  const row = useRef<HTMLElement>(null);
  const { pathname } = useLocation();

  useEffect(() => {
    const chosen = row.current?.querySelector<HTMLElement>('[aria-current="page"]');
    if (!row.current || !chosen || typeof row.current.scrollTo !== "function") return;
    row.current.scrollTo({
      left: chosen.offsetLeft - (row.current.clientWidth - chosen.offsetWidth) / 2,
      behavior: "smooth",
    });
  }, [pathname]);

  return (
    <nav ref={row} aria-label={label} className="tabs">
      {items.map((item) => (
        <NavLink
          key={item.path}
          to={item.path ? `${base}/${item.path}` : base}
          end
          className={({ isActive }) => `tab-link ${isActive ? "lens text-ink" : "text-muted"}`}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}
