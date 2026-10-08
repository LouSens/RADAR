import { AbsoluteFill, useCurrentFrame } from "remotion";
import portfolio from "../fixtures/portfolio.json";
import { C, FONT, NUM_FEATURES } from "../theme";
import { COPY, EASE, EASE_IN_OUT, tween } from "../timing";
import {
  ExampleNote,
  Ladder,
  TONE,
  TopEdge,
  base,
  formatMoney,
  glass,
  label,
} from "../ui/kit";
import { Words } from "../Words";

const { holdings, step } = portfolio;
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

// The bar of shares (viz.tsx, StackBar), in frame pixels.
const BAR = { left: 310, width: 1300, top: 452, height: 44 } as const;
// The card the next step is on, before the camera moves in on it.
const CARD = { width: 800, top: 650, zoom: 2 } as const;
const CARD_MIDDLE = 824;

/**
 * Shot 7. The bar of what is held now reshapes into the plan, and the camera moves in on
 * the next step: three prices, lighting one by one. Figures: the made-up example in
 * fixtures/portfolio.json.
 */
export const Plan: React.FC = () => {
  const frame = useCurrentFrame();
  const arrive = tween(frame, 0, 10, 0, 1, EASE);
  const reshape = tween(frame, 16, 36, 0, 1, EASE_IN_OUT);
  const push = tween(frame, 40, 60, 0, 1, EASE_IN_OUT);
  const scale = mix(1, 1.6, push);
  // The price ladder runs right to left: today's price first, then each lower one.
  const lit = step.rungs.map((_, i) =>
    tween(frame, 60 + i * 9, 68 + i * 9, 0, 1, EASE),
  );
  const named = (text: string, shown: number): React.ReactNode => (
    <span
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        whiteSpace: "nowrap",
        opacity: shown,
        filter: shown < 1 ? `blur(${(1 - shown) * 10}px)` : undefined,
      }}
    >
      {text}
    </span>
  );

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", top: 96 }}>
        {/* The first sentence stands in the middle until the second joins it. */}
        <div
          style={{
            display: "flex",
            gap: 28,
            translate: `${tween(frame, 42, 56, 318, 0, EASE_IN_OUT)}px 0`,
          }}
        >
          <Words text={COPY.plan[0]} at={4} size={92} />
          <Words text={COPY.plan[1]} at={46} size={92} />
        </div>
      </AbsoluteFill>

      {/* Everything below is one picture the camera moves in on. */}
      <AbsoluteFill
        style={{
          transformOrigin: `960px ${CARD_MIDDLE}px`,
          translate: `0 ${(610 - CARD_MIDDLE) * push}px`,
          scale,
        }}
      >
        <div style={{ opacity: arrive * (1 - Math.min(push * 2.4, 1)) }}>
          <div
            style={{
              position: "absolute",
              left: BAR.left,
              top: BAR.top - 64,
              height: 48,
              fontFamily: FONT,
              fontSize: 34,
              fontWeight: 600,
              letterSpacing: "-0.02em",
              color: C.ink,
            }}
          >
            {named("Now", 1 - tween(frame, 16, 26, 0, 1))}
            {named("Your plan", tween(frame, 24, 34, 0, 1))}
          </div>
          <div
            style={{
              position: "absolute",
              left: BAR.left,
              top: BAR.top,
              width: BAR.width,
              height: BAR.height,
              display: "flex",
              overflow: "hidden",
              borderRadius: 999,
              background: "rgba(255,255,255,0.08)",
            }}
          >
            {holdings.map((holding) => (
              <span
                key={holding.symbol}
                style={{
                  width: `${mix(holding.money, holding.plan, reshape) * 100}%`,
                  background: TONE[holding.tone],
                  boxShadow: `inset -3px 0 0 ${C.bg}`,
                }}
              />
            ))}
          </div>
          <div
            style={{
              position: "absolute",
              left: BAR.left,
              top: BAR.top + BAR.height + 22,
              width: BAR.width,
              display: "flex",
              gap: 44,
              fontFamily: FONT,
              fontSize: 26,
              color: C.muted,
            }}
          >
            {holdings.map((holding) => (
              <span
                key={holding.symbol}
                style={{ display: "flex", alignItems: "center", gap: 10 }}
              >
                <span
                  style={{
                    width: 14,
                    height: 14,
                    borderRadius: "50%",
                    background: TONE[holding.tone],
                  }}
                />
                {holding.name}
                <span
                  style={{
                    fontFeatureSettings: NUM_FEATURES,
                    fontVariantNumeric: "tabular-nums",
                    color: C.ink,
                  }}
                >
                  {Math.round(mix(holding.money, holding.plan, reshape) * 100)}%
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* StepsPanel.tsx, StepsCard. */}
        <div
          style={{
            position: "absolute",
            left: 960 - CARD.width / 2,
            top: CARD.top,
            opacity: tween(frame, 26, 40, 0, 1),
          }}
        >
          <div
            style={{
              ...base,
              ...glass,
              width: CARD.width / CARD.zoom,
              zoom: CARD.zoom,
              padding: 16,
            }}
          >
            <TopEdge />
            <p style={{ ...label, margin: 0 }}>What to do now</p>
            <p
              style={{
                margin: "6px 0 0",
                fontSize: 18,
                fontWeight: 600,
                letterSpacing: "-0.025em",
                lineHeight: 1.4,
              }}
            >
              Buy {formatMoney(step.amount)} of {step.name}
            </p>
            <div style={{ marginTop: 16 }}>
              <Ladder rungs={step.rungs} lit={lit} />
            </div>
          </div>
        </div>
      </AbsoluteFill>
      <ExampleNote opacity={arrive} />
    </AbsoluteFill>
  );
};
