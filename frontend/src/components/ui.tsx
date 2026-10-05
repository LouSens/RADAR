import type { ReactNode } from "react";

import type { Asset } from "../api/client";

export function Panel({
  title,
  aside,
  children,
  className = "",
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`rounded-lg border border-line bg-panel p-4 ${className}`}>
      {(title || aside) && (
        <header className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          {title && <h2 className="text-base font-semibold">{title}</h2>}
          {aside && <div className="text-xs text-muted">{aside}</div>}
        </header>
      )}
      {children}
    </section>
  );
}

/** Every chart carries one: what it shows, the window, and the sample size. */
export function Caption({ children }: { children: ReactNode }) {
  return <p className="mt-2 text-xs text-muted">{children}</p>;
}

export function Pill({ tone, children }: { tone: "ok" | "warn" | "muted"; children: ReactNode }) {
  const colour =
    tone === "ok"
      ? "text-calm border-calm/40"
      : tone === "warn"
        ? "text-alert border-alert/40"
        : "text-muted border-line";
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs ${colour}`}>
      {children}
    </span>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-md bg-raised px-3 py-2 text-sm text-muted">{children}</p>;
}

/** CSS variable for an asset's series colour. */
export function assetColorVar(asset: Pick<Asset, "symbol" | "asset_class">): string {
  if (asset.symbol === "BTC/USD") return "--btc";
  if (asset.symbol === "GLD" || asset.symbol === "PAXG/USD") return "--gold";
  return asset.asset_class === "stock" ? "--stock" : "--accent";
}
