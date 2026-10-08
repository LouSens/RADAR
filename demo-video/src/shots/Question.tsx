import { AbsoluteFill, useCurrentFrame } from "remotion";
import market from "../fixtures/market.json";
import { C, fade } from "../theme";
import { COPY, EASE, tween } from "../timing";
import { Headline, MARGIN, Small, TOP, hero } from "../Type";
import { formatPrice } from "../ui/kit";

const bitcoin = market.markets[0];
const closes = bitcoin.weekCloses;

/** The price changes this often, in frames. */
export const TICK = 4;
/** The hours the shot plays through: the last of the week, ending on the newest. */
export const HOURS = 30;
const shown = closes.slice(closes.length - HOURS);
/** Hours before those, already drawn on the first frame so that it has a trace. */
const BEFORE = 24;
const traced = closes.slice(closes.length - HOURS - BEFORE);

// The trace beside the price, in frame pixels.
const TRACE = { left: 1240, width: 552, top: 600, height: 230 } as const;
const LOW = Math.min(...traced);
const HIGH = Math.max(...traced);
const point = (i: number): readonly [number, number] => [
  TRACE.left + (i / (traced.length - 1)) * TRACE.width,
  TRACE.top + TRACE.height * (1 - (traced[i] - LOW) / (HIGH - LOW)),
];

/**
 * Shot 1. A Bitcoin price that will not keep still, and the question it puts. The prices
 * are real: the last hours of the week in fixtures/market.json, one every few frames.
 * The picture is there from the first frame.
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

  const head = point(BEFORE + step);
  const path = traced
    .slice(0, BEFORE + step + 1)
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
        style={{ position: "absolute", inset: 0 }}
      >
        <defs>
          <linearGradient id="question-trace" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor={C.btc} stopOpacity="0.1" />
            <stop offset="1" stopColor={C.btc} stopOpacity="0.9" />
          </linearGradient>
        </defs>
        {
          <path
            d={path}
            fill="none"
            stroke="url(#question-trace)"
            strokeWidth={4}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        }
        <circle
          cx={head[0]}
          cy={head[1]}
          r={18 + knock * 22}
          fill={fade(C.btc, 0.22)}
        />
        <circle cx={head[0]} cy={head[1]} r={8 + knock * 4} fill={C.btc} />
      </svg>

      <Headline
        lines={COPY.question}
        at={8}
        lineAt={[8, 30]}
        accent={C.btc}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
      />

      <Small
        at={-20}
        text={
          <span style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <span
              style={{
                width: 20,
                height: 20,
                borderRadius: "50%",
                background: C.btc,
              }}
            />
            Bitcoin
            <span style={{ color: up ? C.calm : C.alert }}>
              {step === 0
                ? ""
                : `${up ? "▲" : "▼"} ${Math.abs((price / before - 1) * 100).toFixed(2)}% this hour`}
            </span>
          </span>
        }
        style={{ position: "absolute", left: MARGIN, top: 520 }}
      />
      <div
        style={{
          ...hero,
          position: "absolute",
          left: MARGIN - 8,
          top: 592,
          translate: `0 ${(up ? -1 : 1) * knock * 10}px`,
        }}
      >
        {formatPrice(price)}
      </div>
    </AbsoluteFill>
  );
};
