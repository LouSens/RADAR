import type { ReactNode } from "react";
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

/**
 * One quiet dot for the whole system. Green when data and the live feed are both fine;
 * otherwise amber, and the System page says why.
 */
function SystemDot() {
  const stream = useStreamStatus();
  const health = useHealth().data?.status;
  const good = stream === "open" && health === "ok";
  const text = good ? "All systems normal" : "Something needs attention";
  return (
    <Link
      to="/system"
      title={text}
      aria-label={`System status: ${text}`}
      className="grid h-9 w-9 place-items-center rounded-full text-muted transition-colors hover:bg-white/8 hover:text-ink"
    >
      <span className="relative">
        <Icon>{icon.system}</Icon>
        <span
          className={`absolute -right-0.5 -top-0.5 h-2 w-2 rounded-full ring-2 ring-[#12131a] ${
            good ? "bg-calm" : "bg-alert"
          }`}
        />
      </span>
    </Link>
  );
}

const topLink = ({ isActive }: { isActive: boolean }) =>
  `flex items-center gap-2 rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-300 ${
    isActive ? "lens text-ink" : "text-muted hover:text-ink"
  }`;

const tab = ({ isActive }: { isActive: boolean }) =>
  `flex min-w-0 flex-1 flex-col items-center gap-1 rounded-[20px] py-2 text-[11px] font-medium transition-all duration-300 ${
    isActive ? "lens text-ink" : "text-muted"
  }`;

export function Layout() {
  const primary = useAssets().data?.filter((a) => a.is_primary) ?? [];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="pointer-events-none fixed inset-x-0 top-0 z-40 px-3 pt-3 sm:px-5 sm:pt-4">
        <div className="capsule pointer-events-auto mx-auto flex h-[52px] max-w-[1200px] items-center gap-1 rounded-full pl-4 pr-2 sm:pl-5">
          <Link to="/" className="mr-2 flex items-center gap-2.5 sm:mr-4" aria-label="RADAR home">
            <RadarMark />
            <span className="text-[15px] font-bold tracking-[0.14em]">RADAR</span>
          </Link>
          <nav aria-label="Main" className="hidden items-center gap-0.5 md:flex">
            <NavLink to="/" end className={topLink}>
              Overview
            </NavLink>
            {primary.map((asset) => (
              <NavLink key={asset.slug} to={`/asset/${asset.slug}`} className={topLink}>
                <span
                  className="h-1.5 w-1.5 rounded-full"
                  style={{ background: `var(${assetColorVar(asset)})` }}
                  aria-hidden="true"
                />
                {shortName(asset)}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <SystemDot />
          </div>
        </div>
      </header>

      <main className="pb-tabbar mx-auto w-full max-w-[1200px] flex-1 px-4 pt-[5.25rem] sm:px-6 sm:pt-28">
        <Outlet />
        <p className="mt-12 max-w-[78ch] text-xs leading-relaxed text-faint">
          RADAR is an analytics tool for information and education. It is not financial advice and it
          does not place trades. Historical patterns do not guarantee future results. Gold is
          represented by GLD, a fund backed by physical gold that trades only in US market hours.
        </p>
      </main>

      {/* Phones get a floating tab bar within thumb reach, as an app would. */}
      <nav
        aria-label="Main, phone"
        className="pointer-events-none fixed inset-x-0 bottom-0 z-40 px-3 pb-[calc(0.75rem+env(safe-area-inset-bottom,0px))] md:hidden"
      >
        <div className="capsule pointer-events-auto mx-auto flex max-w-md gap-1 rounded-[26px] p-1.5">
          <NavLink to="/" end className={tab}>
            <Icon>{icon.home}</Icon>
            Overview
          </NavLink>
          {primary.map((asset) => (
            <NavLink key={asset.slug} to={`/asset/${asset.slug}`} className={tab}>
              <AssetGlyph asset={asset} />
              <span className="max-w-full truncate px-1">{shortName(asset)}</span>
            </NavLink>
          ))}
          <NavLink to="/system" className={tab}>
            <Icon>{icon.system}</Icon>
            System
          </NavLink>
        </div>
      </nav>
    </div>
  );
}
