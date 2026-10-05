import type { ReactNode } from "react";

import type { Asset } from "../api/client";

/** Section marker, as on the portfolio site: an accent bar, the name, and a hairline. */
export function SectionLabel({ children, aside }: { children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-5 flex items-center gap-3 text-sm">
      <span className="h-[3px] w-6 rounded-full bg-accent" aria-hidden="true" />
      <span className="text-ink/70">{children}</span>
      <span className="h-px flex-1 bg-white/10" aria-hidden="true" />
      {aside && <span className="text-xs text-muted">{aside}</span>}
    </div>
  );
}

export function Panel({
  title,
  aside,
  children,
  className = "",
  lift = false,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  lift?: boolean;
}) {
  return (
    <section className={`glass ${lift ? "glass-lift" : ""} p-5 sm:p-6 ${className}`}>
      {(title || aside) && (
        <header className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
          {title && <h2 className="text-lg font-semibold tracking-tight">{title}</h2>}
          {aside && <div className="text-xs text-muted">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/** Every chart carries one: what it shows, the window, and the sample size. */
export function Caption({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-xs leading-relaxed text-muted">{children}</p>;
}

export function Pill({ tone, children }: { tone: "ok" | "warn" | "muted"; children: ReactNode }) {
  const colour =
    tone === "ok"
      ? "border-calm/30 bg-calm/10 text-calm"
      : tone === "warn"
        ? "border-alert/30 bg-alert/10 text-alert"
        : "border-line bg-white/[0.03] text-muted";
  return (
    <span
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${colour}`}
    >
      {children}
    </span>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="well px-4 py-3 text-sm text-muted">{children}</p>;
}

export function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="well px-4 py-3">
      <div className="text-xs text-muted">{label}</div>
      <div className="num mt-0.5 text-base">{value}</div>
    </div>
  );
}

/** CSS variable for an asset's series colour. */
export function assetColorVar(asset: Pick<Asset, "symbol" | "asset_class">): string {
  if (asset.symbol === "BTC/USD") return "--btc";
  if (asset.symbol === "GLD" || asset.symbol === "PAXG/USD") return "--gold";
  return asset.asset_class === "stock" ? "--stock" : "--accent";
}

/** A short name for tight spaces: "US stocks (S&P 500)" becomes "US stocks". */
export function shortName(asset: Pick<Asset, "name">): string {
  return asset.name.split(" (")[0] ?? asset.name;
}
