import { AbsoluteFill, useCurrentFrame } from "remotion";
import { AREA, OPENS, Answer, ZOOM } from "../Beat";
import film from "../fixtures/film.json";
import { C } from "../theme";
import { EASE_IN_OUT, shot, tween } from "../timing";
import { DOCK } from "../Type";
import { AT } from "../ui/Desk";
import { base, num } from "../ui/kit";
import { Ping, Ticker, settle } from "../ui/motion";

const events = film.calendar.slice(0, 4);
const FED = events.findIndex((event) => event.key === "fed");

/** This shot is short: its question starts for its dock sooner than the others'. */
export const DOCKS = 4;
export const ASKED = DOCKS + DOCK;
/** When the first row slides up, and how long after it each other does. */
export const ROWS = ASKED + OPENS - 6;
export const EVERY = 3;
/** The count of days on the Fed's row, rolling down to what it is. */
export const ROLL = [ROWS + 4, ROWS + 16] as const;
export const PINGED = ROLL[1] + 2;

const TOP = 76;
const PITCH = 66;
/** How many days above the real count the roll starts from. */
const FROM = 9;

const when = (iso: string): string =>
  new Date(iso).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "Asia/Singapore",
  });

/**
 * Shot 8. The app's calendar: its rows slide up in turn, the count of days on the Fed's
 * decision rolls down to what it is, and the ring lands on what that day has meant for
 * gold. Figures: the app's calendar and what it measured (fixtures/film.json). Times
 * are the viewer's, as on the page.
 */
export const Calendar: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("calendar").duration;
  const rolled = tween(frame, ROLL[0], ROLL[1], 0, 1, EASE_IN_OUT);
  return (
    <AbsoluteFill>
      <Answer
        duration={duration}
        from={AT.coming}
        card
        asked={ASKED}
        framed={ASKED + OPENS - 6}
        title="Coming up"
        headline={`${events[0].name}: in ${events[0].days} days`}
      >
        {events.map((event, i) => {
          const slid = settle(frame, ROWS + i * EVERY, 15);
          return (
            <div
              key={event.at}
              style={{
                ...base,
                position: "absolute",
                left: 28,
                right: 28,
                top: TOP + i * PITCH + 18,
                height: PITCH,
                boxSizing: "border-box",
                borderTop: `1px solid ${C.line}`,
                paddingTop: 12,
                display: "flex",
                justifyContent: "space-between",
                translate: `0 ${(1 - slid) * 46}px`,
                opacity: Math.min(Math.max(slid * 1.6, 0), 1),
              }}
            >
              <span style={{ display: "flex", flexDirection: "column" }}>
                <span
                  style={{ fontSize: 19, fontWeight: 600, lineHeight: 1.35 }}
                >
                  {event.name}
                </span>
                <span style={{ fontSize: 15, color: C.muted, lineHeight: 1.4 }}>
                  {event.line}
                </span>
              </span>
              <span style={{ ...num, fontSize: 16, whiteSpace: "nowrap" }}>
                <span style={{ fontWeight: 700 }}>
                  In{" "}
                  <Ticker
                    value={
                      i === FED ? event.days + FROM * (1 - rolled) : event.days
                    }
                    places={i === FED ? 2 : undefined}
                  />{" "}
                  days
                </span>
                <span style={{ color: C.muted }}> · {when(event.at)}</span>
              </span>
            </div>
          );
        })}
      </Answer>
      <Ping
        since={frame - PINGED}
        x={AREA.x + (28 + 150) * ZOOM}
        y={AREA.y + (TOP + FED * PITCH + 18 + 49) * ZOOM}
      />
    </AbsoluteFill>
  );
};
