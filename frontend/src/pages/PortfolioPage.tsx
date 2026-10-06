import { Fragment, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import type { LimitHorizon, Portfolio, PortfolioAnalysis, PortfolioLimit } from "../api/client";
import { usePortfolio, usePortfolioAnalysis, useRelationships } from "../api/queries";
import { DriverEvidence, driverHeadline } from "../components/DriversPanel";
import { HoldingsEditor } from "../components/HoldingsEditor";
import { LevelsPanel, MixesPanel, targetSummary } from "../components/PlanPanels";
import { oddsLabel } from "../components/RiskPanel";
import { Tabs } from "../components/Tabs";
import { Caption, Message, Panel, Segmented } from "../components/ui";
import {
  Bars,
  Donut,
  OneIn,
  RiskScale,
  StateChip,
  Tile,
  TileGrid,
  holdingColour,
  levelColour,
  type Part,
} from "../components/viz";
import { formatChange, formatCount, formatMoney, formatPrice, formatShare } from "../lib/format";
import {
  PORTFOLIO_SECTIONS,
  isPortfolioSection,
  largestImbalance,
  worstEpisode,
} from "../lib/portfolio";
import { formatDate } from "../lib/time";

const BASE = "/portfolio";
const MIN_DAYS = 250;
// The mix's daily movement as a multiple of US stocks': where each level ends.
const RISK_BANDS = [
  { upTo: 0.5, label: "low" },
  { upTo: 1, label: "moderate" },
  { upTo: 2, label: "high" },
  { upTo: Infinity, label: "very high" },
];
const REFERENCE_NAME: Record<string, string> = {
  TLT: "Government bonds",
  GLD: "Gold",
  SPY: "US stocks",
  "BTC/USD": "Bitcoin",
};
const sessions = (steps: number) => (steps === 1 ? "1 market session" : `${steps} market sessions`);
const expected = (value: number) => (value < 10 ? value.toFixed(1) : value.toFixed(0));
const shownLimit = (horizon: LimitHorizon | undefined, level: number) =>
  horizon?.levels.find((l) => l.level === level)?.methods.find((m) => m.method === horizon.shown);

/** The answers as figures and small pictures; each tile leads to its evidence. */
function Brief({ analysis }: { analysis: PortfolioAnalysis }) {
  const { xray, trust, value } = analysis;
  const covered = analysis.covered_value;
  const level = analysis.risk_level;
  const day = shownLimit(
    analysis.limits.find((h) => h.horizon_days === 1),
    0.95,
  );
  const names = analysis.driver_names as Record<string, string>;
  const name = (symbol: string) =>
    (analysis.positions.find((p) => p.symbol === symbol)?.name ?? symbol).split(" (")[0] ?? symbol;
  const parts = (pick: (h: (typeof xray.holdings)[number]) => number): Part[] =>
    xray.holdings.map((holding, i) => ({
      key: holding.symbol,
      name: name(holding.symbol),
      share: pick(holding),
      colour: holdingColour(holding.symbol, i),
    }));
  const rough = analysis.states
    .filter((state) => state.label === "turbulent")
    .reduce((sum, state) => sum + state.weight, 0);
  const episodes = analysis.stress.filter((e) => e.available && e.change != null);

  // While stock markets are shut: what Bitcoin's move has meant for a held market's open.
  const together = useRelationships().data;
  const linked = together?.weekends.find(
    (row) =>
      row.verdict === "moves with" &&
      row.slope != null &&
      analysis.positions.some((p) => p.symbol === row.symbol),
  );
  const held = analysis.positions.find((p) => p.symbol === linked?.symbol);
  const weekend =
    together?.weekend_now && linked?.slope != null && held
      ? {
          move: Math.expm1(together.weekend_now.bitcoin_move),
          slope: linked.slope,
          name: name(held.symbol),
          value: held.value,
        }
      : undefined;

  return (
    <section aria-label="In brief" className="flex flex-col gap-3 @xl:gap-4">
      {analysis.unmeasured.length > 0 && (
        <p className="well px-4 py-3 text-sm text-muted">
          {analysis.unmeasured.map((item) => (
            <span key={item.symbol}>
              <span className="font-medium text-ink">{item.name}</span> (
              {formatShare(item.weight, 0)} of your money) is not in the risk figures yet: it has{" "}
              {item.days} of the {MIN_DAYS} days of prices needed.{" "}
            </span>
          ))}
          The figures below describe the other {formatShare(covered / value, 0)}.
        </p>
      )}
      {analysis.young.length > 0 && (
        <p className="well px-4 py-3 text-sm text-muted">
          {analysis.young.map((item) => (
            <span key={item.symbol}>
              <span className="font-medium text-ink">{item.name}</span> is a newer holding with{" "}
              {item.days} days of prices, so its risk is an estimate from a short record.{" "}
            </span>
          ))}
          Loss figures are measured on the other holdings and scaled up for it.
        </p>
      )}
      <TileGrid>
        <Tile
          label="Your money, and where the risk sits"
          to={`${BASE}/sources`}
          trust={trust.xray}
          wide
        >
          <span className="flex flex-wrap items-center gap-x-6 gap-y-4">
            <Donut
              inner={parts((h) => h.weight)}
              outer={parts((h) => h.risk_share)}
              centre={formatMoney(value)}
              caption="Inner ring: money · Outer ring: risk"
              label={`Money: ${parts((h) => h.weight)
                .map((p) => `${p.name} ${(p.share * 100).toFixed(0)}%`)
                .join(", ")}. Risk: ${parts((h) => h.risk_share)
                .map((p) => `${p.name} ${(p.share * 100).toFixed(0)}%`)
                .join(", ")}.`}
            />
            <span className="grid min-w-[12rem] flex-1 grid-cols-[minmax(0,1fr)_auto_auto] items-center gap-x-4 gap-y-2 text-sm">
              <span />
              <span className="label text-right text-xs">Money</span>
              <span className="label text-right text-xs">Risk</span>
              {parts((h) => h.weight).map((part, i) => (
                <Fragment key={part.key}>
                  <span className="flex min-w-0 items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ background: part.colour }}
                      aria-hidden="true"
                    />
                    <span className="truncate">{part.name}</span>
                  </span>
                  <span className="num text-right text-muted">{formatShare(part.share, 0)}</span>
                  <span className="num text-right font-medium">
                    {formatShare(xray.holdings[i]?.risk_share ?? 0, 0)}
                  </span>
                </Fragment>
              ))}
            </span>
          </span>
        </Tile>

        {level && (
          <Tile
            label="Risk level"
            to={`${BASE}/sources`}
            trust={trust.xray}
            figure={
              <span className="capitalize" style={{ color: levelColour(level.label) }}>
                {level.label}
              </span>
            }
            note={`${level.ratio.toFixed(1)}× the daily movement of US stocks`}
          >
            <RiskScale
              ratio={level.ratio}
              bands={RISK_BANDS}
              references={Object.entries(level.references as Record<string, number>).map(
                ([symbol, ratio]) => ({ name: REFERENCE_NAME[symbol] ?? symbol, ratio }),
              )}
            />
          </Tile>
        )}

        {analysis.plan && (
          <Tile
            label="Against your target"
            to={`${BASE}/levels`}
            figure={targetSummary(analysis.plan).figure}
            note={targetSummary(analysis.plan).note}
          >
            <span className="flex flex-col gap-1.5 text-xs text-muted">
              {analysis.plan.levels.map((item) => (
                <span key={item.level} className="flex items-center justify-between gap-3">
                  <span
                    className="capitalize"
                    style={{
                      color:
                        analysis.plan?.target?.level === item.level
                          ? levelColour(item.level)
                          : undefined,
                    }}
                  >
                    {item.level}
                  </span>
                  <span className="num">{formatShare(item.cash_share, 0)} in cash</span>
                </span>
              ))}
            </span>
          </Tile>
        )}

        <Tile
          label="Daily movement"
          to={`${BASE}/sources`}
          trust={trust.xray}
          figure={`±${formatMoney(covered * xray.daily_volatility)}`}
          note={`±${formatShare(xray.daily_volatility)} of the whole`}
        >
          <Bars
            format={(v) => `±${formatShare(v)}`}
            rows={[
              { key: "mix", name: "Held together", value: xray.daily_volatility },
              {
                key: "alone",
                name: "If they always moved together",
                value: xray.undiversified_volatility,
                colour: "var(--muted)",
              },
            ]}
          />
        </Tile>

        {day && (
          <Tile
            label="Possible loss in a day"
            to={`${BASE}/limits`}
            trust={trust.risk}
            figure={formatMoney(covered * day.var)}
            note={`${formatShare(day.var, 1)}, passed on about 1 day in 20`}
          >
            <OneIn lit={1} of={20} label="About 1 day in 20" />
          </Tile>
        )}

        {analysis.states.length > 0 && (
          <Tile
            label="Your markets right now"
            to="/together"
            figure={rough > 0 ? `${formatShare(rough, 0)} in turbulence` : "None in turbulence"}
            note="share of your money"
          >
            <span className="flex flex-wrap gap-2">
              {analysis.states.map((state) => (
                <StateChip key={state.symbol} label={state.label}>
                  <span className="text-ink">{name(state.symbol)}</span>
                </StateChip>
              ))}
            </span>
          </Tile>
        )}

        {analysis.drivers && (
          <Tile
            label="What it moves with"
            to={`${BASE}/forces`}
            trust={trust.drivers ?? undefined}
            figure={formatShare(analysis.drivers.r_squared, 0)}
            note="of daily moves they account for"
          >
            <span className="flex flex-col gap-1.5 text-xs">
              {analysis.drivers.drivers
                .filter((d) => d.verdict !== "no measurable link")
                .map((d) => (
                  <span key={d.symbol} className="flex items-center justify-between gap-3">
                    <span className="truncate text-muted">{names[d.symbol] ?? d.symbol}</span>
                    <span className={d.verdict === "moves with" ? "text-calm" : "text-alert"}>
                      {d.verdict === "moves with" ? "▲ with" : "▼ against"}
                    </span>
                  </span>
                ))}
              {analysis.drivers.strongest == null && (
                <span className="text-muted">None measurable right now</span>
              )}
            </span>
          </Tile>
        )}

        {weekend && (
          <Tile
            label="While stocks are shut"
            to="/together/weekends"
            figure={formatChange(weekend.move)}
            note="Bitcoin since the last close"
          >
            <span className="text-xs leading-relaxed text-muted">
              {weekend.name} has opened by about {formatShare(Math.abs(weekend.slope), 0)} of such a
              move:{" "}
              <span className="num text-ink">
                {formatMoney(Math.abs(weekend.slope * weekend.move * weekend.value))}{" "}
                {weekend.slope * weekend.move >= 0 ? "up" : "down"}
              </span>{" "}
              on your holding.
            </span>
          </Tile>
        )}

        {episodes.length > 0 && (
          <Tile
            label="Past crashes replayed on your mix"
            to={`${BASE}/episodes`}
            trust={trust.stress}
            wide
          >
            <Bars
              format={(v) => formatChange(v)}
              rows={episodes.map((e) => ({
                key: e.name,
                name: e.missing.length > 0 ? `${e.name} (partial)` : e.name,
                value: e.change ?? 0,
                colour: (e.change ?? 0) < 0 ? "var(--alert)" : "var(--calm)",
              }))}
            />
          </Tile>
        )}
      </TileGrid>
    </section>
  );
}

function Bar({ share, colour }: { share: number; colour: string }) {
  return (
    <span className="block h-1.5 w-full rounded-full bg-white/8" aria-hidden="true">
      <span
        className="block h-full rounded-full"
        style={{ width: `${Math.min(Math.max(share, 0), 1) * 100}%`, background: colour }}
      />
    </span>
  );
}

function Sources({ analysis }: { analysis: PortfolioAnalysis }) {
  const { xray, positions } = analysis;
  const covered = analysis.covered_value;
  const imbalance = largestImbalance(positions, xray);
  const name = (symbol: string) => positions.find((p) => p.symbol === symbol)?.name ?? symbol;
  return (
    <Panel
      id="sources"
      title="Risk by holding"
      trust={analysis.trust.xray}
      headline={
        imbalance && positions.length > 1
          ? `${imbalance.name}: ${formatShare(imbalance.weight, 0)} of the money, ${formatShare(imbalance.riskShare, 0)} of the risk`
          : `±${formatShare(xray.daily_volatility)} on a typical day`
      }
    >
      <ul className="flex flex-col">
        {xray.holdings.map((holding) => {
          const position = positions.find((p) => p.symbol === holding.symbol);
          return (
            <li
              key={holding.symbol}
              className="grid grid-cols-1 gap-x-8 gap-y-3 border-t border-line py-4 first:border-t-0 first:pt-0 @xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1fr)_minmax(0,1fr)]"
            >
              <div>
                <p className="font-medium">{name(holding.symbol)}</p>
                <p className="num text-sm text-muted">
                  {position ? formatMoney(position.value) : ""} · swings ±
                  {formatShare(holding.daily_volatility)} a day
                </p>
              </div>
              <div>
                <p className="flex justify-between text-sm">
                  <span className="label">Share of the money</span>
                  <span className="num font-medium">{formatShare(holding.weight, 0)}</span>
                </p>
                <div className="mt-1.5">
                  <Bar share={holding.weight} colour="var(--muted)" />
                </div>
              </div>
              <div>
                <p className="flex justify-between text-sm">
                  <span className="label">Share of the risk</span>
                  <span className="num font-medium">{formatShare(holding.risk_share, 0)}</span>
                </p>
                <div className="mt-1.5">
                  <Bar share={holding.risk_share} colour="var(--accent)" />
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <Caption>
        Share of the risk is each holding&apos;s part of how much the whole mix swings from day to
        day. It counts both how much the holding moves and how much it moves with the others. The
        shares add up to 100%. Measured on {formatCount(xray.n_days)} trading days from{" "}
        {formatDate(xray.first_day)} to {formatDate(xray.last_day)}, the days every holding has
        prices for.
      </Caption>

      <div className="border-t border-line pt-5">
        <h3 className="text-sm font-semibold tracking-tight">What holding them together does</h3>
        <dl className="mt-3 grid grid-cols-1 gap-4 @xl:grid-cols-3">
          <div className="well p-4">
            <dt className="label">Typical day for the mix</dt>
            <dd className="price-lg mt-2">±{formatShare(xray.daily_volatility)}</dd>
            <dd className="num mt-1 text-sm text-muted">
              {formatMoney(covered * xray.daily_volatility)}
            </dd>
          </div>
          <div className="well p-4">
            <dt className="label">If they always moved together</dt>
            <dd className="price-lg mt-2">±{formatShare(xray.undiversified_volatility)}</dd>
            <dd className="mt-1 text-sm text-muted">The gap is what mixing them takes off.</dd>
          </div>
          <div className="well p-4">
            <dt className="label">Deepest fall of this mix</dt>
            <dd className="price-lg mt-2 text-alert">{formatShare(xray.deepest_fall.depth, 1)}</dd>
            <dd className="mt-1 text-sm text-muted">
              {formatDate(xray.deepest_fall.peak_day)} to {formatDate(xray.deepest_fall.trough_day)}
            </dd>
          </div>
        </dl>
        <Caption>
          The deepest fall is for today&apos;s proportions held throughout the same period, from a
          high to the lowest close after it.
        </Caption>
      </div>

      {xray.symbols.length > 1 && (
        <div className="border-t border-line pt-5">
          <h3 className="text-sm font-semibold tracking-tight">How closely they move together</h3>
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="label text-left">
                  <th className="pb-2 font-normal" />
                  {xray.symbols.map((symbol) => (
                    <th key={symbol} className="pb-2 pl-3 text-right font-normal">
                      {symbol}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {xray.symbols.map((symbol, i) => (
                  <tr key={symbol} className="border-t border-line">
                    <th className="py-2 pr-3 text-left font-normal">{name(symbol)}</th>
                    {xray.correlation[i]?.map((value, j) => (
                      <td
                        key={j}
                        className={`num py-2 pl-3 text-right ${i === j ? "text-faint" : ""}`}
                      >
                        {i === j ? "–" : value.toFixed(2)}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Caption>
            Correlation of daily returns over the same {formatCount(xray.n_days)} days: 1 means they
            always move together, 0 means no link, below 0 means they tend to move opposite ways.
            Bitcoin&apos;s weekend move is counted in Monday, beside the markets that were closed.
          </Caption>
        </div>
      )}
    </Panel>
  );
}

const HORIZONS = [
  { value: "1", label: "1 day" },
  { value: "7", label: "1 week" },
] as const;
type HorizonKey = (typeof HORIZONS)[number]["value"];

const METHOD: Record<string, string> = {
  historical: "this mix's past losses as they were",
  filtered: "this mix's past losses scaled to how much it has been swinging lately",
};

function LimitCard({
  level,
  limit,
  value,
  period,
}: {
  level: number;
  limit: PortfolioLimit;
  value: number;
  period: string;
}) {
  const test = limit.backtest;
  return (
    <div className="well p-4">
      <p className="label">
        Loss limit for {oddsLabel(level)} periods of {period}
      </p>
      <p className="price-lg mt-2">{formatShare(limit.var, 1)}</p>
      <p className="num mt-1 text-sm text-muted">{formatMoney(value * limit.var)}</p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        When the loss has gone past this limit, it has averaged about{" "}
        <span className="num text-ink">{formatShare(limit.expected_shortfall, 1)}</span>, or{" "}
        <span className="num text-ink">{formatMoney(value * limit.expected_shortfall)}</span>.
      </p>
      <p className="mt-2 text-sm leading-relaxed text-muted">
        Broken <span className="num text-ink">{formatCount(test.breaches)}</span> times in{" "}
        <span className="num text-ink">{formatCount(test.n)}</span> past periods; about{" "}
        <span className="num text-ink">{expected(test.expected_breaches)}</span> would be expected.
      </p>
      {!test.reliable && (
        <p className="mt-2 text-sm text-alert">
          This limit has not held at its stated rate. Treat it as unreliable.
        </p>
      )}
    </div>
  );
}

function Limits({ analysis }: { analysis: PortfolioAnalysis }) {
  const [key, setKey] = useState<HorizonKey>("1");
  const horizon = analysis.limits.find((h) => String(h.horizon_days) === key) ?? analysis.limits[0];
  const day = shownLimit(
    analysis.limits.find((h) => h.horizon_days === 1),
    0.95,
  );
  if (!horizon) return null;
  const period = sessions(horizon.steps);
  const sample = shownLimit(horizon, 0.95)?.backtest;
  return (
    <Panel
      id="limits"
      title="Possible loss"
      trust={analysis.trust.risk}
      headline={
        day
          ? `${formatShare(day.var, 1)}, or ${formatMoney(analysis.covered_value * day.var)}, one-day loss limit`
          : undefined
      }
    >
      <div className="flex justify-end">
        <Segmented options={HORIZONS} value={key} onChange={setKey} label="Length of period" />
      </div>
      <div className="grid grid-cols-1 gap-4 @xl:grid-cols-2">
        {horizon.levels.map((level) => {
          const limit = shownLimit(horizon, level.level);
          return limit ? (
            <LimitCard
              key={level.level}
              level={level.level}
              limit={limit}
              value={analysis.covered_value}
              period={period}
            />
          ) : null;
        })}
      </div>
      <Caption>
        These limits come from {METHOD[horizon.shown] ?? horizon.shown}, the method whose past
        limits held closest to their stated rates. Each past limit was set using only what was known
        that day, then compared with the loss that followed
        {sample
          ? `, over ${formatCount(sample.n)} periods of ${period} from ${formatDate(sample.first_day)} to ${formatDate(sample.last_day)}`
          : ""}
        . Today&apos;s proportions are assumed throughout. A week is five market sessions, and
        weekly periods do not overlap.
      </Caption>
    </Panel>
  );
}

function Episodes({ analysis }: { analysis: PortfolioAnalysis }) {
  const worst = worstEpisode(analysis.stress);
  const name = (symbol: string) =>
    analysis.positions.find((p) => p.symbol === symbol)?.name ?? symbol;
  return (
    <Panel
      id="episodes"
      title="Past crashes"
      trust={analysis.trust.stress}
      headline={
        worst?.change != null ? `${formatChange(worst.change)} through ${worst.name}` : undefined
      }
    >
      <ul className="flex flex-col">
        {analysis.stress.map((episode) => (
          <li key={episode.name} className="border-t border-line py-5 first:border-t-0 first:pt-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <h3 className="font-medium">{episode.name}</h3>
              <p className="num text-sm text-muted">
                {formatDate(episode.start)} to {formatDate(episode.end)}
              </p>
            </div>
            {!episode.available || episode.change == null ? (
              <p className="mt-2 text-sm text-muted">
                Not replayed: none of the holdings has prices for these dates.
              </p>
            ) : (
              <>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  <span
                    className={`num text-lg font-semibold ${episode.change < 0 ? "text-alert" : "text-calm"}`}
                  >
                    {formatChange(episode.change)}
                  </span>{" "}
                  from first day to last, or{" "}
                  <span className="num text-ink">
                    {formatMoney(
                      Math.abs(analysis.covered_value * episode.covered_weight * episode.change),
                    )}
                  </span>{" "}
                  on today&apos;s value.
                  {episode.deepest_fall != null && (
                    <>
                      {" "}
                      Deepest fall on the way{" "}
                      <span className="num text-ink">{formatShare(episode.deepest_fall, 1)}</span>.
                    </>
                  )}
                  {episode.worst_day && episode.worst_day_change != null && (
                    <>
                      {" "}
                      Worst day {formatDate(episode.worst_day)}:{" "}
                      <span className="num text-ink">{formatChange(episode.worst_day_change)}</span>
                      .
                    </>
                  )}
                </p>
                <ul className="mt-3 grid grid-cols-1 gap-x-8 @xl:grid-cols-2">
                  {episode.parts.map((part) => (
                    <li
                      key={part.symbol}
                      className="flex items-baseline justify-between gap-4 border-t border-line py-2 text-sm"
                    >
                      <span>{name(part.symbol)}</span>
                      <span className="num text-muted">
                        itself {formatChange(part.change)} · added{" "}
                        <span className="text-ink">{formatChange(part.contribution)}</span>
                      </span>
                    </li>
                  ))}
                </ul>
                {episode.missing.length > 0 && (
                  <p className="mt-3 text-sm text-alert">
                    Partial: no prices for {episode.missing.map(name).join(", ")} in this period.
                    The figures cover the other {formatShare(episode.covered_weight, 0)} of the
                    portfolio. Nothing was substituted.
                  </p>
                )}
              </>
            )}
          </li>
        ))}
      </ul>
      <Caption>
        Each episode replays today&apos;s proportions through the real prices of that period, as if
        bought on the first day and left alone. What each holding added is its share at the start
        times its own change; the parts add up to the total. Past episodes show what has happened,
        not the worst that can.
      </Caption>
    </Panel>
  );
}

function Forces({ analysis }: { analysis: PortfolioAnalysis }) {
  if (!analysis.drivers) {
    return <Message>There is not enough shared history to measure this yet.</Message>;
  }
  const names = analysis.driver_names as Record<string, string>;
  return (
    <Panel
      id="forces"
      title="What it moves with"
      trust={analysis.trust.drivers ?? undefined}
      headline={driverHeadline(analysis.drivers, names)}
    >
      <DriverEvidence window={analysis.drivers} names={names} subject="your mix" />
    </Panel>
  );
}

/** A gap smaller than this share is put down to prices moving since the last close. */
const GAP_TOLERANCE = 0.03;

/**
 * What Binance says the account is worth, wallet by wallet, beside what RADAR found.
 * A shortfall is stated, never hidden: money RADAR did not find is in none of its figures.
 */
export function ExchangeCheck({
  wallets,
  found,
}: {
  wallets: Portfolio["wallets"];
  found: number | undefined;
}) {
  const total = wallets.reduce((sum, wallet) => sum + wallet.value, 0);
  const gap = found === undefined ? undefined : total - found;
  const short = gap !== undefined && total > 0 && gap / total > GAP_TOLERANCE;
  return (
    <section className="glass p-5 @xl:p-7" aria-label="Checked against Binance">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="text-base font-semibold tracking-tight">Checked against Binance</h2>
        {gap !== undefined && (
          <p className={`text-sm font-medium ${short ? "text-alert" : "text-calm"}`}>
            {short ? `${formatMoney(gap)} not found` : "Everything accounted for"}
          </p>
        )}
      </div>
      <div className="mt-4 grid grid-cols-1 gap-x-10 gap-y-5 @xl:grid-cols-2">
        <Bars
          format={formatMoney}
          rows={[
            { key: "binance", name: "Binance says", value: total, colour: "var(--muted)" },
            ...(found !== undefined
              ? [{ key: "radar", name: "RADAR found", value: found, colour: "var(--accent)" }]
              : []),
          ]}
        />
        <Bars
          format={formatMoney}
          rows={wallets.map((wallet) => ({
            key: wallet.name,
            name: `${wallet.name} wallet`,
            value: wallet.value,
            colour: "var(--muted)",
          }))}
        />
      </div>
      {short && (
        <p className="mt-4 text-sm leading-relaxed text-alert">
          RADAR could not find {formatMoney(gap)} of what Binance reports. That money is in none of
          the figures on the other tabs.
        </p>
      )}
      <Caption>
        Binance's figures are its own totals per wallet at the last read. RADAR's figure values what
        it found at the last US market close, so the two can differ a little while prices move; a
        difference under {formatShare(GAP_TOLERANCE, 0)} is treated as that.
      </Caption>
    </section>
  );
}

export function PortfolioPage() {
  const { section } = useParams();
  const portfolio = usePortfolio();
  const analysis = usePortfolioAnalysis().data ?? undefined;

  if (!isPortfolioSection(section)) return <Navigate to={BASE} replace />;
  const empty = portfolio.data !== undefined && portfolio.data.holdings.length === 0;
  const needsHoldings = (
    <Message>
      {empty
        ? "Add your holdings to see this. "
        : "There is nothing to show for these holdings yet. "}
      <Link to={`${BASE}/holdings`} className="font-medium text-ink underline underline-offset-2">
        Go to holdings
      </Link>
    </Message>
  );

  return (
    <div className="flex flex-col gap-4 @xl:gap-6">
      <div className="aurora" aria-hidden="true" />
      <header className="flex items-baseline gap-3">
        <h1 className="title">Portfolio</h1>
        {analysis && <span className="label num">{formatMoney(analysis.value)}</span>}
      </header>
      <Tabs base={BASE} items={PORTFOLIO_SECTIONS} label="Portfolio pages" />

      {portfolio.isPending && <Message>Loading…</Message>}
      {portfolio.isError && <Message>The portfolio is unavailable right now.</Message>}

      {portfolio.data && (section === undefined || section === "") && (
        <>
          {analysis ? <Brief analysis={analysis} /> : needsHoldings}
          {analysis && (
            <section className="glass p-5 @xl:p-7">
              <h2 className="text-base font-semibold tracking-tight">What you hold</h2>
              <ul className="mt-3">
                {analysis.positions.map((position) => (
                  <li
                    key={position.symbol}
                    className="flex items-baseline justify-between gap-4 border-t border-line py-2.5 text-sm first:border-t-0"
                  >
                    <span>
                      {position.name}{" "}
                      <span className="num text-muted">
                        {formatCount(position.quantity)} at {formatPrice(position.price)}
                      </span>
                    </span>
                    <span className="num font-medium">
                      {formatMoney(position.value)}{" "}
                      <span className="text-muted">{formatShare(position.weight, 0)}</span>
                    </span>
                  </li>
                ))}
              </ul>
              <Caption>
                Valued at the market close on {formatDate(analysis.as_of)}. Recalculated every hour
                as new prices are stored.
              </Caption>
            </section>
          )}
        </>
      )}

      {portfolio.data && section === "holdings" && portfolio.data.wallets.length > 0 && (
        <ExchangeCheck wallets={portfolio.data.wallets} found={analysis?.value} />
      )}

      {portfolio.data && section === "holdings" && (
        <section className="glass p-5 @xl:p-7">
          <h2 className="mb-4 text-base font-semibold tracking-tight">Your holdings</h2>
          <HoldingsEditor portfolio={portfolio.data} />
        </section>
      )}

      {portfolio.data &&
        section === "levels" &&
        (analysis ? <LevelsPanel analysis={analysis} /> : needsHoldings)}
      {portfolio.data &&
        section === "mixes" &&
        (analysis ? <MixesPanel analysis={analysis} /> : needsHoldings)}
      {portfolio.data &&
        section === "sources" &&
        (analysis ? <Sources analysis={analysis} /> : needsHoldings)}
      {portfolio.data &&
        section === "limits" &&
        (analysis ? <Limits analysis={analysis} /> : needsHoldings)}
      {portfolio.data &&
        section === "forces" &&
        (analysis ? <Forces analysis={analysis} /> : needsHoldings)}
      {portfolio.data &&
        section === "episodes" &&
        (analysis ? <Episodes analysis={analysis} /> : needsHoldings)}
    </div>
  );
}
