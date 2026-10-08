import { AbsoluteFill, useCurrentFrame } from "remotion";
import { ASKED, AREA, Answer, ZOOM } from "../Beat";
import film from "../fixtures/film.json";
import { C, fade } from "../theme";
import { EASE, EASE_IN_OUT, shot, tween } from "../timing";
import { AT } from "../ui/Desk";
import { base, formatPrice, num } from "../ui/kit";
import { Ping, Segmented, Ticker, settle } from "../ui/motion";

const { range } = film;

// The chart, in the app's pixels inside the answer's frame (832 by 388).
const LEFT = 40;
const SPAN = 752;
const BASE = 346;
const TALL = 150;
/** The row the two ends of the range come to rest on. */
const ROW = 134;
/** The one price is as large as the film's hero numbers (260 in the frame); the two
 *  ends of the range come down to this. */
const HERO = 130;
const RESTING = 50;
/** Where the one price stands before it is cut. */
const START = { x: 416, y: 222 } as const;

const first = range.edges[0];
const last = range.edges[range.edges.length - 1];
const x = (value: number): number =>
  LEFT + ((value - first) / (last - first)) * SPAN;
const X_LOW = x(range.low);
const X_HIGH = x(range.high);
const X_NOW = x(range.startPrice);
const MOST = Math.max(...range.counts);
const BAR = SPAN / range.counts.length;
const NOW_BAR = Math.floor((X_NOW - LEFT) / BAR);

const PRICE = Math.round(range.startPrice);
const LOW = Math.round(range.low);
const HIGH = Math.round(range.high);

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** When the cut starts to open and when the two figures land. */
export const OPEN = [ASKED + 18, ASKED + 44] as const;
/** When the first bar starts to grow. */
export const RISE = ASKED + 26;
/** When the card draws itself round the chart, and when the ring spreads. */
export const FRAMED = ASKED + 50;
export const PINGED = ASKED + 62;

/** How wide the price is, and one digit of it, as multiples of its size. */
const WIDE = 3.9;
const DIGIT = 0.62;
/** The clear space between the two copies, `open` of the way through the move. */
const gapAt = (open: number): number =>
  (X_HIGH - X_LOW) * open - WIDE * mix(HERO, RESTING, open);
/** How far through the move the two whole figures would first stand clear. */
const CLEAR = (() => {
  for (let open = 0; open <= 1; open += 0.001) {
    if (gapAt(open) > DIGIT * mix(HERO, RESTING, open)) {
      return open;
    }
  }
  return 1;
})();
/** By when each half has been made whole again, and counting starts. */
const COUNT_FROM = Math.min(CLEAR + 0.14, 0.9);

/** One figure, centred on a point, counting as a meter does. */
const Figure: React.FC<{
  readonly value: number;
  readonly cx: number;
  readonly cy: number;
  readonly size: number;
  readonly mask: string;
}> = ({ value, cx, cy, size, mask }) => (
  <div
    style={{
      position: "absolute",
      inset: 0,
      maskImage: mask,
      WebkitMaskImage: mask,
    }}
  >
    <div
      style={{
        ...base,
        position: "absolute",
        left: cx,
        top: cy,
        translate: "-50% -50%",
        fontSize: size,
        fontWeight: 600,
        letterSpacing: "-0.04em",
      }}
    >
      <Ticker value={value} prefix="$" places={5} />
    </div>
  </div>
);

/**
 * Shot 5. One price is cut down the middle into the low and the high of the week's
 * range, the simulated outcomes grow between them from today's price outwards, and the
 * app's own card draws itself round the chart. Figures: the app's simulation of
 * Bitcoin's next seven days (fixtures/film.json).
 */
export const Range: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("range").duration;

  // One move, on one curve. The price is two copies of itself lying exactly together.
  // Each copy shows only its own half, cut at its own middle: the left copy its left
  // half, the right copy its right half. So what parts is one figure in two halves,
  // and it still reads $83,276. Only when the two would stand clear of each other as
  // whole figures is each half made whole, and only then does each count to its end of
  // the range. No frame has a figure made of two different numbers.
  const open = tween(frame, OPEN[0], OPEN[1], 0, 1, EASE_IN_OUT);
  const size = mix(HERO, RESTING, open);
  const cy = mix(START.y, ROW, open);
  const lowX = mix(START.x, X_LOW, open);
  const highX = mix(START.x, X_HIGH, open);
  const seam = (lowX + highX) / 2;
  const whole = tween(open, CLEAR, COUNT_FROM, 0, 1, EASE_IN_OUT);
  const half = (WIDE * size) / 2 + 6;
  const cutLeft = lowX + half * whole;
  const cutRight = highX - half * whole;
  const leftOnly = `linear-gradient(to right, #000 ${cutLeft}px, transparent ${cutLeft}px)`;
  const rightOnly = `linear-gradient(to right, transparent ${cutRight}px, #000 ${cutRight}px)`;
  const counted = tween(open, COUNT_FROM, 1, 0, 1, (t) => t);
  // The price rises into the frame once its question has docked above it and Home
  // has stood back, so that it is never read against a lit card.
  const arrived = tween(frame, ASKED + 9, ASKED + 17, 0, 1, EASE);
  // While the price is still large and low in the frame, no bar grows into it.
  const room = BASE - (cy + size * 0.5 + 10);
  const guides = tween(frame, OPEN[1] - 4, OPEN[1] + 10, 0, 1, EASE);
  const chosen = tween(frame, FRAMED + 8, FRAMED + 18, 0, 1, EASE_IN_OUT);

  return (
    <AbsoluteFill>
      <Answer
        duration={duration}
        from={AT.btc}
        framed={FRAMED}
        title="Price range ahead"
        badge="solid"
        aside={
          frame >= FRAMED + 4 ? (
            <Segmented options={["1 day", "1 week", "1 month"]} at={chosen} />
          ) : null
        }
      >
        {/* The outcomes: bright inside the range, dim outside it, as in the app. */}
        {frame >= RISE &&
          range.counts.map((count, i) => {
            const mid = (range.edges[i] + range.edges[i + 1]) / 2;
            const inside = mid >= range.low && mid <= range.high;
            const grown = settle(
              frame,
              RISE + Math.abs(i - NOW_BAR) * 1.25,
              14,
            );
            const height = Math.max(
              Math.min((count / MOST) * TALL * grown, room),
              0,
            );
            // The range lights once both of its ends have landed.
            const lit = inside
              ? tween(frame, OPEN[1] - 6, OPEN[1] + 6, 0.45, 1)
              : 0.28;
            return (
              <div
                key={range.edges[i]}
                style={{
                  position: "absolute",
                  left: LEFT + i * BAR + 1,
                  width: BAR - 2,
                  top: BASE - height,
                  height,
                  borderRadius: "2px 2px 0 0",
                  background: fade(C.btc, lit),
                }}
              />
            );
          })}
        <div
          style={{
            position: "absolute",
            left: LEFT,
            width: SPAN * tween(frame, RISE - 4, RISE + 26, 0, 1, EASE),
            top: BASE,
            height: 1,
            background: C.lineStrong,
          }}
        />
        {/* Where each end of the range falls among the outcomes. */}
        {[X_LOW, X_HIGH].map((at) => (
          <div
            key={at}
            style={{
              position: "absolute",
              left: at - 0.5,
              top: ROW + 32,
              width: 1,
              height: (BASE - ROW - 32) * guides,
              background: `linear-gradient(${C.ink}, ${fade(C.ink, 0.25)})`,
              opacity: 0.7,
            }}
          />
        ))}
        {[first, last].map((edge, i) => (
          <span
            key={edge}
            style={{
              ...base,
              ...num,
              position: "absolute",
              left: i ? undefined : LEFT,
              right: i ? 832 - LEFT - SPAN : undefined,
              top: BASE + 6,
              fontSize: 12,
              color: C.faint,
              opacity: guides,
            }}
          >
            {formatPrice(edge)}
          </span>
        ))}

        {/* One figure and a cut: the left copy is only ever seen left of the cut and the
            right copy right of it, so two whole figures never touch. */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              position: "absolute",
              inset: 0,
              translate: `0 ${(1 - arrived) * 110}%`,
            }}
          >
            <Figure
              value={mix(PRICE, LOW, counted)}
              cx={lowX}
              cy={cy}
              size={size}
              mask={leftOnly}
            />
            <Figure
              value={mix(PRICE, HIGH, counted)}
              cx={highX}
              cy={cy}
              size={size}
              mask={rightOnly}
            />
          </div>
        </div>
        {/* The cut itself: a lit line where the price parts, so that the two halves are
            read as one figure being opened and not as a longer one. */}
        <div
          style={{
            position: "absolute",
            left: seam - 1.5,
            top: cy - size * 0.62,
            width: 3,
            height: size * 1.24,
            borderRadius: 2,
            background: C.btc,
            boxShadow: `0 0 16px 4px ${fade(C.btc, 0.6)}`,
            opacity:
              tween(frame, OPEN[0] - 4, OPEN[0], 0, 1) *
              (1 - tween(open, 0.02, 0.12, 0, 1)),
          }}
        />
        <span
          style={{
            ...base,
            position: "absolute",
            left: (X_LOW + X_HIGH) / 2,
            top: ROW,
            translate: "-50% -50%",
            fontSize: 22,
            fontWeight: 500,
            color: C.muted,
            opacity: guides,
          }}
        >
          to
        </span>
        <span
          style={{
            ...base,
            position: "absolute",
            left: LEFT,
            top: ROW - 62,
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: "0.075em",
            textTransform: "uppercase",
            color: C.muted,
            opacity: guides,
          }}
        >
          80% of simulated outcomes after {range.days} days
        </span>
      </Answer>
      <Ping
        since={frame - PINGED}
        x={AREA.x + ((X_LOW + X_HIGH) / 2) * ZOOM}
        y={AREA.y + ROW * ZOOM}
        reach={240}
      />
    </AbsoluteFill>
  );
};
