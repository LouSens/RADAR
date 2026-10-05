import { useStreamStatus } from "../api/live";
import { useHealth } from "../api/queries";
import { Notice, Panel, Pill } from "../components/ui";
import { formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime, formatDuration, zoneLabel } from "../lib/time";

const STATUS_TEXT = {
  ok: "All primary data is current",
  degraded: "Some data needs attention",
  down: "The database cannot be reached",
} as const;

export function StatusPage() {
  const health = useHealth();
  const stream = useStreamStatus();
  const data = health.data;

  return (
    <div className="flex flex-col gap-4">
      <header>
        <h1 className="text-2xl font-semibold">Methodology and status</h1>
        <p className="max-w-[68ch] text-muted">
          Whether data is arriving and how complete it is. Model descriptions and their measured
          accuracy are added here as each model is built. Times are shown in {zoneLabel()}.
        </p>
      </header>

      {health.isPending && <Notice>Checking the system…</Notice>}
      {health.isError && (
        <Notice>The API did not answer. Start it with “uv run radar api”.</Notice>
      )}

      {data && (
        <>
          <Panel title="System">
            <div className="flex flex-wrap gap-2">
              <Pill tone={data.status === "ok" ? "ok" : "warn"}>{STATUS_TEXT[data.status]}</Pill>
              <Pill tone={data.database ? "ok" : "warn"}>
                {data.database ? "Database connected" : "Database unreachable"}
              </Pill>
              <Pill tone={stream === "open" ? "ok" : "warn"}>
                {stream === "open" ? "Live feed connected" : "Live feed not connected"}
              </Pill>
            </div>
            <dl className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
              <div className="rounded-md bg-raised px-3 py-2">
                <dt className="text-xs text-muted">Last data sync</dt>
                <dd className="num">{data.last_sync ? formatDateTime(data.last_sync) : "never"}</dd>
              </div>
              <div className="rounded-md bg-raised px-3 py-2">
                <dt className="text-xs text-muted">Last quality check</dt>
                <dd className="num">
                  {data.quality.last_run ? formatDateTime(data.quality.last_run) : "never"}
                </dd>
              </div>
              <div className="rounded-md bg-raised px-3 py-2">
                <dt className="text-xs text-muted">Quality findings</dt>
                <dd className="num">
                  {formatCount(data.quality.findings)} checks, {data.quality.warnings} warnings,{" "}
                  {data.quality.failures} failures
                </dd>
              </div>
            </dl>
          </Panel>

          <Panel title="Data coverage" aside={`${data.series.length} series`}>
            {data.series.length === 0 ? (
              <Notice>No price data is stored yet. Run “uv run radar backfill”.</Notice>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[640px] border-collapse text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="border-b border-line py-1.5 pr-3 font-medium">Asset</th>
                      <th className="border-b border-line py-1.5 pr-3 font-medium">Bars</th>
                      <th className="border-b border-line py-1.5 pr-3 text-right font-medium">Stored</th>
                      <th className="border-b border-line py-1.5 pr-3 font-medium">From</th>
                      <th className="border-b border-line py-1.5 pr-3 font-medium">Latest bar ended</th>
                      <th className="border-b border-line py-1.5 pr-3 text-right font-medium">Missing</th>
                      <th className="border-b border-line py-1.5 font-medium">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.series.map((s) => (
                      <tr key={`${s.symbol}-${s.timeframe}`}>
                        <td className="border-b border-line py-1.5 pr-3">
                          {s.symbol}
                          {s.is_primary && <span className="text-muted"> · primary</span>}
                        </td>
                        <td className="border-b border-line py-1.5 pr-3">
                          {s.timeframe === "1Hour" ? "Hourly" : "Daily"}
                        </td>
                        <td className="num border-b border-line py-1.5 pr-3 text-right">
                          {formatCount(s.bars)}
                        </td>
                        <td className="num border-b border-line py-1.5 pr-3">{formatDate(s.first_ts)}</td>
                        <td className="num border-b border-line py-1.5 pr-3">
                          {formatDuration(s.lag_seconds)} ago
                        </td>
                        <td className="num border-b border-line py-1.5 pr-3 text-right">
                          {s.missing_share === null ? "not checked" : formatShare(s.missing_share)}
                        </td>
                        <td className="border-b border-line py-1.5">
                          <Pill tone={s.stale ? "warn" : "ok"}>{s.stale ? "Behind" : "Current"}</Pill>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-2 text-xs text-muted">
              “Missing” is the share of bars the trading calendar expects that are not stored, from
              the latest quality check. Stock series are current if a bar arrived in the last 5 days,
              which allows for weekends and holidays.
            </p>
          </Panel>

          <Panel title="Known limits">
            <ul className="list-disc space-y-1 pl-5 text-sm">
              <li>Crypto prices come from one exchange (Kraken, through Alpaca).</li>
              <li>Gold is the GLD fund: no weekend or overnight prices.</li>
              <li>Live stock prices come from one exchange (IEX); stored history is 15 minutes delayed.</li>
              <li>Crypto history starts in 2021, so rare events are under-sampled.</li>
              <li>The newest hour or day is drawn from the live feed and is not stored until it ends.</li>
            </ul>
          </Panel>
        </>
      )}
    </div>
  );
}
