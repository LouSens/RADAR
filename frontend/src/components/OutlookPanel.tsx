import { useState, type FormEvent } from "react";

import type { Asset, Calibration, OutlookHorizon, Simulation } from "../api/client";
import { useCalibration, useLevel, useSimulation } from "../api/queries";
import { formatChange, formatCount, formatPrice, formatShare } from "../lib/format";
import {
  errorAgainstBaseline,
  fanShape,
  histogramBars,
  positionInHistogram,
  shownRange,
  stepsLabel,
} from "../lib/outlook";
import { formatDate } from "../lib/time";
import { Evidence, Caption, Panel, Segmented, StatRow, assetColorVar, type PanelProps } from "./ui";
import { CardSkeleton } from "./Skeleton";

const HORIZONS = [
  { value: "1", label: "1 day" },
  { value: "7", label: "1 week" },
  { value: "30", label: "1 month" },
] as const;
type HorizonKey = (typeof HORIZONS)[number]["value"];

const spread = (low: number | null | undefined, high: number | null | undefined) =>
  low == null || high == null ? "" : ` (${formatShare(low, 0)} to ${formatShare(high, 0)})`;
const percent = (level: number) => `${Math.round(level * 100)}%`;
const rangeText = (low: number, high: number) => `${formatPrice(low)} to ${formatPrice(high)}`;

function Histogram({
  horizon,
  startPrice,
  band,
  colorVar,
}: {
  horizon: OutlookHorizon;
  startPrice: number;
  band: { low: number; high: number } | undefined;
  colorVar: string;
}) {
  const width = 600;
  const height = 150;
  const bars = histogramBars(horizon, width, height);
  const start = positionInHistogram(horizon, startPrice);
  const first = horizon.histogram_edges[0];
  const last = horizon.histogram_edges.at(-1);
  if (!bars.length || first === undefined || last === undefined) return null;
  return (
    <div>
      <div className="relative">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-40 w-full"
          role="img"
          aria-label={`Simulated prices from ${formatPrice(first)} to ${formatPrice(last)}`}
        >
          {bars.map((bar, i) => {
            const middle = (bar.from + bar.to) / 2;
            const inside = band ? middle >= band.low && middle <= band.high : true;
            return (
              <rect
                key={i}
                x={bar.x}
                y={bar.y}
                width={bar.width}
                height={bar.height}
                rx="1"
                fill={`var(${colorVar})`}
                opacity={inside ? 0.85 : 0.28}
              />
            );
          })}
        </svg>
        {start !== undefined && (
          <div
            className="pointer-events-none absolute inset-y-0 border-l border-dashed border-white/50"
            style={{ left: `${start * 100}%` }}
          >
            <span className="num absolute -top-5 -translate-x-1/2 whitespace-nowrap text-xs text-muted">
              Now {formatPrice(startPrice)}
            </span>
          </div>
        )}
      </div>
      <div className="num mt-2 flex justify-between text-xs text-faint">
        <span>{formatPrice(first)}</span>
        <span>{formatPrice(last)}</span>
      </div>
    </div>
  );
}

function Fan({
  simulation,
  steps,
  colorVar,
}: {
  simulation: Simulation;
  steps: number;
  colorVar: string;
}) {
  const width = 600;
  const height = 150;
  const shape = fanShape(simulation.fan, steps, width, height);
  if (!shape) return null;
  return (
    <div>
      <div className="flex gap-3">
        <div className="num flex flex-col justify-between text-right text-xs text-faint">
          <span>{formatPrice(shape.high)}</span>
          <span>{formatPrice(shape.low)}</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-40 min-w-0 flex-1"
          role="img"
          aria-label={`Spread of simulated prices widening from ${formatPrice(
            simulation.start_price,
          )} to between ${formatPrice(shape.low)} and ${formatPrice(shape.high)}`}
        >
          <path d={shape.outer} fill={`var(${colorVar})`} opacity="0.16" />
          <path d={shape.inner} fill={`var(${colorVar})`} opacity="0.3" />
          <path
            d={shape.median}
            fill="none"
            stroke={`var(${colorVar})`}
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
    </div>
  );
}

function LevelCheck({
  asset,
  simulation,
  horizon,
}: {
  asset: Asset;
  simulation: Simulation;
  horizon: OutlookHorizon;
}) {
  const suggestion = Number((simulation.start_price * 1.05).toPrecision(3));
  const [text, setText] = useState(String(suggestion));
  const level = useLevel(asset.slug);
  const value = Number(text);
  const valid = Number.isFinite(value) && value > 0;
  const answer =
    level.data && level.data.level === value && level.data.horizon_days === horizon.horizon_days
      ? level.data
      : undefined;
  const above = value >= simulation.start_price;
  const period = stepsLabel(horizon.steps, asset.trades_continuously);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (valid) level.mutate({ level: value, horizon_days: horizon.horizon_days });
  }

  return (
    <div>
      <h3 className="text-sm font-semibold tracking-tight">Check a price level</h3>
      <form onSubmit={submit} className="mt-3 flex flex-wrap items-end gap-3">
        <label className="min-w-0 flex-1">
          <span className="label">Price in US dollars</span>
          <input
            type="number"
            inputMode="decimal"
            min="0"
            step="any"
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="num well mt-1 block w-full px-3 py-2 text-base text-ink outline-none focus:border-white/30"
          />
        </label>
        <button type="submit" className="btn btn-ghost" disabled={!valid || level.isPending}>
          {level.isPending ? "Counting…" : "Check"}
        </button>
      </form>
      {level.isError && (
        <p className="mt-3 text-sm text-alert">That could not be checked. Try again shortly.</p>
      )}
      {answer ? (
        <dl className="mt-3">
          <StatRow label={`Ends ${above ? "at or above" : "below"} ${formatPrice(answer.level)}`}>
            {formatShare(above ? answer.ends_above : answer.ends_below, 1)}
          </StatRow>
          <StatRow label={`Reaches ${formatPrice(answer.level)} at any daily close`}>
            {formatShare(answer.touches, 1)}
          </StatRow>
        </dl>
      ) : (
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Enter a price to see how often the simulated outcomes end past it after {period}, and how
          often they touch it on the way.
        </p>
      )}
      {answer && (
        <Caption
          facts={[
            { label: "Shows", value: `Share of ${formatCount(answer.n_paths)} simulated outcomes` },
            { label: "Over", value: period },
            {
              label: "Judged at",
              value: "Each day's close, so a move within a day is not counted",
            },
          ]}
        />
      )}
    </div>
  );
}

function TrackRecord({
  asset,
  calibration,
  horizon,
}: {
  asset: Asset;
  calibration: Calibration;
  horizon: OutlookHorizon;
}) {
  const rows = calibration.rows.filter((row) => row.horizon_days === horizon.horizon_days);
  const first = rows[0];
  if (!first) return null;
  const error = errorAgainstBaseline(first);
  const level = Math.abs(error) < 0.005;
  return (
    <Evidence summary="How past ranges held">
      <div>
        <table className="w-full text-sm">
          <thead>
            <tr className="label text-left">
              <th className="pb-2 font-normal">Range</th>
              <th className="pb-2 text-right font-normal">Held</th>
              <th className="pb-2 text-right font-normal">Held, adjusted</th>
              <th className="pb-2 text-right font-normal">Cases</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.nominal} className="border-t border-line">
                <td className="num py-2">{percent(row.nominal)}</td>
                <td className="num py-2 text-right">
                  {formatShare(row.empirical, 1)}
                  <span className="text-muted">
                    {spread(row.empirical_low, row.empirical_high)}
                  </span>
                </td>
                <td className="num py-2 text-right">
                  {formatShare(row.empirical_conformal, 1)}
                  <span className="text-muted">
                    {spread(row.conformal_low, row.conformal_high)}
                  </span>
                </td>
                <td className="num py-2 text-right">{formatCount(row.n)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="prose text-sm leading-relaxed text-muted">
        For every day from {formatDate(first.first_origin)} to {formatDate(first.last_origin)} the
        simulation was run using only what was known that day, looking{" "}
        {stepsLabel(first.steps, asset.trades_continuously)} ahead, then compared with what
        happened. A range that works should hold about as often as it states. The figures in
        brackets are where the true rate plausibly lies; a range is doing its job when its stated
        level falls inside them. The adjustment widens or narrows each range using how earlier
        ranges held.{" "}
        {level
          ? "Its forecast error was about level with a simple forecast that assumes constant volatility."
          : `Its forecast error was ${formatShare(Math.abs(error), 1)} ${
              error < 0 ? "lower" : "higher"
            } than a simple forecast that assumes constant volatility${
              error < 0 ? "." : ", so here the simulation adds nothing over that simple forecast."
            }`}
      </p>
    </Evidence>
  );
}

export function OutlookPanel({ asset, trust }: PanelProps) {
  const query = useSimulation(asset.slug);
  const simulation = query.data;
  const calibration = useCalibration(asset.slug).data;
  const [key, setKey] = useState<HorizonKey>("7");
  if (query.isPending) return <CardSkeleton lines={5} />;
  if (!simulation) return null;
  const horizon =
    simulation.horizons.find((h) => String(h.horizon_days) === key) ?? simulation.horizons[0];
  if (!horizon) return null;

  const week = simulation.horizons
    .find((h) => h.horizon_days === 7)
    ?.intervals.find((i) => i.level === 0.8);
  const weekRange = week ? shownRange(week) : undefined;
  const colorVar = assetColorVar(asset);
  const period = stepsLabel(horizon.steps, asset.trades_continuously);
  const ranges = horizon.intervals.map((interval) => ({
    interval,
    ...shownRange(interval),
  }));
  const main = ranges.find((r) => r.interval.level === 0.8) ?? ranges[0];
  const median = horizon.quantiles["0.5"];
  const widest = ranges.filter((r) => r.adjusted && r.interval.adjusted_is_widest);

  return (
    <Panel
      id="outlook"
      title="Price range ahead"
      trust={trust}
      headline={weekRange ? `${rangeText(weekRange.low, weekRange.high)} in a week` : undefined}
    >
      <div className="flex justify-end">
        <Segmented options={HORIZONS} value={key} onChange={setKey} label="How far ahead" />
      </div>

      <div className="grid grid-cols-1 gap-x-12 gap-y-7 @4xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <div>
          {main && (
            <>
              <p className="label">
                {percent(main.interval.level)} of simulated outcomes after {period}
              </p>
              <p className="price-lg mt-2">{rangeText(main.low, main.high)}</p>
            </>
          )}
          <dl className="mt-4">
            {median !== undefined && (
              <StatRow label="Middle outcome">
                {formatPrice(median)}{" "}
                <span className="text-muted">
                  {formatChange(median / simulation.start_price - 1)}
                </span>
              </StatRow>
            )}
            {ranges
              .filter((r) => r !== main)
              .map((r) => (
                <StatRow key={r.interval.level} label={`${percent(r.interval.level)} of outcomes`}>
                  {rangeText(r.low, r.high)}
                </StatRow>
              ))}
            <StatRow label="Typical deepest dip on the way">
              {formatChange(horizon.expected_worst_drawdown)}
            </StatRow>
          </dl>
        </div>
        <div className="pt-5">
          <Histogram
            horizon={horizon}
            startPrice={simulation.start_price}
            band={main}
            colorVar={colorVar}
          />
          <Caption
            facts={[
              { label: "Shows", value: "How the spread of outcomes widens" },
              { label: "Over", value: period },
              { label: "Line", value: "The middle outcome" },
              {
                label: "Bands",
                value: `Darker holds half of ${formatCount(simulation.n_paths)} outcomes, lighter 90%`,
              },
            ]}
          />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-12 gap-y-7 border-t border-line pt-6 @4xl:grid-cols-[minmax(0,1.4fr)_minmax(0,0.8fr)]">
        <div>
          <Fan simulation={simulation} steps={horizon.steps} colorVar={colorVar} />
          <Caption
            facts={[
              {
                label: "Shows",
                value: `Where ${formatCount(simulation.n_paths)} simulated prices end`,
              },
              { label: "Over", value: period },
              { label: "From", value: `The close on ${formatDate(simulation.as_of)}` },
              {
                label: "Brighter bars",
                value: `Inside the ${main ? percent(main.interval.level) : ""} range`,
              },
              { label: "Not drawn", value: "The most extreme 1% of outcomes" },
            ]}
          />
        </div>
        <LevelCheck key={asset.slug} asset={asset} simulation={simulation} horizon={horizon} />
      </div>

      {calibration && <TrackRecord asset={asset} calibration={calibration} horizon={horizon} />}

      <details className="about">
        <summary>How this works</summary>
        <p className="prose mt-3 text-xs leading-relaxed text-muted">
          This is a spread of outcomes, not a prediction. Each simulated path starts from the
          current market state, moves between states as this market has in the past, and draws each
          day&apos;s move from real past moves in that state. It assumes the future resembles the
          past.
          {main?.adjusted
            ? " Ranges shown are adjusted using how earlier ranges held."
            : " How past ranges held has not been measured yet, so ranges are shown as simulated."}
          {widest.length > 0 &&
            ` The ${widest.map((r) => percent(r.interval.level)).join(" and ")} range has been widened as far as it can go for this period, so it covers nearly every simulated outcome.`}
        </p>
      </details>
    </Panel>
  );
}
