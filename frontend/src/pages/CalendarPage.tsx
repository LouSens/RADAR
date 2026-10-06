import { Link, Navigate, useParams } from "react-router-dom";

import type { Calendar } from "../api/client";
import { useAssets, useCalendar } from "../api/queries";
import { Tabs } from "../components/Tabs";
import { Caption, Message, Panel, assetColorVar } from "../components/ui";
import { formatCount, formatShare } from "../lib/format";
import { formatDate, formatDateTime } from "../lib/time";

const BASE = "/calendar";
export const CALENDAR_PAGES = [
  { path: "", label: "Coming up" },
  { path: "fed", label: "Fed decisions" },
  { path: "jobs", label: "Jobs reports" },
  { path: "inflation", label: "Inflation reports" },
] as const;
type EventKey = Exclude<(typeof CALENDAR_PAGES)[number]["path"], "">;
const isEventKey = (value: string | undefined): value is EventKey =>
  CALENDAR_PAGES.some((page) => page.path !== "" && page.path === value);

type EventResult = Calendar["results"][number];
type MarketResult = EventResult["markets"][number];
type Share = MarketResult["event_day"];

const SIZE_WORDS: Record<string, string> = {
  "moves more on these days": "Moves more on these days",
  "moves less on these days": "Moves less on these days",
  "no measurable difference": "Moves about as much as any day",
  "not enough events": "Too few events to judge",
};
const PATTERN_WORDS: Record<string, string> = {
  "leans up": "More often up",
  "leans down": "More often down",
  "tends to carry on": "Tends to carry on",
  "tends to reverse": "Tends to reverse",
  "no measurable pattern": "No pattern",
  "not enough events": "Too few events",
};
const found = (verdict: string) =>
  verdict !== "not enough events" && !verdict.startsWith("no measurable");

/** Whole calendar days from now until a moment, counted in the viewer's own time zone. */
export function daysAway(at: string, now: Date = new Date()): number {
  const day = (d: Date) => Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
  return Math.round((day(new Date(at)) - day(now)) / 86_400_000);
}

export function when(days: number): string {
  return days <= 0 ? "Today" : days === 1 ? "Tomorrow" : `In ${days} days`;
}

/** The size finding for one event across markets, as one short line. */
export function sizeLine(result: EventResult, names: Record<string, string>): string {
  const more = result.markets
    .filter((m) => m.size.verdict === "moves more on these days")
    .map((m) => (names[m.symbol] ?? m.symbol).split(" (")[0]);
  return more.length > 0
    ? `${more.join(" and ")} ${more.length === 1 ? "has" : "have"} moved more than usual on these days`
    : "No market has moved measurably more on these days";
}

function Upcoming({ calendar }: { calendar: Calendar }) {
  const names = calendar.names as Record<string, string>;
  const next = calendar.upcoming[0];
  return (
    <Panel
      id="upcoming"
      title="Coming up"
      headline={
        next
          ? `${next.name}: ${when(daysAway(next.at)).toLowerCase()}`
          : "No scheduled events are on file"
      }
    >
      <ul className="-my-2 flex flex-col">
        {calendar.upcoming.map((event) => {
          const result = calendar.results.find((r) => r.key === event.key);
          return (
            <li key={`${event.key}-${event.at}`} className="border-t border-line first:border-t-0">
              <Link
                to={`${BASE}/${event.key}`}
                className="group flex flex-col gap-1 py-4 @xl:flex-row @xl:items-baseline @xl:justify-between @xl:gap-6"
              >
                <span className="min-w-0">
                  <span className="block font-medium group-hover:text-accent">{event.name}</span>
                  {result && (
                    <span className="mt-0.5 block text-sm text-muted">
                      {sizeLine(result, names)}
                    </span>
                  )}
                </span>
                <span className="num shrink-0 text-sm text-muted @xl:text-right">
                  <span className="font-medium text-ink">{when(daysAway(event.at))}</span> ·{" "}
                  {formatDateTime(event.at)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
      <Caption>
        Dates and times come from the published schedules of the US Federal Reserve and the US
        Bureau of Labor Statistics, shown in your local time. They were taken on one day and are
        refreshed about once a year, so a date moved since then will not show until the next
        refresh. Only scheduled events are listed. RADAR does not know what figure is expected, so
        it cannot say whether a number will surprise; each event links to how markets have behaved
        around past ones.
      </Caption>
    </Panel>
  );
}

function ShareBar({ label, share }: { label: string; share: Share }) {
  if (share.share == null || share.baseline == null) return null;
  const at = (value: number) => `${value * 100}%`;
  const judged = share.verdict !== "not enough events";
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3 text-sm">
        <span className="text-muted">{label}</span>
        <span className="num font-medium">
          {formatShare(share.share, 0)}{" "}
          <span className="font-normal text-muted">any day {formatShare(share.baseline, 0)}</span>
        </span>
      </div>
      <div
        className="relative mt-2 h-2 rounded-full bg-white/8"
        role="img"
        aria-label={`${label}: ${formatShare(share.share, 0)}, plausibly between ${formatShare(share.low ?? 0, 0)} and ${formatShare(share.high ?? 0, 0)}; ${formatShare(share.baseline, 0)} on any day`}
      >
        <span
          className="absolute inset-y-0 rounded-full"
          style={{
            left: at(share.low ?? share.share),
            right: `calc(100% - ${at(share.high ?? share.share)})`,
            background: judged
              ? "color-mix(in srgb, var(--accent) 45%, transparent)"
              : "rgba(255,255,255,0.18)",
          }}
        />
        <span
          className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bg"
          style={{ left: at(share.share), background: judged ? "var(--accent)" : "var(--muted)" }}
        />
        <span
          className="absolute -inset-y-1 w-0.5 bg-ink"
          style={{ left: at(share.baseline) }}
          aria-hidden="true"
        />
      </div>
      <p className={`mt-1.5 text-xs ${found(share.verdict) ? "text-ink" : "text-faint"}`}>
        {PATTERN_WORDS[share.verdict] ?? share.verdict}
      </p>
    </div>
  );
}

function MarketCard({
  market,
  name,
  colour,
}: {
  market: MarketResult;
  name: string;
  colour: string;
}) {
  const { size } = market;
  const reach = Math.max(size.on_event ?? 0, size.other_days ?? 0) || 1;
  const rows = [
    { key: "event", label: "On these days", value: size.on_event, colour },
    {
      key: "other",
      label: "On any other day",
      value: size.other_days,
      colour: "rgba(255,255,255,0.35)",
    },
  ];
  return (
    <li className="well flex flex-col gap-5 px-4 py-4">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <h3 className="flex items-center gap-2 font-medium">
          <span
            className="h-2.5 w-2.5 rounded-full"
            style={{ background: colour }}
            aria-hidden="true"
          />
          {name}
        </h3>
        <p className="num text-sm text-muted">
          {formatCount(market.n_events)} past events
          {market.first_day && market.last_day
            ? `, ${formatDate(market.first_day)} to ${formatDate(market.last_day)}`
            : ""}
        </p>
      </div>
      {market.n_events > 0 && (
        <>
          <div>
            <p className="label mb-2">Typical move on the day</p>
            <div className="flex flex-col gap-2">
              {rows.map((row) =>
                row.value == null ? null : (
                  <div
                    key={row.key}
                    className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3"
                  >
                    <span className="min-w-0">
                      <span className="block text-xs text-muted">{row.label}</span>
                      <span className="mt-1 block h-1.5 rounded-full bg-white/8">
                        <span
                          className="block h-full rounded-full"
                          style={{ width: `${(row.value / reach) * 100}%`, background: row.colour }}
                        />
                      </span>
                    </span>
                    <span className="num text-sm font-medium">±{formatShare(row.value, 2)}</span>
                  </div>
                ),
              )}
            </div>
            <p className={`mt-2 text-xs ${found(size.verdict) ? "text-ink" : "text-faint"}`}>
              {SIZE_WORDS[size.verdict] ?? size.verdict}
            </p>
          </div>
          <div className="grid grid-cols-1 gap-x-8 gap-y-5 @3xl:grid-cols-2">
            <ShareBar label="Ended higher the day before" share={market.day_before} />
            <ShareBar label="Ended higher on the day" share={market.event_day} />
            <ShareBar label="Next day went the same way as the day" share={market.next_day} />
            <ShareBar label="Next week went the same way as the day" share={market.next_week} />
          </div>
        </>
      )}
    </li>
  );
}

function Results({ calendar, eventKey }: { calendar: Calendar; eventKey: EventKey }) {
  const assets = useAssets().data ?? [];
  const names = calendar.names as Record<string, string>;
  const result = calendar.results.find((r) => r.key === eventKey);
  if (!result) return <Message>This event has not been measured yet.</Message>;
  const next = calendar.upcoming.find((e) => e.key === eventKey);
  const patterns = result.markets.flatMap((m) =>
    [m.day_before, m.event_day, m.next_day, m.next_week].filter((s) => found(s.verdict)),
  ).length;
  const trust = (calendar.trust as Record<string, Calendar["trust"][string]>)[eventKey];
  return (
    <Panel id="event" title={result.name} trust={trust} headline={sizeLine(result, names)}>
      <div className="well px-4 py-3 text-sm">
        {next ? (
          <p>
            <span className="label">Next</span>{" "}
            <span className="num font-medium">{when(daysAway(next.at))}</span>
            <span className="num text-muted"> · {formatDateTime(next.at)}</span>
          </p>
        ) : (
          <p className="text-muted">No date for the next one is on file.</p>
        )}
        <p className="mt-1.5 text-muted">
          {patterns > 0
            ? "A pattern in direction was found for at least one market below."
            : "No pattern in direction was found: not before these days, not on them, and not after."}
        </p>
      </div>
      <ul className="flex flex-col gap-3">
        {result.markets.map((market) => {
          const asset = assets.find((a) => a.symbol === market.symbol);
          return (
            <MarketCard
              key={market.symbol}
              market={market}
              name={(names[market.symbol] ?? market.symbol).split(" (")[0] ?? market.symbol}
              colour={asset ? `var(${assetColorVar(asset)})` : "var(--accent)"}
            />
          );
        })}
      </ul>
      <Caption>
        An event&apos;s day is the trading day of its date: the market session for gold and US
        stocks, the calendar day in world time for Bitcoin. Moves are from one day&apos;s close to
        the next. On each bar the dot is how often it happened around these events, the band is the
        range that share could plausibly lie in, and the line is the same share on any day: a band
        that covers the line means no pattern. The questions and the rules for judging them were
        written down before any result was computed, and {calendar.direction_tests} comparisons of
        direction and {calendar.size_tests} of size were then looked at together, so a result counts
        only if it still stands out after allowing for that. Fewer than 30 events are not judged.
        RADAR does not know the figure that was expected, so this says nothing about how a market
        reacts to a surprise.
      </Caption>
    </Panel>
  );
}

export function CalendarPage() {
  const { event } = useParams();
  const query = useCalendar();
  if (event !== undefined && !isEventKey(event)) return <Navigate to={BASE} replace />;
  return (
    <div className="flex flex-col gap-4 @xl:gap-6">
      <div className="aurora" aria-hidden="true" />
      <header>
        <h1 className="title">Calendar</h1>
      </header>
      <Tabs base={BASE} items={CALENDAR_PAGES} label="Calendar pages" />
      {query.isPending && <Message>Loading…</Message>}
      {query.data === null && <Message>The calendar has not been worked out yet.</Message>}
      {query.isError && <Message>The calendar is unavailable right now.</Message>}
      {query.data &&
        (event === undefined ? (
          <Upcoming calendar={query.data} />
        ) : (
          <Results calendar={query.data} eventKey={event} />
        ))}
    </div>
  );
}
