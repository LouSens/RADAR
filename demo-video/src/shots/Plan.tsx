import {
  AbsoluteFill,
  spring,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { ASKED, AREA, OPENS, Answer, ZOOM } from "../Beat";
import film from "../fixtures/film.json";
import { C, darker, fade, lighter } from "../theme";
import { BEAT, COPY, EASE_IN_OUT, shot, tween } from "../timing";
import { Rise } from "../Type";
import { AT } from "../ui/Desk";
import { Ladder, base, formatMoney, label } from "../ui/kit";
import { Ping, StackBar, Swatch, Ticker, pop } from "../ui/motion";

const { holdings, step } = film.portfolio;
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** When the bar reshapes from what is held into the plan: half a second. */
export const RESHAPE = [ASKED + OPENS - 2, ASKED + OPENS + 13] as const;
/** When each coin lands on its price: one a beat. */
export const LANDS = [
  RESHAPE[1] + 4,
  RESHAPE[1] + 4 + BEAT,
  RESHAPE[1] + 4 + BEAT * 2,
] as const;
/** How long a coin is in the air. */
const FALL = 7;
/** How far above its price a coin appears: inside the card, just over the ladder. */
const DROP = 30;
export const PINGED = LANDS[2] + 6;

/** The ladder, in the app's pixels inside the answer, drawn half as large again. */
const LADDER = { x: 28, y: 204, w: 776, zoom: 1.5 } as const;
/** Where each price is along the ladder (ui/kit, Ladder): today's on the right. */
const deepest = Math.max(...step.rungs.map((r) => r.below));
const along = (below: number): number => 1 - (below / deepest) * 0.84;

/**
 * Shot 7. The app's card for what to do now, at full width. Its bar reshapes from what
 * is held into the plan, and then three coins drop on to the three prices of the
 * ladder, one a beat, each with a small bounce. Figures: the made-up example portfolio
 * (fixtures/film.json).
 */
export const Plan: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const duration = shot("plan").duration;
  const reshape = tween(frame, RESHAPE[0], RESHAPE[1], 0, 1, EASE_IN_OUT);
  const shown = pop(frame, ASKED + OPENS - 2);
  const shares = holdings.map((h) => ({
    symbol: h.symbol,
    tone: h.tone,
    share: mix(h.money, h.plan, reshape),
  }));

  return (
    <AbsoluteFill>
      <Answer
        duration={duration}
        from={AT.todo}
        card
        framed={ASKED + OPENS - 6}
        title="What to do now"
        headline={`Buy ${formatMoney(step.amount)} of ${step.name}`}
      >
        {/* The plan bar (viz.tsx): what is held, becoming the plan. */}
        <div
          style={{
            ...base,
            position: "absolute",
            left: 28,
            right: 28,
            top: 94,
            opacity: Math.min(shown, 1),
          }}
        >
          <div style={{ ...label, position: "relative", height: 20 }}>
            <span style={{ position: "absolute" }}>
              <Rise at={ASKED + OPENS - 2} out={RESHAPE[0] + 4}>
                Now
              </Rise>
            </span>
            <span style={{ position: "absolute", color: C.accent }}>
              <Rise at={RESHAPE[0] + 8}>Your plan</Rise>
            </span>
          </div>
          <StackBar shares={shares} height={12} />
          <div
            style={{ display: "flex", gap: 26, marginTop: 10, fontSize: 14 }}
          >
            {shares.map((part, i) => (
              <span
                key={part.symbol}
                style={{ display: "flex", alignItems: "center", gap: 7 }}
              >
                <Swatch tone={part.tone} />
                <span style={{ color: C.muted }}>{holdings[i].name}</span>
                <span style={{ fontWeight: 600 }}>
                  <Ticker value={part.share * 100} suffix="%" places={2} />
                </span>
              </span>
            ))}
          </div>
        </div>

        {/* The ladder (StepsPanel.tsx), and a coin for each of its prices. */}
        <div style={{ position: "absolute", left: LADDER.x, top: LADDER.y }}>
          <div
            style={{
              position: "relative",
              width: LADDER.w / LADDER.zoom,
              zoom: LADDER.zoom,
              opacity: Math.min(shown, 1),
            }}
          >
            <Ladder
              rungs={step.rungs}
              lit={LANDS.map((at) => tween(frame, at, at + 6, 0, 1))}
            />
            {step.rungs.map((rung, i) => {
              const since = frame - (LANDS[i] - FALL);
              if (since < 0) {
                return null;
              }
              // It falls, lands on the dot with a small bounce, and settles into it.
              const fallen = tween(since, 0, FALL, 0, 1, (t) => t * t);
              const bounce =
                since > FALL
                  ? Math.abs(Math.sin(((since - FALL) * Math.PI) / 7)) *
                    16 *
                    Math.exp(-(since - FALL) / 5)
                  : 0;
              const rest = spring({
                frame: since - FALL - 10,
                fps,
                config: { damping: 16, mass: 0.5, stiffness: 160 },
              });
              const size = mix(24, 12, rest);
              return (
                <span
                  key={rung.price}
                  style={{
                    position: "absolute",
                    left: `${along(rung.below) * 100}%`,
                    top: 28,
                    width: size,
                    height: size,
                    translate: `-50% calc(-50% + ${-(1 - fallen) * DROP - bounce}px)`,
                    borderRadius: "50%",
                    background: `linear-gradient(180deg, ${lighter(C.accent)} 0%, ${C.accent} 45%, ${darker(C.accent)} 100%)`,
                    boxShadow: `0 0 12px ${fade(C.accent, 0.5)}, inset 0 0 0 1.5px ${fade("#ffffff", 0.35)}`,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 13,
                    fontWeight: 700,
                    color: "#0a2a33",
                    // It appears where it starts to fall, growing from nothing in a few frames.
                    scale: tween(since, 0, 3, 0.2, 1),
                    opacity: rest > 0.9 ? 0 : tween(since, 0, 2, 0, 1),
                  }}
                >
                  {rest < 0.4 ? "$" : ""}
                </span>
              );
            })}
          </div>
        </div>

        <div
          style={{
            ...base,
            position: "absolute",
            left: 28,
            right: 28,
            bottom: 22,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "baseline",
          }}
        >
          <span style={{ fontSize: 20, fontWeight: 500, color: C.muted }}>
            <Rise at={LANDS[0] + 4}>{COPY.plan.small}</Rise>
          </span>
          <span
            style={{ ...label, display: "flex", alignItems: "center", gap: 8 }}
          >
            <Rise at={ASKED + OPENS}>{COPY.example}</Rise>
          </span>
        </div>
      </Answer>
      <Ping
        since={frame - PINGED}
        x={AREA.x + 150 * ZOOM}
        y={AREA.y + 55 * ZOOM}
        reach={220}
      />
    </AbsoluteFill>
  );
};
