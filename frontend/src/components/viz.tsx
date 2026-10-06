import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import type { Trust } from "../api/client";
import { TrustBadge } from "./ui";

/**
 * One answer on a dashboard: a label, a large figure, and a small picture of it. The
 * whole tile leads to the page holding the evidence.
 */
export function Tile({
  label,
  to,
  trust,
  figure,
  note,
  wide = false,
  children,
}: {
  label: string;
  to: string;
  trust?: Trust;
  figure?: ReactNode;
  note?: ReactNode;
  wide?: boolean;
  children?: ReactNode;
}) {
  return (
    <Link
      to={to}
      aria-label={label}
      className={`tile group flex min-w-0 flex-col ${wide ? "@2xl:col-span-2" : ""}`}
    >
      <span className="flex items-center justify-between gap-2">
        <span className="label">{label}</span>
        <TrustBadge trust={trust} />
      </span>
      {figure !== undefined && (
        <span className="num mt-2 block text-[1.6rem] font-semibold leading-tight tracking-tight">
          {figure}
        </span>
      )}
      {note && <span className="mt-0.5 block text-sm text-muted">{note}</span>}
      {children && <span className="mt-auto block pt-4">{children}</span>}
    </Link>
  );
}

export function TileGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-3 @lg:grid-cols-2 @4xl:grid-cols-3 @xl:gap-4">
      {children}
    </div>
  );
}

/** A track from `min` to `max` with a marker, and optionally a shaded band and a tick. */
export function Meter({
  value,
  min,
  max,
  band,
  tick,
  colour = "var(--accent)",
  left,
  right,
  label,
}: {
  value: number;
  min: number;
  max: number;
  band?: [number, number];
  tick?: number;
  colour?: string;
  left?: ReactNode;
  right?: ReactNode;
  label: string;
}) {
  const at = (x: number) => `${Math.min(Math.max((x - min) / (max - min || 1), 0), 1) * 100}%`;
  return (
    <span className="block">
      <span className="relative block h-2 rounded-full bg-white/8" role="img" aria-label={label}>
        {band && (
          <span
            className="absolute inset-y-0 rounded-full"
            style={{
              left: at(band[0]),
              right: `calc(100% - ${at(band[1])})`,
              background: `color-mix(in srgb, ${colour} 38%, transparent)`,
            }}
          />
        )}
        {tick !== undefined && (
          <span className="absolute -inset-y-1 w-px bg-line-strong" style={{ left: at(tick) }} />
        )}
        <span
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bg"
          style={{ left: at(value), background: colour }}
        />
      </span>
      {(left !== undefined || right !== undefined) && (
        <span className="num mt-1.5 flex justify-between text-xs text-faint">
          <span>{left}</span>
          <span>{right}</span>
        </span>
      )}
    </span>
  );
}

export interface Part {
  key: string;
  name: string;
  share: number;
  colour: string;
}

/** One bar split into parts that add up to the whole. */
export function StackBar({ parts, label }: { parts: Part[]; label: string }) {
  return (
    <span
      className="flex h-3 overflow-hidden rounded-full bg-white/8"
      role="img"
      aria-label={`${label}: ${parts.map((p) => `${p.name} ${(p.share * 100).toFixed(0)}%`).join(", ")}`}
    >
      {parts.map((part) => (
        <span
          key={part.key}
          title={`${part.name} ${(part.share * 100).toFixed(0)}%`}
          style={{ width: `${Math.max(part.share, 0) * 100}%`, background: part.colour }}
        />
      ))}
    </span>
  );
}

export function Legend({ parts }: { parts: Part[] }) {
  return (
    <span className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted">
      {parts.map((part) => (
        <span key={part.key} className="flex items-center gap-1.5">
          <span
            className="h-2 w-2 rounded-full"
            style={{ background: part.colour }}
            aria-hidden="true"
          />
          {part.name}
        </span>
      ))}
    </span>
  );
}

/** Bars side by side on one scale, for comparing a few amounts. */
export function Bars({
  rows,
  format,
}: {
  rows: { key: string; name: string; value: number; colour?: string }[];
  format: (value: number) => string;
}) {
  const reach = Math.max(...rows.map((r) => Math.abs(r.value)), 1e-12);
  return (
    <span className="flex flex-col gap-2">
      {rows.map((row) => (
        <span key={row.key} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3">
          <span className="min-w-0">
            <span className="block truncate text-xs text-muted">{row.name}</span>
            <span className="mt-1 block h-1.5 rounded-full bg-white/8">
              <span
                className="block h-full rounded-full"
                style={{
                  width: `${(Math.abs(row.value) / reach) * 100}%`,
                  background: row.colour ?? "var(--accent)",
                }}
              />
            </span>
          </span>
          <span className="num text-sm font-medium">{format(row.value)}</span>
        </span>
      ))}
    </span>
  );
}

/** Twenty dots with the rare ones lit: "about 1 day in 20" as a picture. */
export function OneIn({ lit, of, label }: { lit: number; of: number; label: string }) {
  return (
    <span className="flex flex-wrap gap-1.5" role="img" aria-label={label}>
      {Array.from({ length: of }, (_, i) => (
        <span
          key={i}
          className="h-2.5 w-2.5 rounded-full"
          style={{ background: i < lit ? "var(--alert)" : "rgba(255,255,255,0.12)" }}
        />
      ))}
    </span>
  );
}

/** A small line of values over time, with no axes. */
export function Spark({
  values,
  colour = "var(--accent)",
  min,
  max,
  label,
}: {
  values: (number | null | undefined)[];
  colour?: string;
  min?: number;
  max?: number;
  label: string;
}) {
  const known = values.filter((v): v is number => v != null);
  if (known.length < 2) return null;
  const low = min ?? Math.min(...known);
  const high = max ?? Math.max(...known);
  const width = 200;
  const height = 44;
  const step = width / (values.length - 1);
  let path = "";
  let drawing = false;
  values.forEach((value, i) => {
    if (value == null) {
      drawing = false;
      return;
    }
    const y = height - ((value - low) / (high - low || 1)) * height;
    path += `${drawing ? "L" : "M"}${(i * step).toFixed(1)},${y.toFixed(1)} `;
    drawing = true;
  });
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="block h-11 w-full"
      role="img"
      aria-label={label}
    >
      {min !== undefined && max !== undefined && min < 0 && max > 0 && (
        <line
          x1="0"
          x2={width}
          y1={height - ((0 - low) / (high - low)) * height}
          y2={height - ((0 - low) / (high - low)) * height}
          stroke="var(--line-strong)"
          strokeDasharray="2 4"
          vectorEffect="non-scaling-stroke"
        />
      )}
      <path
        d={path.trim()}
        fill="none"
        stroke={colour}
        strokeWidth="1.8"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

const STATE_COLOUR: Record<string, string> = {
  calm: "var(--calm)",
  normal: "var(--muted)",
  elevated: "var(--gold)",
  turbulent: "var(--alert)",
};

export const stateColour = (label: string) => STATE_COLOUR[label] ?? "var(--accent)";

/** A market state as a coloured pill. */
export function StateChip({ label, children }: { label: string; children?: ReactNode }) {
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium capitalize"
      style={{
        color: stateColour(label),
        background: `color-mix(in srgb, ${stateColour(label)} 14%, transparent)`,
      }}
    >
      {children}
      {label}
    </span>
  );
}

const PALETTE = ["--btc", "--gold", "--stock", "--accent", "--calm", "--alert"];

/** A stable colour for each holding. Cash is always the quiet one. */
export function holdingColour(symbol: string, index: number): string {
  if (symbol === "USD") return "rgba(255,255,255,0.28)";
  if (symbol === "BTC/USD") return "var(--btc)";
  if (symbol === "GLD" || symbol === "PAXG/USD") return "var(--gold)";
  if (symbol === "SPY") return "var(--stock)";
  return `var(${PALETTE[(index + 3) % PALETTE.length]})`;
}
