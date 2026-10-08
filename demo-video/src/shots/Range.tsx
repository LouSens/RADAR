import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import market from "../fixtures/market.json";
import { C, FEATURES, FONT, NUM_FEATURES, fade } from "../theme";
import { COPY, EASE, EASE_IN_OUT, tween } from "../timing";
import { Words } from "../Words";

const { range } = market;

const price = (value: number): string =>
  `$${Math.round(value).toLocaleString("en-US")}`;

// The chart, in frame pixels.
const LEFT = 210;
const SPAN = 1500;
const BASE = 866;
const TALL = 372;
const ROW = 372;

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

/** How far each half moves from the middle before it sets off for its end. */
const APART = 330;

const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** One figure, centred on a point, in the app's figures. */
const Figure: React.FC<{
  readonly value: number;
  readonly cx: number;
  readonly cy: number;
  readonly size: number;
  readonly opacity?: number;
}> = ({ value, cx, cy, size, opacity = 1 }) => (
  <div
    style={{
      position: "absolute",
      left: cx,
      top: cy,
      translate: "-50% -50%",
      fontFamily: FONT,
      fontFeatureSettings: NUM_FEATURES,
      fontVariantNumeric: "tabular-nums",
      fontSize: size,
      fontWeight: 600,
      letterSpacing: "-0.04em",
      lineHeight: 1,
      whiteSpace: "nowrap",
      color: C.ink,
      opacity,
    }}
  >
    {price(value)}
  </div>
);

/**
 * Shot 5. One price slides apart into the low and the high of the week's range, and the
 * simulated outcomes grow between them. Figures: fixtures/market.json.
 */
export const Range: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  const arrive = tween(frame, 0, 10, 0, 1, EASE);
  // First the one figure parts into two of itself, far enough to stand clear; then the
  // two travel to the ends of the range, counting away from the price as they go.
  const part = tween(frame, 22, 36, 0, 1, EASE_IN_OUT);
  const travel = tween(frame, 34, 54, 0, 1, EASE_IN_OUT);
  const counted = tween(frame, 36, 54, 0, 1, EASE);
  const size = 250 - 100 * part - 58 * travel;
  const cy = mix(540, ROW, travel);
  const lowX = 960 - APART * part + (X_LOW - (960 - APART)) * travel;
  const highX = 960 + APART * part + (X_HIGH - (960 + APART)) * travel;
  const seam = (lowX + highX) / 2;
  const guides = tween(frame, 52, 66, 0, 1, EASE);
  const now = tween(frame, 54, 66, 0, 1, EASE);
  const badge = spring({
    frame: frame - 74,
    fps,
    config: { damping: 11, mass: 0.5, stiffness: 190 },
  });

  const label: React.CSSProperties = {
    fontFamily: FONT,
    fontFeatureSettings: FEATURES,
    fontSize: 22,
    fontWeight: 600,
    letterSpacing: "0.075em",
    textTransform: "uppercase",
    color: C.muted,
  };

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", top: 64 }}>
        {/* The first sentence stands in the middle until the second joins it. */}
        <div
          style={{
            display: "flex",
            gap: 28,
            translate: `${tween(frame, 40, 54, 196, 0, EASE_IN_OUT)}px 0`,
          }}
        >
          <Words text={COPY.range[0]} at={8} size={92} accent={C.btc} />
          <Words text={COPY.range[1]} at={44} size={92} accent={C.btc} />
        </div>
      </AbsoluteFill>

      {/* The card's own heading: whose range, and how far it can be leaned on. */}
      <div
        style={{
          position: "absolute",
          left: LEFT,
          width: SPAN,
          top: 236,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          opacity: tween(frame, 48, 60, 0, 1),
        }}
      >
        <div
          style={{ ...label, display: "flex", alignItems: "center", gap: 14 }}
        >
          <span
            style={{
              width: 14,
              height: 14,
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
            fontSize: 26,
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

      {/* The outcomes: bright inside the range, dim outside it, as in the app. */}
      {range.counts.map((count, i) => {
        const mid = (range.edges[i] + range.edges[i + 1]) / 2;
        const inside = mid >= range.low && mid <= range.high;
        const start = 42 + Math.abs(i - NOW_BAR) * 1.15;
        const grown = spring({
          frame: frame - start,
          fps,
          config: { damping: 14, mass: 0.6, stiffness: 140 },
        });
        const height = (count / MOST) * TALL * grown;
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
          width: SPAN * tween(frame, 38, 60, 0, 1, EASE),
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
          top: BASE - TALL - 60,
          translate: "-50% 0",
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontSize: 28,
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
          top: BASE - TALL - 16,
          width: 0,
          height: (TALL + 16) * now,
          borderLeft: `2px dashed ${fade(C.ink, 0.6)}`,
        }}
      />

      {/* What the big figure is, until it parts. */}
      <div
        style={{
          ...label,
          position: "absolute",
          left: 960,
          top: 356,
          translate: "-50% 0",
          display: "flex",
          alignItems: "center",
          gap: 16,
          fontSize: 30,
          opacity: arrive * (1 - tween(frame, 18, 26, 0, 1)),
        }}
      >
        <span
          style={{
            width: 18,
            height: 18,
            borderRadius: "50%",
            background: C.btc,
          }}
        />
        Bitcoin now
      </div>

      {/* One figure cut down a seam: each half keeps to its own side of it, so the two
          are a single price until they have slid clear of each other. */}
      <AbsoluteFill style={{ clipPath: `inset(0 ${1920 - seam}px 0 0)` }}>
        <Figure
          value={mix(range.startPrice, range.low, counted)}
          cx={lowX}
          cy={cy}
          size={size}
          opacity={arrive}
        />
      </AbsoluteFill>
      <AbsoluteFill style={{ clipPath: `inset(0 0 0 ${seam}px)` }}>
        <Figure
          value={mix(range.startPrice, range.high, counted)}
          cx={highX}
          cy={cy}
          size={size}
          opacity={arrive}
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
            tween(frame, 19, 23, 0, 1) * (1 - tween(frame, 30, 40, 0, 1)),
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
          top: BASE + 18,
          display: "flex",
          justifyContent: "space-between",
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontSize: 26,
          color: C.faint,
          opacity: tween(frame, 60, 72, 0, 1),
        }}
      >
        <span>{price(first)}</span>
        <span>{price(last)}</span>
      </div>
      <AbsoluteFill style={{ alignItems: "center", top: BASE + 84 }}>
        <Words
          text={`${range.paths.toLocaleString("en-US")} simulated weeks.`}
          at={64}
          size={36}
          weight={500}
          colour={C.muted}
        />
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
