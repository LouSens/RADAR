import type { Regime } from "../api/client";
import { useRegime } from "../api/queries";
import { formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime, zoneLabel } from "../lib/time";
import { Panel, type PanelProps } from "./ui";
import { CardSkeleton } from "./Skeleton";

const TONE: Record<string, string> = {
  calm: "var(--calm)",
  normal: "var(--muted)",
  elevated: "var(--gold)",
  turbulent: "var(--alert)",
};

const tone = (label: string) => TONE[label] ?? "var(--accent)";
const title = (label: string) => label.charAt(0).toUpperCase() + label.slice(1);
const days = (value: number) => `${Math.round(value)} day${Math.round(value) === 1 ? "" : "s"}`;

/** The regime on each day of the window, as one continuous band. */
function Timeline({ regime }: { regime: Regime }) {
  const points = regime.history;
  const first = points[0];
  const last = points.at(-1);
  if (!first || !last) return null;
  const start = Date.parse(first.ts);
  const span = Date.parse(last.ts) - start || 1;
  // Merge consecutive days with the same label into one segment.
  const segments: { label: string; from: number; to: number }[] = [];
  for (const point of points) {
    const at = (Date.parse(point.ts) - start) / span;
    const open = segments.at(-1);
    if (open && open.label === point.label) open.to = at;
    else segments.push({ label: point.label, from: open ? open.to : 0, to: at });
  }
  return (
    <div>
      <div
        className="flex h-9 overflow-hidden rounded-lg"
        role="img"
        aria-label={`Market state on each of the last ${points.length} days`}
      >
        {segments.map((segment, i) => (
          <div
            key={i}
            title={title(segment.label)}
            style={{
              width: `${Math.max((segment.to - segment.from) * 100, 0.2)}%`,
              background: tone(segment.label),
              opacity: segment.label === "normal" ? 0.35 : 0.8,
            }}
          />
        ))}
      </div>
      <div className="num mt-2 flex justify-between text-xs text-faint">
        <span>{formatDate(first.ts)}</span>
        <span>{formatDate(last.ts)}</span>
      </div>
    </div>
  );
}

export function RegimePanel({ asset, trust }: PanelProps) {
  const query = useRegime(asset.slug);
  const regime = query.data;
  if (query.isPending) return <CardSkeleton lines={5} />;
  if (query.isError || !regime) return null;

  const current = regime.states.find((s) => s.label === regime.label);
  const evaluation = regime.evaluation;

  return (
    <Panel
      id="market-state"
      title="Current state"
      trust={trust}
      headline={`${title(regime.label)}, ${days(regime.days_in_state)} so far`}
    >
      <div className="grid grid-cols-1 gap-x-12 gap-y-7 @4xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)]">
        <div>
          <div className="flex items-center gap-3">
            <span
              className="h-3 w-3 rounded-full"
              style={{ background: tone(regime.label) }}
              aria-hidden="true"
            />
            <span className="price-lg">{title(regime.label)}</span>
          </div>
          <p className="mt-3 text-sm leading-relaxed text-muted">
            <span className="num text-ink">{formatShare(regime.probability, 0)}</span> probability,
            for <span className="num text-ink">{days(regime.days_in_state)}</span> so far.
            {current && (
              <>
                {" "}
                Stays of this kind have typically lasted{" "}
                <span className="num text-ink">{days(current.typical_duration_days)}</span>.
              </>
            )}
          </p>
          <p className="mt-2 text-xs text-faint">
            As of {formatDateTime(regime.as_of)} {zoneLabel()}
          </p>
        </div>

        <div>
          <Timeline regime={regime} />
          <div className="mt-5 grid grid-cols-1 gap-x-6 @xl:grid-cols-3">
            {regime.states.map((state) => {
              const next = Object.entries(state.next_states).sort((a, b) => b[1] - a[1])[0];
              return (
                <div key={state.label} className="border-t border-line py-3">
                  <div className="flex items-center gap-2 text-sm font-medium">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: tone(state.label) }}
                      aria-hidden="true"
                    />
                    {title(state.label)}
                  </div>
                  <dl className="mt-2 space-y-1 text-sm">
                    <div className="flex justify-between gap-3">
                      <dt className="label">Daily swing</dt>
                      <dd className="num">{formatShare(state.typical_daily_volatility)}</dd>
                    </div>
                    <div className="flex justify-between gap-3">
                      <dt className="label">Typical stay</dt>
                      <dd className="num">{days(state.typical_duration_days)}</dd>
                    </div>
                    {next && (
                      <div className="flex justify-between gap-3">
                        <dt className="label">Usually next</dt>
                        <dd>
                          {title(next[0])}{" "}
                          <span className="num text-muted">{formatShare(next[1], 0)}</span>
                        </dd>
                      </div>
                    )}
                  </dl>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <details className="about">
        <summary>How this works</summary>
        <p className="prose mt-3 text-xs leading-relaxed text-muted">
          The state on each day is estimated from that day and earlier days only, using daily
          returns and volatility for {formatCount(regime.model.n_train)} days from{" "}
          {formatDate(regime.model.train_start)}.
          {evaluation && (
            <>
              {" "}
              Tested on {formatCount(evaluation.n_days)} days the model had not seen (
              {formatDate(evaluation.first_test_day)} to {formatDate(evaluation.last_test_day)}),
              the average swing on the following day was{" "}
              {Object.entries(evaluation.next_day_volatility)
                .map(([label, value]) => `${formatShare(value)} after ${label}`)
                .join(", ")}
              .
              {evaluation.volatility_is_ordered
                ? ""
                : " These are not in order, so treat the state as a weak signal."}
            </>
          )}{" "}
          A change of state is detected after it begins, not before.
        </p>
      </details>
    </Panel>
  );
}
