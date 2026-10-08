import type { Moves } from "../api/client";
import { useMoves } from "../api/queries";
import { formatChange } from "../lib/format";
import { formatDate } from "../lib/time";
import { CardSkeleton } from "./Skeleton";
import { Caption, Change, Evidence, Message, Panel, type PanelProps } from "./ui";

type Day = Moves["days"][number];

/** Days listed in the open; the rest are one tap away. */
const SHOWN = 7;
/** A day counts as unusually large when it beat this share of the days before it. */
const UNUSUAL = 0.95;

const upOrDown = (move: number) => (move >= 0 ? "Up" : "Down");
const size = (fraction: number) => `${Math.abs(fraction * 100).toFixed(2)}%`;

/** "Larger than 97 of the last 100 days", from the share of earlier days it beat. */
export function rankWords(rank: number): string {
  return `Larger than ${Math.round(rank * 100)} of 100 days before it`;
}

/** The newest day in one line. */
export function headline(day: Day, wider: string | null | undefined): string {
  const start = `${upOrDown(day.move)} ${size(day.move)} on ${formatDate(day.day)}`;
  if (day.market != null && day.own != null && wider) {
    return `${start}: ${formatChange(day.market)} with ${wider}, ${formatChange(day.own)} its own`;
  }
  if (day.rank != null) return `${start}: ${rankWords(day.rank).toLowerCase()}`;
  return start;
}

/** One part of a move as a bar from the middle: right for up, left for down. */
function Part({
  label,
  value,
  reach,
  colour,
}: {
  label: string;
  value: number;
  reach: number;
  colour: string;
}) {
  const width = `${Math.min(Math.abs(value) / reach, 1) * 50}%`;
  return (
    <div className="grid grid-cols-[5.5rem_minmax(0,1fr)_4rem] items-center gap-x-3">
      <span className="truncate text-xs text-muted">{label}</span>
      <span className="relative block h-2 rounded-full bg-white/8">
        <span className="absolute inset-y-[-2px] left-1/2 w-px bg-line-strong" />
        <span
          className="absolute inset-y-0 rounded-full"
          style={{
            background: colour,
            width,
            ...(value >= 0 ? { left: "50%" } : { right: "50%" }),
          }}
        />
      </span>
      <span className="num text-right text-xs">{formatChange(value)}</span>
    </div>
  );
}

function Chip({ children, strong = false }: { children: React.ReactNode; strong?: boolean }) {
  return (
    <span
      className={`rounded-full border px-2.5 py-0.5 text-xs ${
        strong ? "border-line-strong text-ink" : "border-line text-muted"
      }`}
    >
      {children}
    </span>
  );
}

function DayRow({
  day,
  wider,
  widerColour,
  reach,
}: {
  day: Day;
  wider: string | null | undefined;
  widerColour: string;
  reach: number;
}) {
  const split = day.market != null && day.own != null && wider;
  const unusual = day.rank != null && day.rank >= UNUSUAL;
  return (
    <li className="flex flex-col gap-2.5 border-t border-line py-3.5 first:border-t-0 first:pt-0">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-sm font-medium">{formatDate(day.day)}</span>
        <Change value={day.move} className="text-sm font-semibold" />
      </div>
      {split && (
        <div className="flex flex-col gap-1.5">
          <Part
            label={`With ${wider}`}
            value={day.market ?? 0}
            reach={reach}
            colour={widerColour}
          />
          <Part
            label="Its own"
            value={day.own ?? 0}
            reach={reach}
            colour="rgba(255,255,255,0.6)"
          />
        </div>
      )}
      <div className="flex flex-wrap gap-1.5">
        {day.times_usual != null && (
          <Chip strong={unusual}>
            {`${day.times_usual >= 10 ? "10+" : day.times_usual.toFixed(1)}× a usual day`}
          </Chip>
        )}
        {unusual && day.rank != null && <Chip strong>{rankWords(day.rank)}</Chip>}
        {day.events.map((event) => (
          <Chip key={event}>{event} that day</Chip>
        ))}
        {day.state_from && day.state_to && (
          <Chip strong>
            <span className="capitalize">{day.state_from}</span> to {day.state_to}
          </Chip>
        )}
      </div>
      {day.headlines.length > 0 && (
        <details className="about">
          <summary>
            {day.headlines.length === 1
              ? "1 headline that day"
              : `${day.headlines.length} headlines that day`}
          </summary>
          <ul className="mt-2 flex flex-col gap-1.5 text-sm text-muted">
            {day.headlines.map((item) => (
              <li key={`${item.created_at}-${item.headline}`}>
                {item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="underline-offset-2 hover:text-ink hover:underline"
                  >
                    {item.headline}
                  </a>
                ) : (
                  item.headline
                )}
                {item.source && <span className="text-faint"> · {item.source}</span>}
              </li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

/**
 * Why it moved: each recent day's move, the part that went with the wider market where
 * that link holds up, how large the day was for this asset, and what else is known about
 * the day. Nothing here is given as the cause of a move.
 */
export function MovesPanel({ asset }: PanelProps) {
  const query = useMoves(asset.slug);
  if (query.isPending) return <CardSkeleton lines={5} />;
  const moves = query.data;
  if (!moves || moves.days.length === 0) {
    return (
      <Panel id="moves" title="Why it moved">
        <Message>There are not enough days of prices for this yet.</Message>
      </Panel>
    );
  }
  const wider = moves.split_shown ? moves.reference_name?.split(" (")[0] : null;
  const widerColour = moves.reference === "BTC/USD" ? "var(--btc)" : "var(--stock)";
  const reach = Math.max(
    ...moves.days.flatMap((d) => [d.move, d.market ?? 0, d.own ?? 0].map(Math.abs)),
    1e-9,
  );
  const first = moves.days[0];
  const row = (day: Day) => (
    <DayRow key={day.day} day={day} wider={wider} widerColour={widerColour} reach={reach} />
  );
  return (
    <Panel
      id="moves"
      title="Why it moved"
      trust={moves.trust}
      headline={first ? headline(first, wider) : undefined}
    >
      <ul>{moves.days.slice(0, SHOWN).map(row)}</ul>
      {moves.days.length > SHOWN && (
        <Evidence summary={`${moves.days.length - SHOWN} earlier days`}>
          <ul>{moves.days.slice(SHOWN).map(row)}</ul>
        </Evidence>
      )}
      <Caption
        facts={[
          ...(wider
            ? [
                {
                  label: `With ${wider}`,
                  value: `How much it has moved for each 1% move of ${wider} over the 90 days before, times what ${wider} did that day`,
                },
                { label: "Its own", value: "The rest of the day's move" },
              ]
            : []),
          { label: "A usual day", value: "The size of its days over the 30 days before" },
          { label: "Events and headlines", value: "What fell on the day, not what caused it" },
        ]}
      >
        This says what happened alongside a move. It does not say why prices will move next.
      </Caption>
    </Panel>
  );
}
