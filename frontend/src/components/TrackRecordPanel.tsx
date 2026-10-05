import type { TrackRecord } from "../api/client";
import { useTrackRecord } from "../api/queries";
import { formatCount, formatShare } from "../lib/format";
import { stepsLabel } from "../lib/outlook";
import { formatDate } from "../lib/time";
import { Caption, Panel, type PanelProps } from "./ui";

type Row = TrackRecord["rows"][number];

const HORIZON: Record<number, string> = { 1: "1 day", 7: "1 week", 30: "1 month" };

/** What a logged forecast was, in plain words. */
export function describe(row: Row): string {
  const period = HORIZON[row.horizon_days] ?? `${row.horizon_days} days`;
  if (row.kind === "outlook_range") {
    return `${Math.round(Number(row.key) * 100)}% outlook range, ${period}`;
  }
  if (row.kind === "loss_limit") {
    return `${Math.round(Number(row.key) * 100)}% loss limit, ${period}`;
  }
  return `Expected swings, ${period}`;
}

function result(row: Row): string {
  if (row.resolved === 0) return "No results yet";
  if (row.held != null && row.held_share != null) {
    const spread =
      row.held_low != null && row.held_high != null
        ? ` (${formatShare(row.held_low, 0)} to ${formatShare(row.held_high, 0)})`
        : "";
    return `Held ${formatCount(row.held)} of ${formatCount(row.resolved)}: ${formatShare(row.held_share, 0)}${spread}`;
  }
  if (row.forecast_to_outcome != null) {
    const off = row.forecast_to_outcome - 1;
    return `${formatCount(row.resolved)} scored; forecasts ran ${formatShare(Math.abs(off), 0)} ${
      off >= 0 ? "above" : "below"
    } what happened`;
  }
  return `${formatCount(row.resolved)} scored`;
}

export function TrackRecordPanel({ asset, defaultOpen }: PanelProps) {
  const record = useTrackRecord(asset.slug).data;
  if (!record || record.rows.length === 0 || !record.recording_since) return null;
  const longest = Math.max(...record.rows.map((row) => row.horizon_days));

  return (
    <Panel
      id="live-record"
      title="Live record"
      defaultOpen={defaultOpen}
      headline={`${formatCount(record.recorded)} logged, ${formatCount(record.resolved)} scored`}
    >
      <header>
        <p className="text-sm leading-relaxed text-muted">
          <span className="num text-ink">{formatCount(record.recorded)}</span> forecasts written
          down since {formatDate(record.recording_since)};{" "}
          <span className="num text-ink">{formatCount(record.resolved)}</span> have an outcome so
          far.
        </p>
      </header>
      <ul>
        {record.rows.map((row) => (
          <li
            key={`${row.kind}-${row.horizon_days}-${row.key}`}
            className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-line py-2 text-sm first:border-t-0"
          >
            <span>{describe(row)}</span>
            <span className={`num ${row.resolved === 0 ? "text-faint" : "text-muted"}`}>
              {result(row)}
              {row.expected_share != null && row.resolved > 0
                ? `; should be about ${formatShare(row.expected_share, 0)}`
                : ""}
            </span>
          </li>
        ))}
      </ul>
      <Caption>
        Everything else on this page is tested by replaying the past. This is different: each
        day&apos;s forecasts are written down when they are made and never edited, then scored once
        the days they cover have ended. With few results the ranges in brackets are wide, and that
        is the honest reading. A {stepsLabel(longest, asset.trades_continuously)} forecast needs
        that long before it can be scored.
      </Caption>
    </Panel>
  );
}
