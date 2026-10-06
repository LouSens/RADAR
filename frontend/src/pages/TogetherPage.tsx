import { useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import type { CorrelationGrid, Pair, Relationships, Trust } from "../api/client";
import { useAssets, useRelationships } from "../api/queries";
import { Tabs } from "../components/Tabs";
import { Caption, Message, Panel, Segmented, TrustBadge, shortName } from "../components/ui";
import { formatChange, formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime } from "../lib/time";
import {
  TOGETHER_SECTIONS,
  correlationPath,
  headlineSpillovers,
  isTogetherSection,
  linkWords,
  pairKey,
  spillSentence,
  weekendSentence,
} from "../lib/together";

const BASE = "/together";
type Namer = (symbol: string) => string;

const Figure = ({ children }: { children: ReactNode }) => (
  <span className="num font-semibold text-ink">{children}</span>
);

function Line({ trust, to, children }: { trust?: Trust; to: string; children: ReactNode }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-3 gap-y-1.5 border-t border-line py-3 first:border-t-0 first:pt-0">
      <p className="min-w-0 flex-1 basis-72 text-[15px] leading-relaxed">{children}</p>
      <span className="flex shrink-0 items-center gap-3">
        <TrustBadge trust={trust} />
        <Link
          to={to}
          className="text-xs text-muted underline-offset-2 hover:text-ink hover:underline"
        >
          Evidence
        </Link>
      </span>
    </li>
  );
}

function Brief({ data, name }: { data: Relationships; name: Namer }) {
  const now = data.weekend_now;
  return (
    <section className="glass p-5 @xl:p-7" aria-labelledby="in-brief">
      <h2 id="in-brief" className="text-base font-semibold tracking-tight">
        In brief
      </h2>
      <ul className="mt-4">
        {data.pairs.map(
          (pair) =>
            pair.current_90 != null && (
              <Line key={pairKey(pair)} trust={pair.trust} to={`${BASE}/pairs`}>
                Over the last 90 trading days, {name(pair.a)} and {name(pair.b)}{" "}
                {linkWords(pair.current_90)} (<Figure>{pair.current_90.toFixed(2)}</Figure>, against{" "}
                <Figure>{pair.full.toFixed(2)}</Figure> over the whole record).
              </Line>
            ),
        )}
        {headlineSpillovers(data.spillovers)
          .filter((row) => row.verdict === "spills over")
          .map((row) => (
            <Line
              key={`${row.source}-${row.target}`}
              trust={data.spillover_trust}
              to={`${BASE}/spillovers`}
            >
              {spillSentence(row, name)}
            </Line>
          ))}
        {data.weekends.map((row) => (
          <Line key={row.symbol} trust={data.weekend_trust} to={`${BASE}/weekends`}>
            {weekendSentence(row, name)}
          </Line>
        ))}
        {now && (
          <Line to={`${BASE}/weekends`}>
            Bitcoin has moved <Figure>{formatChange(Math.expm1(now.bitcoin_move))}</Figure> since
            stock markets closed on {formatDate(now.since)}.
          </Line>
        )}
      </ul>
      <p className="mt-4 text-xs leading-relaxed text-faint">
        These describe what has happened together in the past. They do not say one market causes
        another to move, and relationships between markets change.
      </p>
    </section>
  );
}

const SERIES = [
  { key: "rolling_90", label: "Last 90 days", colour: "var(--accent)", width: 2 },
  { key: "rolling_30", label: "Last 30 days", colour: "var(--muted)", width: 1 },
  { key: "weighted", label: "Fast-adapting", colour: "var(--gold)", width: 1.5 },
] as const;

function PairChart({ pair, a, b }: { pair: Pair; a: string; b: string }) {
  const width = 600;
  const height = 180;
  const first = pair.series[0];
  const last = pair.series.at(-1);
  if (!first || !last) return null;
  return (
    <div>
      <div className="flex gap-3">
        <div className="num flex flex-col justify-between text-right text-xs text-faint">
          <span>+1</span>
          <span>0</span>
          <span>−1</span>
        </div>
        <svg
          viewBox={`0 0 ${width} ${height}`}
          preserveAspectRatio="none"
          className="h-44 min-w-0 flex-1"
          role="img"
          aria-label={`How closely ${a} and ${b} have moved together over time`}
        >
          <line
            x1="0"
            x2={width}
            y1={height / 2}
            y2={height / 2}
            stroke="var(--line-strong)"
            strokeDasharray="3 4"
            vectorEffect="non-scaling-stroke"
          />
          {SERIES.map((series) => (
            <path
              key={series.key}
              d={correlationPath(
                pair.series.map((point) => point[series.key]),
                width,
                height,
              )}
              fill="none"
              stroke={series.colour}
              strokeWidth={series.width}
              vectorEffect="non-scaling-stroke"
            />
          ))}
        </svg>
      </div>
      <div className="num mt-2 flex justify-between pl-8 text-xs text-faint">
        <span>{formatDate(first.day)}</span>
        <span>{formatDate(last.day)}</span>
      </div>
      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted">
        {SERIES.map((series) => (
          <li key={series.key} className="flex items-center gap-2">
            <span className="h-0.5 w-4" style={{ background: series.colour }} aria-hidden="true" />
            {series.label}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Pairs({ data, name }: { data: Relationships; name: Namer }) {
  const options = data.pairs.map((pair) => ({
    value: pairKey(pair),
    label: `${name(pair.a)} and ${name(pair.b)}`,
  }));
  const [chosen, setChosen] = useState(options[0]?.value ?? "");
  const pair = data.pairs.find((p) => pairKey(p) === chosen) ?? data.pairs[0];
  if (!pair) return <Message>There is not enough shared history yet.</Message>;
  const a = name(pair.a);
  const b = name(pair.b);
  return (
    <Panel
      id="pairs"
      title="Pair by pair"
      trust={pair.trust}
      headline={
        pair.current_90 != null
          ? `${a} and ${b} ${linkWords(pair.current_90)}: ${pair.current_90.toFixed(2)}`
          : undefined
      }
    >
      {options.length > 1 && (
        <div className="-mx-1 overflow-x-auto px-1">
          <Segmented options={options} value={pairKey(pair)} onChange={setChosen} label="Pair" />
        </div>
      )}
      <dl className="grid grid-cols-2 gap-4 @xl:grid-cols-4">
        {[
          ["Last 30 days", pair.current_30],
          ["Last 90 days", pair.current_90],
          ["Fast-adapting", pair.current_weighted],
          ["Whole record", pair.full],
        ].map(([label, value]) => (
          <div key={String(label)} className="well p-4">
            <dt className="label">{label}</dt>
            <dd className="price-lg mt-2">{typeof value === "number" ? value.toFixed(2) : "–"}</dd>
          </div>
        ))}
      </dl>
      <PairChart pair={pair} a={a} b={b} />
      <Caption>
        Correlation of daily returns: +1 means they always move together, 0 means no link, −1 means
        always opposite. The 90-day reading has a 95% range of{" "}
        {pair.low_90 != null && pair.high_90 != null
          ? `${pair.low_90.toFixed(2)} to ${pair.high_90.toFixed(2)}`
          : "unknown width"}
        . The fast-adapting line counts recent days more, so a change shows in it sooner. The chart
        covers the last {formatCount(pair.series.length)} trading days; the whole record is{" "}
        {formatCount(pair.n_days)} days from {formatDate(pair.first_day)}. Markets that shut at
        weekends are compared with Bitcoin&apos;s move from Friday&apos;s close to Monday&apos;s
        close.
      </Caption>

      <div className="border-t border-line pt-5">
        <h3 className="text-sm font-semibold tracking-tight">
          By the state {name(pair.regime_of)} was in
        </h3>
        <ul className="mt-3">
          {pair.by_regime.map((row) => (
            <li
              key={row.label}
              className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 border-t border-line py-2.5 text-sm first:border-t-0"
            >
              <span className="capitalize">{row.label}</span>
              <span className="num text-muted">
                {row.correlation != null && row.low != null && row.high != null ? (
                  <>
                    <span className="font-medium text-ink">{row.correlation.toFixed(2)}</span> (
                    {row.low.toFixed(2)} to {row.high.toFixed(2)})
                  </>
                ) : (
                  "too few days to say"
                )}{" "}
                · {formatCount(row.n)} days
              </span>
            </li>
          ))}
        </ul>
        <Caption>
          The same correlation, measured separately on the days each state applied. The state is the
          one known at the time. Ranges in brackets are 95% ranges; where they overlap, the states
          do not differ measurably.
        </Caption>
      </div>
    </Panel>
  );
}

function cellColour(value: number): string {
  const strength = Math.round(Math.min(Math.abs(value), 1) * 70);
  return `color-mix(in srgb, ${value >= 0 ? "var(--accent)" : "var(--alert)"} ${strength}%, transparent)`;
}

function GridTable({ grid, name }: { grid: CorrelationGrid; name: Namer }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[34rem] border-separate border-spacing-0.5 text-xs">
        <thead>
          <tr>
            <th />
            {grid.symbols.map((symbol) => (
              <th key={symbol} className="label px-1 pb-1 text-center font-normal">
                {symbol.split("/")[0]}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.symbols.map((symbol, i) => (
            <tr key={symbol}>
              <th className="whitespace-nowrap pr-2 text-left text-[13px] font-normal">
                {name(symbol)}
              </th>
              {grid.matrix[i]?.map((value, j) => (
                <td
                  key={j}
                  className="num rounded-md px-1 py-2 text-center"
                  style={{ background: i === j ? "transparent" : cellColour(value) }}
                  title={`${name(symbol)} and ${name(grid.symbols[j] ?? "")}`}
                >
                  {i === j ? "" : value.toFixed(2)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const SPANS = [
  { value: "recent", label: "Last 90 days" },
  { value: "full", label: "Whole record" },
] as const;

function AllMarkets({ data, name }: { data: Relationships; name: Namer }) {
  const [span, setSpan] = useState<(typeof SPANS)[number]["value"]>("recent");
  const grid = span === "recent" ? data.grid_recent : data.grid_full;
  if (!grid) return <Message>There is not enough shared history yet.</Message>;
  return (
    <Panel id="grid" title="All markets" headline="Which markets behave alike">
      <div className="flex justify-end">
        <Segmented options={SPANS} value={span} onChange={setSpan} label="Period" />
      </div>
      <GridTable grid={grid} name={name} />
      <Caption>
        Correlation of daily returns between every pair, on the {formatCount(grid.n_days)} trading
        days from {formatDate(grid.first_day)} to {formatDate(grid.last_day)} that all of them have
        prices for. Blue cells moved together, red cells moved opposite ways, and stronger colour
        means a closer link. Markets that behave alike are placed next to each other.
      </Caption>
    </Panel>
  );
}

function Spillovers({ data, name }: { data: Relationships; name: Namer }) {
  const found = headlineSpillovers(data.spillovers).filter((r) => r.verdict === "spills over");
  return (
    <Panel
      id="spillovers"
      title="When one turns rough"
      trust={data.spillover_trust}
      headline={
        found.length > 0
          ? `${found.length} of ${headlineSpillovers(data.spillovers).length} pairs show larger swings afterwards`
          : "No pair shows measurably larger swings afterwards"
      }
    >
      <ul>
        {headlineSpillovers(data.spillovers).map((row) => (
          <li
            key={`${row.source}-${row.target}`}
            className="border-t border-line py-4 first:border-t-0 first:pt-0"
          >
            <p className="leading-relaxed">{spillSentence(row, name)}</p>
            <ul className="mt-2 grid grid-cols-1 gap-x-8 text-sm @xl:grid-cols-3">
              {data.spillovers
                .filter((r) => r.source === row.source && r.target === row.target)
                .map((r) => (
                  <li key={r.steps} className="num flex justify-between gap-3 py-1 text-muted">
                    <span>
                      Next {r.steps} session{r.steps === 1 ? "" : "s"}
                    </span>
                    <span>
                      {r.ratio != null && r.ratio_low != null && r.ratio_high != null ? (
                        <>
                          <span
                            className={r.verdict === "spills over" ? "font-medium text-ink" : ""}
                          >
                            {r.ratio.toFixed(2)}×
                          </span>{" "}
                          ({r.ratio_low.toFixed(2)} to {r.ratio_high.toFixed(2)})
                        </>
                      ) : (
                        "–"
                      )}
                    </span>
                  </li>
                ))}
            </ul>
            <p className="mt-1 text-xs text-faint">{formatCount(row.episodes)} past episodes</p>
          </li>
        ))}
      </ul>
      <Caption>
        An episode starts on the first day a market&apos;s state reads turbulent after a stretch
        when it did not, using the reading available that day. The figure is the other market&apos;s
        average daily swing over the sessions that followed, as a multiple of its usual swing, with
        a 95% range. A pair is said to spill over only when that is larger than chance would give,
        after allowing for the {data.spillovers.length} comparisons made. Fewer than 15 episodes is
        too few to judge. Two markets can both be reacting to the same news; this does not show that
        one causes the other.
      </Caption>
    </Panel>
  );
}

function Weekends({ data, name }: { data: Relationships; name: Namer }) {
  const now = data.weekend_now;
  const linked = data.weekends.filter((w) => w.verdict === "moves with");
  return (
    <Panel
      id="weekends"
      title="Weekend gaps"
      trust={data.weekend_trust}
      headline={
        linked.length > 0
          ? `${linked.map((w) => name(w.symbol)).join(" and ")} open in line with Bitcoin's weekend`
          : "No measurable link to Bitcoin's weekend move"
      }
    >
      {now && (
        <div className="well p-4">
          <p className="label">While stock markets are shut</p>
          <p className="price-lg mt-2">{formatChange(Math.expm1(now.bitcoin_move))}</p>
          <p className="mt-1 text-sm text-muted">
            Bitcoin&apos;s move since the close on {formatDate(now.since)}, as of{" "}
            {formatDateTime(now.as_of)}.
          </p>
          {linked.map(
            (row) =>
              row.slope != null && (
                <p key={row.symbol} className="mt-2 text-sm leading-relaxed text-muted">
                  Historically {name(row.symbol)} opened by about{" "}
                  <span className="num text-ink">{formatShare(Math.abs(row.slope), 0)}</span> of a
                  move like this, which would be{" "}
                  <span className="num text-ink">
                    {formatChange(row.slope * Math.expm1(now.bitcoin_move))}
                  </span>
                  . Single weekends vary widely around that.
                </p>
              ),
          )}
        </div>
      )}
      <ul>
        {data.weekends.map((row) => (
          <li key={row.symbol} className="border-t border-line py-4 first:border-t-0 first:pt-0">
            <p className="leading-relaxed">{weekendSentence(row, name)}</p>
            {row.correlation != null && row.low != null && row.high != null && (
              <dl className="num mt-2 grid grid-cols-1 gap-x-8 text-sm text-muted @xl:grid-cols-3">
                <div className="flex justify-between gap-3 py-1">
                  <dt>Correlation</dt>
                  <dd>
                    <span className="text-ink">{row.correlation.toFixed(2)}</span> (
                    {row.low.toFixed(2)} to {row.high.toFixed(2)})
                  </dd>
                </div>
                <div className="flex justify-between gap-3 py-1">
                  <dt>Usual Monday open</dt>
                  <dd>{row.gap_usual != null ? formatChange(row.gap_usual) : "–"}</dd>
                </div>
                <div className="flex justify-between gap-3 py-1">
                  <dt>After Bitcoin&apos;s worst weekends</dt>
                  <dd className="text-ink">
                    {row.gap_after_worst != null ? formatChange(row.gap_after_worst) : "–"}
                  </dd>
                </div>
              </dl>
            )}
            <p className="mt-1 text-xs text-faint">
              {formatCount(row.weekends)} weekends
              {row.worst_count > 0 ? `; the worst tenth is ${row.worst_count}` : ""}
            </p>
          </li>
        ))}
      </ul>
      <Caption>
        Bitcoin trades while stock markets are shut. Each weekend compares Bitcoin&apos;s move from
        the last close to the next open with where the market opened against its last close. Long
        weekends are included. Bitcoin&apos;s price at the open is the last one known before it. A
        link is claimed only when it is larger than chance would give.
      </Caption>
    </Panel>
  );
}

export function TogetherPage() {
  const { section } = useParams();
  const assets = useAssets().data ?? [];
  const query = useRelationships();
  if (!isTogetherSection(section)) return <Navigate to={BASE} replace />;
  const name: Namer = (symbol) => {
    const asset = assets.find((a) => a.symbol === symbol);
    return asset ? shortName(asset) : symbol;
  };
  const data = query.data ?? undefined;

  return (
    <div className="flex flex-col gap-4 @xl:gap-6">
      <div className="aurora" aria-hidden="true" />
      <header className="flex items-baseline gap-3">
        <h1 className="title">Markets together</h1>
      </header>
      <Tabs base={BASE} items={TOGETHER_SECTIONS} label="Markets together pages" />
      {query.isPending && <Message>Loading…</Message>}
      {!query.isPending && !data && <Message>Nothing is stored for this yet.</Message>}
      {data && (section === undefined || section === "") && <Brief data={data} name={name} />}
      {data && section === "pairs" && <Pairs data={data} name={name} />}
      {data && section === "grid" && <AllMarkets data={data} name={name} />}
      {data && section === "spillovers" && <Spillovers data={data} name={name} />}
      {data && section === "weekends" && <Weekends data={data} name={name} />}
    </div>
  );
}
