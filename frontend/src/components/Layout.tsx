import { NavLink, Outlet } from "react-router-dom";

import { useStreamStatus } from "../api/live";
import { useAssets, useHealth } from "../api/queries";
import { Pill } from "./ui";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `block rounded-md px-3 py-1.5 text-sm transition-colors ${
    isActive ? "bg-panel font-medium text-ink shadow-[inset_0_0_0_1px_var(--line)]" : "text-muted hover:bg-raised hover:text-ink"
  }`;

function NavGroup({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="contents md:block">
      <div className="hidden px-3 pb-1 text-[11px] font-medium uppercase tracking-wider text-muted md:block">
        {label}
      </div>
      <div className="contents md:flex md:flex-col md:gap-0.5">{children}</div>
    </div>
  );
}

function SystemStatus() {
  const stream = useStreamStatus();
  const health = useHealth();
  const data = health.data?.status;
  return (
    <div className="flex flex-wrap gap-1.5 px-3">
      <Pill tone={stream === "open" ? "ok" : "warn"}>
        {stream === "open" ? "Live feed on" : stream === "connecting" ? "Connecting" : "Live feed off"}
      </Pill>
      <Pill tone={data === "ok" ? "ok" : data === undefined ? "muted" : "warn"}>
        {data === "ok" ? "Data current" : data === undefined ? "Checking data" : "Data needs attention"}
      </Pill>
    </div>
  );
}

export function Layout() {
  const assets = useAssets();
  const primary = assets.data?.filter((a) => a.is_primary) ?? [];
  return (
    <div className="mx-auto grid min-h-screen max-w-[1240px] grid-cols-1 gap-x-6 px-4 md:grid-cols-[210px_minmax(0,1fr)]">
      <aside className="flex flex-col gap-3 pt-4 md:sticky md:top-0 md:h-screen md:gap-5 md:py-5">
        <div className="px-3">
          <div className="text-xl font-semibold tracking-[0.12em]">RADAR</div>
          <div className="text-[11px] text-muted">Regimes · Analytics · Distributions · Alerts · Risk</div>
        </div>
        <nav aria-label="Main" className="flex flex-row flex-wrap gap-1 md:flex-col md:gap-4">
          <NavGroup label="Markets">
            <NavLink to="/" end className={linkClass}>
              Overview
            </NavLink>
            {primary.map((asset) => (
              <NavLink key={asset.slug} to={`/asset/${asset.slug}`} className={linkClass}>
                {asset.name}
              </NavLink>
            ))}
            <NavLink to="/relationships" className={linkClass}>
              Bitcoin vs gold
            </NavLink>
          </NavGroup>
          <NavGroup label="Yours">
            <NavLink to="/portfolio" className={linkClass}>
              Portfolio
            </NavLink>
            <NavLink to="/signals" className={linkClass}>
              Signals
            </NavLink>
          </NavGroup>
          <NavGroup label="System">
            <NavLink to="/status" className={linkClass}>
              Methodology and status
            </NavLink>
          </NavGroup>
        </nav>
        <div className="md:mt-auto">
          <SystemStatus />
        </div>
      </aside>
      <div className="flex min-w-0 flex-col py-4 md:py-5">
        <main className="flex-1">
          <Outlet />
        </main>
        <footer className="mt-8 border-t border-line pt-3 text-xs text-muted">
          RADAR is an analytics tool for information and education. It is not financial advice and it
          does not place trades. Historical patterns do not guarantee future results. Gold is
          represented by GLD, a fund backed by physical gold that trades only in US market hours.
        </footer>
      </div>
    </div>
  );
}
