import { useState } from "react";

import type { RiskHorizon, RiskMethod } from "../api/client";
import { useRisk } from "../api/queries";
import { formatCount, formatShare } from "../lib/format";
import { formatDate } from "../lib/time";
import { Caption, Evidence, Panel, Segmented, type PanelProps } from "./ui";

const HORIZONS = [
  { value: "1", label: "1 day" },
  { value: "7", label: "1 week" },
] as const;
type HorizonKey = (typeof HORIZONS)[number]["value"];

const METHOD: Record<string, string> = {
  historical: "Past losses as they were",
  filtered: "Past losses scaled to expected swings",
  simulator: "Outlook simulation",
};

/** "19 in 20" for 95%, "99 in 100" for 99%. */
export function oddsLabel(level: number): string {
  const misses = Math.round((1 - level) * 100);
  return misses === 5 ? "19 in 20" : `${100 - misses} in 100`;
}

const expected = (value: number) => (value < 10 ? value.toFixed(1) : value.toFixed(0));

/** "A bad day (about 1 in 20)", "A very bad week (about 1 in 100)". */
export function badLabel(level: number, steps: number): string {
  const unit = steps === 1 ? "day" : "week";
  return `A ${level >= 0.99 ? "very bad" : "bad"} ${unit} (about 1 in ${Math.round(1 / (1 - level))})`;
}

function Limit({ level, method, steps }: { level: number; method: RiskMethod; steps: number }) {
  const unit = steps === 1 ? "days" : "weeks";
  return (
    <div className="well p-4">
      <p className="label">{badLabel(level, steps)}</p>
      <p className="price-lg mt-2">{formatShare(method.var, 1)}</p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Beyond that, losses have averaged{" "}
        <span className="num text-ink">{formatShare(method.expected_shortfall, 1)}</span>.
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Passed <span className="num text-ink">{formatCount(method.breaches)}</span> times in{" "}
        <span className="num text-ink">{formatCount(method.n)}</span> past {unit}; about{" "}
        <span className="num text-ink">{expected(method.expected_breaches)}</span> expected.
      </p>
      {!method.reliable && (
        <p className="mt-2 text-sm text-alert">
          This figure has not held up in the past. Treat it as rough.
        </p>
      )}
    </div>
  );
}

function Methods({ horizon }: { horizon: RiskHorizon }) {
  const names = [...new Set(horizon.levels.flatMap((level) => level.methods.map((m) => m.method)))];
  const cell = (name: string, level: number) =>
    horizon.levels.find((l) => l.level === level)?.methods.find((m) => m.method === name);
  return (
    <div>
      <table className="w-full text-sm">
        <thead>
          <tr className="label text-left">
            <th className="pb-2 font-normal">Method</th>
            {horizon.levels.map((level) => (
              <th key={level.level} className="pb-2 text-right font-normal" colSpan={2}>
                {oddsLabel(level.level)} limit, and times broken
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {names.map((name) => (
            <tr key={name} className="border-t border-line">
              <td className="py-2">
                {METHOD[name] ?? name}
                {name === horizon.shown && <span className="text-muted"> (shown)</span>}
              </td>
              {horizon.levels.map((level) => {
                const method = cell(name, level.level);
                return method ? (
                  <td key={level.level} className="num py-2 text-right" colSpan={2}>
                    {formatShare(method.var, 1)}{" "}
                    <span className={method.reliable ? "text-muted" : "text-alert"}>
                      {formatCount(method.breaches)} of {formatCount(method.n)}
                      {method.reliable ? "" : ", unreliable"}
                    </span>
                  </td>
                ) : (
                  <td key={level.level} className="py-2 text-right text-faint" colSpan={2}>
                    –
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function RiskPanel({ asset, trust }: PanelProps) {
  const risk = useRisk(asset.slug).data;
  const [key, setKey] = useState<HorizonKey>("1");
  if (!risk) return null;
  const horizon = risk.horizons.find((h) => String(h.horizon_days) === key) ?? risk.horizons[0];
  if (!horizon) return null;
  const day = risk.horizons.find((h) => h.horizon_days === 1);
  const dayLimit = day?.levels
    .find((l) => l.level === 0.95)
    ?.methods.find((m) => m.method === day.shown);
  const sample = horizon.levels[0]?.methods[0];

  return (
    <Panel
      id="risk"
      title="Possible loss"
      trust={trust}
      headline={dayLimit ? `A bad day could cost ${formatShare(dayLimit.var, 1)}` : undefined}
    >
      <div className="flex justify-end">
        <Segmented options={HORIZONS} value={key} onChange={setKey} label="Over" />
      </div>

      <div className="grid grid-cols-1 gap-4 @xl:grid-cols-2">
        {horizon.levels.map((level) => {
          const method = level.methods.find((m) => m.method === horizon.shown);
          return method ? (
            <Limit key={level.level} level={level.level} method={method} steps={horizon.steps} />
          ) : null;
        })}
      </div>

      <Evidence>
        <p className="prose text-sm leading-relaxed text-muted">
          Each figure was set on a past day from what was known then, and compared with the loss
          that followed
          {sample ? `, ${formatCount(sample.n)} times` : ""} from {formatDate(horizon.first_day)} to{" "}
          {formatDate(horizon.last_day)}. A good figure is passed about as often as it says. Three
          ways of working it out were tried; the one that held best is shown.
        </p>
        <Methods horizon={horizon} />
      </Evidence>

      {risk.drawdowns.length > 0 && (
        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold tracking-tight">Deepest falls on record</h3>
          <ul className="mt-3">
            {risk.drawdowns.map((fall) => (
              <li
                key={fall.peak_day}
                className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-line py-2 text-sm first:border-t-0"
              >
                <span className="num font-medium text-alert">{formatShare(fall.depth, 1)}</span>
                <span className="text-muted">
                  {formatDate(fall.peak_day)} to {formatDate(fall.trough_day)},{" "}
                  {fall.recovered_day
                    ? `recovered by ${formatDate(fall.recovered_day)}`
                    : "not yet recovered"}
                </span>
              </li>
            ))}
          </ul>
          <Caption
            facts={[
              {
                label: "Shows",
                value: "Every fall from a high to the lowest close before it recovered",
              },
              { label: "Window", value: `Since ${formatDate(asset.history_start)}` },
            ]}
          />
        </div>
      )}
    </Panel>
  );
}
