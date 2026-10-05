// Times are stored and sent in UTC. Everything shown to the viewer is converted here, to
// the browser's zone, and the zone is named beside it.

const NEW_YORK = "America/New_York";

/** The viewer's zone as a short offset, for example "GMT+8". */
export function zoneLabel(zone?: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    timeZoneName: "shortOffset",
  }).formatToParts(new Date());
  return parts.find((p) => p.type === "timeZoneName")?.value ?? "local time";
}

/** "5 Oct 2026, 17:04" in the viewer's zone. */
export function formatDateTime(ts: string | number | Date, zone?: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(new Date(ts));
}

/** "5 Oct 2026" in the viewer's zone. */
export function formatDate(ts: string | number | Date, zone?: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(ts));
}

/** "3 minutes", "2 hours", "4 days": a rough, readable duration. */
export function formatDuration(seconds: number): string {
  const abs = Math.max(0, seconds);
  const pick = (value: number, unit: string) => {
    const n = Math.round(value);
    return `${n} ${unit}${n === 1 ? "" : "s"}`;
  };
  if (abs < 90) return pick(abs, "second");
  if (abs < 90 * 60) return pick(abs / 60, "minute");
  if (abs < 36 * 3600) return pick(abs / 3600, "hour");
  return pick(abs / 86400, "day");
}

/** Calendar date ("2026-10-05") of an instant in a given zone. */
export function isoDateIn(ts: string | number | Date, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(ts));
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/**
 * The trading day a daily bar belongs to. Stock daily bars are stamped at midnight New
 * York time; crypto daily bars at midnight UTC.
 */
export function tradingDay(ts: string, assetClass: "crypto" | "stock"): string {
  return isoDateIn(ts, assetClass === "stock" ? NEW_YORK : "UTC");
}

/**
 * Seconds for the chart library, shifted so its UTC axis reads as the viewer's local
 * time. The library has no time zone support of its own.
 */
export function chartSeconds(ts: string | number): number {
  const ms = typeof ts === "number" ? ts : Date.parse(ts);
  return Math.floor(ms / 1000) - new Date(ms).getTimezoneOffset() * 60;
}
