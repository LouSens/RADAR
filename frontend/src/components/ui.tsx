import { useEffect, useState, type ReactNode } from "react";

import type { Asset, Trust } from "../api/client";
import { formatChange } from "../lib/format";
import { positionIn, sparklinePath, type Range } from "../lib/stats";

export function Card({
  children,
  className = "",
  lift = false,
}: {
  children: ReactNode;
  className?: string;
  lift?: boolean;
}) {
  return <section className={`glass ${lift ? "glass-lift" : ""} ${className}`}>{children}</section>;
}

export function CardHeader({ title, children }: { title: ReactNode; children?: ReactNode }) {
  return (
    <header className="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
      <h2 className="text-base font-semibold tracking-tight">{title}</h2>
      {children}
    </header>
  );
}

/** Every chart carries one: what it shows, the window, and the sample size. */
export function Caption({ children }: { children: ReactNode }) {
  return <p className="mt-3 text-xs leading-relaxed text-faint">{children}</p>;
}

export function Message({ children }: { children: ReactNode }) {
  return <p className="well px-4 py-3 text-sm text-muted">{children}</p>;
}

/** A change figure, coloured by direction, with an arrow for readers who cannot rely on colour. */
export function Change({
  value,
  className = "",
}: {
  value: number | undefined;
  className?: string;
}) {
  if (value === undefined) return <span className={`num text-faint ${className}`}>–</span>;
  const up = value >= 0;
  return (
    <span className={`num whitespace-nowrap ${up ? "text-calm" : "text-alert"} ${className}`}>
      <span aria-hidden="true">{up ? "▲" : "▼"} </span>
      {formatChange(value).replace(/^[+−]/, "")}
      <span className="sr-only">{up ? " up" : " down"}</span>
    </span>
  );
}

export function ChangeChip({ value }: { value: number | undefined }) {
  if (value === undefined) return null;
  const up = value >= 0;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-sm font-medium ${
        up ? "bg-calm/12 text-calm" : "bg-alert/12 text-alert"
      }`}
    >
      <Change value={value} />
    </span>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      className="inline-flex rounded-full border border-line bg-white/[0.03] p-0.5"
      role="group"
      aria-label={label}
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={value === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded-full px-3 py-1 text-[13px] font-medium transition-colors ${
            value === option.value ? "bg-white/12 text-ink" : "text-muted hover:text-ink"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function Sparkline({
  values,
  colorVar,
  width = 120,
  height = 36,
}: {
  values: number[];
  colorVar: string;
  width?: number;
  height?: number;
}) {
  const path = sparklinePath(values, width, height);
  if (!path) return <div style={{ width, height }} />;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-full w-full"
      aria-hidden="true"
    >
      <path
        d={path}
        fill="none"
        stroke={`var(${colorVar})`}
        strokeWidth="1.6"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

/** A low-to-high track with a marker at the current price. */
export function RangeBar({
  range,
  price,
  colorVar,
  format,
}: {
  range: Range;
  price: number;
  colorVar: string;
  format: (value: number) => string;
}) {
  const at = positionIn(range, price) * 100;
  return (
    <div>
      <div className="relative h-1.5 rounded-full bg-white/8">
        <div
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bg"
          style={{ left: `${at}%`, background: `var(${colorVar})` }}
        />
      </div>
      <div className="num mt-2 flex justify-between text-xs text-muted">
        <span>{format(range.low)}</span>
        <span>{format(range.high)}</span>
      </div>
    </div>
  );
}

export function StatRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-line py-2.5 last:border-b-0">
      <dt className="label">{label}</dt>
      <dd className="num text-right text-sm font-medium">{children}</dd>
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

const GRADE: Record<Trust["grade"], { word: string; colour: string }> = {
  solid: { word: "Solid", colour: "var(--calm)" },
  fair: { word: "Fair", colour: "var(--gold)" },
  rough: { word: "Rough", colour: "var(--alert)" },
};

/** How far a claim can be leaned on. The same mark on every claim in the app. */
export function TrustBadge({ trust }: { trust: Trust | undefined }) {
  if (!trust) return null;
  const grade = GRADE[trust.grade];
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-line px-2 py-0.5 text-xs font-medium text-muted"
      title={trust.reason}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: grade.colour }}
        aria-hidden="true"
      />
      <span className="sr-only">Evidence: </span>
      {grade.word}
    </span>
  );
}

/** What every section of a market page takes. */
export interface PanelProps {
  asset: Asset;
  trust?: Trust;
  defaultOpen?: boolean;
}

/**
 * One section of a market page. Closed, it shows the claim and how far to trust it;
 * opened, it shows the evidence. A link to its id opens it.
 */
export function Panel({
  id,
  title,
  headline,
  trust,
  defaultOpen = false,
  children,
}: {
  id: string;
  title: string;
  headline?: ReactNode;
  trust?: Trust;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  useEffect(() => {
    const openIfTarget = () => {
      if (window.location.hash === `#${id}`) setOpen(true);
    };
    openIfTarget();
    window.addEventListener("hashchange", openIfTarget);
    return () => window.removeEventListener("hashchange", openIfTarget);
  }, [id]);

  return (
    <section id={id} className="glass scroll-mt-24">
      <h2>
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={() => setOpen((was) => !was)}
          className="flex w-full flex-wrap items-center gap-x-3 gap-y-1.5 p-5 text-left sm:px-7"
        >
          <span className="text-base font-semibold tracking-tight">{title}</span>
          <TrustBadge trust={trust} />
          <span className="num ml-auto min-w-0 text-sm text-muted">{headline}</span>
          <svg
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`shrink-0 text-faint transition-transform duration-200 ${open ? "rotate-180" : ""}`}
            aria-hidden="true"
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
          <span className="sr-only">{open ? "Hide the detail" : "Show the detail"}</span>
        </button>
      </h2>
      {open && (
        <div id={`${id}-body`} className="flex flex-col gap-6 border-t border-line p-5 sm:p-7">
          {trust && (
            <p className="text-sm leading-relaxed text-muted">
              <span className="font-medium text-ink">
                Why {GRADE[trust.grade].word.toLowerCase()}:
              </span>{" "}
              {trust.reason}
            </p>
          )}
          {children}
        </div>
      )}
    </section>
  );
}
