import { Link } from "react-router-dom";

import { useCalendar } from "../api/queries";
import { daysAway, when } from "../pages/CalendarPage";
import { CardSkeleton } from "./Skeleton";

/** The next few scheduled economic events, on the Overview. */
export function ComingUp() {
  const query = useCalendar();
  const next = query.data?.upcoming.slice(0, 3) ?? [];
  if (query.isPending) return <CardSkeleton lines={3} />;
  if (next.length === 0) return null;
  return (
    <section className="glass p-4 @xl:p-7" aria-labelledby="coming-up-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="coming-up-title" className="text-base font-semibold tracking-tight">
          Coming up
        </h2>
        <Link to="/calendar" className="text-sm font-medium text-muted hover:text-ink">
          Calendar
        </Link>
      </div>
      <ul className="mt-2 flex flex-col">
        {next.map((event) => (
          <li key={`${event.key}-${event.at}`} className="border-t border-line first:border-t-0">
            <Link
              to="/calendar"
              className="group flex items-baseline justify-between gap-4 py-3 text-sm"
            >
              <span className="min-w-0 truncate font-medium group-hover:text-accent">
                {event.name}
              </span>
              <span className="num shrink-0 text-muted">{when(daysAway(event.at))}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
