import { useState } from "react";

import type { NewsTest, VolatilityHorizon } from "../api/client";
import { useNewsTest, useVolatility } from "../api/queries";
import { formatChange, formatCount, formatShare } from "../lib/format";
import { stepsLabel } from "../lib/outlook";
import { formatDate } from "../lib/time";
import { Caption, Panel, Segmented, StatRow, assetColorVar, type PanelProps } from "./ui";

const HORIZONS = [
  { value: "1", label: "1 day" },
  { value: "7", label: "1 week" },
] as const;
type HorizonKey = (typeof HORIZONS)[number]["value"];

const METHOD: Record<string, string> = {
  har: "Recent swings: last day, week, and month",
  gbt: "Tree model with the market state",
  carry: "Yesterday repeated",
  regime: "Average for the current market state",
};

/** Two lines on one scale: what was forecast each day, and what then happened. */
export function linePaths(
  history: VolatilityHorizon["history"],
  width: number,
  height: number,
): { forecast: string; realised: string; high: number } | undefined {
  if (history.length < 2) return undefined;
  const values = history.flatMap((p) =>
    p.realised == null ? [p.forecast] : [p.forecast, p.realised],
  );
  const high = Math.max(...values);
  if (!(high > 0)) return undefined;
  const x = (i: number) => (i / (history.length - 1)) * width;
  const y = (value: number) => height - (value / high) * height;
  const path = (pick: (p: VolatilityHorizon["history"][number]) => number | null | undefined) => {
    let open = false;
    const parts: string[] = [];
    history.forEach((point, i) => {
      const value = pick(point);
      if (value == null) {
        open = false;
        return;
      }
      parts.push(`${open ? "L" : "M"}${x(i).toFixed(1)},${y(value).toFixed(1)}`);
      open = true;
    });
    return parts.join(" ");
  };
  return { forecast: path((p) => p.forecast), realised: path((p) => p.realised), high };
}

function History({ horizon, colorVar }: { horizon: VolatilityHorizon; colorVar: string }) {
  const width = 600;
  const height = 140;
  const paths = linePaths(horizon.history, width, height);
  const first = horizon.history[0];
  const last = horizon.history.at(-1);
  if (!paths || !first || !last) return null;
  return (
    <div>
      <div className="flex gap-3">
        <div className="num flex flex-col justify-between text-right text-xs text-faint">
          <span>{formatShare(paths.high, 1)}</span>
          <span>{formatShare(0, 0)}</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-36 min-w-0 flex-1"
          role="img"
          aria-label="Forecast daily swing against the swing that followed"
        >
          <path
            d={paths.realised}
            fill="none"
            stroke="var(--muted)"
            strokeWidth="1"
            opacity="0.55"
            vectorEffect="non-scaling-stroke"
          />
          <path
            d={paths.forecast}
            fill="none"
            stroke={`var(${colorVar})`}
            strokeWidth="2"
            vectorEffect="non-scaling-stroke"
          />
        </svg>
      </div>
      <div className="num mt-2 flex justify-between pl-12 text-xs text-faint">
        <span>{formatDate(first.ts)}</span>
        <span>{formatDate(last.ts)}</span>
      </div>
    </div>
  );
}

function verdict(pValue: number | null | undefined, worse: boolean): string {
  if (pValue == null) return "Shown";
  if (pValue >= 0.05) return "No measurable difference";
  return worse ? "Measurably worse" : "Measurably better";
}

const FAMILY: Record<string, string> = {
  har: "The method shown",
  gbt: "Tree model",
};

/** Forecast error with and without news, side by side, with the verdict in words. */
export function NewsCheck({ test, horizonDays }: { test: NewsTest; horizonDays: number }) {
  const horizon = test.horizons.find((h) => h.horizon_days === horizonDays) ?? test.horizons[0];
  if (!horizon) return null;
  const reach = Math.max(...horizon.pairs.flatMap((p) => [p.qlike_without, p.qlike_with]), 1e-9);
  const helped = horizon.pairs.some((pair) => pair.verdict === "news helps");
  return (
    <div className="border-t border-line pt-5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="text-sm font-semibold tracking-tight">Does news improve this forecast?</h3>
        <p className={`text-sm font-medium ${helped ? "text-calm" : "text-muted"}`}>
          {helped ? "Yes, measurably" : "No measurable gain"}
        </p>
      </div>
      <div className="mt-4 grid grid-cols-1 gap-x-10 gap-y-5 @xl:grid-cols-2">
        {horizon.pairs.map((pair) => (
          <div key={pair.family}>
            <p className="label">{FAMILY[pair.family] ?? pair.family}</p>
            {[
              { name: "Without news", value: pair.qlike_without, colour: "var(--muted)" },
              { name: "With news", value: pair.qlike_with, colour: "var(--accent)" },
            ].map((row) => (
              <div
                key={row.name}
                className="mt-2 grid grid-cols-[6rem_minmax(0,1fr)_auto] items-center gap-x-3 text-sm"
              >
                <span className="text-muted">{row.name}</span>
                <span className="block h-1.5 rounded-full bg-white/8">
                  <span
                    className="block h-full rounded-full"
                    style={{ width: `${(row.value / reach) * 100}%`, background: row.colour }}
                  />
                </span>
                <span className="num font-medium">{row.value.toFixed(3)}</span>
              </div>
            ))}
            <p className="num mt-2 text-xs text-faint">
              {pair.improvement >= 0 ? "Error lower by " : "Error higher by "}
              {formatShare(Math.abs(pair.improvement), 1)}
              {pair.verdict === "news helps" ? ", more than chance" : ", within chance"}
            </p>
          </div>
        ))}
      </div>
      <Caption>
        The same forecast was made twice on each of {formatCount(horizon.n)} days from{" "}
        {formatDate(horizon.first_day)} to {formatDate(horizon.last_day)}: once from past movement
        alone, and once also knowing how many articles were published that day, how unusual that
        number was, and their tone. Shorter bars mean smaller error. News counts as an improvement
        only if the error is lower by more than chance would give, after allowing for the{" "}
        {test.comparisons} comparisons made across all markets. This rule was written down before
        the test was run.
      </Caption>
    </div>
  );
}

export function VolatilityPanel({ asset, trust }: PanelProps) {
  const volatility = useVolatility(asset.slug).data;
  const newsTest = useNewsTest(asset.slug).data;
  const [key, setKey] = useState<HorizonKey>("1");
  if (!volatility) return null;
  const horizon =
    volatility.horizons.find((h) => String(h.horizon_days) === key) ?? volatility.horizons[0];
  if (!horizon) return null;

  const nextDay = volatility.horizons.find((h) => h.horizon_days === 1);
  const period = stepsLabel(horizon.steps, asset.trades_continuously);
  const shown = horizon.scores.find((s) => s.model === horizon.shown);
  const trees = horizon.shown === "gbt";

  return (
    <Panel
      id="swings"
      title="Daily movement"
      trust={trust}
      headline={nextDay ? `±${formatShare(nextDay.forecast)} a day` : undefined}
    >
      <div className="flex justify-end">
        <Segmented options={HORIZONS} value={key} onChange={setKey} label="How far ahead" />
      </div>

      <div className="grid grid-cols-1 gap-x-12 gap-y-7 @4xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <div>
          <p className="label">Typical daily move expected over the next {period}</p>
          <p className="price-lg mt-2">±{formatShare(horizon.forecast)}</p>
          <dl className="mt-4">
            {horizon.last_realised != null && (
              <>
                <StatRow label={`Over the last ${period} it was`}>
                  ±{formatShare(horizon.last_realised)}
                </StatRow>
                <StatRow label="Forecast against that">
                  {formatChange(horizon.forecast / horizon.last_realised - 1)}
                </StatRow>
              </>
            )}
          </dl>
          <p className="mt-3 text-xs leading-relaxed text-faint">
            This is the size of a typical move in either direction. It says nothing about which
            direction.
          </p>
        </div>
        <div>
          <History horizon={horizon} colorVar={assetColorVar(asset)} />
          <Caption>
            The coloured line is the forecast made on each day; the grey line is the swing that
            followed over the next {period}. Last {formatCount(horizon.history.length)} forecasts.
          </Caption>
        </div>
      </div>

      <div className="border-t border-line pt-5">
        <h3 className="text-sm font-semibold tracking-tight">How each method has done</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[26rem] text-sm">
            <thead>
              <tr className="label text-left">
                <th className="pb-2 font-normal">Method</th>
                <th className="pb-2 text-right font-normal">Forecast error</th>
                <th className="pb-2 text-right font-normal">Against the one shown</th>
              </tr>
            </thead>
            <tbody>
              {horizon.scores.map((score) => (
                <tr key={score.model} className="border-t border-line">
                  <td className="py-2">{METHOD[score.model] ?? score.model}</td>
                  <td className="num py-2 text-right">{score.qlike.toFixed(3)}</td>
                  <td className="py-2 text-right text-muted">
                    {score.model === horizon.shown
                      ? "Shown"
                      : verdict(
                          score.model === "har" && trees
                            ? shown?.dm_p_value_vs_har
                            : score.dm_p_value_vs_har,
                          score.qlike > (shown?.qlike ?? 0),
                        )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Caption>
          Scored on {formatCount(horizon.n)} days from {formatDate(horizon.first_day)} to{" "}
          {formatDate(horizon.last_day)}, each forecast made with only what was known that day.
          Lower error is better; zero would be a perfect forecast.{" "}
          {trees
            ? "The tree model is shown because it was measurably better than the simpler method on those days."
            : "The tree model was not measurably better than the simpler method on those days, so the simpler one is shown."}
        </Caption>
      </div>

      {newsTest && <NewsCheck test={newsTest} horizonDays={horizon.horizon_days} />}
    </Panel>
  );
}
