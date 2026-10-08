import { spring, useCurrentFrame } from "remotion";
import { Lock, MORPH, Pulled, Smear, filmFrame, rate } from "../Chain";
import film from "../fixtures/film.json";
import { C, darker, fade, lighter } from "../theme";
import { COPY, EASE_IN_OUT, FPS, shot, tween } from "../timing";
import { Rise } from "../Type";
import type { Box } from "../ui/Desk";
import { TONE, base, formatMoney, formatPrice, num } from "../ui/kit";
import { Ticker, pop } from "../ui/motion";
import { BAR, Example, HEADING, HOLDINGS, MONEY, RISK, Weighed } from "./Risk";

const { step } = film.portfolio;
export const PLAN = HOLDINGS.map((h) => h.plan);
const mix = (a: number, b: number, t: number): number => a + (b - a) * t;

/** The plan bar, under its question and its headline. */
export const PLAN_BAR: Box = { x: 128, y: 444, w: 1664, h: 92 };
/** The ladder's line, and where each of its prices is along it: today's on the right. */
/** The legend under the bar, and the ladder 48 pixels under that. */
const LEGEND = { top: PLAN_BAR.y + PLAN_BAR.h + 22, tall: 70 } as const;
export const STOP = 40;
export const RAIL = {
  y: LEGEND.top + LEGEND.tall + 48 + STOP / 2,
  left: 128,
  right: 1792,
} as const;
const deepest = Math.max(...step.rungs.map((r) => r.below));
export const STOPS = step.rungs.map(
  (rung) =>
    RAIL.left + (RAIL.right - RAIL.left) * (1 - (rung.below / deepest) * 0.84),
);
export const LINE = "rgba(255,255,255,0.34)";

/** When the bar reshapes from what is held into the plan. */
export const RESHAPE = [37, 47] as const;
/** When the ladder's line comes down out of the bar, and runs out both ways. */
export const DROPS = [47, 51] as const;
export const RUNS = [50, 57] as const;
/** When each coin lands on its price. */
export const LANDS = [59, 64, 69] as const;
/** How long a coin is in the air, and how far above its price it appears. */
const FALL = 7;
const DROP = 52;
export const LOCKED = LANDS[2] + 3;

/** One of the ladder's prices: a ring on the line that fills when its coin lands. */
export const Stop: React.FC<{
  readonly x: number;
  readonly y: number;
  readonly by?: number;
  readonly lit?: number;
}> = ({ x, y, by = 1, lit = 1 }) => (
  <span
    style={{
      position: "absolute",
      left: x,
      top: y,
      width: STOP,
      height: STOP,
      translate: "-50% -50%",
      scale: String(by * (1 + 0.5 * Math.sin(Math.min(lit, 1) * Math.PI))),
      borderRadius: "50%",
      boxSizing: "border-box",
      border: `5px solid ${C.accent}`,
      background: lit > 0.5 ? C.accent : C.bg,
      boxShadow:
        lit > 0
          ? `0 0 ${24 * Math.min(lit, 1)}px ${4 * Math.min(lit, 1)}px ${fade(C.accent, 0.55)}`
          : undefined,
    }}
  />
);

/**
 * Shot 7. The bar of shot 6 goes back from risk to money and thins into the app's plan
 * bar: what is held now, then the plan. The ladder's line comes down out of the bar's
 * end and runs along under it, and a coin drops on to each of its three prices. Figures: the made-up example portfolio (fixtures/film.json).
 */
export const Plan: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("plan").duration;
  const leaves = duration - 8;
  const thinned = tween(frame, 0, MORPH - 2, 0, 1, EASE_IN_OUT);
  const reshape = tween(frame, RESHAPE[0], RESHAPE[1], 0, 1, EASE_IN_OUT);
  const shares = HOLDINGS.map((_, i) =>
    mix(mix(RISK[i], MONEY[i], thinned), PLAN[i], reshape),
  );
  const box: Box = {
    x: mix(BAR.x, PLAN_BAR.x, thinned),
    y: mix(BAR.y, PLAN_BAR.y, thinned),
    w: mix(BAR.w, PLAN_BAR.w, thinned),
    h: mix(BAR.h, PLAN_BAR.h, thinned),
  };
  const going = 1 - tween(frame, 0, 5, 0, 1, (t) => t);
  const dropped = tween(frame, DROPS[0], DROPS[1], 0, 1, EASE_IN_OUT);
  const run = tween(frame, RUNS[0], RUNS[1], 0, 1, EASE_IN_OUT);
  const foot = PLAN_BAR.y + PLAN_BAR.h;

  return (
    <Pulled film={filmFrame("plan", frame)}>
      <Smear y={rate(frame, 0, MORPH - 2) * 60}>
        <Weighed
          box={box}
          shares={shares}
          figures={going}
          names={going}
          mark={<Lock frame={frame + 100} at={0} out={100} pad={20} />}
        />
      </Smear>
      {/* The heading of shot 6 leaves where it stood. */}
      <span
        style={{
          ...base,
          position: "absolute",
          left: BAR.x,
          top: BAR.y - HEADING.above,
          fontSize: HEADING.size,
          fontWeight: 600,
          lineHeight: 1.2,
          color: C.btc,
        }}
      >
        <Rise at={-100} out={0}>
          Your risk
        </Rise>
      </span>

      <span
        style={{
          ...base,
          ...num,
          position: "absolute",
          left: PLAN_BAR.x,
          top: 244,
          fontSize: 92,
          fontWeight: 700,
          letterSpacing: "-0.03em",
          lineHeight: 1.15,
          whiteSpace: "nowrap",
        }}
      >
        <Rise at={10} out={leaves}>
          Buy {formatMoney(step.amount)} of {step.name}
        </Rise>
        <Lock frame={frame} at={LOCKED} out={leaves} pad={20} />
      </span>
      <span
        style={{
          ...base,
          position: "absolute",
          right: 1920 - PLAN_BAR.x - PLAN_BAR.w,
          top: 280,
          fontSize: 40,
          fontWeight: 500,
          color: C.muted,
          whiteSpace: "nowrap",
        }}
      >
        <Rise at={LANDS[0]} out={leaves}>
          {COPY.plan.small}
        </Rise>
      </span>
      <span
        style={{
          ...base,
          position: "absolute",
          left: PLAN_BAR.x,
          top: 368,
          fontSize: 46,
          fontWeight: 600,
          lineHeight: 1.3,
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ position: "absolute", color: C.muted }}>
          <Rise at={8} out={RESHAPE[0] - 1}>
            Now
          </Rise>
        </span>
        <span style={{ position: "absolute", color: C.accent }}>
          <Rise at={RESHAPE[0] + 4} out={leaves}>
            Your plan
          </Rise>
        </span>
      </span>
      <Example
        at={12}
        out={leaves}
        style={{ right: 1920 - PLAN_BAR.x - PLAN_BAR.w, top: 380 }}
      />
      {/* What each holding is of the whole, counting as the bar reshapes. */}
      <div
        style={{
          ...base,
          position: "absolute",
          left: PLAN_BAR.x,
          top: LEGEND.top,
          display: "flex",
          gap: 60,
          fontSize: 44,
          whiteSpace: "nowrap",
        }}
      >
        {HOLDINGS.map((holding, i) => (
          <Rise key={holding.symbol} at={MORPH - 2 + i * 2} out={leaves}>
            <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <span
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: "50%",
                  boxSizing: "border-box",
                  background:
                    holding.tone === "cash"
                      ? "transparent"
                      : TONE[holding.tone],
                  border:
                    holding.tone === "cash"
                      ? `3px solid ${C.faint}`
                      : undefined,
                }}
              />
              <span style={{ color: C.muted }}>{holding.name}</span>
              <Ticker
                value={mix(MONEY[i], PLAN[i], reshape) * 100}
                suffix="%"
                places={2}
                style={{ fontWeight: 700 }}
              />
            </span>
          </Rise>
        ))}
      </div>

      {/* The ladder's line, out of the bar: down, then both ways along. */}
      {frame >= DROPS[0] && (
        <Smear
          x={rate(frame, RUNS[0], RUNS[1]) * 500}
          y={rate(frame, DROPS[0], DROPS[1]) * 150}
        >
          <span
            style={{
              position: "absolute",
              left: RAIL.right - 4,
              top: foot,
              width: 4,
              height: (RAIL.y - foot) * dropped,
              borderRadius: 2,
              background: LINE,
            }}
          />
          <span
            style={{
              position: "absolute",
              left: mix(RAIL.right, RAIL.left, run),
              top: RAIL.y - 2,
              width: mix(0, RAIL.right - RAIL.left, run),
              height: 4,
              borderRadius: 2,
              background: LINE,
            }}
          />
        </Smear>
      )}
      {step.rungs.map((rung, i) => {
        const at = RUNS[1] - 3 + i * 2;
        const lit = tween(frame, LANDS[i], LANDS[i] + 6, 0, 1);
        const align =
          i === 0 ? "-100%" : i === step.rungs.length - 1 ? "0" : "-50%";
        const edge =
          i === 0 ? STOP / 2 : i === step.rungs.length - 1 ? -STOP / 2 : 0;
        return (
          <span key={rung.price}>
            {frame >= at && (
              <Stop x={STOPS[i]} y={RAIL.y} by={pop(frame, at)} lit={lit} />
            )}
            <span
              style={{
                ...base,
                ...num,
                position: "absolute",
                left: STOPS[i] + edge,
                top: RAIL.y + 30,
                translate: `${align} 0`,
                fontSize: 44,
                lineHeight: 1.3,
                color: C.muted,
                whiteSpace: "nowrap",
              }}
            >
              <Rise at={at + 1} out={leaves}>
                {i === 0 ? "now " : ""}
                {formatPrice(rung.price)}
              </Rise>
            </span>
            <span
              style={{
                ...base,
                ...num,
                position: "absolute",
                left: STOPS[i] + edge,
                top: RAIL.y + 88,
                translate: `${align} 0`,
                fontSize: 58,
                fontWeight: 700,
                lineHeight: 1.3,
                whiteSpace: "nowrap",
              }}
            >
              <Rise at={LANDS[i] + 1} out={leaves}>
                {formatMoney(rung.amount)}
              </Rise>
            </span>
          </span>
        );
      })}
      {/* A coin for each price: it falls, lands with a small bounce, and settles in. */}
      {step.rungs.map((rung, i) => {
        const since = frame - (LANDS[i] - FALL);
        if (since < 0) {
          return null;
        }
        const fallen = tween(since, 0, FALL, 0, 1, (t) => t * t);
        const bounce =
          since > FALL
            ? Math.abs(Math.sin(((since - FALL) * Math.PI) / 7)) *
              26 *
              Math.exp(-(since - FALL) / 5)
            : 0;
        const rest = spring({
          frame: since - FALL - 8,
          fps: FPS,
          config: { damping: 16, mass: 0.5, stiffness: 160 },
        });
        const size = mix(60, STOP, rest);
        return (
          <span
            key={`coin-${rung.price}`}
            style={{
              ...base,
              position: "absolute",
              left: STOPS[i],
              top: RAIL.y,
              width: size,
              height: size,
              translate: `-50% calc(-50% + ${-(1 - fallen) * DROP - bounce}px)`,
              borderRadius: "50%",
              background: `linear-gradient(180deg, ${lighter(C.accent)} 0%, ${C.accent} 45%, ${darker(C.accent)} 100%)`,
              boxShadow: `0 0 24px ${fade(C.accent, 0.5)}, inset 0 0 0 3px ${fade("#ffffff", 0.35)}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 30,
              fontWeight: 700,
              lineHeight: 1,
              color: "#0a2a33",
              scale: String(tween(since, 0, 3, 0.2, 1)),
              opacity: rest > 0.9 ? 0 : tween(since, 0, 2, 0, 1),
            }}
          >
            {rest < 0.4 ? "$" : ""}
          </span>
        );
      })}
      {(["← buy more if it falls", "today"] as const).map((note, i) => (
        <span
          key={note}
          style={{
            ...base,
            position: "absolute",
            left: i ? undefined : RAIL.left,
            right: i ? 1920 - RAIL.right : undefined,
            top: RAIL.y + 186,
            fontSize: 40,
            color: C.muted,
            whiteSpace: "nowrap",
          }}
        >
          <Rise at={RUNS[1] + 2} out={leaves}>
            {note}
          </Rise>
        </span>
      ))}
    </Pulled>
  );
};
