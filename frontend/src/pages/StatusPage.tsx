import { useStreamStatus } from "../api/live";
import { useHealth } from "../api/queries";
import { Notice, Panel, Pill, SectionLabel, Stat } from "../components/ui";
import { formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime, formatDuration, zoneLabel } from "../lib/time";

const STATUS_TEXT = {
  ok: "All primary data is current",
  degraded: "Some data needs attention",
  down: "The database cannot be reached",
} as const;

const LIMITS = [
  "Crypto prices come from one exchange (Kraken, through Alpaca).",
  "Gold is the GLD fund: no weekend or overnight prices.",
  "Live stock prices come from one exchange (IEX); stored history is 15 minutes delayed.",
  "Crypto history starts in 2021, so rare events are under-sampled.",
  "The newest hour or day is drawn from the live feed and is not stored until it ends.",
];

export function StatusPage() {
  const health = useHealth();
  const stream = useStreamStatus();
  const data = health.data;

  return (
    <div className="flex flex-col gap-10">
      <header className="rise">
        <h1 className="display text-fluid-h2">Methodology and status</h1>
        <p className="mt-3 max-w-[64ch] text-muted">
          Whether data is arriving and how complete it is. Model descriptions and their measured
          accuracy are added here as each model is built. Times are shown in {zoneLabel()}.
        </p>
      </header>

      {health.isPending && <Notice>Checking the system…</Notice>}
      {health.isError && <Notice>The API did not answer. Start it with “uv run radar api”.</Notice>}

      {data && (
        <>
          <section className="rise rise-2">
            <SectionLabel>System</SectionLabel>
            <div className="mb-4 flex flex-wrap gap-2">
              <Pill tone={data.status === "ok" ? "ok" : "warn"}>{STATUS_TEXT[data.status]}</Pill>
              <Pill tone={data.database ? "ok" : "warn"}>
                {data.database ? "Database connected" : "Database unreachable"}
              </Pill>
              <Pill tone={stream === "open" ? "ok" : "warn"}>
                {stream === "open" ? "Live feed connected" : "Live feed not connected"}
              </Pill>
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <Stat label="Last data sync" value={data.last_sync ? formatDateTime(data.last_sync) : "never"} />
              <Stat
                label="Last quality check"
                value={data.quality.last_run ? formatDateTime(data.quality.last_run) : "never"}
              />
              <Stat
                label="Quality findings"
                value={`${formatCount(data.quality.findings)} checks · ${data.quality.warnings} warnings · ${data.quality.failures} failures`}
              />
            </div>
          </section>

          <Panel title="Data coverage" aside={`${data.series.length} series`}>
            {data.series.length === 0 ? (
              <Notice>No price data is stored yet. Run “uv run radar backfill”.</Notice>
            ) : (
              <div className="-mx-2 overflow-x-auto px-2">
                <table className="w-full min-w-[680px] border-collapse text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted">
                      <th className="border-b border-line pb-2 pr-3 font-medium">Asset</th>
                      <th className="border-b border-line pb-2 pr-3 font-medium">Bars</th>
                      <th className="border-b border-line pb-2 pr-3 text-right font-medium">Stored</th>
                      <th className="border-b border-line pb-2 pr-3 font-medium">From</th>
                      <th className="border-b border-line pb-2 pr-3 font-medium">Latest bar ended</th>
                      <th className="border-b border-line pb-2 pr-3 text-right font-medium">Missing</th>
                      <th className="border-b border-line pb-2 font-medium">State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.series.map((s) => (
                      <tr key={`${s.symbol}-${s.timeframe}`} className="hover:bg-white/[0.025]">
                        <td className="border-b border-line py-2.5 pr-3 font-medium">
                          {s.symbol}
                          {s.is_primary && <span className="font-normal text-faint"> · primary</span>}
                        </td>
                        <td className="border-b border-line py-2.5 pr-3 text-muted">
                          {s.timeframe === "1Hour" ? "Hourly" : "Daily"}
                        </td>
                        <td className="num border-b border-line py-2.5 pr-3 text-right">
                          {formatCount(s.bars)}
                        </td>
                        <td className="num border-b border-line py-2.5 pr-3 text-muted">
                          {formatDate(s.first_ts)}
                        </td>
                        <td className="num border-b border-line py-2.5 pr-3">
                          {formatDuration(s.lag_seconds)} ago
                        </td>
                        <td className="num border-b border-line py-2.5 pr-3 text-right">
                          {s.missing_share === null ? "not checked" : formatShare(s.missing_share)}
                        </td>
                        <td className="border-b border-line py-2.5">
                          <Pill tone={s.stale ? "warn" : "ok"}>{s.stale ? "Behind" : "Current"}</Pill>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="mt-4 max-w-[80ch] text-xs leading-relaxed text-muted">
              “Missing” is the share of bars the trading calendar expects that are not stored, from the
              latest quality check. Stock series are current if a bar arrived in the last 5 days, which
              allows for weekends and holidays.
            </p>
          </Panel>

          <section>
            <SectionLabel>Known limits</SectionLabel>
            <ul className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {LIMITS.map((limit) => (
                <li key={limit} className="well px-4 py-3 text-sm text-muted">
                  {limit}
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
