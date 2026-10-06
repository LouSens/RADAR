import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import type { Asset } from "../api/client";
import { useStreamStatus } from "../api/live";
import { useAssets, useHealth } from "../api/queries";
import { assetColorVar, shortName } from "./ui";

function RadarMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="10" stroke="var(--accent)" strokeOpacity="0.35" strokeWidth="1.2" />
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

/** A coloured ring carrying the asset's initial: the asset's mark in navigation. */
function AssetGlyph({ asset, size = 22 }: { asset: Asset; size?: number }) {
  return (
    <span
      className="grid place-items-center rounded-full border text-[10px] font-bold leading-none"
      style={{
        width: size,
        height: size,
        borderColor: `var(${assetColorVar(asset)})`,
        color: `var(${assetColorVar(asset)})`,
      }}
      aria-hidden="true"
    >
      {shortName(asset).charAt(0)}
    </span>
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

const tab = ({ isActive }: { isActive: boolean }) =>
  `flex min-w-0 flex-1 flex-col items-center gap-1 rounded-[20px] py-2 text-[10.5px] font-medium transition-all duration-300 ${
    isActive ? "lens text-ink" : "text-muted"
  }`;

function Sidebar({
  primary,
  collapsed,
  canToggle,
  onToggle,
}: {
  primary: Asset[];
  collapsed: boolean;
  canToggle: boolean;
  onToggle: () => void;
}) {
  const good = useSystemGood();
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
        {!collapsed && canToggle && (
          <CollapseButton collapsed={collapsed} onToggle={onToggle} />
        )}
      </div>

      <nav aria-label="Main" className="mt-4 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        <NavLink to="/" end className={sideLink} title="Overview">
          <span className="grid w-[22px] shrink-0 place-items-center">
            <Icon>{icon.home}</Icon>
          </span>
          <span className={hidden}>Overview</span>
        </NavLink>

        <p className={`label mt-5 px-2.5 pb-1 text-xs ${collapsed ? "sr-only" : ""}`}>Markets</p>
        {collapsed && <div className="mx-2.5 my-3 border-t border-line" aria-hidden="true" />}
        {primary.map((asset) => {
          const to = `/asset/${asset.slug}`;
          return (
            <div key={asset.slug}>
              <NavLink to={to} className={sideLink} title={shortName(asset)}>
                <span className="grid w-[22px] shrink-0 place-items-center">
                  <AssetGlyph asset={asset} />
                </span>
                <span className={hidden}>{shortName(asset)}</span>
              </NavLink>
            </div>
          );
        })}
        <NavLink to="/together" className={sideLink} title="Markets together">
          <span className="grid w-[22px] shrink-0 place-items-center">
            <Icon>{icon.together}</Icon>
          </span>
          <span className={hidden}>Markets together</span>
        </NavLink>

        <p className={`label mt-5 px-2.5 pb-1 text-xs ${collapsed ? "sr-only" : ""}`}>Yours</p>
        {collapsed && <div className="mx-2.5 my-3 border-t border-line" aria-hidden="true" />}
        <NavLink to="/portfolio" className={sideLink} title="Portfolio">
          <span className="grid w-[22px] shrink-0 place-items-center">
            <Icon>{icon.portfolio}</Icon>
          </span>
          <span className={hidden}>Portfolio</span>
        </NavLink>
      </nav>

      <div className="mt-2 flex flex-col gap-1 border-t border-line pt-2">
        <NavLink to="/system" className={sideLink} title="System">
          <SystemIcon good={good} />
          <span className={hidden}>System</span>
          <span className="sr-only">
            : {good ? "all systems normal" : "something needs attention"}
          </span>
        </NavLink>
        {collapsed && canToggle && (
          <CollapseButton collapsed={collapsed} onToggle={onToggle} />
        )}
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
  const primary = useAssets().data?.filter((a) => a.is_primary) ?? [];
  const [preferCollapsed, setCollapsed] = useState(readCollapsed);
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
      <Sidebar primary={primary} collapsed={collapsed} canToggle={wide} onToggle={toggle} />

      {/* Phones navigate with the tabs at the bottom, within thumb reach; nothing on top. */}
      <div
        className={`flex min-w-0 flex-1 flex-col transition-[padding] duration-300 ${
          collapsed ? "md:pl-[80px]" : "md:pl-[244px]"
        }`}
      >
        <main className="page pb-tabbar @container mx-auto w-full max-w-[1280px] flex-1">
          <Outlet />
          {/* On a phone the tabs hold the markets and the portfolio; the status lives here. */}
          <Link
            to="/system"
            className="mt-12 inline-flex items-center gap-2 text-xs text-muted hover:text-ink md:hidden"
          >
            <span
              className={`h-2 w-2 rounded-full ${good ? "bg-calm" : "bg-alert"}`}
              aria-hidden="true"
            />
            {good ? "All systems normal" : "Something needs attention"}
          </Link>
          <p className="mt-4 max-w-[78ch] text-xs leading-relaxed text-faint md:mt-12">
            RADAR is an analytics tool for information and education. It is not financial advice and
            it does not place trades. Historical patterns do not guarantee future results. Gold is
            represented by GLD, a fund backed by physical gold that trades only in US market hours.
          </p>
        </main>
      </div>

      <nav
        aria-label="Main, phone"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom,0px))] md:hidden"
      >
        <div className="capsule pointer-events-auto mx-auto flex max-w-lg gap-0.5 rounded-[26px] p-1.5">
          <NavLink to="/" end className={tab}>
            <Icon>{icon.home}</Icon>
            Overview
          </NavLink>
          {primary.map((asset) => (
            <NavLink key={asset.slug} to={`/asset/${asset.slug}`} className={tab}>
              <AssetGlyph asset={asset} />
              <span className="max-w-full truncate px-0.5">
                {shortName(asset).replace(/^US s/, "S")}
              </span>
            </NavLink>
          ))}
          <NavLink to="/together" className={tab}>
            <Icon>{icon.together}</Icon>
            <span className="max-w-full truncate px-0.5">Together</span>
          </NavLink>
          <NavLink to="/portfolio" className={tab}>
            <Icon>{icon.portfolio}</Icon>
            <span className="max-w-full truncate px-1">Portfolio</span>
          </NavLink>
        </div>
      </nav>
    </div>
  );
}
