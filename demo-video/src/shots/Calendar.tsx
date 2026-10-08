import { AbsoluteFill, useCurrentFrame } from "remotion";
import { Lock, Smear, rate } from "../Chain";
import film from "../fixtures/film.json";
import { C } from "../theme";
import { EASE_IN_OUT, tween } from "../timing";
import { AT, DESK } from "../ui/Desk";
import { base, num } from "../ui/kit";
import { Ticker, pop, settle } from "../ui/motion";
import { LINE, PLAN, PLAN_BAR, RAIL, STOPS, Stop } from "./Plan";
import { Weighed } from "./Risk";

const events = film.calendar.slice(0, 4);
const FED = events.findIndex((event) => event.key === "fed");

// The timeline, in the frame's own pixels, above its question.
const LINE_X = 168;
const FOOT = 760;
const LONG = 664;
const nodeY = (i: number): number => 150 + i * 180;
const ROW = { x: 232, w: 1560, name: 50 } as const;

/** When the ladder's line has swung up into the timeline. */
const SWING = [0, 12] as const;
/** When the first row comes off the line, and how long after it each other does. */
export const ROWS = 8;
export const EVERY = 3;
/** The count of days on the Fed's row, rolling down to what it is. */
export const ROLL = [18, 30] as const;
export const LOCKED = ROLL[1] + 2;
/** When the rows fly to their places on Home, which comes back round them. */
export const FLIES = 45;
const FLIGHT = 14;
export const LANDED = FLIES + FLIGHT;
/** How many days above the real count the roll starts from. */
const FROM = 9;

/** The rows of Home's own "Coming up" card (ui/Desk), in the frame. */
const HOME_ROWS = 3;
const SMALL = (14 * DESK.zoom) / ROW.name;
const homeRow = (i: number): { x: number; y: number; w: number } => ({
  x: (AT.coming.x + 28) * DESK.zoom,
  // The middle of the row's line of text.
  y: (AT.coming.y + 56.6 + i * 42.4 + (i > 0 ? i : 0) + 10 + 11.2) * DESK.zoom,
  w: (AT.coming.w - 56) * DESK.zoom,
});

const when = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Singapore",
  });
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** A row on its way to Home: where it is, how wide it is laid out, how large drawn. */
const flown = (frame: number): number =>
  tween(frame, FLIES, LANDED, 0, 1, EASE_IN_OUT);
const rowAt = (
  i: number,
  t: number,
): { left: number; top: number; width: number; k: number } => {
  const to = homeRow(Math.min(i, HOME_ROWS - 1));
  return {
    left: mix(ROW.x, to.x, t),
    top: mix(nodeY(i) - 58, to.y - (ROW.name * 1.25 * SMALL) / 2, t),
    width: mix(ROW.w, to.w / SMALL, t),
    k: mix(1, SMALL, t),
  };
};

/**
 * How Home is drawn while the rows fly, at a frame of this shot: larger, and placed so
 * that its "Coming up" card is round the rows all the way. So the camera pulls back
 * from the rows to the whole of Home, and no row passes over another card.
 */
export const homeAt = (frame: number): { k: number; x: number; y: number } => {
  const row = rowAt(0, flown(frame));
  const to = homeRow(0);
  const k = (row.width * row.k) / to.w;
  return {
    k,
    x: row.left - k * to.x,
    y: row.top + (ROW.name * 1.25 * row.k) / 2 - k * to.y,
  };
};

/**
 * Shot 8. The ladder's line of shot 7 swings up into the calendar's timeline, its three
 * prices become dates, and the rows hang off it. The count of days on the Fed's
 * decision rolls down to what it is and is marked. Then Home comes back under the rows
 * and each flies to its own place in Home's card. Figures: the app's calendar and what
 * it measured (fixtures/film.json). Times are the viewer's, as on the page.
 */
export const Calendar: React.FC = () => {
  const frame = useCurrentFrame();
  const swing = tween(frame, SWING[0], SWING[1], 0, 1, EASE_IN_OUT);
  const rolled = tween(frame, ROLL[0], ROLL[1], 0, 1, EASE_IN_OUT);
  const pivot = {
    x: mix(RAIL.left, LINE_X, swing),
    y: mix(RAIL.y, FOOT, swing),
  };
  const long = mix(RAIL.right - RAIL.left, LONG, swing);
  const turn = (-Math.PI / 2) * swing;
  // The ladder's three prices ride the line to the first three dates; a fourth joins.
  const along = (i: number): number => {
    const to = (FOOT - nodeY(i)) / LONG;
    const from =
      i < STOPS.length ? (STOPS[i] - RAIL.left) / (RAIL.right - RAIL.left) : to;
    return mix(from, to, swing);
  };
  const leaving = 1 - tween(frame, FLIES, FLIES + 5, 0, 1, (t) => t);
  const handed = 1 - tween(frame, LANDED - 1, LANDED + 3, 0, 1, (t) => t);

  return (
    <AbsoluteFill>
      {/* What is left of shot 7: its bar, going. */}
      {frame < 6 && (
        <AbsoluteFill
          style={{ opacity: 1 - tween(frame, 0, 5, 0, 1, (t) => t) }}
        >
          <Weighed box={PLAN_BAR} shares={PLAN} figures={0} names={0} />
        </AbsoluteFill>
      )}
      <AbsoluteFill style={{ opacity: leaving }}>
        <Smear
          x={rate(frame, SWING[0], SWING[1]) * 900}
          y={rate(frame, SWING[0], SWING[1]) * 500}
        >
          <span
            style={{
              position: "absolute",
              left: pivot.x,
              top: pivot.y - 2,
              width: long,
              height: 4,
              borderRadius: 2,
              background: LINE,
              transformOrigin: "0 50%",
              rotate: `${turn}rad`,
            }}
          />
        </Smear>
        {events.map((event, i) => {
          const u = along(i) * long;
          const by = i < STOPS.length ? 1 : pop(frame, SWING[1] - 4);
          return frame >= SWING[1] - 4 || i < STOPS.length ? (
            <Stop
              key={event.at}
              x={pivot.x + Math.cos(turn) * u}
              y={pivot.y + Math.sin(turn) * u}
              by={by}
              lit={1}
            />
          ) : null;
        })}
      </AbsoluteFill>

      {events.map((event, i) => {
        const slid = settle(frame, ROWS + i * EVERY, 15);
        const home = i < HOME_ROWS;
        const row = rowAt(i, home ? flown(frame) : 0);
        const less = 1 - Math.min(flown(frame) * 2.5, 1);
        return (
          <div
            key={event.at}
            style={{
              ...base,
              position: "absolute",
              left: row.left,
              top: row.top,
              width: row.width,
              transformOrigin: "0 0",
              scale: String(row.k),
              display: "flex",
              justifyContent: "space-between",
              translate: `${(1 - slid) * -60}px 0`,
              opacity:
                Math.min(Math.max(slid * 1.6, 0), 1) *
                (home ? handed : leaving),
            }}
          >
            <span style={{ display: "flex", flexDirection: "column" }}>
              <span
                style={{
                  fontSize: ROW.name,
                  fontWeight: 600,
                  lineHeight: 1.25,
                  whiteSpace: "nowrap",
                }}
              >
                {event.name}
              </span>
              <span
                style={{
                  fontSize: 34,
                  color: C.muted,
                  lineHeight: 1.4,
                  whiteSpace: "nowrap",
                  opacity: less,
                }}
              >
                {event.line}
              </span>
            </span>
            <span
              style={{
                ...num,
                display: "flex",
                flexDirection: "column",
                alignItems: "flex-end",
              }}
            >
              <span
                style={{
                  position: "relative",
                  fontSize: ROW.name,
                  fontWeight: 700,
                  lineHeight: 1.25,
                  whiteSpace: "nowrap",
                }}
              >
                In{" "}
                <Ticker
                  value={
                    i === FED ? event.days + FROM * (1 - rolled) : event.days
                  }
                  places={i === FED ? 2 : undefined}
                />{" "}
                days
                {i === FED && (
                  <Lock frame={frame} at={LOCKED} out={FLIES - 4} pad={16} />
                )}
              </span>
              <span
                style={{
                  fontSize: 34,
                  color: C.muted,
                  lineHeight: 1.4,
                  whiteSpace: "nowrap",
                  opacity: less,
                }}
              >
                {when(event.at)}
              </span>
            </span>
          </div>
        );
      })}
    </AbsoluteFill>
  );
};
