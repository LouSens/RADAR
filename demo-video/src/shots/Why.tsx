import { AbsoluteFill, interpolateColors, useCurrentFrame } from "remotion";
import { Lock, Pulled, Smear, filmFrame, rate } from "../Chain";
import film from "../fixtures/film.json";
import { C, fade } from "../theme";
import { EASE_IN_OUT, shot, tween } from "../timing";
import { base, num } from "../ui/kit";
import { Pop, pop, settle } from "../ui/motion";

const days = film.moves.days;
const worst = days[days.length - 1];
const week = film.markets[0].weekCloses;

/** This shot starts early: its first frames are the push into Home's Bitcoin card. */
export const LEAD = 14;

// The chart, in the frame's own pixels, under its question.
export const LEFT = 128;
export const RIGHT = 1792;
export const MIDDLE = 590;
const HALF = 270;
const SLOT = (RIGHT - LEFT) / days.length;
const WIDE = 34;
const usual = (d: (typeof days)[number]): number =>
  d.timesUsual ? Math.abs(d.move) / d.timesUsual : 0;
const MOST = Math.max(...days.map((d) => Math.max(Math.abs(d.move), usual(d))));
const y = (move: number): number => MIDDLE - (move / MOST) * HALF;
const x = (i: number): number => LEFT + (i + 0.5) * SLOT;
const last = days.length - 1;

/**
 * The week's line in Home's Bitcoin card, in the frame (ui/Desk and ui/kit put it
 * there), and the push that makes it as wide as the chart. Home is pushed by the same
 * move (DeskLayer), so the line never leaves its place on the card.
 */
const SPARK = { x: 416.27, y: 680.67, w: 428.8, h: 58.67 } as const;
/** The card draws its line 2 in from the sides of a box 120 by 36 (ui/kit, Sparkline). */
const INSET = { x: 2 / 120, y: 2 / 36 } as const;
/** How thick the card's line is, in the frame. */
const CARD_LINE = 1.6;
const CLOSE = (RIGHT - LEFT) / SPARK.w;
const FROM = { x: SPARK.x + SPARK.w / 2, y: SPARK.y + SPARK.h / 2 } as const;
export const pushAt = (film: number): { k: number; x: number; y: number } => {
  const at = shot("why").from;
  const t = tween(film, at - LEAD, at, 0, 1, EASE_IN_OUT);
  const k = 1 + (CLOSE - 1) * t;
  return {
    k,
    x: FROM.x + ((LEFT + RIGHT) / 2 - FROM.x) * t,
    y: FROM.y + (MIDDLE - FROM.y) * t,
  };
};
/** The point of Home the push holds on to. */
export const PUSHED_FROM = FROM;

/** When the line has fallen flat and is the chart's own line. */
const FLAT = [0, 9] as const;
/** When the first bar grows, and the band of a usual day is laid in. */
export const BARS = 5;
const BAND = 6;
/** The crosshair's slide along the days, to the day of the fall. */
export const CROSS = [28, 40] as const;
/** When that day's bar drops, when its figures pop up, and when they are marked. */
export const DROP = CROSS[1];
export const TIP = DROP + 4;
export const LOCKED = TIP + 6;

const short = (iso: string): string =>
  new Date(iso).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
const percent = (move: number): string =>
  `${move < 0 ? "−" : "+"}${Math.abs(move * 100).toFixed(2)}%`;

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
 * The thirty days: a bar a day about a line, at their true scale, in the app's green
 * and red, with a pale band for the size of a usual day. The next shot draws them too,
 * to flatten them.
 */
export const Chart: React.FC<{
  /** How far each day's bar has grown. */
  readonly grown: (i: number) => number;
  /** How far the band has been laid in, and how strongly it and the labels show. */
  readonly laid: number;
  readonly notes: number;
  /** The day the crosshair is on, if it is on one. */
  readonly under?: number;
  /** How thick the line is, and its colour. */
  readonly line?: number;
  readonly colour?: string;
}> = ({
  grown,
  laid,
  notes,
  under,
  line = 4,
  colour = "rgba(255,255,255,0.3)",
}) => (
  <>
    <svg
      width={1920}
      height={1080}
      style={{ position: "absolute", left: 0, top: 0 }}
    >
      <defs>
        <clipPath id="why-band">
          <rect x={LEFT} y={0} width={(RIGHT - LEFT) * laid} height={1080} />
        </clipPath>
      </defs>
      <polygon
        points={band()}
        fill={fade(C.ink, 0.09)}
        stroke={fade(C.ink, 0.22)}
        strokeWidth={2}
        clipPath="url(#why-band)"
        opacity={notes}
      />
      <line
        x1={LEFT}
        x2={RIGHT}
        y1={MIDDLE}
        y2={MIDDLE}
        stroke={colour}
        strokeWidth={line}
        strokeLinecap="round"
      />
      {days.map((d, i) => {
        const fell = i === last;
        const tall = Math.max(Math.abs(y(d.move) - MIDDLE) * grown(i), 0);
        const tint = d.move < 0 ? C.alert : C.calm;
        return (
          <rect
            key={d.day}
            x={x(i) - WIDE / 2}
            width={WIDE}
            y={d.move < 0 ? MIDDLE : MIDDLE - tall}
            height={tall}
            rx={Math.min(7, tall / 2)}
            fill={fell || i === under ? tint : fade(tint, 0.7)}
          />
        );
      })}
    </svg>
    <span
      style={{
        ...base,
        position: "absolute",
        left: LEFT,
        top: y(usual(days[0])) - 58,
        fontSize: 34,
        color: C.muted,
        opacity: laid * notes,
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
          top: MIDDLE + HALF + 20,
          translate: i === last ? "-100% 0" : i === 0 ? "0 0" : "-50% 0",
          fontSize: 34,
          color: C.muted,
          opacity: laid * notes,
        }}
      >
        {short(days[i].day)}
      </span>
    ))}
  </>
);

/** Where the day's figures stand: beside its bar, half way down it. */
const TIP_AT = {
  right: 1920 - (x(last) - WIDE / 2 - 30),
  y: (MIDDLE + y(worst.move)) / 2,
} as const;

/** The day's fall, and how large it was against a usual day. */
export const Tip: React.FC<{
  readonly by: number;
  readonly children?: React.ReactNode;
}> = ({ by, children }) => (
  <Pop
    by={by}
    origin="100% 50%"
    style={{
      position: "absolute",
      right: TIP_AT.right,
      top: TIP_AT.y,
      translate: "0 -50%",
    }}
  >
    <span
      style={{
        ...base,
        ...num,
        position: "relative",
        padding: "14px 28px",
        borderRadius: 22,
        background: "#1d2029",
        border: `2px solid ${fade(C.alert, 0.6)}`,
        boxShadow: "0 18px 44px rgba(0,0,0,0.55)",
        fontSize: 46,
        fontWeight: 600,
        lineHeight: 1.3,
        whiteSpace: "nowrap",
      }}
    >
      <span style={{ color: C.alert }}>{percent(worst.move)}</span>
      <span style={{ color: C.faint }}> · </span>
      {(worst.timesUsual ?? 0).toFixed(1)}× a usual day
      {children}
    </span>
  </Pop>
);

/**
 * Shot 3. The camera pushes into Home's Bitcoin card and the week's line there is
 * stretched to the width of the frame, falls flat, and thirty days grow about it as
 * bars, at their true scale. A crosshair slides to the day it fell: its bar drops in
 * red, and its figures pop up beside it and are marked. Figures: the app's "why it
 * moved" data for Bitcoin (fixtures/film.json).
 */
export const Why: React.FC = () => {
  const frame = useCurrentFrame() - LEAD;
  const at = filmFrame("why", frame);
  const out = shot("why").duration - 5;

  const push = pushAt(at);
  const box = {
    x: push.x - (SPARK.w * push.k) / 2,
    y: push.y - (SPARK.h * push.k) / 2,
    w: SPARK.w * push.k,
    h: SPARK.h * push.k,
  };
  const flat = tween(frame, FLAT[0], FLAT[1], 0, 1, EASE_IN_OUT);
  const low = Math.min(...week);
  const high = Math.max(...week);
  const path = week
    .map((value, i) => {
      const px =
        box.x + (INSET.x + (i / (week.length - 1)) * (1 - 2 * INSET.x)) * box.w;
      const py =
        box.y +
        (1 - INSET.y - ((value - low) / (high - low)) * (1 - 2 * INSET.y)) *
          box.h;
      return `${i === 0 ? "M" : "L"}${px.toFixed(1)} ${(py + (MIDDLE - py) * flat).toFixed(1)}`;
    })
    .join(" ");

  const laid = tween(frame, BAND, BAND + 12, 0, 1, EASE_IN_OUT);
  const slide = tween(frame, CROSS[0], CROSS[1], 0, 1, EASE_IN_OUT);
  const sliding = slide > 0 && slide < 1;
  const under = Math.round(slide * last);
  const crossX = LEFT + (0.5 + slide * last) * SLOT;

  return (
    <Pulled film={at}>
      {frame >= FLAT[1] ? (
        <Chart
          grown={(i) =>
            i === last
              ? settle(frame, DROP, 11)
              : settle(frame, BARS + i * 0.5, 14)
          }
          laid={laid}
          notes={1}
          under={sliding ? under : undefined}
        />
      ) : (
        <>
          <Smear y={rate(frame, FLAT[0], FLAT[1]) * box.h}>
            <svg width={1920} height={1080}>
              <path
                d={path}
                fill="none"
                stroke={interpolateColors(
                  flat,
                  [0, 1],
                  [C.btc, "rgba(255,255,255,0.3)"],
                )}
                strokeWidth={
                  CARD_LINE +
                  (6 - CARD_LINE) * tween(frame, -LEAD, 0, 0, 1, EASE_IN_OUT) -
                  2 * flat
                }
                strokeLinejoin="round"
                strokeLinecap="round"
              />
            </svg>
          </Smear>
          <AbsoluteFill>
            <Chart
              grown={(i) =>
                i === last ? 0 : settle(frame, BARS + i * 0.5, 14)
              }
              laid={laid}
              notes={1}
              line={0}
            />
          </AbsoluteFill>
        </>
      )}

      {/* The crosshair, and what it is on while it slides. */}
      {slide > 0 && frame < out + 6 && (
        <div
          style={{
            position: "absolute",
            left: crossX - 1.5,
            top: MIDDLE - HALF - 10,
            width: 3,
            height: HALF * 2 + 20,
            backgroundImage: `linear-gradient(${fade(C.ink, 0.7)} 55%, transparent 55%)`,
            backgroundSize: "3px 14px",
            opacity: 1 - tween(frame, TIP, TIP + 8, 0, 0.6, (t) => t),
          }}
        />
      )}
      {sliding && (
        <span
          style={{
            ...base,
            ...num,
            position: "absolute",
            left: Math.min(Math.max(crossX, LEFT + 150), RIGHT - 150),
            top: MIDDLE - HALF - 76,
            translate: "-50% 0",
            padding: "4px 18px",
            borderRadius: 16,
            background: "#1d2029",
            border: `2px solid ${C.line}`,
            fontSize: 34,
            lineHeight: 1.4,
            whiteSpace: "nowrap",
          }}
        >
          {short(days[under].day)} · {percent(days[under].move)}
        </span>
      )}
      <Tip by={pop(frame, TIP)}>
        <Lock frame={frame} at={LOCKED} out={out - 1} />
      </Tip>
    </Pulled>
  );
};
