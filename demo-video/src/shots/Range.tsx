import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import market from "../fixtures/market.json";
import { C, FEATURES, FONT, NUM_FEATURES, fade } from "../theme";
import { COPY, EASE, EASE_IN_OUT, tween } from "../timing";
import { HERO, Headline, LINE, MARGIN, Small, TOP, hero } from "../Type";

const { range } = market;

const price = (value: number): string =>
  `$${Math.round(value).toLocaleString("en-US")}`;

// The card under the headline, in frame pixels: its heading, the row the two ends of the
// range come to rest on, and the chart.
const LEFT = 210;
const SPAN = 1500;
const HEADING = 394;
const ROW = 514;
const BASE = 936;
const TALL = 296;
/** The size the two figures come down to, as figures of the card. */
const RESTING = 92;
/** Where the one price stands before it is cut. */
const START = { x: 960, y: 690 } as const;

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

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** When the cut starts to open and when the two figures land. */
export const OPEN = [22, 56] as const;
/** How wide the price is, and its widest digit, as multiples of its size. */
const WIDE = 3.84;
const DIGIT = 0.64;
/** The clear space between the two copies, `open` of the way through the move. */
const gapAt = (open: number): number =>
  (X_HIGH - X_LOW) * open - WIDE * mix(HERO, RESTING, open);
/** How far through the move the space first exceeds one digit: counting starts there. */
const COUNT_FROM = (() => {
  for (let open = 0; open <= 1; open += 0.001) {
    if (gapAt(open) > DIGIT * mix(HERO, RESTING, open)) {
      return open;
    }
  }
  return 1;
})();

/** One figure, centred on a point. It starts as a hero number. */
const Figure: React.FC<{
  readonly value: number;
  readonly cx: number;
  readonly cy: number;
  readonly size: number;
}> = ({ value, cx, cy, size }) => (
  <div
    style={{
      ...hero,
      position: "absolute",
      left: cx,
      top: cy,
      translate: "-50% -50%",
      fontSize: size,
    }}
  >
    {price(value)}
  </div>
);

/**
 * Shot 5. One price is cut into the low and the high of the week's range, and the
 * simulated outcomes rise in the cut. Figures: fixtures/market.json.
 */
export const Range: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // One move, on one curve. The price is two copies of itself lying exactly together,
  // the left one shown only left of a cut and the right one only right of it. Both show
  // the same value while they part, so no frame has a figure made of two different
  // numbers. Once they stand clear of each other, with more than a digit of space
  // between them, each counts to its end of the range as it finishes its journey.
  const open = tween(frame, OPEN[0], OPEN[1], 0, 1, EASE_IN_OUT);
  const size = mix(HERO, RESTING, open);
  const cy = mix(START.y, ROW, open);
  const lowX = mix(START.x, X_LOW, open);
  const highX = mix(START.x, X_HIGH, open);
  const seam = (lowX + highX) / 2;
  const gap = Math.max(gapAt(open), 0);
  const cutLeft = seam - gap / 2 + Math.min(gap, 6);
  const cutRight = seam + gap / 2 - Math.min(gap, 6);
  const leftOnly = `linear-gradient(to right, #000 ${cutLeft}px, transparent ${cutLeft}px)`;
  const rightOnly = `linear-gradient(to left, #000 ${1920 - cutRight}px, transparent ${1920 - cutRight}px)`;
  const counted = tween(open, COUNT_FROM, 1, 0, 1, (t) => t);
  // While the price is still large and low in the frame, no bar rises into it.
  const room = BASE - (cy + size * 0.45 + 22);
  const guides = tween(frame, 54, 68, 0, 1, EASE);
  const now = tween(frame, 56, 68, 0, 1, EASE);
  const badge = spring({
    frame: frame - 74,
    fps,
    config: { damping: 11, mass: 0.5, stiffness: 190 },
  });

  const label: React.CSSProperties = {
    fontFamily: FONT,
    fontFeatureSettings: FEATURES,
    fontSize: 34,
    fontWeight: 600,
    letterSpacing: "0.075em",
    textTransform: "uppercase",
    color: C.muted,
  };

  return (
    <AbsoluteFill>
      <Headline
        lines={COPY.range.lines}
        at={6}
        lineAt={[6, 46]}
        accent={C.btc}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
      />
      {/* The small line stands on the second line's baseline, after its one word. */}
      <Small
        text={COPY.range.small}
        at={62}
        style={{
          position: "absolute",
          left: MARGIN + 520,
          top: TOP + LINE + 76,
        }}
      />

      {/* The card's own heading: whose range, and how far it can be leaned on. */}
      <div
        style={{
          position: "absolute",
          left: LEFT,
          width: SPAN,
          top: HEADING,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          opacity: tween(frame, 50, 62, 0, 1),
        }}
      >
        <div
          style={{ ...label, display: "flex", alignItems: "center", gap: 14 }}
        >
          <span
            style={{
              width: 20,
              height: 20,
              borderRadius: "50%",
              background: C.btc,
            }}
          />
          Bitcoin · price range ahead · {range.horizonDays} days
        </div>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 12,
            padding: "7px 20px",
            borderRadius: 999,
            border: `1.5px solid ${C.lineStrong}`,
            fontFamily: FONT,
            fontSize: 34,
            fontWeight: 500,
            color: C.ink,
            scale: badge,
            opacity: Math.min(badge * 2, 1),
            textTransform: "capitalize",
          }}
        >
          <span
            style={{
              width: 12,
              height: 12,
              borderRadius: "50%",
              background: C.calm,
              boxShadow: `0 0 ${12 * badge}px ${fade(C.calm, 0.8)}`,
            }}
          />
          {range.grade}
        </div>
      </div>

      {/* The outcomes: bright inside the range, dim outside it, as in the app. They rise
          in the opening cut, from today's price outwards. */}
      {range.counts.map((count, i) => {
        const mid = (range.edges[i] + range.edges[i + 1]) / 2;
        const inside = mid >= range.low && mid <= range.high;
        const start = 27 + Math.abs(i - NOW_BAR) * 1.25;
        const grown = spring({
          frame: frame - start,
          fps,
          config: { damping: 14, mass: 0.6, stiffness: 140 },
        });
        const height = Math.min((count / MOST) * TALL * grown, room);
        return (
          <div
            key={range.edges[i]}
            style={{
              position: "absolute",
              left: LEFT + i * BAR + 2,
              width: BAR - 4,
              top: BASE - height,
              height,
              borderRadius: "4px 4px 0 0",
              background: inside ? C.btc : fade(C.btc, 0.3),
              boxShadow: inside
                ? `0 0 ${24 * grown}px ${fade(C.btc, 0.22)}`
                : undefined,
            }}
          />
        );
      })}
      <div
        style={{
          position: "absolute",
          left: LEFT,
          width: SPAN * tween(frame, 26, 56, 0, 1, EASE),
          top: BASE,
          height: 2,
          background: C.lineStrong,
        }}
      />

      {/* Where each end of the range falls among the outcomes. */}
      {[X_LOW, X_HIGH].map((at) => (
        <div
          key={at}
          style={{
            position: "absolute",
            left: at - 1,
            top: ROW + 62,
            width: 2,
            height: (BASE - ROW - 62) * guides,
            background: `linear-gradient(${C.ink}, ${fade(C.ink, 0.25)})`,
            opacity: 0.7,
          }}
        />
      ))}

      {/* Today's price stays where it was, as a mark on the chart. */}
      <div
        style={{
          position: "absolute",
          left: X_NOW,
          top: BASE - TALL - 58,
          translate: "-50% 0",
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontSize: 34,
          color: C.muted,
          whiteSpace: "nowrap",
          opacity: now,
        }}
      >
        Now {price(range.startPrice)}
      </div>
      <div
        style={{
          position: "absolute",
          left: X_NOW - 1,
          top: BASE - TALL - 14,
          width: 0,
          height: (TALL + 14) * now,
          borderLeft: `2px dashed ${fade(C.ink, 0.6)}`,
        }}
      />

      {/* One figure and a cut: the left copy is only ever seen left of the cut and the
          right copy right of it, so two whole figures never touch. */}
      <AbsoluteFill style={{ maskImage: leftOnly, WebkitMaskImage: leftOnly }}>
        <Figure
          value={mix(range.startPrice, range.low, counted)}
          cx={lowX}
          cy={cy}
          size={size}
        />
      </AbsoluteFill>
      <AbsoluteFill
        style={{ maskImage: rightOnly, WebkitMaskImage: rightOnly }}
      >
        <Figure
          value={mix(range.startPrice, range.high, counted)}
          cx={highX}
          cy={cy}
          size={size}
        />
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          left: seam - 2,
          top: cy - size * 0.72,
          width: 4,
          height: size * 1.44,
          borderRadius: 2,
          background: C.btc,
          boxShadow: `0 0 28px 6px ${fade(C.btc, 0.6)}`,
          opacity:
            tween(frame, 19, 23, 0, 1) * (1 - tween(frame, 27, 38, 0, 1)),
        }}
      />
      <div
        style={{
          position: "absolute",
          left: (X_LOW + X_HIGH) / 2,
          top: ROW,
          translate: "-50% -50%",
          fontFamily: FONT,
          fontSize: 44,
          fontWeight: 500,
          color: C.muted,
          opacity: tween(frame, 50, 60, 0, 1),
        }}
      >
        to
      </div>

      <div
        style={{
          position: "absolute",
          left: LEFT,
          width: SPAN,
          top: BASE + 10,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontSize: 34,
          color: C.faint,
          opacity: tween(frame, 60, 72, 0, 1),
        }}
      >
        <span>{price(first)}</span>
        <span>{price(last)}</span>
      </div>
    </AbsoluteFill>
  );
};
