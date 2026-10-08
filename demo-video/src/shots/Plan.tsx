import { AbsoluteFill, useCurrentFrame } from "remotion";
import portfolio from "../fixtures/portfolio.json";
import { C, metal } from "../theme";
import { BEAT, COPY, EASE, EASE_IN_OUT, tween } from "../timing";
import { LINE, MARGIN, Small, TOP } from "../Type";
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

/** The grid's width: the card and the bar both run from margin to margin. */
const WIDE = 1920 - MARGIN * 2;
// The bar of shares (viz.tsx, StackBar), where the small line will stand after it.
const BAR = { top: TOP + LINE * 2 + 18, height: 40 } as const;
// The card the next step is on (StepsPanel.tsx, StepsCard), at full width.
const CARD = { top: 476, zoom: 3.2 } as const;

/** How long the bar is on, and when each blip lands on its price: one a beat. */
const BAR_LEAVES = 15;
export const LANDS = [BEAT * 2, BEAT * 3, BEAT * 4] as const;
/** How long a blip is in the air. */
const FLIGHT = 11;
/** What the account holds, in the order of shot 3's blips. */
const BLIPS = [C.btc, C.gold, C.stock] as const;

/**
 * Shot 7. The card with the next step is there, full size, from the first frame. For half
 * a second the bar above it reshapes from what is held into the plan; then the three
 * blips of shot 3 fly in and land on the three prices, one a beat, each lighting its dot.
 * Figures: the made-up example in fixtures/portfolio.json.
 */
export const Plan: React.FC = () => {
  const frame = useCurrentFrame();
  const reshape = tween(frame, 2, 12, 0, 1, EASE_IN_OUT);
  const leaves = tween(frame, BAR_LEAVES, BAR_LEAVES + 6, 0, 1, EASE);
  // The price ladder runs right to left: today's price first, then each lower one.
  const lit = LANDS.map((at) => tween(frame, at, at + 7, 0, 1, EASE));
  const blips = LANDS.map((at, i) => ({
    colour: BLIPS[i],
    flown: tween(frame, at - FLIGHT, at, 0, 1, EASE_IN_OUT),
  }));

  return (
    <AbsoluteFill>

      {/* What is held, becoming the plan; then the small line takes its place. */}
      <div
        style={{
          position: "absolute",
          left: MARGIN,
          top: BAR.top,
          width: WIDE * (1 - leaves),
          height: BAR.height,
          display: "flex",
          gap: 8,
        }}
      >
        {holdings.map((holding) => (
          <span
            key={holding.symbol}
            style={{
              flex: `${mix(holding.money, holding.plan, reshape)} 1 0%`,
              borderRadius: 999,
              // Cash is not a colour: it is the track left unfilled, as in the app.
              background:
                holding.symbol === "USD"
                  ? "rgba(255,255,255,0.08)"
                  : metal(TONE[holding.tone]),
            }}
          />
        ))}
      </div>
      <Small
        text={COPY.plan.small}
        at={BAR_LEAVES + 4}
        style={{ position: "absolute", left: MARGIN, top: BAR.top - 4 }}
      />

      <div style={{ position: "absolute", left: MARGIN, top: CARD.top }}>
        <div
          style={{
            ...base,
            ...glass,
            width: WIDE / CARD.zoom,
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
            <Ladder rungs={step.rungs} lit={lit} blips={blips} />
          </div>
        </div>
      </div>
      <ExampleNote
        style={{ left: "auto", right: MARGIN, bottom: "auto", top: TOP + 16 }}
      />
    </AbsoluteFill>
  );
};
