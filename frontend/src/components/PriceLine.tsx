import { formatDateTime, zoneLabel } from "../lib/time";

/** Says how current a price is: live, or the time it was last true. */
export function Freshness({ live, asOf }: { live: boolean; asOf: number | undefined }) {
  if (live) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-calm">
        <span
          className="live-dot inline-block h-1.5 w-1.5 rounded-full bg-calm"
          aria-hidden="true"
        />
        Live
      </span>
    );
  }
  if (asOf === undefined) return null;
  return (
    <span className="text-xs text-faint">
      As of {formatDateTime(asOf)} {zoneLabel()}
    </span>
  );
}
