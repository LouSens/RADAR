import { useState } from "react";
import { Link, NavLink, Outlet } from "react-router-dom";

import { useStreamStatus } from "../api/live";
import { useAssets, useHealth } from "../api/queries";
import { Pill, shortName } from "./ui";

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

function StatusPills() {
  const stream = useStreamStatus();
  const health = useHealth().data?.status;
  return (
    <>
      <Pill tone={stream === "open" ? "ok" : "warn"}>
        <span
          className={`inline-block h-1.5 w-1.5 rounded-full ${stream === "open" ? "live-dot bg-calm" : "bg-alert"}`}
          aria-hidden="true"
        />
        {stream === "open" ? "Live feed on" : stream === "connecting" ? "Connecting" : "Live feed off"}
      </Pill>
      <Pill tone={health === "ok" ? "ok" : health === undefined ? "muted" : "warn"}>
        {health === "ok" ? "Data current" : health === undefined ? "Checking data" : "Data needs attention"}
      </Pill>
    </>
  );
}

const desktopLink = ({ isActive }: { isActive: boolean }) =>
  `rounded-full px-3 py-1.5 text-sm transition-colors ${
    isActive ? "bg-white/10 text-ink" : "text-muted hover:text-ink"
  }`;

const mobileLink = ({ isActive }: { isActive: boolean }) =>
  `flex items-center justify-between rounded-2xl px-4 py-3 text-base ${
    isActive ? "bg-white/10 text-ink" : "text-muted"
  }`;

export function Layout() {
  const assets = useAssets();
  const [open, setOpen] = useState(false);
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];

  const links = [
    { to: "/", label: "Overview", end: true },
    ...primary.map((a) => ({ to: `/asset/${a.slug}`, label: shortName(a), end: false })),
    { to: "/relationships", label: "Compare", end: false },
    { to: "/portfolio", label: "Portfolio", end: false },
    { to: "/signals", label: "Signals", end: false },
    { to: "/status", label: "Status", end: false },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="fixed inset-x-0 top-0 z-40 px-3 pt-3 sm:px-5">
        <div className="glass mx-auto flex h-14 max-w-[1180px] items-center gap-3 !rounded-full px-4 sm:px-5">
          <Link
            to="/"
            className="flex items-center gap-2.5"
            aria-label="RADAR, overview"
            onClick={() => setOpen(false)}
          >
            <RadarMark />
            <span className="text-[15px] font-extrabold tracking-[0.16em]">RADAR</span>
          </Link>
          <nav aria-label="Main" className="mx-auto hidden items-center gap-0.5 lg:flex">
            {links.map((link) => (
              <NavLink key={link.to} to={link.to} end={link.end} className={desktopLink}>
                {link.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto hidden items-center gap-1.5 sm:flex lg:ml-0">
            <StatusPills />
          </div>
          <button
            type="button"
            className="ml-auto grid h-9 w-9 place-items-center rounded-full border border-line-strong sm:ml-1 lg:hidden"
            aria-expanded={open}
            aria-controls="phone-menu"
            aria-label={open ? "Close menu" : "Open menu"}
            onClick={() => setOpen((v) => !v)}
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              {open ? (
                <path d="M3 3l10 10M13 3 3 13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              ) : (
                <path d="M2 4.5h12M2 8h12M2 11.5h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
              )}
            </svg>
          </button>
        </div>
        {open && (
          <div id="phone-menu" className="glass rise mx-auto mt-2 max-w-[1180px] p-2 lg:hidden">
            <nav aria-label="Main, phone" className="flex flex-col">
              {links.map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  end={link.end}
                  className={mobileLink}
                  onClick={() => setOpen(false)}
                >
                  {link.label}
                  <span aria-hidden="true" className="text-faint">
                    →
                  </span>
                </NavLink>
              ))}
            </nav>
            <div className="flex flex-wrap gap-1.5 px-3 pb-2 pt-3 sm:hidden">
              <StatusPills />
            </div>
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-[1180px] flex-1 px-4 pb-16 pt-24 sm:px-6 sm:pt-28">
        <Outlet />
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-[1180px] flex-col gap-3 px-4 py-8 text-xs leading-relaxed text-muted sm:px-6 md:flex-row md:items-start md:justify-between">
          <p className="max-w-[70ch]">
            RADAR is an analytics tool for information and education. It is not financial advice and it
            does not place trades. Historical patterns do not guarantee future results. Gold is
            represented by GLD, a fund backed by physical gold that trades only in US market hours.
          </p>
          <p className="num shrink-0 text-faint">Regimes · Analytics · Distributions · Alerts · Risk</p>
        </div>
      </footer>
    </div>
  );
}
