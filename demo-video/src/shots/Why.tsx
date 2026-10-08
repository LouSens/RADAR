import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ASKED, AREA, Answer, ZOOM } from "../Beat";
import film from "../fixtures/film.json";
import { C, fade } from "../theme";
import { EASE_IN_OUT, shot, tween } from "../timing";
import { AT } from "../ui/Desk";
import { base, num } from "../ui/kit";
import { Ping, Pop, pop, settle } from "../ui/motion";

const days = film.moves.days;
const worst = days[days.length - 1];

// The chart, in the app's pixels inside the answer's frame.
const LEFT = 44;
const RIGHT = 788;
const MIDDLE = 236;
const HALF = 118;
const SLOT = (RIGHT - LEFT) / days.length;
const usual = (d: (typeof days)[number]): number =>
  d.timesUsual ? Math.abs(d.move) / d.timesUsual : 0;
const MOST = Math.max(...days.map((d) => Math.max(Math.abs(d.move), usual(d))));
const y = (move: number): number => MIDDLE - (move / MOST) * HALF;
const x = (i: number): number => LEFT + (i + 0.5) * SLOT;

/** When the band of a usual day is laid in, and when the first bar grows. */
export const BAND = ASKED + 6;
export const BARS = ASKED + 10;
/** The crosshair's slide along the days, to the day of the fall. */
export const CROSS = [ASKED + 34, ASKED + 50] as const;
/** When that day's bar drops, and when its figures pop up. */
export const DROP = CROSS[1];
export const TIP = DROP + 5;
/** When the card draws itself round the chart, and when the ring spreads. */
export const FRAMED = ASKED + 62;
export const PINGED = ASKED + 74;

const short = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
const percent = (move: number): string =>
  `${move < 0 ? "−" : "+"}${Math.abs(move * 100).toFixed(2)}%`;

/** The pale band: the size of a usual day, above and below the line, day by day. */
const band = (): string => {
  const top = days.map(
    (d, i) => `${x(i).toFixed(1)},${y(usual(d)).toFixed(1)}`,
  );
  const foot = days
    .map((d, i) => `${x(i).toFixed(1)},${y(-usual(d)).toFixed(1)}`)
    .reverse();
  return [...top, ...foot].join(" ");
};

/**
 * Shot 3. Bitcoin's last thirty days as bars about a line, with a pale band for the size
 * of a usual day. A crosshair slides to the day it fell; that day's bar drops out of the
 * band in red, and its figures pop up. Then the app's own card draws itself round the
 * chart. Figures: the app's "why it moved" data for Bitcoin (fixtures/film.json).
 */
export const Why: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("why").duration;
  const last = days.length - 1;
  const laid = tween(frame, BAND, BAND + 14, 0, 1, EASE_IN_OUT);
  const slide = tween(frame, CROSS[0], CROSS[1], 0, 1, EASE_IN_OUT);
  const under = Math.round(slide * last);
  const crossX = LEFT + (0.5 + slide * last) * SLOT;
  const tip = pop(frame, TIP);
  const tipY = y(worst.move) + 22;

  return (
    <AbsoluteFill>
      <Answer
        duration={duration}
        from={AT.btc}
        framed={FRAMED}
        title="Why it moved"
        headline={`Down ${Math.abs(worst.move * 100).toFixed(2)}% on ${short(worst.day)}: larger than ${Math.round((worst.rank ?? 0) * 100)} of 100 days before it`}
        badge={film.moves.trust}
      >
        {frame >= BAND && (
          <svg
            width={832}
            height={388}
            style={{
              position: "absolute",
              left: 0,
              top: 0,
              overflow: "visible",
            }}
          >
            <defs>
              <clipPath id="why-band">
                <rect
                  x={LEFT}
                  y={0}
                  width={(RIGHT - LEFT) * laid}
                  height={388}
                />
              </clipPath>
            </defs>
            <polygon
              points={band()}
              fill={fade(C.ink, 0.07)}
              stroke={fade(C.ink, 0.16)}
              strokeWidth={0.75}
              clipPath="url(#why-band)"
            />
            <line
              x1={LEFT}
              x2={LEFT + (RIGHT - LEFT) * laid}
              y1={MIDDLE}
              y2={MIDDLE}
              stroke={C.lineStrong}
              strokeWidth={1}
            />
            {days.map((d, i) => {
              const fell = i === last;
              // The days grow one after another; the day of the fall waits for the
              // crosshair, then drops.
              const grown = fell
                ? settle(frame, DROP, 11)
                : settle(frame, BARS + i, 14);
              const tall = Math.abs(y(d.move) - MIDDLE) * grown;
              const colour = fell
                ? C.alert
                : d.move < 0
                  ? fade(C.alert, 0.5)
                  : fade(C.calm, 0.5);
              return (
                <rect
                  key={d.day}
                  x={x(i) - SLOT * 0.3}
                  width={SLOT * 0.6}
                  y={d.move < 0 ? MIDDLE : MIDDLE - tall}
                  height={Math.max(tall, 0)}
                  rx={2.5}
                  fill={
                    i === under && slide > 0 && !fell
                      ? d.move < 0
                        ? C.alert
                        : C.calm
                      : colour
                  }
                  style={
                    fell && grown > 0.5
                      ? { filter: `drop-shadow(0 0 6px ${fade(C.alert, 0.6)})` }
                      : undefined
                  }
                />
              );
            })}
            {slide > 0 && (
              <line
                x1={crossX}
                x2={crossX}
                y1={MIDDLE - HALF - 6}
                y2={MIDDLE + HALF + 6}
                stroke={fade(C.ink, 0.5)}
                strokeWidth={1}
                strokeDasharray="3 3"
              />
            )}
          </svg>
        )}
        {/* A usual day, named once at the band's edge. */}
        <span
          style={{
            ...base,
            position: "absolute",
            left: LEFT,
            top: y(usual(days[0])) - 22,
            fontSize: 11,
            color: C.faint,
            opacity: laid,
          }}
        >
          A usual day
        </span>
        {[0, Math.floor(last / 2), last].map((i) => (
          <span
            key={i}
            style={{
              ...base,
              ...num,
              position: "absolute",
              left: x(i),
              top: MIDDLE + HALF + 10,
              translate: i === last ? "-100% 0" : i === 0 ? "0 0" : "-50% 0",
              fontSize: 11,
              color: C.faint,
              opacity: laid,
            }}
          >
            {short(days[i].day)}
          </span>
        ))}
        {/* What the crosshair is on, while it slides. */}
        {slide > 0 && tip < 0.05 && (
          <span
            style={{
              ...base,
              ...num,
              position: "absolute",
              left: crossX,
              top: MIDDLE - HALF - 30,
              translate: "-50% 0",
              padding: "1px 8px",
              borderRadius: 8,
              background: "#1b1d24",
              border: `1px solid ${C.line}`,
              fontSize: 12,
              whiteSpace: "nowrap",
            }}
          >
            {short(days[under].day)} · {percent(days[under].move)}
          </span>
        )}
        {/* Where it stops: the day's fall, and how large it was against a usual day. */}
        <Pop
          by={tip}
          origin="100% 0"
          style={{
            position: "absolute",
            left: x(last) - 14,
            top: tipY,
            translate: "-100% 0",
          }}
        >
          <span
            style={{
              ...base,
              ...num,
              padding: "7px 14px",
              borderRadius: 12,
              background: "#1b1d24",
              border: `1px solid ${fade(C.alert, 0.5)}`,
              boxShadow: "0 12px 30px rgba(0,0,0,0.5)",
              fontSize: 18,
              fontWeight: 600,
              whiteSpace: "nowrap",
            }}
          >
            <span style={{ color: C.alert }}>{percent(worst.move)}</span>
            <span style={{ color: C.faint }}> · </span>
            {(worst.timesUsual ?? 0).toFixed(1)}× a usual day
          </span>
        </Pop>
      </Answer>
      <Ping
        since={frame - PINGED}
        x={AREA.x + (x(last) - 14 - 92) * ZOOM}
        y={AREA.y + (tipY + 20) * ZOOM}
      />
    </AbsoluteFill>
  );
};
