import { interpolateColors, useCurrentFrame } from "remotion";
import { Lock, MORPH, Pulled, Smear, filmFrame, rate } from "../Chain";
import film from "../fixtures/film.json";
import { C, fade, metal } from "../theme";
import { COPY, EASE_IN_OUT, shot, tween } from "../timing";
import { Rise } from "../Type";
import type { Box } from "../ui/Desk";
import { TONE, base, label, num } from "../ui/kit";
import { Ticker, pop, settle } from "../ui/motion";
import { DIM, OUTCOMES } from "./Range";

export const HOLDINGS = film.portfolio.holdings;
export const MONEY = HOLDINGS.map((h) => h.money);
export const RISK = HOLDINGS.map((h) => h.risk);

/** The one bar: 85% of the frame wide, above its question. */
export const BAR: Box = { x: 144, y: 400, w: 1632, h: 160 };
/** The bar's small heading, and how far above the bar it stands. */
export const HEADING = { size: 48, above: 190 } as const;
const TRACK = "rgba(255,255,255,0.13)";
const GAP = 5;
/** How wide each holding's name is under the bar, with its dot, at the size it is set. */
const NAME_WIDE = [158, 112, 200, 118] as const;

/** When the bar fills by money, left to right. */
export const FILL = [MORPH + 2, MORPH + 20] as const;
/** When the same bar is weighed again, by risk. */
export const REWEIGH = 50;
export const LOCKED = REWEIGH + 14;

const clamp = (value: number): number => Math.min(Math.max(value, 0), 1);

/**
 * The app's bar of holdings (viz.tsx, StackBar) at the film's size: each holding a
 * piece in its own colour with its share written in it, and cash the track left
 * unfilled. A share too narrow to hold its figure carries it above. The next shot
 * draws it too, to turn it into the plan.
 */
export const Weighed: React.FC<{
  readonly box: Box;
  readonly shares: readonly number[];
  /** The figures, where they do not simply follow the pieces. */
  readonly values?: readonly number[];
  /** How far the bar has filled from the left, and how round its ends are. */
  readonly filled?: number;
  readonly round?: number;
  /** How strongly the figures and the names show. */
  readonly figures?: number;
  readonly names?: number;
  /** How far each holding's figure has popped in. */
  readonly shown?: (i: number) => number;
  /** Drawn round Bitcoin's figure. */
  readonly mark?: React.ReactNode;
}> = ({
  box,
  shares,
  values = shares,
  filled = 1,
  round = 999,
  figures = 1,
  names = 1,
  shown = () => 1,
  mark,
}) => {
  const starts = shares.map((_, i) =>
    shares.slice(0, i).reduce((sum, share) => sum + Math.max(share, 0), 0),
  );
  const middle = (i: number): number =>
    box.x + (starts[i] + Math.max(shares[i], 0) / 2) * box.w;
  // Names stand under their pieces, moved apart where two would touch.
  const centres = shares.map((_, i) =>
    Math.max(middle(i), box.x + NAME_WIDE[i] / 2),
  );
  for (let i = 1; i < centres.length; i++) {
    centres[i] = Math.max(
      centres[i],
      centres[i - 1] + (NAME_WIDE[i - 1] + NAME_WIDE[i]) / 2 + 26,
    );
  }
  return (
    <>
      <div
        style={{
          position: "absolute",
          left: box.x,
          top: box.y,
          width: box.w,
          height: box.h,
          borderRadius: round,
          overflow: "hidden",
          background: TRACK,
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            clipPath: `inset(0 ${(1 - filled) * 100}% 0 0)`,
          }}
        >
          {HOLDINGS.map((holding, i) =>
            holding.tone === "cash" ? null : (
              <span
                key={holding.symbol}
                style={{
                  position: "absolute",
                  left: starts[i] * box.w,
                  top: 0,
                  width: Math.max(shares[i] * box.w - GAP, 0),
                  height: "100%",
                  background: metal(TONE[holding.tone]),
                }}
              />
            ),
          )}
        </div>
      </div>
      {figures > 0 &&
        HOLDINGS.map((holding, i) => {
          const share = Math.max(shares[i], 0);
          const value = Math.max(values[i], 0) * 100;
          const digits = value >= 9.5 ? 2 : 1;
          const need = 72 * (digits * 0.62 + 0.85);
          const fits = clamp((share * box.w - need) / 30);
          const there =
            clamp((share - 0.01) / 0.01) * Math.min(shown(i), 1) * figures;
          const cash = holding.tone === "cash";
          const figure = <Ticker value={value} suffix="%" places={digits} />;
          return (
            <span key={holding.symbol}>
              <span
                style={{
                  ...base,
                  ...num,
                  position: "absolute",
                  left: middle(i),
                  top: box.y + box.h / 2,
                  translate: "-50% -50%",
                  scale: String(0.6 + 0.4 * shown(i)),
                  fontSize: 72,
                  fontWeight: 700,
                  lineHeight: 1,
                  color: cash ? C.ink : "#14161c",
                  opacity: fits * there,
                }}
              >
                {figure}
                {i === 0 && mark}
              </span>
              <span
                style={{
                  ...base,
                  ...num,
                  position: "absolute",
                  left: middle(i),
                  top: box.y - 14,
                  translate: "-50% -100%",
                  fontSize: 64,
                  fontWeight: 700,
                  lineHeight: 1,
                  color: cash ? C.ink : TONE[holding.tone],
                  opacity: (1 - fits) * there,
                }}
              >
                {figure}
              </span>
            </span>
          );
        })}
      {names > 0 &&
        HOLDINGS.map((holding, i) => (
          <span
            key={holding.symbol}
            style={{
              ...base,
              position: "absolute",
              left: centres[i],
              top: box.y + box.h + 20,
              translate: "-50% 0",
              display: "flex",
              alignItems: "center",
              gap: 12,
              fontSize: 36,
              fontWeight: 500,
              whiteSpace: "nowrap",
              opacity:
                clamp((shares[i] - 0.01) / 0.01) *
                Math.min(shown(i), 1) *
                names,
            }}
          >
            <span
              style={{
                width: 16,
                height: 16,
                borderRadius: "50%",
                boxSizing: "border-box",
                background:
                  holding.tone === "cash" ? "transparent" : TONE[holding.tone],
                border:
                  holding.tone === "cash" ? `3px solid ${C.faint}` : undefined,
              }}
            />
            {holding.name}
          </span>
        ))}
    </>
  );
};

/** The note that the figures are an example, as the app says on its own pages. */
export const Example: React.FC<{
  readonly at: number;
  readonly out?: number;
  readonly style: React.CSSProperties;
}> = ({ at, out, style }) => (
  <span
    style={{
      ...base,
      ...label,
      position: "absolute",
      fontSize: 34,
      whiteSpace: "nowrap",
      ...style,
    }}
  >
    <Rise at={at} out={out}>
      {COPY.example}
    </Rise>
  </span>
);

/**
 * Shot 6. The outcomes of shot 5 slide sideways and merge into one thick bar. It fills
 * from the left with how the account's money is split; then the same bar is weighed
 * again by risk, all its pieces at once: Bitcoin's pushes out to two thirds, cash
 * shrinks to nothing, and every figure rolls to its new value. Figures: the made-up
 * example portfolio (fixtures/film.json).
 */
export const Risk: React.FC = () => {
  const frame = useCurrentFrame();
  const duration = shot("risk").duration;
  const merged = tween(frame, 0, MORPH - 2, 0, 1, EASE_IN_OUT);
  const paled = tween(frame, 7, MORPH, 0, 1, (t) => t);
  const filled = tween(frame, FILL[0], FILL[1], 0, 1, EASE_IN_OUT);
  // A spring: the pieces go a little too far and come back.
  const weighed = settle(frame, REWEIGH, 12);
  const shares = MONEY.map((money, i) => money + (RISK[i] - money) * weighed);
  const counted = tween(frame, REWEIGH, REWEIGH + 12, 0, 1, EASE_IN_OUT);
  // Whole figures at both ends, so that no wheel is left between two of them.
  const values = MONEY.map(
    (money, i) =>
      (Math.round(money * 100) +
        (Math.round(RISK[i] * 100) - Math.round(money * 100)) * counted) /
      100,
  );
  const slice = BAR.w / OUTCOMES.length;
  const starts = MONEY.map((_, i) =>
    MONEY.slice(0, i).reduce((sum, share) => sum + share, 0),
  );

  return (
    <Pulled film={filmFrame("risk", frame)}>
      {frame < MORPH ? (
        <Smear
          x={rate(frame, 0, MORPH - 2) * 70}
          y={rate(frame, 0, MORPH - 2) * 400}
        >
          {OUTCOMES.map((from, i) => (
            <span
              key={from.x}
              style={{
                position: "absolute",
                left: from.x + (BAR.x + i * slice - from.x) * merged,
                top: from.y + (BAR.y - from.y) * merged,
                width: from.w + (slice + 0.6 - from.w) * merged,
                height: from.h + (BAR.h - from.h) * merged,
                background: interpolateColors(
                  paled,
                  [0, 1],
                  [fade(C.btc, from.inside ? 1 : DIM), TRACK],
                ),
              }}
            />
          ))}
        </Smear>
      ) : (
        <Weighed
          box={BAR}
          shares={shares}
          values={values}
          filled={filled}
          round={tween(frame, MORPH, MORPH + 5, 0, BAR.h / 2, EASE_IN_OUT)}
          names={1}
          shown={(i) =>
            pop(
              frame,
              FILL[0] + (starts[i] + MONEY[i] / 2) * (FILL[1] - FILL[0]) * 0.9,
            )
          }
          mark={<Lock frame={frame} at={LOCKED} out={duration + 20} pad={20} />}
        />
      )}
      <span
        style={{
          ...base,
          position: "absolute",
          left: BAR.x,
          top: BAR.y - HEADING.above,
          fontSize: HEADING.size,
          fontWeight: 600,
          lineHeight: 1.2,
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ position: "absolute", color: C.muted }}>
          <Rise at={FILL[0] - 4} out={REWEIGH - 3}>
            Your money
          </Rise>
        </span>
        <span style={{ position: "absolute", color: C.btc }}>
          <Rise at={REWEIGH + 3}>Your risk</Rise>
        </span>
      </span>
      <Example
        at={FILL[0]}
        out={duration - 8}
        style={{ right: 1920 - BAR.x - BAR.w, top: BAR.y - HEADING.above + 10 }}
      />
    </Pulled>
  );
};
