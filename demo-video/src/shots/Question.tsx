import { AbsoluteFill, useCurrentFrame } from "remotion";
import market from "../fixtures/market.json";
import { C, FONT, NUM_FEATURES, fade } from "../theme";
import { COPY, EASE, tween } from "../timing";
import { formatPrice, label } from "../ui/kit";
import { Words } from "../Words";

const bitcoin = market.markets[0];
const closes = bitcoin.weekCloses;

/** The price changes this often, in frames. */
const TICK = 4;
/** The hours the shot plays through: the last of the week, ending on the newest. */
const HOURS = 30;
const FIRST = closes.length - HOURS;

// The trace under the price, in frame pixels.
const TRACE = { left: 0, width: 1920, top: 742, height: 190 } as const;
const shown = closes.slice(FIRST);
const LOW = Math.min(...shown);
const HIGH = Math.max(...shown);
const point = (i: number): readonly [number, number] => [
  TRACE.left + (i / (HOURS - 1)) * TRACE.width,
  TRACE.top + TRACE.height * (1 - (shown[i] - LOW) / (HIGH - LOW)),
];

/**
 * Shot 1. A Bitcoin price that will not keep still, and the question it puts. The prices
 * are real: the last hours of the week in fixtures/market.json, one every few frames.
 */
export const Question: React.FC = () => {
  const frame = useCurrentFrame();
  const step = Math.min(Math.floor(frame / TICK), HOURS - 1);
  const since = frame - step * TICK;
  const price = shown[step];
  const before = shown[Math.max(step - 1, 0)];
  const up = price >= before;
  // Each new price knocks the figure a little the way it moved, and it settles back.
  const knock =
    step === 0 || step === HOURS - 1
      ? 0
      : 1 - tween(since, 0, TICK, 0, 1, EASE);
  const arrive = tween(frame, 0, 12, 0, 1, EASE);

  const head = point(step);
  const path = shown
    .slice(0, step + 1)
    .map(
      (_, i) =>
        `${i === 0 ? "M" : "L"}${point(i)[0].toFixed(1)} ${point(i)[1].toFixed(1)}`,
    )
    .join(" ");

  return (
    <AbsoluteFill>
      {/* The hours so far, drawn as they pass. */}
      <svg
        width={1920}
        height={1080}
        style={{ position: "absolute", inset: 0, opacity: 0.5 * arrive }}
      >
        <defs>
          <linearGradient id="question-trace" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor={C.btc} stopOpacity="0" />
            <stop offset="0.35" stopColor={C.btc} stopOpacity="0.55" />
            <stop offset="1" stopColor={C.btc} stopOpacity="1" />
          </linearGradient>
        </defs>
        {step > 0 && (
          <path
            d={path}
            fill="none"
            stroke="url(#question-trace)"
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )}
        <circle cx={head[0]} cy={head[1]} r={7 + knock * 5} fill={C.btc} />
        <circle
          cx={head[0]}
          cy={head[1]}
          r={16 + knock * 22}
          fill={fade(C.btc, 0.25 * (1 - knock * 0.5))}
        />
      </svg>

      <div
        style={{
          ...label,
          fontFamily: FONT,
          position: "absolute",
          left: 960,
          top: 388,
          translate: "-50% 0",
          display: "flex",
          alignItems: "center",
          gap: 14,
          fontSize: 26,
          opacity: arrive,
        }}
      >
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: "50%",
            background: C.btc,
          }}
        />
        Bitcoin
      </div>
      <div
        style={{
          position: "absolute",
          left: 960,
          top: 540,
          translate: `-50% calc(-50% + ${(up ? -1 : 1) * knock * 9}px)`,
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontVariantNumeric: "tabular-nums",
          fontSize: 176,
          fontWeight: 600,
          letterSpacing: "-0.04em",
          lineHeight: 1,
          whiteSpace: "nowrap",
          color: C.ink,
          opacity: arrive,
          filter: arrive < 1 ? `blur(${(1 - arrive) * 14}px)` : undefined,
        }}
      >
        {formatPrice(price)}
      </div>
      <div
        style={{
          position: "absolute",
          left: 960,
          top: 652,
          translate: "-50% 0",
          fontFamily: FONT,
          fontFeatureSettings: NUM_FEATURES,
          fontVariantNumeric: "tabular-nums",
          fontSize: 34,
          fontWeight: 500,
          whiteSpace: "nowrap",
          color: up ? C.calm : C.alert,
          opacity: arrive * (step === 0 ? 0 : 1),
        }}
      >
        {up ? "▲" : "▼"} {Math.abs((price / before - 1) * 100).toFixed(2)}% this
        hour
      </div>

      {/* The two answers, one each side of the price. */}
      <div
        style={{
          position: "absolute",
          left: 0,
          width: 620,
          top: 540,
          translate: "0 -50%",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Words text={COPY.question[0]} at={12} size={96} accent={C.btc} />
      </div>
      <div
        style={{
          position: "absolute",
          right: 0,
          width: 620,
          top: 540,
          translate: "0 -50%",
          display: "flex",
          justifyContent: "center",
        }}
      >
        <Words text={COPY.question[1]} at={36} size={96} accent={C.btc} />
      </div>
    </AbsoluteFill>
  );
};
