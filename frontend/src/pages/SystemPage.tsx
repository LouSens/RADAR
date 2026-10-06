import { useStreamStatus } from "../api/live";
import { useHealth } from "../api/queries";
import { Card, CardHeader, Message } from "../components/ui";
import { formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime, formatDuration, zoneLabel } from "../lib/time";

const HEADLINE = {
  ok: "All systems normal",
  degraded: "Some data is behind",
  down: "Data is unavailable",
} as const;

const ABOUT = [
  "Crypto prices come from one exchange, Kraken.",
  "Gold is represented by the GLD fund, which has no weekend or overnight prices.",
  "Live stock prices come from one exchange (IEX). Stored stock history is 15 minutes delayed.",
  "Crypto history starts in 2021, so rare events are thinly represented.",
  "The newest point on a chart is drawn from the live feed until its hour or day ends.",
];

function Dot({ good }: { good: boolean }) {
  return (
    <span
      className={`inline-block h-2 w-2 shrink-0 rounded-full ${good ? "bg-calm" : "bg-alert"}`}
      aria-hidden="true"
    />
  );
}

function Summary({ label, value, good }: { label: string; value: string; good: boolean }) {
  return (
    <div className="flex items-center justify-between gap-4 px-5 py-4 @xl:block @xl:py-5">
      <div className="label">{label}</div>
      <div className="flex items-center gap-2.5 font-medium @xl:mt-2">
        <Dot good={good} />
        <span className="num">{value}</span>
      </div>
    </div>
  );
}

export function SystemPage() {
  const health = useHealth();
  const stream = useStreamStatus();
  const data = health.data;
  const issues = data ? data.quality.warnings + data.quality.failures : 0;

  return (
    <div className="flex flex-col gap-6 @xl:gap-8">
      <header className="rise">
        <h1 className="title">System</h1>
        <p className="label mt-1">
          {data ? HEADLINE[data.status] : "Data feeds and coverage"} · times in {zoneLabel()}
        </p>
      </header>

      {health.isPending && <Message>Checking…</Message>}
      {health.isError && <Message>System status is unavailable right now.</Message>}

      {data && (
        <>
          <div className="glass rise rise-2 grid grid-cols-1 divide-y divide-line @xl:grid-cols-3 @xl:divide-x @xl:divide-y-0">
            <Summary
              label="Live prices"
              value={stream === "open" ? "Connected" : "Disconnected"}
              good={stream === "open"}
            />
            <Summary
              label="Last update"
              value={data.last_sync ? formatDateTime(data.last_sync) : "Never"}
              good={data.database && data.last_sync !== null}
            />
            <Summary
              label="Data checks"
              value={
                data.quality.last_run === null
                  ? "Not run yet"
                  : issues === 0
                    ? `${formatCount(data.quality.findings)} passed`
                    : `${formatCount(issues)} to review`
              }
              good={data.quality.last_run !== null && issues === 0}
            />
          </div>

          <Card className="rise rise-3 p-5 @xl:p-6">
            <CardHeader title="Coverage" />
            {data.series.length === 0 ? (
              <Message>No price history has been loaded yet.</Message>
            ) : (
              <div className="-mx-2 overflow-x-auto px-2">
                <table className="w-full min-w-[640px] border-collapse text-sm">
                  <thead>
                    <tr className="label text-xs">
                      <th
                        scope="col"
                        className="border-b border-line pb-2 pr-3 text-left font-normal"
                      >
                        Market
                      </th>
                      <th
                        scope="col"
                        className="border-b border-line pb-2 pr-3 text-left font-normal"
                      >
                        Interval
                      </th>
                      <th
                        scope="col"
                        className="border-b border-line pb-2 pr-3 text-right font-normal"
                      >
                        Bars
                      </th>
                      <th
                        scope="col"
                        className="border-b border-line pb-2 pr-3 text-left font-normal"
                      >
                        Since
                      </th>
                      <th
                        scope="col"
                        className="border-b border-line pb-2 pr-3 text-left font-normal"
                      >
                        Updated
                      </th>
                      <th scope="col" className="border-b border-line pb-2 text-right font-normal">
                        Gaps
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.series.map((s) => (
                      <tr key={`${s.symbol}-${s.timeframe}`}>
                        <td className="border-b border-line py-2.5 pr-3 font-medium">{s.symbol}</td>
                        <td className="border-b border-line py-2.5 pr-3 text-muted">
                          {s.timeframe === "1Hour" ? "Hourly" : "Daily"}
                        </td>
                        <td className="num border-b border-line py-2.5 pr-3 text-right">
                          {formatCount(s.bars)}
                        </td>
                        <td className="num border-b border-line py-2.5 pr-3 text-muted">
                          {formatDate(s.first_ts)}
                        </td>
                        <td className="border-b border-line py-2.5 pr-3">
                          <span className="inline-flex items-center gap-2">
                            <Dot good={!s.stale} />
                            <span className="num">{formatDuration(s.lag_seconds)} ago</span>
                            {s.stale && <span className="text-alert">behind</span>}
                          </span>
                        </td>
                        <td className="num border-b border-line py-2.5 text-right text-muted">
                          {s.missing_share === null ? "–" : formatShare(s.missing_share)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-4 max-w-[78ch] text-xs leading-relaxed text-faint">
              Gaps is the share of bars the trading calendar expects that are missing. Stock markets
              count as up to date for 5 days after their last bar, to allow for weekends and
              holidays.
            </p>
          </Card>

          <Card className="p-5 @xl:p-6">
            <CardHeader title="About the data" />
            <ul className="flex flex-col">
              {ABOUT.map((line) => (
                <li
                  key={line}
                  className="border-b border-line py-2.5 text-sm text-muted last:border-b-0"
                >
                  {line}
                </li>
              ))}
            </ul>
          </Card>
        </>
      )}
    </div>
  );
}
