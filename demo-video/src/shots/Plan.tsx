import { AbsoluteFill, useCurrentFrame } from "remotion";
import portfolio from "../fixtures/portfolio.json";
import { C, FONT, NUM_FEATURES } from "../theme";
import { COPY, EASE, EASE_IN_OUT, tween } from "../timing";
import { Headline, LINE, MARGIN, Small, TOP } from "../Type";
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

const { holdings, step } = portfolio;
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

// The bar of shares (viz.tsx, StackBar), in frame pixels, under the headline.
const BAR = { left: MARGIN, width: 1664, top: 548, height: 40 } as const;
// The card the next step is on, before the camera moves in on it.
const CARD = { width: 800, top: 690, zoom: 2 } as const;
const CARD_MIDDLE = 842;
/** Where the card's middle comes to, and how much larger it is, once the camera is in. */
const CLOSE = { middle: 752, scale: 1.42 } as const;

/**
 * Shot 7. The bar of what is held now reshapes into the plan, and the camera moves in on
 * the next step: three prices, lighting one by one. Figures: the made-up example in
 * fixtures/portfolio.json. The picture is there from the first frame.
 */
export const Plan: React.FC = () => {
  const frame = useCurrentFrame();
  const reshape = tween(frame, 14, 34, 0, 1, EASE_IN_OUT);
  const push = tween(frame, 38, 58, 0, 1, EASE_IN_OUT);
  // The price ladder runs right to left: today's price first, then each lower one.
  const lit = step.rungs.map((_, i) =>
    tween(frame, 58 + i * 8, 66 + i * 8, 0, 1, EASE),
  );
  const named = (text: string, shown: number): React.ReactNode => (
    <span
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        whiteSpace: "nowrap",
        opacity: shown,
      }}
    >
      {text}
    </span>
  );

  return (
    <AbsoluteFill>
      <Headline
        lines={COPY.plan.lines}
        at={2}
        lineAt={[2, 32]}
        style={{ position: "absolute", left: MARGIN, top: TOP }}
      />
      <Small
        text={COPY.plan.small}
        at={16}
        style={{ position: "absolute", left: MARGIN, top: TOP + LINE * 2 + 14 }}
      />

      {/* Everything below is one picture the camera moves in on. */}
      <AbsoluteFill
        style={{
          transformOrigin: `960px ${CARD_MIDDLE}px`,
          translate: `0 ${(CLOSE.middle - CARD_MIDDLE) * push}px`,
          scale: mix(1, CLOSE.scale, push),
        }}
      >
        <div style={{ opacity: 1 - Math.min(push * 2.4, 1) }}>
          <div
            style={{
              position: "absolute",
              left: BAR.left,
              top: BAR.top - 50,
              height: 40,
              ...label,
              fontFamily: FONT,
              fontSize: 22,
            }}
          >
            {named("Now", 1 - tween(frame, 14, 24, 0, 1))}
            {named("Your plan", tween(frame, 22, 32, 0, 1))}
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
              top: BAR.top + BAR.height + 18,
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
      <ExampleNote />
    </AbsoluteFill>
  );
};
