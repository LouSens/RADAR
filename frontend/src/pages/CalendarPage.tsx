import type { Calendar } from "../api/client";
import { useCalendar } from "../api/queries";
import { PageSkeleton } from "../components/Skeleton";
import { Caption, Message, Panel } from "../components/ui";
import { formatDateTime } from "../lib/time";

type EventResult = Calendar["results"][number];

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
    ? `${more.join(" and ")} moved more than usual on these days`
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
              <div className="flex flex-col gap-1 py-4 @xl:flex-row @xl:items-baseline @xl:justify-between @xl:gap-6">
                <span className="min-w-0">
                  <span className="block font-medium">{event.name}</span>
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
              </div>
            </li>
          );
        })}
      </ul>
      <Caption
        facts={[
          {
            label: "Dates from",
            value:
              "The published schedules of the US Federal Reserve and Bureau of Labor Statistics",
          },
          { label: "Shown in", value: "Your local time" },
          {
            label: "Refreshed",
            value:
              "Taken on one day, about once a year; a date moved since then waits for the next refresh",
          },
          { label: "Listed", value: "Scheduled events only" },
        ]}
      >
        RADAR does not know what figure is expected, so it cannot say whether a number will
        surprise.
      </Caption>
    </Panel>
  );
}

export function CalendarPage() {
  const query = useCalendar();
  return (
    <div className="flex flex-col gap-4 @xl:gap-6">
      <header>
        <h1 className="title">Calendar</h1>
      </header>
      {query.isPending && <PageSkeleton />}
      {query.data === null && <Message>The calendar has not been worked out yet.</Message>}
      {query.isError && <Message>The calendar is unavailable right now.</Message>}
      {query.data && <Upcoming calendar={query.data} />}
    </div>
  );
}
