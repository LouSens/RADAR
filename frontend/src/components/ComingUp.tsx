import { Link } from "react-router-dom";

import { useCalendar } from "../api/queries";
import { formatDateTime } from "../lib/time";
import { daysAway, when } from "../pages/CalendarPage";

/** The next few scheduled economic events, on the Overview. */
export function ComingUp() {
  const calendar = useCalendar().data;
  const next = calendar?.upcoming.slice(0, 3) ?? [];
  if (next.length === 0) return null;
  return (
    <section className="glass p-5 @xl:p-7" aria-labelledby="coming-up-title">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="coming-up-title" className="text-base font-semibold tracking-tight">
          Coming up
        </h2>
        <Link to="/calendar" className="text-sm font-medium text-muted hover:text-ink">
          Calendar
        </Link>
      </div>
      <ul className="mt-3 grid grid-cols-1 gap-3 @2xl:grid-cols-3">
        {next.map((event) => (
          <li key={`${event.key}-${event.at}`}>
            <Link
              to={`/calendar/${event.key}`}
              className="well block px-4 py-3 transition-colors hover:bg-white/[0.04]"
            >
              <span className="label block">{when(daysAway(event.at))}</span>
              <span className="mt-1 block font-medium">{event.name}</span>
              <span className="num mt-0.5 block text-sm text-muted">
                {formatDateTime(event.at)}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
