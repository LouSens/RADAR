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

/** How wide the cut between the two figures is once it has opened. */
const CUT = 200;

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
  // One move, on one curve. The price is two copies of itself lying exactly together,
  // the left one shown only left of a cut and the right one only right of it. As the cut
  // opens, each copy travels to its end of the range, shrinks to its place in the row and
  // counts to its value, so position, size and value all change together and none jumps.
  const open = tween(frame, 22, 56, 0, 1, EASE_IN_OUT);
  const size = mix(250, 92, open);
  const cy = mix(540, ROW, open);
  const lowX = mix(960, X_LOW, open);
  const highX = mix(960, X_HIGH, open);
  const seam = (lowX + highX) / 2;
  const cutLeft = seam - (CUT / 2) * open;
  const cutRight = seam + (CUT / 2) * open;
  // The cut is sharp while the copies lie together and softens as they part.
  const soft = 18 * open;
  const leftOnly = `linear-gradient(to right, #000 ${cutLeft - soft}px, transparent ${cutLeft}px)`;
  const rightOnly = `linear-gradient(to left, #000 ${1920 - cutRight - soft}px, transparent ${1920 - cutRight}px)`;
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
            translate: `${tween(frame, 42, 56, 196, 0, EASE_IN_OUT)}px 0`,
          }}
        >
          <Words text={COPY.range[0]} at={8} size={92} accent={C.btc} />
          <Words text={COPY.range[1]} at={46} size={92} accent={C.btc} />
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
          opacity: tween(frame, 50, 62, 0, 1),
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
        // The outcomes rise in the opening cut, from today's price outwards.
        const start = 27 + Math.abs(i - NOW_BAR) * 1.25;
        const grown = spring({
          frame: frame - start,
          fps,
          config: { damping: 14, mass: 0.6, stiffness: 140 },
        });
        // While the price is still large and low in the frame, no bar rises into it.
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

      {/* One figure and a cut: the left copy is only ever seen left of the cut and the
          right copy right of it, so two whole figures never touch. */}
      <AbsoluteFill style={{ maskImage: leftOnly, WebkitMaskImage: leftOnly }}>
        <Figure
          value={mix(range.startPrice, range.low, open)}
          cx={lowX}
          cy={cy}
          size={size}
          opacity={arrive}
        />
      </AbsoluteFill>
      <AbsoluteFill
        style={{ maskImage: rightOnly, WebkitMaskImage: rightOnly }}
      >
        <Figure
          value={mix(range.startPrice, range.high, open)}
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
