import { useId, type ReactNode } from "react";

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

/** One short fact about a chart: a name and a value, not a sentence. */
export interface Fact {
  label: string;
  value: ReactNode;
}

/**
 * Every chart carries one: what it shows, the window, and the sample size. The facts are
 * laid out as tiles across the card's full width, because a stack of short named values is
 * read at a glance where the same thing as a paragraph is skipped. Anything that genuinely
 * needs sentences goes in `children`, under the facts, kept to one readable column.
 */
export function Caption({ facts, children }: { facts?: readonly Fact[]; children?: ReactNode }) {
  return (
    <details className="about mt-3">
      <summary>About this</summary>
      <div>
        {facts && facts.length > 0 && (
          <dl className="facts">
            {facts.map((fact) => (
              <div key={fact.label}>
                <dt className="label">{fact.label}</dt>
                <dd>{fact.value}</dd>
              </div>
            ))}
          </dl>
        )}
        {children && <p className="prose mt-3 text-xs leading-relaxed text-muted">{children}</p>}
      </div>
    </details>
  );
}

/**
 * How a figure was tested, for the reader who wants it. Closed by default: the answer
 * comes first and the working is one tap away.
 */
export function Evidence({
  children,
  summary = "How this was checked",
}: {
  children: ReactNode;
  summary?: string;
}) {
  return (
    <details className="about">
      <summary>{summary}</summary>
      <div className="mt-4 flex flex-col gap-5">{children}</div>
    </details>
  );
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
      className="inline-flex max-w-full flex-wrap rounded-[20px] border border-line bg-white/[0.03] p-0.5"
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
  const id = useId();
  if (!path) return <div style={{ width, height }} />;
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-full w-full"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor={`var(${colorVar})`} stopOpacity="0.28" />
          <stop offset="1" stopColor={`var(${colorVar})`} stopOpacity="0" />
        </linearGradient>
      </defs>
      <path d={`${path} L${width},${height} L0,${height} Z`} fill={`url(#${id})`} />
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
export function assetColorVar(
  asset: Pick<Asset, "symbol" | "asset_class"> & { kind?: string | null },
): string {
  if (asset.kind === "bitcoin" || asset.symbol === "BTC/USD") return "--btc";
  // By what it is where that is known; by name for the two forms of gold otherwise.
  if (asset.kind === "gold" || asset.symbol === "GLD" || asset.symbol === "PAXG/USD")
    return "--gold";
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
}

/**
 * One section of a market page, always laid out the same way: its name and trust mark,
 * the claim in one line, why it earned that mark, then the evidence.
 */
export function Panel({
  id,
  title,
  headline,
  trust,
  children,
}: {
  id: string;
  title: string;
  headline?: ReactNode;
  trust?: Trust;
  children: ReactNode;
}) {
  return (
    <section id={id} className="glass" aria-labelledby={`${id}-title`}>
      <header className="p-4 @xl:p-7">
        <div className="flex items-center justify-between gap-3">
          <h2 id={`${id}-title`} className="label">
            {title}
          </h2>
          <TrustBadge trust={trust} />
        </div>
        {headline && (
          <p className="num mt-1.5 text-lg font-semibold leading-snug tracking-tight @xl:text-xl">
            {headline}
          </p>
        )}
        {trust && (
          <details className="about mt-2">
            <summary>Why {GRADE[trust.grade].word.toLowerCase()}</summary>
            <p className="mt-2 prose text-sm leading-relaxed text-muted">{trust.reason}</p>
          </details>
        )}
      </header>
      <div className="flex flex-col gap-5 border-t border-line p-4 @xl:gap-6 @xl:p-7">
        {children}
      </div>
    </section>
  );
}
