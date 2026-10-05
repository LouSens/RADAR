import { useState } from "react";

import type { Asset, RiskHorizon, RiskMethod } from "../api/client";
import { useRisk } from "../api/queries";
import { formatCount, formatShare } from "../lib/format";
import { stepsLabel } from "../lib/outlook";
import { formatDate } from "../lib/time";
import { Caption, Segmented } from "./ui";

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

function Limit({ level, method, period }: { level: number; method: RiskMethod; period: string }) {
  return (
    <div className="well p-4">
      <p className="label">
        Loss limit for {oddsLabel(level)} periods of {period}
      </p>
      <p className="price-lg mt-2">{formatShare(method.var, 1)}</p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        When the loss has gone past this limit, it has averaged about{" "}
        <span className="num text-ink">{formatShare(method.expected_shortfall, 1)}</span>.
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Broken <span className="num text-ink">{formatCount(method.breaches)}</span> times in{" "}
        <span className="num text-ink">{formatCount(method.n)}</span> past periods; about{" "}
        <span className="num text-ink">{expected(method.expected_breaches)}</span> would be
        expected.
      </p>
      {!method.reliable && (
        <p className="mt-2 text-sm text-alert">
          This limit has not held at its stated rate. Treat it as unreliable.
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
    <div className="overflow-x-auto">
      <table className="w-full min-w-[30rem] text-sm">
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

export function RiskPanel({ asset }: { asset: Asset }) {
  const risk = useRisk(asset.slug).data;
  const [key, setKey] = useState<HorizonKey>("1");
  if (!risk) return null;
  const horizon = risk.horizons.find((h) => String(h.horizon_days) === key) ?? risk.horizons[0];
  if (!horizon) return null;
  const period = stepsLabel(horizon.steps, asset.trades_continuously);
  const sample = horizon.levels[0]?.methods[0];

  return (
    <section id="risk" className="glass flex scroll-mt-24 flex-col gap-6 p-5 sm:p-7">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-3">
        <h2 className="text-base font-semibold tracking-tight">Downside risk</h2>
        <Segmented options={HORIZONS} value={key} onChange={setKey} label="Length of period" />
      </header>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {horizon.levels.map((level) => {
          const method = level.methods.find((m) => m.method === horizon.shown);
          return method ? (
            <Limit key={level.level} level={level.level} method={method} period={period} />
          ) : null;
        })}
      </div>

      <div className="border-t border-line pt-5">
        <h3 className="text-sm font-semibold tracking-tight">How each method&apos;s limits held</h3>
        <div className="mt-3">
          <Methods horizon={horizon} />
        </div>
        <Caption>
          Each limit was set using only what was known that day, then compared with the loss that
          followed
          {sample ? `, over ${formatCount(sample.n)} periods of ${period}` : ""} from{" "}
          {formatDate(horizon.first_day)} to {formatDate(horizon.last_day)}. A limit that works is
          broken about as often as it states. The figures shown above come from the method whose
          limits held closest to that. A limit is marked unreliable when it was broken measurably
          more or less often than stated, after allowing for the number of limits tested together.
        </Caption>
      </div>

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
          <Caption>
            Falls from a high to the lowest daily close before the price recovered, since{" "}
            {formatDate(asset.history_start)}.
          </Caption>
        </div>
      )}
    </section>
  );
}
