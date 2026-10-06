import { useState } from "react";

import type { DriverWindow, Trust } from "../api/client";
import { useDrivers } from "../api/queries";
import { formatCount, formatShare } from "../lib/format";
import { formatDate } from "../lib/time";
import { Caption, Panel, Segmented, type PanelProps } from "./ui";

const VERDICT: Record<string, string> = {
  "moves with": "Moves with it",
  "moves against": "Moves against it",
  "no measurable link": "No measurable link",
};

/** The strongest driver in a sentence, or that none is measurable. */
export function driverHeadline(window: DriverWindow, names: Record<string, string>): string {
  const strongest = window.drivers.find((d) => d.symbol === window.strongest);
  if (!strongest) return "No outside force shows a measurable link right now";
  const name = names[strongest.symbol] ?? strongest.symbol;
  return strongest.verdict === "moves with"
    ? `Moving most with ${name}`
    : `Moving most against ${name}`;
}

/** One bar per driver with its 95% range, on a shared scale centred on zero. */
export function DriverBars({
  window,
  names,
}: {
  window: DriverWindow;
  names: Record<string, string>;
}) {
  const reach = Math.max(
    ...window.drivers.flatMap((d) => [Math.abs(d.low), Math.abs(d.high)]),
    1e-9,
  );
  const at = (value: number) => 50 + (value / reach) * 50;
  return (
    <ul className="flex flex-col">
      {window.drivers.map((driver) => {
        const measurable = driver.verdict !== "no measurable link";
        const colour = !measurable
          ? "var(--faint)"
          : driver.coefficient > 0
            ? "var(--calm)"
            : "var(--alert)";
        return (
          <li
            key={driver.symbol}
            className="grid grid-cols-1 gap-x-6 gap-y-2 border-t border-line py-3 first:border-t-0 first:pt-0 @xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]"
          >
            <div className="flex items-baseline justify-between gap-3">
              <span className="font-medium">{names[driver.symbol] ?? driver.symbol}</span>
              <span className={`text-sm ${measurable ? "text-ink" : "text-faint"}`}>
                {VERDICT[driver.verdict] ?? driver.verdict}
              </span>
            </div>
            <div>
              <div className="relative h-4" aria-hidden="true">
                <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                <span
                  className="absolute top-1/2 h-px -translate-y-1/2"
                  style={{
                    left: `${at(driver.low)}%`,
                    width: `${at(driver.high) - at(driver.low)}%`,
                    background: colour,
                  }}
                />
                <span
                  className="absolute top-1/2 h-2.5 w-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full"
                  style={{ left: `${at(driver.coefficient)}%`, background: colour }}
                />
              </div>
              <p className="num mt-1 text-right text-xs text-muted">
                {formatShare(driver.coefficient)} ({formatShare(driver.low)} to{" "}
                {formatShare(driver.high)})
              </p>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function DriverEvidence({
  window,
  names,
  subject,
}: {
  window: DriverWindow;
  names: Record<string, string>;
  subject: string;
}) {
  const score = window.out_of_sample;
  return (
    <>
      <DriverBars window={window} names={names} />
      <Caption>
        Each dot is how much {subject} moved on a day when that force moved by one of its own
        typical days, with the others held still. The line is the 95% range; when it crosses the
        centre, no link can be claimed. Measured on the {formatCount(window.window)} trading days
        from {formatDate(window.first_day)} to {formatDate(window.last_day)}. Each force is
        represented by a fund that tracks it.
      </Caption>
      <dl className="grid grid-cols-1 gap-4 border-t border-line pt-5 @xl:grid-cols-3">
        <div className="well p-4">
          <dt className="label">Moves these forces account for</dt>
          <dd className="price-lg mt-2">{formatShare(window.r_squared, 0)}</dd>
          <dd className="mt-1 text-sm text-muted">In this window. The rest is its own.</dd>
        </div>
        {score && (
          <>
            <div className="well p-4">
              <dt className="label">On days it had not seen</dt>
              <dd className="price-lg mt-2">{formatShare(Math.max(score.r_squared, 0), 0)}</dd>
              <dd className="mt-1 text-sm text-muted">
                Over {formatCount(score.n_days)} days since {formatDate(score.first_day)}.
              </dd>
            </div>
            <div className="well p-4">
              <dt className="label">
                {names[window.baseline] ?? window.baseline} alone, same days
              </dt>
              <dd className="price-lg mt-2">
                {formatShare(Math.max(score.baseline_r_squared, 0), 0)}
              </dd>
              <dd className="mt-1 text-sm text-muted">The simple rival to beat.</dd>
            </div>
          </>
        )}
      </dl>
      <Caption>
        The unseen-day figure fits on one window and predicts the 20 trading days after it, again
        and again. It is the honest one: a model can always explain the days it was fitted on. This
        shows what has moved together, not what causes what.
      </Caption>
    </>
  );
}

const WINDOWS = [
  { value: "250", label: "1 year" },
  { value: "90", label: "90 days" },
] as const;
type WindowKey = (typeof WINDOWS)[number]["value"];

export function DriversPanel({ asset, trust }: PanelProps & { trust?: Trust }) {
  const drivers = useDrivers(asset.slug).data;
  const [key, setKey] = useState<WindowKey>("250");
  if (!drivers) return null;
  const window = drivers.windows.find((w) => String(w.window) === key) ?? drivers.windows.at(-1);
  if (!window) return null;
  const names = drivers.names as Record<string, string>;
  return (
    <Panel
      id="drivers"
      title="What it moves with"
      trust={trust ?? drivers.trust}
      headline={driverHeadline(window, names)}
    >
      <div className="flex justify-end">
        <Segmented options={WINDOWS} value={key} onChange={setKey} label="Period measured" />
      </div>
      <DriverEvidence
        window={window}
        names={names}
        subject={asset.name.split(" (")[0] ?? asset.name}
      />
    </Panel>
  );
}
