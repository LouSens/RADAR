import { useCurrentFrame } from "remotion";
import {
  BELOW_QUESTION as AREA,
  Lock,
  Pulled,
  Smear,
  filmFrame,
  rate,
} from "../Chain";
import film from "../fixtures/film.json";
import { C, fade } from "../theme";
import { EASE, EASE_IN, EASE_IN_OUT, shot, tween } from "../timing";
import { base, formatPrice, num } from "../ui/kit";
import { Ticker, settle } from "../ui/motion";
import { BEAD, Bead, THICK, Track, beadAt, trackY } from "./Level";

const { range } = film;

/** The chart is laid out at half size and drawn at twice that, inside its zone. */
const ZOOM = 2;
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

/** When the five beads have come together, and the price has risen out of them. */
const MEET = 10;
const ARRIVES = [8, 16] as const;
/** When the cut starts to open and when the two figures land. */
export const OPEN = [26, 52] as const;
/** When the first bar starts to grow, and when the range is marked. */
export const RISE = 34;
export const LOCKED = OPEN[1] + 8;

/** How wide the price is, and one digit of it, as multiples of its size. */
const WIDE = 3.9;
const DIGIT = 0.62;
/** Where each of the price's five digits is, from its middle, in its own size. */
const DIGITS = [-1.06, -0.44, 0.42, 1.04, 1.66] as const;
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

/** The outcomes as they stand at the end of the shot, in the frame's own pixels. */
export const OUTCOMES = range.counts.map((count, i) => {
  const mid = (range.edges[i] + range.edges[i + 1]) / 2;
  const tall = (count / MOST) * TALL;
  return {
    x: AREA.x + (LEFT + i * BAR + 1) * ZOOM,
    y: AREA.y + (BASE - tall) * ZOOM,
    w: (BAR - 2) * ZOOM,
    h: tall * ZOOM,
    inside: mid >= range.low && mid <= range.high,
  };
});
export const DIM = 0.38;

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
 * Shot 5. The five beads of shot 4 fly together and the price rises out of them, one
 * bead a digit. The price is cut down the middle into the low and the high of the
 * week's range, and the simulated outcomes grow between them from today's price
 * outwards. Figures: the app's simulation of Bitcoin's next seven days
 * (fixtures/film.json).
 */
export const Range: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("range").duration;
  const leaves = duration - 8;
  const gone = tween(frame, leaves, duration, 0, 1, EASE_IN);

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
  const arrived = tween(frame, ARRIVES[0], ARRIVES[1], 0, 1, EASE);
  // While the price is still large and low in the frame, no bar grows into it.
  const room = BASE - (cy + size * 0.5 + 10);
  const guides =
    tween(frame, OPEN[1] - 4, OPEN[1] + 10, 0, 1, EASE) * (1 - gone);
  const thinned = tween(frame, 0, 6, 0, 1, EASE_IN_OUT);

  return (
    <Pulled film={filmFrame("range", frame)}>
      {/* What is left of shot 4: its bars thin away and its beads fly together. */}
      {thinned < 1 &&
        [0, 1, 2, 3, 4].map((i) => (
          <Track
            key={i}
            y={trackY(i) + (THICK / 2) * thinned}
            thick={THICK * (1 - thinned)}
            opacity={1 - thinned}
          />
        ))}
      {frame < MEET + 7 && (
        <Smear x={rate(frame, 0, MEET) * 500} y={rate(frame, 0, MEET) * 300}>
          {DIGITS.map((offset, i) => {
            const from = beadAt(i);
            const flown = tween(
              frame,
              i * 0.5,
              MEET + i * 0.5,
              0,
              1,
              EASE_IN_OUT,
            );
            const burst = tween(frame, MEET, MEET + 6, 0, 1, EASE);
            return (
              <Bead
                key={offset}
                x={mix(
                  from.x,
                  AREA.x + (START.x + offset * HERO) * ZOOM,
                  flown,
                )}
                y={mix(from.y, AREA.y + START.y * ZOOM, flown)}
                size={BEAD + 30 * flown + 150 * burst}
                opacity={1 - burst}
              />
            );
          })}
        </Smear>
      )}

      {/* Placed first and enlarged inside: `zoom` would enlarge the placing as well. */}
      <div style={{ position: "absolute", left: AREA.x, top: AREA.y }}>
        <div
          style={{
            ...base,
            position: "relative",
            width: AREA.w / ZOOM,
            height: AREA.h / ZOOM,
            zoom: ZOOM,
          }}
        >
          {/* The outcomes: bright inside the range, dim outside it, as in the app. */}
          {frame >= RISE &&
            range.counts.map((count, i) => {
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
              const lit = OUTCOMES[i].inside
                ? tween(frame, OPEN[1] - 6, OPEN[1] + 6, 0.5, 1)
                : DIM;
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
              height: 2,
              background: "rgba(255,255,255,0.3)",
              opacity: 1 - gone,
            }}
          />
          {/* Where each end of the range falls among the outcomes. */}
          {[X_LOW, X_HIGH].map((at) => (
            <div
              key={at}
              style={{
                position: "absolute",
                left: at - 1,
                top: ROW + 32,
                width: 2,
                height: (BASE - ROW - 32) * guides,
                background: `linear-gradient(${C.ink}, ${fade(C.ink, 0.25)})`,
                opacity: 0.7 * (1 - gone),
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
                top: BASE + 5,
                fontSize: 17,
                color: C.muted,
                opacity: guides,
              }}
            >
              {formatPrice(edge)}
            </span>
          ))}

          {/* One figure and a cut: the left copy is only ever seen left of the cut and
              the right copy right of it, so two whole figures never touch. */}
          <div style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
            <div
              style={{
                position: "absolute",
                inset: 0,
                translate: `0 ${(1 - arrived) * 110 - gone * 110}%`,
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
          {/* The cut itself: a lit line where the price parts, so that the two halves
              are read as one figure being opened and not as a longer one. */}
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
              top: ROW - 72,
              fontSize: 17,
              fontWeight: 600,
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: C.muted,
              opacity: guides,
            }}
          >
            80% of simulated outcomes after {range.days} days
          </span>
        </div>
      </div>
      <div
        style={{
          position: "absolute",
          left: AREA.x + (X_LOW - (WIDE * RESTING) / 2) * ZOOM,
          top: AREA.y + (ROW - 34) * ZOOM,
          width: (X_HIGH - X_LOW + WIDE * RESTING) * ZOOM,
          height: 68 * ZOOM,
        }}
      >
        <Lock frame={frame} at={LOCKED} out={leaves} pad={12} />
      </div>
    </Pulled>
  );
};
