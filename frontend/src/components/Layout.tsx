import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";

import { useStreamStatus } from "../api/live";
import { useAssets, useHealth } from "../api/queries";
import { assetColorVar } from "./ui";

function RadarMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle
        cx="12"
        cy="12"
        r="10"
        stroke="var(--accent)"
        strokeOpacity="0.35"
        strokeWidth="1.2"
      />
      <circle cx="12" cy="12" r="6" stroke="var(--accent)" strokeOpacity="0.6" strokeWidth="1.2" />
      <path d="M12 12 19 5" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="12" cy="12" r="1.8" fill="var(--accent)" />
    </svg>
  );
}

const icon = {
  home: <path d="M4 11.5 12 5l8 6.5V19a1 1 0 0 1-1 1h-4.5v-5h-5v5H5a1 1 0 0 1-1-1v-7.5Z" />,
  system: (
    <>
      <path d="M3 12h4l2.5-6 4 12 2.5-6h5" />
    </>
  ),
  together: (
    <>
      <circle cx="9" cy="12" r="5.5" />
      <circle cx="15" cy="12" r="5.5" />
    </>
  ),
  calendar: (
    <>
      <rect x="4" y="5.5" width="16" height="14" rx="2.5" />
      <path d="M4 10h16M8.5 3.5v4M15.5 3.5v4" />
    </>
  ),
  signals: (
    <>
      <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15l1.5-2Z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </>
  ),
  portfolio: (
    <>
      <path d="M12 3.5a8.5 8.5 0 1 0 8.5 8.5H12V3.5Z" />
      <path d="M15.5 3.6a8.5 8.5 0 0 1 4.9 4.9h-4.9V3.6Z" />
    </>
  ),
};

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

/** Whether everything behind the app is fine: stored data and the live feed. */
function useSystemGood(): boolean {
  const stream = useStreamStatus();
  const health = useHealth().data?.status;
  return stream === "open" && health === "ok";
}

/**
 * The System icon with one quiet dot. Green when all is fine; otherwise red, and the
 * System page says why.
 */
function SystemIcon({ good }: { good: boolean }) {
  return (
    <span className="relative grid w-[22px] shrink-0 place-items-center">
      <Icon>{icon.system}</Icon>
      <span
        className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ring-2 ring-[#12131a] ${
          good ? "bg-calm" : "bg-alert"
        }`}
      />
    </span>
  );
}

/** The five places in RADAR. Everything else is reached from one of them. */
const PLACES = [
  { to: "/", label: "Home", icon: "home", under: [] },
  { to: "/markets", label: "Markets", icon: "together", under: ["/asset"] },
  { to: "/portfolio", label: "Portfolio", icon: "portfolio", under: [] },
  { to: "/signals", label: "Signals", icon: "signals", under: [] },
  { to: "/calendar", label: "Calendar", icon: "calendar", under: [] },
] as const;

/** Whether an address belongs to a place: the place itself or a page under it. */
function isAt(place: (typeof PLACES)[number], pathname: string): boolean {
  if (place.to === "/") return pathname === "/";
  return [place.to, ...place.under].some(
    (root) => pathname === root || pathname.startsWith(`${root}/`),
  );
}

const WIDE = "(min-width: 1024px)";

/** True when there is room for the full sidebar; narrower screens get the icon rail. */
function useWide(): boolean {
  const [wide, setWide] = useState(
    () => typeof window.matchMedia !== "function" || window.matchMedia(WIDE).matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(WIDE);
    const update = () => setWide(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  return wide;
}

const COLLAPSED_KEY = "radar.sidebar.collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

const sideLink = ({ isActive }: { isActive: boolean }) =>
  `flex h-10 items-center gap-3 rounded-xl px-2.5 text-sm font-medium transition-colors duration-200 ${
    isActive ? "lens text-ink" : "text-muted hover:bg-white/5 hover:text-ink"
  }`;

function Sidebar({
  collapsed,
  canToggle,
  onToggle,
}: {
  collapsed: boolean;
  canToggle: boolean;
  onToggle: () => void;
}) {
  const good = useSystemGood();
  const { pathname } = useLocation();
  const hidden = collapsed ? "sr-only" : "truncate";
  return (
    <aside
      className={`capsule fixed inset-y-3 left-3 z-40 hidden flex-col rounded-3xl p-3 transition-[width] duration-300 md:flex ${
        collapsed ? "w-[68px]" : "w-[232px]"
      }`}
    >
      <div className="flex h-11 items-center justify-between gap-2 pl-2">
        <Link to="/" className="flex min-w-0 items-center gap-2.5" aria-label="RADAR home">
          <RadarMark />
          <span className={`text-[15px] font-bold tracking-[0.14em] ${hidden}`}>RADAR</span>
        </Link>
        {!collapsed && canToggle && <CollapseButton collapsed={collapsed} onToggle={onToggle} />}
      </div>

      <nav aria-label="Main" className="mt-4 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {PLACES.map((place) => (
          <Link
            key={place.to}
            to={place.to}
            aria-current={isAt(place, pathname) ? "page" : undefined}
            className={sideLink({ isActive: isAt(place, pathname) })}
            title={place.label}
          >
            <span className="grid w-[22px] shrink-0 place-items-center">
              <Icon>{icon[place.icon]}</Icon>
            </span>
            <span className={hidden}>{place.label}</span>
          </Link>
        ))}
      </nav>

      <div className="mt-2 flex flex-col gap-1 border-t border-line pt-2">
        {/* Only when something is wrong: otherwise it is of no use to the person using it. */}
        {!good && (
          <NavLink to="/system" className={sideLink} title="Something needs attention">
            <SystemIcon good={good} />
            <span className={hidden}>Needs attention</span>
          </NavLink>
        )}
        {collapsed && canToggle && <CollapseButton collapsed={collapsed} onToggle={onToggle} />}
      </div>
    </aside>
  );
}

function CollapseButton({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-label={collapsed ? "Expand the sidebar" : "Collapse the sidebar"}
      aria-expanded={!collapsed}
      className="grid h-10 w-10 shrink-0 place-items-center self-center rounded-xl text-muted transition-colors hover:bg-white/8 hover:text-ink"
    >
      <Icon>
        <rect x="3.5" y="4.5" width="17" height="15" rx="3" />
        <path d="M9.5 4.5v15" />
        <path d={collapsed ? "m13.5 10 2 2-2 2" : "m15.5 10-2 2 2 2"} />
      </Icon>
    </button>
  );
}

export function Layout() {
  const { pathname } = useLocation();
  const [preferCollapsed, setCollapsed] = useState(readCollapsed);

  // The light behind the page takes the colour of the market being looked at. It is
  // set on the document, so it fills the whole window and is never clipped.
  const assets = useAssets().data;
  useEffect(() => {
    const slug = pathname.match(/^\/asset\/([^/]+)/)?.[1];
    const asset = assets?.find((a) => a.slug === slug);
    document.documentElement.style.setProperty(
      "--tint",
      `var(${asset ? assetColorVar(asset) : "--accent"})`,
    );
  }, [pathname, assets]);

  // A new page starts at its top, like any other.
  useEffect(() => {
    if (typeof window.scrollTo === "function") window.scrollTo(0, 0);
  }, [pathname]);

  const wide = useWide();
  const good = useSystemGood();
  // Between a phone and a full desktop there is only room for the icon rail.
  const collapsed = preferCollapsed || !wide;

  function toggle() {
    setCollapsed((was) => {
      try {
        window.localStorage.setItem(COLLAPSED_KEY, was ? "0" : "1");
      } catch {
        // The choice just will not be remembered.
      }
      return !was;
    });
  }

  return (
    <div className="flex min-h-screen flex-col">
      <Sidebar collapsed={collapsed} canToggle={wide} onToggle={toggle} />

      {/* Phones navigate with the tabs at the bottom, within thumb reach; nothing on top. */}
      <div
        className={`flex min-w-0 flex-1 flex-col transition-[padding] duration-300 ${
          collapsed ? "md:pl-[80px]" : "md:pl-[244px]"
        }`}
      >
        <main className="page pb-tabbar @container mx-auto w-full max-w-[1280px] flex-1">
          {/* Each page eases in; the key restarts it when the address changes. */}
          <div key={pathname} className="page-in">
            <Outlet />
          </div>
          {!good && (
            <Link
              to="/system"
              className="mt-12 inline-flex items-center gap-2 text-xs text-muted hover:text-ink md:hidden"
            >
              <span className="h-2 w-2 rounded-full bg-alert" aria-hidden="true" />
              Something needs attention
            </Link>
          )}
          <p className="mt-4 prose text-xs leading-relaxed text-faint md:mt-12">
            For information only. Not financial advice; RADAR places no trades.
          </p>
        </main>
      </div>

      <nav
        aria-label="Main, phone"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom,0px))] md:hidden"
      >
        <div className="capsule capsule-solid pointer-events-auto mx-auto flex max-w-md gap-1 rounded-full p-1.5">
          {PLACES.map((place) => {
            const here = isAt(place, pathname);
            return (
              <Link
                key={place.to}
                to={place.to}
                aria-label={place.label}
                aria-current={here ? "page" : undefined}
                className="bar-tab"
              >
                <Icon>{icon[place.icon]}</Icon>
                {/* Always there, so it can open and close smoothly; hidden from
                    assistive technology, which reads the link's own name. */}
                <span className="bar-tab-label" aria-hidden="true">
                  {place.label}
                </span>
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}
